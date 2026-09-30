"""STORAGE_BACKEND factory: local | minio | dual."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from media_service.storage.local import LocalStorage

logger = logging.getLogger(__name__)


@runtime_checkable
class StorageBackend(Protocol):
    def put_file(self, key: str, src_path: str | Path) -> None: ...
    def download_to_path(self, key: str, dest: str | Path) -> None: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def open_bytes(self, key: str) -> bytes: ...


class DualStorage:
    """
    Write: MinIO first; on put error fall back to local disk.
    Read: try MinIO then local.
    Delete: both (ignore missing).
    """

    def __init__(self, primary, fallback: LocalStorage) -> None:
        self._minio = primary
        self._local = fallback

    def put_file(self, key: str, src_path: str | Path) -> None:
        try:
            self._minio.put_file(key, src_path)
            return
        except Exception as e:
            logger.warning("dual put: MinIO failed for {} ({}); falling back to local", key, e)
            self._local.put_file(key, src_path)

    def download_to_path(self, key: str, dest: str | Path) -> None:
        try:
            if self._minio.exists(key):
                self._minio.download_to_path(key, dest)
                return
        except Exception as e:
            logger.warning("dual download: MinIO miss/error for {} ({}); trying local", key, e)
        self._local.download_to_path(key, dest)

    def delete(self, key: str) -> None:
        try:
            self._minio.delete(key)
        except Exception:
            pass
        try:
            self._local.delete(key)
        except Exception:
            pass

    def exists(self, key: str) -> bool:
        try:
            if self._minio.exists(key):
                return True
        except Exception:
            pass
        return self._local.exists(key)

    def open_bytes(self, key: str) -> bytes:
        try:
            if self._minio.exists(key):
                return self._minio.open_bytes(key)
        except Exception as e:
            logger.warning("dual open_bytes: MinIO miss/error for {} ({}); trying local", key, e)
        return self._local.open_bytes(key)


_storage: StorageBackend | None = None


def _make_minio():
    from media_service.storage.minio_client import MinioStorage

    return MinioStorage()


def get_storage() -> StorageBackend:
    """Singleton storage backend from STORAGE_BACKEND env (default: local)."""
    global _storage
    if _storage is not None:
        return _storage

    backend = (os.getenv("STORAGE_BACKEND") or "local").strip().lower()
    if backend == "minio":
        _storage = _make_minio()
    elif backend == "dual":
        _storage = DualStorage(_make_minio(), LocalStorage())
    else:
        # local (default) and any unknown value → local for safety
        if backend not in ("local", "", "disk"):
            logger.warning("unknown STORAGE_BACKEND={!r}; using local", backend)
        _storage = LocalStorage()
    return _storage


def reset_storage_for_tests() -> None:
    """Clear singleton (tests only)."""
    global _storage
    _storage = None
