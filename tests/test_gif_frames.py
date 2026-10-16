import math
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from media_service.gif_frames import (  # noqa: E402
    average_normalized,
    candidate_indices,
    extract_key_frames,
    pick_three,
)


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


def test_average_normalized_unit_and_scale_invariant():
    out = average_normalized([[3.0, 0.0], [0.0, 10.0], [1.0, 1.0]])
    assert abs(_norm(out) - 1.0) < 1e-9
    # Pre-normalisation: scaling one input must not change result
    out2 = average_normalized([[30.0, 0.0], [0.0, 1.0], [5.0, 5.0]])
    assert all(abs(a - b) < 1e-9 for a, b in zip(out, out2))


def test_average_identical_frames_equals_frame():
    v = [0.6, 0.8]
    assert all(abs(a - b) < 1e-9 for a, b in zip(average_normalized([v, v, v]), v))


def test_candidate_and_pick():
    assert candidate_indices(1) == [0]
    assert candidate_indices(10) == [0, 1, 4, 8, 9]
    assert pick_three(10, set()) == [0, 4, 9]
    assert pick_three(10, {0, 9}) == [1, 4, 8]
    assert pick_three(2, set()) == [0, 1]
    assert pick_three(1, {0}) == [0]


@pytest.mark.skipif(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0,
                    reason="ffmpeg missing")
def test_extract_key_frames_real_mp4(tmp_path):
    src = tmp_path / "a.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10:duration=3",
         "-pix_fmt", "yuv420p", str(src)],
        check=True,
    )
    frames = extract_key_frames(src, tmp_path / "frames")
    assert len(frames) == 3
    assert all(f.is_file() for f in frames)
