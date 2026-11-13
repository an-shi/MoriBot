"""Daily model availability checks driven by config.json."""

from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import datetime

from loguru import logger

from moribot.core.config import ConfigManager

from .provider_service import ProviderConfigService

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ModelHealthScheduler:
    """Run provider test requests at configured local times every day."""

    def __init__(
        self,
        config: ConfigManager,
        provider_service: ProviderConfigService,
        *,
        interval_seconds: float = 20.0,
    ) -> None:
        self.config = config
        self.provider_service = provider_service
        self.interval_seconds = max(5.0, interval_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        enabled, times = self._settings()
        if enabled and times:
            logger.info(
                "Model health checks enabled at {} (server local time).",
                ", ".join(times),
            )
        else:
            logger.info("Model health checks are disabled.")
        self._task = asyncio.create_task(self._loop(), name="model-health-scheduler")

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Scheduled model health check failed.")
            await asyncio.sleep(self.interval_seconds)

    async def _tick(self, now: datetime | None = None) -> bool:
        """Run checks if the current minute matches an unhandled slot."""
        enabled, times = self._settings()
        if not enabled or not times:
            return False

        current = now or datetime.now()
        slot = current.strftime("%H:%M")
        if slot not in times:
            return False

        today = current.strftime("%Y-%m-%d")
        raw_runs = self.config.get("provider.health_check.last_runs", {})
        last_runs = raw_runs if isinstance(raw_runs, dict) else {}
        if last_runs.get(slot) == today:
            return False

        # Persist before running so a crash cannot trigger the same slot again
        # every interval during the rest of the day.
        next_runs = {
            str(key): str(value)
            for key, value in last_runs.items()
            if str(key) in times and str(key) != slot
        }
        next_runs[slot] = today
        self.config.set("provider.health_check.last_runs", next_runs)
        self.config.save()

        await self._run_checks()
        return True

    async def _run_checks(self) -> None:
        results = await self.provider_service.run_health_checks(
            locale=self.config.locale,
        )
        available = sum(1 for result in results if result.ok)
        logger.info(
            "Scheduled model health check finished: {} checked, {} available, {} failed.",
            len(results),
            available,
            len(results) - available,
        )

    def _settings(self) -> tuple[bool, list[str]]:
        raw = self.config.get("provider.health_check", {})
        if not isinstance(raw, dict):
            return False, []
        enabled = bool(raw.get("enabled", False))
        raw_times = raw.get("times", [])
        if not isinstance(raw_times, list):
            return enabled, []
        times = sorted(
            {
                str(value).strip()
                for value in raw_times
                if isinstance(value, str) and _TIME_RE.fullmatch(value.strip())
            }
        )
        return enabled, times
