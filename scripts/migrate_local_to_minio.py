#!/usr/bin/env python3
"""
Idempotent: upload non-deleted Image rows from local IMAGES_DIR into MinIO
when the object key is missing in the bucket.

Usage (from repo root, with env loaded / inside save-worker container):
  PYTHONPATH=src python scripts/migrate_local_to_minio.py

Requires MINIO_* env and local files under images/{user_id}/{uuid}.jpg.
Does not change Postgres paths (keys stay {user_id}/{uuid}.jpg).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow running as `python scripts/migrate_local_to_minio.py` from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import select

from db.models import Image
from db.sync_session import get_sync_sessionmaker
from media_service.paths import IMAGES_DIR
from media_service.storage.minio_client import MinioStorage


def main() -> int:
    dry_run = os.getenv("MIGRATE_DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    minio = MinioStorage()
    Session = get_sync_sessionmaker()

    uploaded = 0
    skipped_missing_local = 0
    skipped_already = 0
    errors = 0

    with Session() as session:
        rows = session.scalars(
            select(Image).where(Image.deleted_at.is_(None))
        ).all()
        keys = [(str(r.image_id), r.path) for r in rows]

    print(f"candidates={len(keys)} dry_run={dry_run} images_dir={IMAGES_DIR}")

    for image_id, key in keys:
        local = IMAGES_DIR / key
        if not local.is_file():
            skipped_missing_local += 1
            continue
        try:
            if minio.exists(key):
                skipped_already += 1
                continue
            if dry_run:
                print(f"would_upload {key}")
                uploaded += 1
                continue
            minio.put_file(key, local)
            uploaded += 1
            print(f"uploaded {key}")
        except Exception as e:
            errors += 1
            print(f"error {image_id} {key}: {e}", file=sys.stderr)

    print(
        f"done uploaded={uploaded} already_in_minio={skipped_already} "
        f"missing_local={skipped_missing_local} errors={errors}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
