"""Character diary management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from moribot.core.db import User
from moribot.core.i18n import translate

from ..deps import get_current_user, get_diary_service, get_locale
from ..responses import ApiResponse, ok
from ..schemas import DiaryGenerateRequest, DiaryOut
from ..services.diary_service import DiaryService

router = APIRouter(prefix="/diaries", tags=["diaries"])


@router.get("", response_model=ApiResponse[list[DiaryOut]])
async def list_diaries(
    character_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service),
) -> dict:
    """List diary entries, newest first."""
    return ok(
        await service.list_diaries(
            character_id,
            limit=limit,
            offset=offset,
        )
    )


@router.post("/generate", response_model=ApiResponse[DiaryOut])
async def generate_diary(
    payload: DiaryGenerateRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service),
) -> dict:
    """Generate or regenerate one diary entry."""
    locale = get_locale(request)
    target_date = service.parse_date(payload.date, locale=locale)
    diary = await service.generate(
        payload.character_id,
        target_date=target_date,
        force=True,
        locale=locale,
    )
    return ok(diary, message=translate("diary.generated", locale))


@router.delete("/{diary_id}", response_model=ApiResponse[dict])
async def delete_diary(
    diary_id: int,
    request: Request,
    _user: User = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service),
) -> dict:
    """Delete a diary entry."""
    locale = get_locale(request)
    await service.delete(diary_id, locale=locale)
    return ok({}, message=translate("diary.deleted", locale))
