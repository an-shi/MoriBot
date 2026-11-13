"""Runtime path resolution for MoriBot.

All mutable state (configuration, database, plugins, logs) lives in a single
data directory. The web dashboard is discovered from an environment override
or the conventional build locations.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _resolve_webui_dir(project_root: Path) -> Path | None:
    """Return the first usable dashboard build directory.

    Args:
        project_root: Root of the MoriBot source tree.

    Returns:
        A directory containing ``index.html``, or ``None`` when the dashboard
        has not been built yet.
    """
    candidates: list[Path] = []
    env_dir = os.environ.get("MORIBOT_WEBUI_DIR", "").strip()
    if env_dir:
        candidates.append(Path(env_dir).expanduser())

    candidates.extend(
        (
            project_root / "dashboard" / "dist",
            project_root / "moribot" / "dashboard" / "dist",
        )
    )

    for candidate in candidates:
        resolved = candidate.resolve() if candidate.exists() else candidate
        if (resolved / "index.html").is_file():
            return resolved
    return None


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Resolved filesystem paths used by the runtime."""

    project_root: Path
    data_dir: Path
    config_file: Path
    log_dir: Path
    db_file: Path
    plugin_dir: Path
    avatar_dir: Path
    media_dir: Path
    webui_dist: Path | None

    @classmethod
    def resolve(
        cls,
        data_dir: str | Path | None = None,
        *,
        project_root: Path | None = None,
    ) -> AppPaths:
        """Build an :class:`AppPaths` from arguments, the environment or defaults.

        Args:
            data_dir: Optional data directory override.
            project_root: Optional source tree root, mainly for tests.

        Returns:
            A fully resolved path bundle.
        """
        root = (project_root or Path(__file__).resolve().parents[2]).resolve()

        if data_dir is not None:
            resolved_data = Path(data_dir).expanduser()
        elif env_dir := os.environ.get("MORIBOT_DATA_DIR", "").strip():
            resolved_data = Path(env_dir).expanduser()
        else:
            resolved_data = root / "data"

        if not resolved_data.is_absolute():
            resolved_data = (Path.cwd() / resolved_data).resolve()
        else:
            resolved_data = resolved_data.resolve()

        return cls(
            project_root=root,
            data_dir=resolved_data,
            config_file=resolved_data / "config.json",
            log_dir=resolved_data / "logs",
            db_file=resolved_data / "moribot.db",
            plugin_dir=resolved_data / "plugins",
            avatar_dir=resolved_data / "avatars",
            media_dir=resolved_data / "media",
            webui_dist=_resolve_webui_dir(root),
        )

    def ensure(self) -> None:
        """Create every directory required at runtime."""
        for directory in (
            self.data_dir,
            self.log_dir,
            self.plugin_dir,
            self.avatar_dir,
            self.media_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
