from pathlib import Path

# Repo root: src/media_service/paths.py -> parents[2] == repo root
REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGES_DIR = REPO_ROOT / "images"
