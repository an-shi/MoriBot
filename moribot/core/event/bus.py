"""Asynchronous event bus.

Adapters publish events into an unbounded queue; a background dispatcher runs
each event through the pipeline in its own task so slow model calls never block
inbound platform readers.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from loguru import logger

from .models import MoriEvent


class EventBus:
    """Queue-backed event dispatcher with bounded concurrency."""

    def __init__(
        self,
        queue: asyncio.Queue[MoriEvent],
        dispatcher: Callable[[MoriEvent], Awaitable[None]],
        *,
        max_concurrency: int = 16,
    ) -> None:
        self.queue = queue
        self._dispatcher = dispatcher
        self._max_concurrency = max(1, max_concurrency)
        self._tasks: set[asyncio.Task[None]] = set()
        self._loop_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start consuming the queue."""
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._consume(), name="moribot-event-bus")
        logger.debug("Event bus started.")

    async def stop(self) -> None:
        """Stop accepting events and drain in-flight work."""
        self._stop_event.set()
        if self._loop_task is not None:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None

        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        while not self.queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
                self.queue.task_done()

        logger.debug("Event bus stopped.")

    async def put(self, event: MoriEvent) -> None:
        """Queue an event for processing."""
        await self.queue.put(event)

    def put_nowait(self, event: MoriEvent) -> None:
        """Queue an event without awaiting; useful for synchronous callbacks."""
        self.queue.put_nowait(event)

    async def _consume(self) -> None:
        while not self._stop_event.is_set():
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

            task = asyncio.create_task(self._dispatch_one(event), name="moribot-event")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

            if len(self._tasks) >= self._max_concurrency:
                done, _ = await asyncio.wait(
                    self._tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for finished in done:
                    self._tasks.discard(finished)

    async def _dispatch_one(self, event: MoriEvent) -> None:
        try:
            await self._dispatcher(event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Pipeline failed for event from {}:{}",
                event.platform_id,
                event.session_id,
            )
        finally:
            self.queue.task_done()
