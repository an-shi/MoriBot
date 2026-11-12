"""JSON-backed runtime configuration with defensive merging and atomic writes."""

from __future__ import annotations

import copy
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

from loguru import logger

from .default import CONFIG_VERSION, DEFAULT_CONFIG


class ConfigManager:
    """Load, merge and persist MoriBot's runtime configuration.

    The manager intentionally uses plain dictionaries so future modules and
    plugins can add configuration sections without a schema migration. Missing
    keys are always backfilled from ``DEFAULT_CONFIG``.
    """

    def __init__(self, config_path: str | Path, defaults: dict[str, Any] | None = None) -> None:
        self.config_path = Path(config_path)
        self.defaults = copy.deepcopy(defaults or DEFAULT_CONFIG)
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        """Read the config file, repairing missing defaults and secrets.

        Returns:
            The loaded configuration dictionary.
        """
        with self._lock:
            changed = False
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            if not self.config_path.exists():
                self._data = copy.deepcopy(self.defaults)
                changed = True
            else:
                try:
                    raw = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
                    if not isinstance(raw, dict):
                        raise ValueError("configuration root must be a JSON object")
                    self._data = raw
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    backup = self.config_path.with_name(
                        f"{self.config_path.stem}.broken-{int(time.time())}.json"
                    )
                    logger.error(
                        "Failed to read config {}: {}. Recreating defaults (backup: {}).",
                        self.config_path,
                        exc,
                        backup,
                    )
                    try:
                        self.config_path.replace(backup)
                    except OSError:
                        logger.exception("Could not back up the broken config file.")
                    self._data = copy.deepcopy(self.defaults)
                    changed = True

                changed = self._merge_missing(self.defaults, self._data) or changed

            if not self._data.get("config_version"):
                self._data["config_version"] = CONFIG_VERSION
                changed = True

            dashboard = self._data.get("dashboard")
            if not isinstance(dashboard, dict):
                dashboard = {}
                self._data["dashboard"] = dashboard
                changed = True
            if not dashboard.get("jwt_secret"):
                dashboard["jwt_secret"] = secrets.token_urlsafe(48)
                changed = True

            if changed:
                self.save()

            return self._data

    @staticmethod
    def _merge_missing(defaults: dict[str, Any], target: dict[str, Any]) -> bool:
        """Recursively add default keys without overwriting user values."""
        changed = False
        for key, default_value in defaults.items():
            if key not in target:
                target[key] = copy.deepcopy(default_value)
                changed = True
                continue

            value = target[key]
            if isinstance(default_value, dict) and isinstance(value, dict):
                changed = ConfigManager._merge_missing(default_value, value) or changed
        return changed

    def save(self) -> None:
        """Atomically persist the current configuration."""
        with self._lock:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.config_path.with_name(f".{self.config_path.name}.tmp")
            payload = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
            temp_path.write_text(payload, encoding="utf-8")

            # os.replace is atomic on both POSIX and Windows when the target
            # lives on the same volume, which is guaranteed by the temp path.
            os.replace(temp_path, self.config_path)
            try:
                os.chmod(self.config_path, 0o600)
            except OSError:
                # Windows filesystems may not honor POSIX modes.
                pass

    def get(self, key: str, default: Any = None) -> Any:
        """Read a value using a dot-separated path."""
        current: Any = self._data
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def set(self, key: str, value: Any) -> None:
        """Write a value using a dot-separated path."""
        with self._lock:
            parts = key.split(".")
            current = self._data
            for part in parts[:-1]:
                child = current.get(part)
                if not isinstance(child, dict):
                    child = {}
                    current[part] = child
                current = child
            current[parts[-1]] = value

    def as_dict(self) -> dict[str, Any]:
        """Return a deep copy safe for callers to mutate."""
        with self._lock:
            return copy.deepcopy(self._data)

    @property
    def bot_name(self) -> str:
        return str(self.get("bot.name", "MoriBot"))

    @property
    def locale(self) -> str:
        from ..i18n import normalize_locale

        return normalize_locale(str(self.get("bot.locale", "zh-CN")))

    @property
    def log_level(self) -> str:
        value = str(self.get("bot.log_level", "INFO")).upper()
        if value not in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}:
            return "INFO"
        return value

    @property
    def jwt_secret(self) -> str:
        secret = str(self.get("dashboard.jwt_secret", "")).strip()
        if not secret:
            raise RuntimeError("dashboard.jwt_secret is not configured")
        return secret

    @property
    def token_expire_hours(self) -> int:
        try:
            value = int(self.get("dashboard.token_expire_hours", 168))
        except (TypeError, ValueError):
            value = 168
        return max(1, value)

    @property
    def cors_origins(self) -> list[str]:
        origins = self.get("dashboard.cors_origins", [])
        if not isinstance(origins, list):
            return []
        return [str(origin) for origin in origins if str(origin).strip()]
