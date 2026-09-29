"""Dual-mode object storage: local disk | MinIO | dual (MinIO+local fallback)."""
from media_service.storage.factory import StorageBackend, get_storage

__all__ = ["StorageBackend", "get_storage"]
