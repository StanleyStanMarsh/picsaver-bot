"""Thin MinIO SDK wrapper. Env matches DevOps compose (.env.example)."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error


def _parse_endpoint(raw: str) -> tuple[str, bool]:
    """
    MINIO_ENDPOINT may be 'http://minio:9000', 'minio:9000', or 'https://host'.
    Returns (host:port, secure).
    """
    raw = (raw or "http://minio:9000").strip()
    if "://" not in raw:
        # bare host:port — default insecure (compose internal)
        return raw, False
    parsed = urlparse(raw)
    host = parsed.hostname or "minio"
    port = parsed.port
    netloc = f"{host}:{port}" if port else host
    secure = parsed.scheme == "https"
    return netloc, secure


class MinioStorage:
    """S3-compatible object storage via MinIO Python SDK."""

    def __init__(self) -> None:
        endpoint, secure_from_url = _parse_endpoint(os.getenv("MINIO_ENDPOINT", "http://minio:9000"))
        # Explicit MINIO_SECURE overrides URL scheme when set
        secure_env = os.getenv("MINIO_SECURE")
        if secure_env is not None and secure_env != "":
            secure = secure_env.strip().lower() in ("1", "true", "yes")
        else:
            secure = secure_from_url

        access = os.getenv("MINIO_ACCESS_KEY", "picsaver")
        secret = os.getenv("MINIO_SECRET_KEY", "change_me_minio_password")
        region = os.getenv("MINIO_REGION", "us-east-1") or None

        self.bucket = os.getenv("MINIO_BUCKET", "picsaver")
        self._client = Minio(
            endpoint,
            access_key=access,
            secret_key=secret,
            secure=secure,
            region=region,
        )
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        try:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
        except S3Error:
            # Race with minio-init or already exists — continue; ops will fail loudly later
            pass
        self._bucket_ready = True

    def put_file(self, key: str, src_path: str | Path) -> None:
        self._ensure_bucket()
        src = Path(src_path)
        self._client.fput_object(
            self.bucket,
            key,
            str(src),
            content_type="image/jpeg",
        )

    def download_to_path(self, key: str, dest: str | Path) -> None:
        self._ensure_bucket()
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        self._client.fget_object(self.bucket, key, str(dest_path))

    def delete(self, key: str) -> None:
        self._ensure_bucket()
        try:
            self._client.remove_object(self.bucket, key)
        except S3Error:
            pass

    def exists(self, key: str) -> bool:
        self._ensure_bucket()
        try:
            self._client.stat_object(self.bucket, key)
            return True
        except S3Error:
            return False

    def open_bytes(self, key: str) -> bytes:
        self._ensure_bucket()
        try:
            response = self._client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except S3Error as e:
            raise FileNotFoundError(key) from e
