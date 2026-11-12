"""Configuration package."""

from .default import CONFIG_VERSION, DEFAULT_CONFIG
from .manager import ConfigManager

__all__ = ["CONFIG_VERSION", "DEFAULT_CONFIG", "ConfigManager"]
