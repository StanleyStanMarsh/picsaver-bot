import logging
import os

from redis import Redis
from rq import Worker

from redis_queue import QUEUE_ADDRESS, QUEUE_PORT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("save-worker")

queues = ["save"]

redis_conn = Redis(host=QUEUE_ADDRESS, port=QUEUE_PORT, db=0)


def _warmup_clip():
    """Load jina-clip-v2 once at worker start so first user job is faster."""
    if os.getenv("CLIP_WARMUP", "1") != "1":
        return
    try:
        from media_service.clip.encoder import embed_text

        logger.info("Warming up CLIP model...")
        embed_text("warmup")
        logger.info("CLIP warmup done")
    except Exception:
        logger.exception("CLIP warmup failed — first job will load the model")


if __name__ == "__main__":
    _warmup_clip()
    try:
        from media_service.qdrant_store import ensure_collection

        ensure_collection()
    except Exception:
        logger.exception("Qdrant ensure_collection failed at startup")
    worker = Worker(queues, connection=redis_conn, name="Image Saver")
    worker.work()
