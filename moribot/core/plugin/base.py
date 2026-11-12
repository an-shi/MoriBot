"""Plugin contract.

A plugin is a directory under ``data/plugins`` containing ``plugin.py``. The
module exposes either a ``plugin`` instance or a ``Plugin`` class:

    from moribot.core.plugin import MoriPlugin

    class Plugin(MoriPlugin):
        name = "echo"
        version = "0.1.0"

        async def initialize(self, ctx):
            self.ctx = ctx

    plugin = Plugin()
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..config import ConfigManager
    from ..db import BaseDatabase
    from ..event import EventBus
    from ..platform import PlatformManager
    from ..provider import ProviderManager


class PluginContext(Protocol):
    """Structural interface handed to plugins.

    ``moribot.core.context.MoriContext`` satisfies this protocol.
    """

    config: ConfigManager
    db: BaseDatabase
    event_bus: EventBus
    provider_manager: ProviderManager
    platform_manager: PlatformManager


class MoriPlugin(abc.ABC):
    """Base class for MoriBot plugins."""

    name: str = "unnamed"
    version: str = "0.0.0"
    description: str = ""

    @abc.abstractmethod
    async def initialize(self, ctx: PluginContext) -> None:
        """Attach to the runtime and register any hooks."""
        raise NotImplementedError

    async def terminate(self) -> None:
        """Release resources during shutdown."""
        return None

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }
