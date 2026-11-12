"""Normalized event model."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    """Kinds of events the dispatcher understands."""

    MESSAGE = "message"
    NOTICE = "notice"
    LIFECYCLE = "lifecycle"


@dataclass(slots=True)
class MoriEvent:
    """A platform-neutral event flowing through the pipeline."""

    type: EventType = EventType.MESSAGE
    platform_id: str = ""
    platform_name: str = ""
    session_id: str = ""
    sender_id: str = ""
    sender_name: str = ""
    message: str = ""
    raw: Any = None
    timestamp: float = field(default_factory=time.time)
    extras: dict[str, Any] = field(default_factory=dict)
    _stopped: bool = field(default=False, repr=False, compare=False)

    def stop(self) -> None:
        """Stop propagation to later pipeline stages."""
        self._stopped = True

    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def unified_origin(self) -> str:
        """Stable session key used by future conversation storage."""
        return f"{self.platform_id}:{self.session_id}"

    def summary(self, max_length: int = 80) -> str:
        text = self.message.replace("\n", " ").strip()
        if len(text) > max_length:
            return text[: max_length - 1] + "…"
        return text
