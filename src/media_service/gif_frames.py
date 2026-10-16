"""GIF (Telegram animation, usually MP4) helpers: ffmpeg frame pick + vector averaging.

SPEC §7a: first / middle / last frame; a uniform (one-colour) edge frame is
replaced by its neighbour; fewer than 3 frames → use what exists.
No torch import here so it stays unit-testable.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

FFPROBE_TIMEOUT = 60
FFMPEG_TIMEOUT = 120
# Pixel std-dev below this → frame treated as one-colour (fade in/out, black).
UNIFORM_STD_THRESHOLD = 3.0


class GifProcessingError(RuntimeError):
    """Animation is broken or frames cannot be extracted."""


def count_frames(path: str | Path) -> int:
    """Exact decoded video frame count via ffprobe (packets of stream v:0)."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_packets", "-show_entries", "stream=nb_read_packets",
        "-of", "json", str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True, timeout=FFPROBE_TIMEOUT)
        streams = json.loads(out.stdout or b"{}").get("streams") or []
        n = int(streams[0].get("nb_read_packets") or 0) if streams else 0
    except (subprocess.SubprocessError, ValueError, OSError, IndexError) as e:
        raise GifProcessingError(f"ffprobe failed: {e}") from e
    if n <= 0:
        raise GifProcessingError("no video frames")
    return n


def candidate_indices(n: int) -> list[int]:
    """Frames to decode: edges + their neighbours + middle (deduped, sorted)."""
    if n <= 0:
        return []
    last = n - 1
    mid = last // 2
    return sorted({0, min(1, last), mid, max(last - 1, 0), last})


def pick_three(n: int, uniform: set[int]) -> list[int]:
    """Choose first/middle/last, swapping a uniform edge frame for its neighbour."""
    if n <= 0:
        return []
    last = n - 1
    mid = last // 2
    first = 1 if (0 in uniform and n > 1 and 1 not in uniform) else 0
    end = last - 1 if (last in uniform and last - 1 > mid and (last - 1) not in uniform) else last
    out: list[int] = []
    for i in (first, mid, end):
        if i not in out:
            out.append(i)
    return out


def _is_uniform(png: Path) -> bool:
    from PIL import Image, ImageStat

    with Image.open(png) as im:
        stat = ImageStat.Stat(im.convert("L"))
    return (stat.stddev[0] if stat.stddev else 0.0) < UNIFORM_STD_THRESHOLD


def extract_key_frames(src: str | Path, out_dir: str | Path) -> list[Path]:
    """Decode candidate frames with ffmpeg, return 1..3 PNG paths (first, mid, last)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = count_frames(src)
    idx = candidate_indices(n)
    select = "+".join(f"eq(n\\,{i})" for i in idx)
    cmd = [
        "ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(src),
        "-vf", f"select='{select}'", "-vsync", "0", "-frames:v", str(len(idx)),
        str(out_dir / "f_%02d.png"),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=FFMPEG_TIMEOUT)
    except (subprocess.SubprocessError, OSError) as e:
        raise GifProcessingError(f"ffmpeg failed: {e}") from e
    files = sorted(out_dir.glob("f_*.png"))
    if not files:
        raise GifProcessingError("ffmpeg produced no frames")
    # ffmpeg writes selected frames in order; map back to indices (truncate if fewer).
    by_idx = dict(zip(idx, files))
    uniform = {i for i, f in by_idx.items() if _is_uniform(f)}
    chosen = [i for i in pick_three(n, uniform) if i in by_idx]
    if not chosen:
        chosen = list(by_idx)[:3]
    return [by_idx[i] for i in chosen]


def average_normalized(vectors: list[list[float]]) -> list[float]:
    """L2-normalise each vector, mean, L2-normalise again (cosine-stable)."""
    if not vectors:
        raise ValueError("no vectors")
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        if len(v) != dim:
            raise ValueError("dimension mismatch")
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        for i, x in enumerate(v):
            acc[i] += x / norm
    acc = [x / len(vectors) for x in acc]
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return [x / norm for x in acc]
