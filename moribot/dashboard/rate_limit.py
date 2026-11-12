"""In-memory login throttling to slow down credential stuffing."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class LoginRateLimiter:
    """Per-client failure window with a temporary lockout."""

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_seconds: float = 60.0,
        block_seconds: float = 120.0,
    ) -> None:
        self.max_failures = max(1, max_failures)
        self.window_seconds = max(1.0, window_seconds)
        self.block_seconds = max(1.0, block_seconds)
        self._failures: dict[str, deque[float]] = {}
        self._blocked_until: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()

    async def retry_after(self, key: str) -> float | None:
        """Return seconds until the client may retry, or ``None`` when allowed."""
        async with self._lock:
            now = time.monotonic()
            self._cleanup(now)

            blocked_until = self._blocked_until.get(key)
            if blocked_until is not None:
                if blocked_until > now:
                    return blocked_until - now
                self._blocked_until.pop(key, None)
                self._failures.pop(key, None)
                return None

            failures = self._failures.get(key)
            if failures and len(failures) >= self.max_failures:
                self._blocked_until[key] = now + self.block_seconds
                failures.clear()
                return self.block_seconds
            return None

    async def register_failure(self, key: str) -> None:
        """Record a failed attempt and lock the client out if needed."""
        async with self._lock:
            now = time.monotonic()
            failures = self._failures.setdefault(key, deque())
            failures.append(now)
            while failures and now - failures[0] > self.window_seconds:
                failures.popleft()
            if len(failures) >= self.max_failures:
                self._blocked_until[key] = now + self.block_seconds
                failures.clear()

    async def reset(self, key: str) -> None:
        """Clear failures after a successful login."""
        async with self._lock:
            self._failures.pop(key, None)
            self._blocked_until.pop(key, None)

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < 300:
            return
        self._last_cleanup = now

        for key, failures in list(self._failures.items()):
            while failures and now - failures[0] > self.window_seconds:
                failures.popleft()
            if not failures:
                self._failures.pop(key, None)

        for key, blocked_until in list(self._blocked_until.items()):
            if blocked_until <= now:
                self._blocked_until.pop(key, None)
