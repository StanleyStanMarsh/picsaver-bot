"""Jina CLIP v2 encoder — loaded once per RQ worker process."""
from __future__ import annotations

import os
import threading
from functools import lru_cache

import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "jinaai/jina-clip-v2")
VECTOR_SIZE = int(os.getenv("CLIP_VECTOR_SIZE", "1024"))
DEVICE = os.getenv("CLIP_DEVICE", "cpu")

_lock = threading.Lock()
_model = None
_processor = None


def get_vector_size() -> int:
    return VECTOR_SIZE


def _ensure_model():
    global _model, _processor
    if _model is not None and _processor is not None:
        return _model, _processor
    with _lock:
        if _model is not None and _processor is not None:
            return _model, _processor
        # Keep CPU thread budget small on 12GB box
        torch.set_num_threads(int(os.getenv("OMP_NUM_THREADS", "2")))
        model = AutoModel.from_pretrained(MODEL_NAME, trust_remote_code=True)
        model = model.to(DEVICE)
        model.eval()
        processor = AutoProcessor.from_pretrained(MODEL_NAME, trust_remote_code=True)
        _model, _processor = model, processor
        return _model, _processor


def embed_image_path(path: str) -> list[float]:
    model, processor = _ensure_model()
    img = Image.open(path).convert("RGB")
    inputs = processor(images=img, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        feats = model.get_image_features(**inputs)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats[0].cpu().float().numpy().tolist()


def embed_text(text: str) -> list[float]:
    model, processor = _ensure_model()
    inputs = processor(
        text=[text],
        return_tensors="pt",
        padding=True,
        truncation=True,
    ).to(DEVICE)
    with torch.no_grad():
        feats = model.get_text_features(**inputs)
        feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats[0].cpu().float().numpy().tolist()
