"""High-level memory client used by MoriBot conversations.

The client talks to the embedded MoriMemory HTTP service through the service
manager. Every call is best-effort: memory is an enhancement, so a stopped or
slow memory service must never block or fail a chat reply.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from moribot.core.config import ConfigManager

from .service_manager import MemoryServiceManager, MemoryServiceStatus


@dataclass(slots=True)
class MemoryRecall:
    """Compact result of a reply-time recall request."""

    text: str = ""
    items: int = 0
    tokens: int = 0
    available: bool = False


class MemoryClient:
    def __init__(self, manager: MemoryServiceManager, config: ConfigManager) -> None:
        self.manager = manager
        self.config = config
        self._ready_until = 0.0
        self._failure_until = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("memory.enabled", True)) and self.manager.settings.enabled

    @property
    def recall_enabled(self) -> bool:
        return self.enabled and bool(self.config.get("memory.recall.enabled", True))

    @property
    def ingest_enabled(self) -> bool:
        return self.enabled and bool(self.config.get("memory.ingest.enabled", True))

    async def status(self) -> MemoryServiceStatus:
        if not self.enabled:
            return MemoryServiceStatus(
                running=False,
                owned=False,
                base_url=self.manager.base_url,
                error="disabled",
            )
        return await self.manager.status()

    def reset(self) -> None:
        """Forget cached readiness after settings change."""
        self._ready_until = 0.0
        self._failure_until = 0.0

    async def recall(
        self,
        *,
        user_id: str,
        character_id: str,
        conversation_id: str,
        query: str,
    ) -> MemoryRecall:
        """Retrieve reply-time context for the current character conversation."""
        query = (query or "").strip()
        if not query or not self.recall_enabled:
            return MemoryRecall()
        if not await self._ensure_service():
            return MemoryRecall()

        payload = {
            "query": query[:4000],
            "mode": "recall",
            "limit": max(1, min(int(self.config.get("memory.recall.limit", 8) or 8), 50)),
            "token_budget": max(
                64,
                int(self.config.get("memory.recall.token_budget", 1600) or 1600),
            ),
            "record_access": True,
        }
        timeout = max(
            1.0,
            float(self.config.get("memory.recall.timeout_seconds", 8) or 8),
        )
        try:
            response = await asyncio.wait_for(
                self.manager.request(
                    "POST",
                    "context",
                    headers=self._principal_headers(
                        user_id=user_id,
                        character_id=character_id,
                        conversation_id=conversation_id,
                    ),
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                ),
                timeout=timeout,
            )
        except (TimeoutError, httpx.HTTPError, OSError, ValueError) as exc:
            self._mark_failure()
            logger.bind(source="memory").warning("Memory recall unavailable: {!r}", exc)
            return MemoryRecall()

        if response.status_code != 200:
            logger.bind(source="memory").warning(
                "Memory recall failed with HTTP {}: {}",
                response.status_code,
                response.text[:300],
            )
            return MemoryRecall()
        logger.bind(source="memory").debug(
            "Memory recall response: status={}",
            response.status_code,
        )
        try:
            data = response.json().get("data") or {}
        except ValueError:
            logger.bind(source="memory").warning("Memory recall returned invalid JSON.")
            return MemoryRecall()
        text = str(data.get("context") or "").strip()
        items = data.get("items")
        return MemoryRecall(
            text=text,
            items=len(items) if isinstance(items, list) else 0,
            tokens=int(data.get("context_tokens", 0) or 0),
            available=True,
        )

    async def ingest(
        self,
        *,
        user_id: str,
        character_id: str,
        conversation_id: str,
        messages: list[dict[str, Any]],
        character_name: str = "",
    ) -> bool:
        """Queue one exchange for background extraction and storage."""
        if not messages or not self.ingest_enabled:
            logger.bind(source="memory").debug(
                "Memory ingest skipped: messages={} enabled={}",
                len(messages),
                self.ingest_enabled,
            )
            return False
        if not await self._ensure_service(force=True):
            logger.bind(source="memory").warning("Memory ingest skipped: service unavailable.")
            return False

        logger.bind(source="memory").debug(
            "Posting memory ingest: conversation={} character={} messages={}",
            conversation_id,
            character_id,
            len(messages),
        )

        payload = {
            "conversation_id": conversation_id,
            "character_id": character_id,
            "character_name": character_name or None,
            "async_mode": True,
            "messages": messages,
        }
        timeout = max(
            2.0,
            float(self.config.get("memory.ingest.timeout_seconds", 15) or 15),
        )
        try:
            response = await asyncio.wait_for(
                self.manager.request(
                    "POST",
                    "conversations/ingest",
                    headers=self._principal_headers(
                        user_id=user_id,
                        character_id=character_id,
                        conversation_id=conversation_id,
                    ),
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                ),
                timeout=timeout,
            )
        except (TimeoutError, httpx.HTTPError, OSError, ValueError) as exc:
            self._mark_failure()
            logger.bind(source="memory").warning("Memory ingest unavailable: {!r}", exc)
            return False

        logger.bind(source="memory").debug(
            "Memory ingest response: status={}",
            response.status_code,
        )

        if response.status_code >= 400:
            logger.bind(source="memory").warning(
                "Memory ingest failed with HTTP {}: {}",
                response.status_code,
                response.text[:300],
            )
            return False
        return True

    async def _ensure_service(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now < self._failure_until:
            return False
        if now < self._ready_until:
            return True
        try:
            started = await self.manager.ensure_started()
        except Exception:
            logger.bind(source="memory").exception("Could not start MoriMemory.")
            started = False
        if started:
            self._ready_until = now + 30.0
            self._failure_until = 0.0
        else:
            self._failure_until = now + 5.0
        return started

    def _mark_failure(self) -> None:
        self._ready_until = 0.0
        self._failure_until = time.monotonic() + 5.0

    @staticmethod
    def _principal_headers(
        *,
        user_id: str,
        character_id: str,
        conversation_id: str,
    ) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Mori-User-Id": user_id,
            "X-Mori-Character-Id": character_id,
            "X-Mori-Conversation-Id": conversation_id,
            "X-Mori-Role": "service",
        }
