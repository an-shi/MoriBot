"""Public and authenticated system information endpoints."""

from __future__ import annotations

import os
import platform as platform_module
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from moribot import __version__
from moribot.core.backup import BackupService, default_backup_filename
from moribot.core.db import User

from ..deps import get_config, get_core, get_current_user, get_locale
from ..responses import ApiResponse, ok
from ..schemas import HealthInfo, PublicInfo, SystemInfo

router = APIRouter(prefix="/system", tags=["system"])


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
