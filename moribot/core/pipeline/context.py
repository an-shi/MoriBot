"""Pipeline execution context shared by all stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import ConfigManager
from ..db import BaseDatabase
from ..platform import PlatformManager
from ..provider import ProviderManager


@dataclass(slots=True)
class PipelineContext:
    """Dependencies available to pipeline stages."""

    config: ConfigManager
    db: BaseDatabase
    provider_manager: ProviderManager
    platform_manager: PlatformManager
    extras: dict[str, Any] = field(default_factory=dict)
