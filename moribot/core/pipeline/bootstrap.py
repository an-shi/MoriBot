"""Ensure built-in stages are imported exactly once."""

from __future__ import annotations

_loaded = False


def ensure_builtin_stages_registered() -> None:
    global _loaded
    if _loaded:
        return
    from . import builtin  # noqa: F401

    _loaded = True
