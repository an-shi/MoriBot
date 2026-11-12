"""Platform adapter abstraction.

Adapters translate an external chat platform (QQ, Telegram, Discord, WebChat,
...) into normalized :class:`moribot.core.event.models.MoriEvent` instances and
send replies back. No concrete adapter is bundled in the foundation.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..event.bus import EventBus


class PlatformAdapter(abc.ABC):
    """Base class for inbound/outbound platform integrations."""

    platform_type: ClassVar[str] = "base"

    def __init__(
        self,
        adapter_id: str,
        *,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.adapter_id = adapter_id
        self.config = dict(config or {})

    @property
    def display_name(self) -> str:
        return str(self.config.get("name") or self.adapter_id)

    @abc.abstractmethod
    async def start(self, event_bus: EventBus) -> None:
        """Connect to the platform and publish inbound events."""
        raise NotImplementedError

    @abc.abstractmethod
    async def stop(self) -> None:
        """Disconnect and release platform resources."""
        raise NotImplementedError

    @abc.abstractmethod
    async def send_message(self, session_id: str, text: str) -> None:
        """Send a plain-text reply to a session."""
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.adapter_id,
            "name": self.display_name,
            "type": self.platform_type,
        }
