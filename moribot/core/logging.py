"""Logging setup and an in-process log broker.

The broker is the foundation for a future live console page: log records are
kept in a bounded ring buffer and fanned out to async subscribers without
blocking the logging thread.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from .paths import AppPaths

RECENT_LOG_LIMIT = 2000
SUBSCRIBER_QUEUE_LIMIT = 1000

_CONFIGURED = False
_BROKER_SINK_ID: int | None = None


@dataclass(slots=True)
class LogEntry:
    """A serializable log record."""

    time: float
    level: str
    message: str
    module: str = ""
    line: int = 0
    text: str = ""
    source: str = "app"

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "level": self.level,
            "message": self.message,
            "module": self.module,
            "line": self.line,
            "text": self.text,
            "source": self.source,
        }


class LogBroker:
    """Thread-safe fan-out hub for log entries."""

    def __init__(self, recent_limit: int = RECENT_LOG_LIMIT) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=recent_limit)
        self._subscribers: dict[asyncio.Queue[LogEntry], asyncio.AbstractEventLoop | None] = {}
        self._lock = threading.Lock()

    def publish(self, entry: LogEntry) -> None:
        """Store an entry and deliver it to every live subscriber."""
        with self._lock:
            self._entries.append(entry)
            subscribers = tuple(self._subscribers.items())

        for queue, loop in subscribers:
            if loop is None or loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(self._offer, queue, entry)
            except RuntimeError:
                # The subscriber loop shut down between the check and the call.
                continue

    @staticmethod
    def _offer(queue: asyncio.Queue[LogEntry], entry: LogEntry) -> None:
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            # Slow consumers lose old messages instead of blocking logging.
            pass

    def recent(self, limit: int = 200) -> list[LogEntry]:
        """Return the most recent entries in chronological order."""
        limit = max(1, min(limit, len(self._entries) or 1))
        with self._lock:
            return list(self._entries)[-limit:]

    async def subscribe(self) -> AsyncIterator[LogEntry]:
        """Yield buffered and future entries until the consumer disconnects."""
        queue: asyncio.Queue[LogEntry] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_LIMIT)
        loop = asyncio.get_running_loop()

        with self._lock:
            self._subscribers[queue] = loop
            backlog = list(self._entries)

        for entry in backlog:
            self._offer(queue, entry)

        try:
            while True:
                yield await queue.get()
        finally:
            with self._lock:
                self._subscribers.pop(queue, None)


class _InterceptHandler(logging.Handler):
    """Route standard-library logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _broker_sink(broker: LogBroker) -> Any:
    def sink(message: Any) -> None:
        record = getattr(message, "record", None)
        if record is None:
            broker.publish(
                LogEntry(time=time.time(), level="INFO", message=str(message), text=str(message))
            )
            return

        broker.publish(
            LogEntry(
                time=record["time"].timestamp(),
                level=record["level"].name,
                message=record["message"],
                module=record["name"] or "",
                line=record["line"] or 0,
                text=str(message),
                source=str(record["extra"].get("source", "app")),
            )
        )

    return sink


def setup_logging(
    paths: AppPaths,
    level: str = "INFO",
    broker: LogBroker | None = None,
) -> None:
    """Configure console, rotating-file and broker sinks once per process.

    Args:
        paths: Resolved runtime paths.
        level: Minimum log level name.
        broker: Optional broker receiving every record.
    """
    global _CONFIGURED, _BROKER_SINK_ID
    level = level.upper()
    paths.log_dir.mkdir(parents=True, exist_ok=True)

    if not _CONFIGURED:
        logger.remove()
        logger.add(
            sys.stderr,
            level=level,
            colorize=True,
            enqueue=True,
            backtrace=False,
            diagnose=False,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
            ),
        )
        logger.add(
            paths.log_dir / "moribot.log",
            level=level,
            rotation="10 MB",
            retention="14 days",
            encoding="utf-8",
            enqueue=True,
            backtrace=False,
            diagnose=False,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}",
        )
        logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
        for name in ("uvicorn.access", "httpx", "httpcore", "aiosqlite", "sqlalchemy.engine"):
            logging.getLogger(name).setLevel(logging.WARNING)
        _CONFIGURED = True

    # Tests and embedding may build several app instances in one process. Keep
    # exactly one broker sink and rebind it to the current broker.
    if _BROKER_SINK_ID is not None:
        try:
            logger.remove(_BROKER_SINK_ID)
        except ValueError:
            pass
        _BROKER_SINK_ID = None
    if broker is not None:
        _BROKER_SINK_ID = logger.add(
            _broker_sink(broker),
            level=level,
            enqueue=True,
            format="{message}",
        )


def get_log_file(paths: AppPaths) -> Path:
    """Return the conventional log file path."""
    return paths.log_dir / "moribot.log"
