"""Core lifecycle: builds managers, starts the bus and tears everything down."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from loguru import logger

from .. import __version__
from .accounts import (
    AdminCredentials,
    ensure_initial_admin,
    reset_admin_password,
)
from .config import ConfigManager
from .context import MoriContext
from .db import SQLiteDatabase, utcnow
from .event import EventBus
from .paths import AppPaths
from .pipeline import PipelineContext, PipelineScheduler
from .platform import PlatformManager
from .platform.mobile_adapter import MobilePlatformAdapter
from .plugin import PluginManager
from .provider import ModelGateway, ProviderManager
from .provider.config import spec_from_record
from .security import SecretBox


class CoreLifecycle:
    """Owns long-lived components and their start/stop ordering."""

    def __init__(
        self,
        paths: AppPaths,
        config: ConfigManager,
        *,
        reset_password: bool = False,
    ) -> None:
        self.paths = paths
        self.config = config
        self._reset_password = reset_password

        self.db = SQLiteDatabase(paths.db_file)
        self.secret_box = SecretBox(config.jwt_secret)
        self.provider_manager = ProviderManager()
        self.model_gateway = ModelGateway(self.provider_manager)
        self.platform_manager = PlatformManager()
        self.mobile_adapter = MobilePlatformAdapter()
        self.platform_manager.register(self.mobile_adapter)

        self.pipeline = PipelineScheduler(
            PipelineContext(
                config=config,
                db=self.db,
                provider_manager=self.provider_manager,
                platform_manager=self.platform_manager,
            )
        )
        self.event_bus = EventBus(asyncio.Queue(), self.pipeline.execute)
        self.context = MoriContext(
            config=config,
            db=self.db,
            event_bus=self.event_bus,
            provider_manager=self.provider_manager,
            platform_manager=self.platform_manager,
        )
        self.plugin_manager = PluginManager(paths.plugin_dir, self.context)

        self.initial_credentials: AdminCredentials | None = None
        self.started_at: datetime | None = None
        self._running = False
        self._stopped = False

    async def initialize(self) -> None:
        """Initialize storage, accounts, pipeline and plugins."""
        await self.db.initialize()

        if self._reset_password:
            self.initial_credentials = await reset_admin_password(
                self.db,
                self.paths,
                self.config.locale,
            )
        else:
            self.initial_credentials = await ensure_initial_admin(
                self.db,
                self.paths,
                self.config.locale,
            )

        await self.pipeline.initialize()
        await self.reload_providers()
        await self.plugin_manager.load_all()

        logger.info(
            "Core initialized: {} provider(s), {} platform(s), {} plugin(s).",
            len(self.provider_manager),
            len(self.platform_manager),
            len(self.plugin_manager),
        )

    async def reload_providers(self) -> None:
        """Rebuild provider instances from persisted model configuration."""
        records = await self.db.list_model_providers()
        specs = []
        for record in records:
            if not record.enabled:
                continue
            spec = spec_from_record(record, self.secret_box)
            if spec is not None:
                specs.append(spec)
        await self.provider_manager.load_specs(specs)

    async def start(self) -> None:
        """Start the event bus and platform adapters."""
        await self.event_bus.start()
        await self.platform_manager.start_all(self.event_bus)
        self.started_at = utcnow()
        self._running = True
        logger.info("MoriBot v{} is running.", __version__)

    async def stop(self) -> None:
        """Stop adapters, drain the bus and release resources."""
        if self._stopped:
            return
        self._stopped = True
        self._running = False
        await self.event_bus.stop()
        await self.platform_manager.stop_all()
        await self.plugin_manager.unload_all()
        await self.provider_manager.close_all()
        await self.db.dispose()
        logger.info("MoriBot stopped.")

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> dict:
        """Return a JSON-friendly runtime summary for the dashboard."""
        now = utcnow()
        uptime = int((now - self.started_at).total_seconds()) if self.started_at else 0
        started_at = None
        if self.started_at is not None:
            started_at = self.started_at.replace(tzinfo=UTC).isoformat()

        return {
            "name": self.config.bot_name,
            "version": __version__,
            "running": self._running,
            "started_at": started_at,
            "uptime_seconds": max(0, uptime),
            "providers": len(self.provider_manager),
            "platforms": len(self.platform_manager),
            "plugins": len(self.plugin_manager),
            "mobile_online": self.mobile_adapter.online_count,
        }
