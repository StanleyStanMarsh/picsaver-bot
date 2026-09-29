"""In-place Telegram save-status edits with throttled progress bar.

Flood control (DevOps):
- Always edit the SAME status message (editMessageText on one message_id).
- Throttle: edits apply on phase / k-of-n changes OR at most once per
  MIN_EDIT_INTERVAL_SEC (~1.2s). Pass force=True for finals / important jumps.
- CLIP encode: UI shows one «Индексация» phase for the whole forward
  pass — do not tick mid-encode (worker sets phase once at encode start).
- Telegram "message is not modified" errors are ignored.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from utils import APP_CTX

if TYPE_CHECKING:
    from aiogram.types import Message

logger = APP_CTX.get_logger()

BAR_WIDTH = 10
MIN_EDIT_INTERVAL_SEC = 1.2

# Worker / bot phase keys → (Russian label, bar fraction 0..1).
# CLIP stays at 0.7 for the whole encode; next bump is qdrant/done only.
PHASES: dict[str, tuple[str, float]] = {
    "download": ("Скачивание / подготовка", 0.15),
    "queue": ("В очереди", 0.30),
    "storage": ("Сохранение в хранилище", 0.40),
    "clip": ("Индексация", 0.70),
    "qdrant": ("Добавление в индекс", 0.90),
    "done": ("Готово", 1.0),
}

MSG_SAVE_OK = "✅ Изображение сохранено и проиндексировано"


def render_bar(done_frac: float, width: int = BAR_WIDTH) -> str:
    """Unicode block progress bar, e.g. [███░░░░░░░] for ~0.3."""
    frac = max(0.0, min(1.0, float(done_frac)))
    filled = int(round(frac * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def format_phase_status(phase: str) -> str:
    label, frac = PHASES.get(phase, ("Обработка", 0.5))
    return f"📸 {label}\n[{render_bar(frac)}]"


def format_album_progress(k: int, n: int) -> str:
    """Album mid-progress: k photos finished out of n."""
    n = max(n, 1)
    k = max(0, min(k, n))
    return f"📸 Альбом  {k}/{n}\n[{render_bar(k / n)}]"


def _is_not_modified(exc: BaseException) -> bool:
    return "message is not modified" in str(exc).lower()


class StatusEditor:
    """Edit one Telegram status message in place with edit throttling."""

    def __init__(self, message: Message | None) -> None:
        self.message = message
        self.last_text: str | None = getattr(message, "text", None) if message else None
        self.last_edit_ts: float = 0.0

    @property
    def available(self) -> bool:
        return self.message is not None

    async def set(self, text: str, *, force: bool = False) -> bool:
        """Edit status to ``text``. Returns True if message reflects ``text``.

        No-op (True) if missing message is absent → False; unchanged text → True;
        throttled skip → False (caller may retry later). ``force=True`` bypasses
        the min-interval throttle (finals / important phase jumps).
        """
        if self.message is None:
            return False
        if text == self.last_text:
            return True
        now = time.monotonic()
        if (
            not force
            and self.last_edit_ts
            and (now - self.last_edit_ts) < MIN_EDIT_INTERVAL_SEC
        ):
            return False
        try:
            await self.message.edit_text(text)
            self.last_text = text
            self.last_edit_ts = now
            return True
        except Exception as e:
            if _is_not_modified(e):
                self.last_text = text
                return True
            logger.warning("status edit failed: %s", e)
            return False

    async def set_phase(self, phase: str, *, force: bool = False) -> bool:
        return await self.set(format_phase_status(phase), force=force)

    async def set_album(self, k: int, n: int, *, force: bool = False) -> bool:
        return await self.set(format_album_progress(k, n), force=force)

    async def finish(self, text: str) -> bool:
        """Final status; always forced so the user sees the outcome."""
        return await self.set(text, force=True)
