from __future__ import annotations

import logging
import os
from uuid import UUID

from qdrant_client import QdrantClient, models

COLLECTION = os.getenv("QDRANT_COLLECTION", "user_images")
VECTOR_SIZE = int(os.getenv("CLIP_VECTOR_SIZE", "1024"))

logger = logging.getLogger("qdrant-search")


def get_qdrant_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL", "http://qdrant:6333")
    api_key = os.getenv("QDRANT_API_KEY") or None
    return QdrantClient(url=url, api_key=api_key, prefer_grpc=False)


def ensure_collection(client: QdrantClient | None = None) -> None:
    client = client or get_qdrant_client()
    names = {c.name for c in client.get_collections().collections}
    if COLLECTION in names:
        return
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(
            size=VECTOR_SIZE,
            distance=models.Distance.COSINE,
        ),
    )
    client.create_payload_index(
        collection_name=COLLECTION,
        field_name="user_id",
        field_schema=models.PayloadSchemaType.INTEGER,
    )


def upsert_image_vector(
    *,
    image_id: UUID,
    vector: list[float],
    user_id: int,
    telegram_file_id: str,
    local_path: str,
    client: QdrantClient | None = None,
) -> None:
    client = client or get_qdrant_client()
    ensure_collection(client)
    client.upsert(
        collection_name=COLLECTION,
        points=[
            models.PointStruct(
                id=str(image_id),
                vector=vector,
                payload={
                    "user_id": user_id,
                    "telegram_file_id": telegram_file_id,
                    "local_path": local_path,
                    "image_id": str(image_id),
                    "model": os.getenv("CLIP_MODEL_NAME", "jinaai/jina-clip-v2"),
                    "dimensions": VECTOR_SIZE,
                },
            )
        ],
    )


def delete_image_vector(
    *,
    image_id: UUID,
    client: QdrantClient | None = None,
) -> None:
    client = client or get_qdrant_client()
    try:
        client.delete(
            collection_name=COLLECTION,
            points_selector=models.PointIdsList(points=[str(image_id)]),
        )
    except Exception:
        names = {c.name for c in client.get_collections().collections}
        if COLLECTION not in names:
            return
        raise


def search_user_images(
    *,
    vector: list[float],
    user_id: int,
    limit: int = 20,
    min_score: float | None = None,
    exclude_file_ids: set[str] | None = None,
    exclude_image_ids: set[str] | None = None,
    client: QdrantClient | None = None,
) -> list[dict]:
    """Cosine search for one user; optional min_score cutoff with kept|drop logs."""
    client = client or get_qdrant_client()
    ensure_collection(client)
    exclude_file_ids = exclude_file_ids or set()
    exclude_image_ids = {str(x) for x in (exclude_image_ids or set())}

    # Pull extra candidates so exclude + cutoff still fill top_k
    fetch_limit = max(limit * 4, limit + len(exclude_file_ids) + 10, 50)
    fetch_limit = min(fetch_limit, 100)

    results = client.query_points(
        collection_name=COLLECTION,
        query=vector,
        limit=fetch_limit,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                )
            ]
        ),
    )

    out: list[dict] = []
    for point in results.points:
        payload = point.payload or {}
        file_id = payload.get("telegram_file_id")
        image_id = str(payload.get("image_id") or point.id)
        score = float(point.score) if point.score is not None else None

        if not file_id:
            continue
        if file_id in exclude_file_ids or image_id in exclude_image_ids:
            logger.info(
                "search hit user_id=%s image_id=%s score=%s decision=drop reason=exclude cutoff=%s top_k=%s",
                user_id,
                image_id,
                score,
                min_score,
                limit,
            )
            continue

        below = min_score is not None and score is not None and score < min_score
        decision = "drop" if below else "kept"
        logger.info(
            "search hit user_id=%s image_id=%s score=%s decision=%s cutoff=%s top_k=%s",
            user_id,
            image_id,
            score,
            decision,
            min_score,
            limit,
        )
        if below:
            continue

        out.append(
            {
                "file_id": file_id,
                "image_id": image_id,
                "score": score,
            }
        )
        if len(out) >= limit:
            break

    logger.info(
        "search done user_id=%s kept=%s cutoff=%s top_k=%s",
        user_id,
        len(out),
        min_score,
        limit,
    )
    return out
