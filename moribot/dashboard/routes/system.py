"""Public and authenticated system information endpoints."""

from __future__ import annotations

import os
import platform as platform_module
import re
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from moribot import __version__
from moribot.core.backup import BackupService, default_backup_filename
from moribot.core.db import User
from moribot.core.errors import MoriError
from moribot.core.i18n import translate
from moribot.core.logging import RECENT_LOG_LIMIT, get_log_file

from ..deps import (
    get_config,
    get_core,
    get_current_user,
    get_locale,
    get_provider_service,
)
from ..responses import ApiResponse, ok
from ..schemas import (
    HealthCheckSettings,
    HealthInfo,
    LogEntryOut,
    ModelHealthRunOut,
    PublicInfo,
    SystemInfo,
    SystemLogsOut,
    SystemSettingsOut,
    SystemSettingsUpdate,
)

router = APIRouter(prefix="/system", tags=["system"])
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_LEVEL_ORDER = {
    "DEBUG": 10,
    "INFO": 20,
    "SUCCESS": 25,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


def _settings_response(config) -> SystemSettingsOut:
    raw = config.get("provider.health_check", {})
    raw = raw if isinstance(raw, dict) else {}
    raw_times = raw.get("times", [])
    times = (
        sorted(
            {
                str(value).strip()
                for value in raw_times
                if isinstance(value, str) and _TIME_RE.fullmatch(value.strip())
            }
        )
        if isinstance(raw_times, list)
        else []
    )
    raw_runs = raw.get("last_runs", {})
    last_runs = (
        {str(key): str(value) for key, value in raw_runs.items()}
        if isinstance(raw_runs, dict)
        else {}
    )
    now = datetime.now().astimezone()
    return SystemSettingsOut(
        health_check=HealthCheckSettings(
            enabled=bool(raw.get("enabled", False)),
            times=times,
            last_runs=last_runs,
        ),
        server_time=now.strftime("%Y-%m-%d %H:%M"),
        timezone=now.tzname() or "",
    )


def _normalize_times(raw_times: list[str], *, enabled: bool, locale: str) -> list[str]:
    if len(raw_times) > 12:
        raise MoriError(translate("settings.too_many_times", locale))
    values: set[str] = set()
    for raw in raw_times:
        value = str(raw).strip()
        if not _TIME_RE.fullmatch(value):
            raise MoriError(translate("settings.invalid_time", locale, value=value))
        values.add(value)
    if enabled and not values:
        raise MoriError(translate("settings.times_required", locale))
    return sorted(values)


@router.get("/public", response_model=ApiResponse[PublicInfo])
async def public_info(config=Depends(get_config)) -> dict:
    """Unauthenticated metadata used by the login screen."""
    return ok(
        PublicInfo(
            name=config.bot_name,
            version=__version__,
            description=str(config.get("bot.description", "")),
        )
    )


@router.get("/health", response_model=ApiResponse[HealthInfo])
async def health(_config=Depends(get_config)) -> dict:
    """Liveness probe."""
    return ok(HealthInfo(status="ok", version=__version__))


@router.get("/info", response_model=ApiResponse[SystemInfo])
async def system_info(
    _user: User = Depends(get_current_user),
    core=Depends(get_core),
) -> dict:
    """Runtime summary for the dashboard home page."""
    status = core.status()
    return ok(
        SystemInfo(
            **status,
            python_version=platform_module.python_version(),
        )
    )


@router.get("/settings", response_model=ApiResponse[SystemSettingsOut])
async def get_system_settings(
    _user: User = Depends(get_current_user),
    config=Depends(get_config),
) -> dict:
    """Return editable system settings."""
    return ok(_settings_response(config))


@router.patch("/settings", response_model=ApiResponse[SystemSettingsOut])
async def update_system_settings(
    payload: SystemSettingsUpdate,
    request: Request,
    _user: User = Depends(get_current_user),
    config=Depends(get_config),
) -> dict:
    """Persist scheduled model health check settings."""
    locale = get_locale(request)
    health = payload.health_check
    times = _normalize_times(health.times, enabled=health.enabled, locale=locale)
    config.set("provider.health_check.enabled", health.enabled)
    config.set("provider.health_check.times", times)
    raw_runs = config.get("provider.health_check.last_runs", {})
    if isinstance(raw_runs, dict):
        config.set(
            "provider.health_check.last_runs",
            {str(key): str(value) for key, value in raw_runs.items() if str(key) in times},
        )
    config.save()
    return ok(_settings_response(config), message=translate("settings.saved", locale))


@router.post("/model-health/run", response_model=ApiResponse[ModelHealthRunOut])
async def run_model_health(
    request: Request,
    _user: User = Depends(get_current_user),
    service=Depends(get_provider_service),
) -> dict:
    """Run a connectivity test for every enabled model immediately."""
    results = await service.run_health_checks(locale=get_locale(request))
    available = sum(1 for result in results if result.ok)
    return ok(
        ModelHealthRunOut(
            checked=len(results),
            available=available,
            failed=len(results) - available,
        )
    )


@router.get("/logs", response_model=ApiResponse[SystemLogsOut])
async def system_logs(
    request: Request,
    level: str | None = Query(default=None, max_length=16),
    source: str | None = Query(default=None, max_length=16),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=300, ge=1, le=1000),
    _user: User = Depends(get_current_user),
) -> dict:
    """Return recent runtime and business API log entries."""
    entries = request.app.state.log_broker.recent(limit=RECENT_LOG_LIMIT)
    min_level = _LEVEL_ORDER.get((level or "").upper(), 0)
    normalized_source = (source or "").strip().lower()
    query = (q or "").strip().lower()

    filtered = []
    for entry in entries:
        if _LEVEL_ORDER.get(entry.level.upper(), 0) < min_level:
            continue
        if normalized_source not in {"", "all"} and entry.source != normalized_source:
            continue
        if query and query not in entry.message.lower():
            continue
        filtered.append(entry)

    total = len(filtered)
    newest_first = list(reversed(filtered))[:limit]
    return ok(
        SystemLogsOut(
            entries=[
                LogEntryOut(
                    time=entry.time,
                    level=entry.level,
                    source=entry.source,
                    message=entry.message,
                    module=entry.module,
                    line=entry.line,
                )
                for entry in newest_first
            ],
            total=total,
        )
    )


@router.get("/logs/download")
async def download_system_logs(
    request: Request,
    _user: User = Depends(get_current_user),
) -> FileResponse:
    """Download the current runtime log file."""
    path = get_log_file(request.app.state.paths)
    if not path.is_file():
        raise MoriError(translate("common.not_found", get_locale(request)), status_code=404)
    return FileResponse(
        path,
        media_type="text/plain",
        filename="moribot.log",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/backup/export")
async def export_backup(
    request: Request,
    _user: User = Depends(get_current_user),
) -> FileResponse:
    """Download a portable archive of every runtime data file except logs."""
    paths = request.app.state.paths
    temp_dir = Path(paths.data_dir) / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix="moribot-export-", suffix=".zip", dir=temp_dir)
    os.close(descriptor)
    temp_path = Path(raw_path)

    try:
        service = BackupService(paths)
        await service.export_to(temp_path, locale=get_locale(request))
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return FileResponse(
        temp_path,
        media_type="application/zip",
        filename=default_backup_filename(),
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(temp_path.unlink, missing_ok=True),
    )
