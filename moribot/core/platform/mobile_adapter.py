"""MoriMobile platform adapter.

The phone connects outbound to the dashboard through ``/api/v1/mobile/ws``.
That direction is deliberate: a home server behind NAT does not need an
inbound port to reach the phone, and the mobile app keeps a single encrypted
WebSocket to the public HTTPS endpoint (or tunnel).

This adapter only tracks live connections and serializes outbound payloads. The
WebSocket route owns authentication, pairing and inbound event creation.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from ..event import EventBus
from .adapter import PlatformAdapter

SendPayload = Callable[[dict[str, Any]], Awaitable[None]]
CloseConnection = Callable[[int, str], Awaitable[None]]


@dataclass(slots=True)
class MobileConnection:
    """A live authenticated MoriMobile WebSocket."""

    device_id: str
    device_name: str
    send_payload: SendPayload
    close: CloseConnection
    connected_at: float = field(default_factory=time.time)


class MobilePlatformAdapter(PlatformAdapter):
    """Bidirectional message bridge for paired MoriMobile devices."""

    platform_type = "morimobile"

    def __init__(self, adapter_id: str = "morimobile") -> None:
        super().__init__(adapter_id, config={"name": "MoriMobile"})
        self.event_bus: EventBus | None = None
        self._connections: dict[str, MobileConnection] = {}

    async def start(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        logger.info("MoriMobile gateway adapter started.")

    async def stop(self) -> None:
        connections = list(self._connections.values())
        self._connections.clear()
        for connection in connections:
            try:
                await connection.send_payload(
                    {
                        "type": "shutdown",
                        "message": "Service is shutting down",
                        "timestamp": time.time(),
                    }
                )
                await connection.close(1001, "Service is shutting down")
            except Exception:
                logger.debug("Failed to close mobile connection {}.", connection.device_id)
        self.event_bus = None

    async def send_message(self, session_id: str, text: str) -> None:
        """Send a text message to a paired device."""
        connection = self._connections.get(session_id)
        if connection is None:
            logger.warning("MoriMobile device {} is not connected; message dropped.", session_id)
            return
        await connection.send_payload(
            {
                "type": "message",
                "id": str(uuid.uuid4()),
                "text": text,
                "timestamp": time.time(),
            }
        )

    async def send_payload(self, device_id: str, payload: dict[str, Any]) -> bool:
        """Send an arbitrary protocol payload to a device."""
        connection = self._connections.get(device_id)
        if connection is None:
            return False
        try:
            await connection.send_payload(payload)
            return True
        except Exception:
            logger.debug("Failed to send payload to mobile device {}.", device_id)
            return False

    async def register_connection(
        self,
        *,
        device_id: str,
        device_name: str,
        send_payload: SendPayload,
        close: CloseConnection,
    ) -> MobileConnection:
        """Attach a connection, replacing an older one for the same device."""
        previous = self._connections.get(device_id)
        if previous is not None:
            try:
                await previous.close(4000, "Replaced by a new connection")
            except Exception:
                logger.debug("Old mobile connection for {} closed uncleanly.", device_id)

        connection = MobileConnection(
            device_id=device_id,
            device_name=device_name,
            send_payload=send_payload,
            close=close,
        )
        self._connections[device_id] = connection
        logger.info("MoriMobile device {} connected.", device_name)
        return connection

    def unregister_connection(
        self,
        device_id: str,
        connection: MobileConnection | None = None,
    ) -> None:
        """Remove a connection if it is still the current one."""
        current = self._connections.get(device_id)
        if current is None:
            return
        if connection is not None and current is not connection:
            return
        self._connections.pop(device_id, None)
        logger.info("MoriMobile device {} disconnected.", device_id)

    async def disconnect_device(
        self,
        device_id: str,
        *,
        reason: str = "Device removed",
    ) -> None:
        """Force a device offline after its token is revoked."""
        connection = self._connections.pop(device_id, None)
        if connection is None:
            return
        try:
            await connection.send_payload(
                {
                    "type": "revoked",
                    "message": reason,
                    "timestamp": time.time(),
                }
            )
            await connection.close(4001, reason)
        except Exception:
            logger.debug("Failed to close revoked mobile device {}.", device_id)

    def is_online(self, device_id: str) -> bool:
        return device_id in self._connections

    @property
    def online_count(self) -> int:
        return len(self._connections)

    @property
    def online_device_ids(self) -> list[str]:
        return list(self._connections)

    def describe(self) -> dict[str, Any]:
        description = super().describe()
        description["online"] = len(self._connections)
        return description
