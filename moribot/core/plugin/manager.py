"""Filesystem plugin loader."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from loguru import logger

from .base import MoriPlugin, PluginContext


class PluginManager:
    """Discover and load plugins from ``data/plugins``."""

    def __init__(self, plugin_dir: str | Path, context: PluginContext) -> None:
        self.plugin_dir = Path(plugin_dir)
        self.context = context
        self._plugins: dict[str, MoriPlugin] = {}
        self._modules: dict[str, str] = {}

    async def load_all(self) -> None:
        """Load every valid plugin directory, isolating failures."""
        self.plugin_dir.mkdir(parents=True, exist_ok=True)

        for entry in sorted(self.plugin_dir.iterdir(), key=lambda path: path.name):
            plugin_file = entry / "plugin.py"
            if not entry.is_dir() or not plugin_file.is_file():
                continue
            await self._load_one(entry, plugin_file)

        logger.info("Loaded {} plugin(s).", len(self._plugins))

    async def _load_one(self, entry: Path, plugin_file: Path) -> None:
        module_name = f"moribot_plugins.{entry.name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                logger.error("Could not build an import spec for {}.", plugin_file)
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception:
            logger.exception("Failed to import plugin module {}.", plugin_file)
            sys.modules.pop(module_name, None)
            return

        candidate = getattr(module, "plugin", None)
        if candidate is None:
            plugin_class = getattr(module, "Plugin", None)
            candidate = plugin_class() if isinstance(plugin_class, type) else None
        if isinstance(candidate, type) and issubclass(candidate, MoriPlugin):
            candidate = candidate()
        if not isinstance(candidate, MoriPlugin):
            logger.error(
                "Plugin {} must expose a MoriPlugin instance named 'plugin'.",
                entry.name,
            )
            sys.modules.pop(module_name, None)
            return

        try:
            await candidate.initialize(self.context)
        except Exception:
            logger.exception("Plugin {} failed to initialize.", entry.name)
            sys.modules.pop(module_name, None)
            return

        self._plugins[entry.name] = candidate
        self._modules[entry.name] = module_name
        logger.info("Plugin loaded: {} v{}.", candidate.name, candidate.version)

    async def unload_all(self) -> None:
        """Terminate plugins in reverse load order."""
        for directory_name, plugin in reversed(list(self._plugins.items())):
            try:
                await plugin.terminate()
            except Exception:
                logger.exception("Plugin {} failed to terminate.", directory_name)
            module_name = self._modules.get(directory_name)
            if module_name:
                sys.modules.pop(module_name, None)

        self._plugins.clear()
        self._modules.clear()

    @property
    def plugins(self) -> list[MoriPlugin]:
        return list(self._plugins.values())

    def describe_all(self) -> list[dict]:
        return [plugin.describe() for plugin in self._plugins.values()]

    def __len__(self) -> int:
        return len(self._plugins)
