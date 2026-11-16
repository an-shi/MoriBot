"""Background scheduler for character diaries."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime

from loguru import logger

from .diary_service import DiaryService


class DiaryScheduler:
    """Check schedules periodically and write due diaries."""

    def __init__(
        self,
        diary_service: DiaryService,
        *,
        interval_seconds: float = 30.0,
    ) -> None:
        self.diary_service = diary_service
        self.interval_seconds = max(10.0, interval_seconds)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        logger.info(
            "Diary scheduler started (checking every {} seconds, server local time).",
            int(self.interval_seconds),
        )
        self._task = asyncio.create_task(self._loop(), name="diary-scheduler")

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
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.bind(source="diary").exception("Diary scheduler tick failed.")
            await asyncio.sleep(self.interval_seconds)

    async def tick(self, now: datetime | None = None) -> int:
        generated = await self.diary_service.generate_due(now)
        if generated:
            logger.info(
                "Diary scheduler generated {} entr{}.",
                len(generated),
                "y" if len(generated) == 1 else "ies",
            )
        return len(generated)
