"""Platform lifecycle management."""

from __future__ import annotations

from loguru import logger

from ..event.bus import EventBus
from .adapter import PlatformAdapter


class PlatformManager:
    """Starts and stops registered platform adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, PlatformAdapter] = {}
        self._running: set[str] = set()

    def register(self, adapter: PlatformAdapter) -> None:
        if adapter.adapter_id in self._adapters:
            logger.warning("Platform {} is already registered; replacing it.", adapter.adapter_id)
        self._adapters[adapter.adapter_id] = adapter

    def unregister(self, adapter_id: str) -> PlatformAdapter | None:
        self._running.discard(adapter_id)
        return self._adapters.pop(adapter_id, None)

    def get(self, adapter_id: str) -> PlatformAdapter | None:
        return self._adapters.get(adapter_id)

    @property
    def adapters(self) -> list[PlatformAdapter]:
        return list(self._adapters.values())

    async def start_all(self, event_bus: EventBus) -> None:
        """Start every adapter, isolating failures.

        Args:
            event_bus: Bus handed to each adapter for inbound events.
        """
        for adapter in list(self._adapters.values()):
            try:
                await adapter.start(event_bus)
                self._running.add(adapter.adapter_id)
                logger.info("Platform {} started.", adapter.adapter_id)
            except Exception:
                logger.exception("Platform {} failed to start.", adapter.adapter_id)

    async def stop_all(self) -> None:
        for adapter in list(self._adapters.values()):
            try:
                await adapter.stop()
            except Exception:
                logger.exception("Platform {} failed to stop cleanly.", adapter.adapter_id)
            finally:
                self._running.discard(adapter.adapter_id)
        self._adapters.clear()

    def describe_all(self) -> list[dict]:
        descriptions = []
        for adapter in self._adapters.values():
            description = adapter.describe()
            description["running"] = adapter.adapter_id in self._running
            descriptions.append(description)
        return descriptions

    def __len__(self) -> int:
        return len(self._adapters)
