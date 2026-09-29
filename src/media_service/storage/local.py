"""Local disk storage under IMAGES_DIR (docker volume images-data)."""
from __future__ import annotations

import shutil
from pathlib import Path

from media_service.paths import IMAGES_DIR


class LocalStorage:
    """Object-key API backed by files under IMAGES_DIR/{key}."""

    def put_file(self, key: str, src_path: str | Path) -> None:
        dest = IMAGES_DIR / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        src = Path(src_path)
        if src.resolve() == dest.resolve():
            return
        shutil.copy2(src, dest)

    def download_to_path(self, key: str, dest: str | Path) -> None:
        src = IMAGES_DIR / key
        if not src.is_file():
            raise FileNotFoundError(key)
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() == dest_path.resolve():
            return
        shutil.copy2(src, dest_path)

    def delete(self, key: str) -> None:
        path = IMAGES_DIR / key
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    def exists(self, key: str) -> bool:
        return (IMAGES_DIR / key).is_file()

    def open_bytes(self, key: str) -> bytes:
        path = IMAGES_DIR / key
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()
