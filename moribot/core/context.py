"""Runtime context exposed to plugins and other extensions."""

from __future__ import annotations

from dataclasses import dataclass

from .config import ConfigManager
from .db import BaseDatabase
from .event import EventBus
from .platform import PlatformManager
from .provider import ProviderManager


@dataclass(slots=True)
class MoriContext:
    """A deliberately small, explicit seam for extensions."""

    config: ConfigManager
    db: BaseDatabase
    event_bus: EventBus
    provider_manager: ProviderManager
    platform_manager: PlatformManager
