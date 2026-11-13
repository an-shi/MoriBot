"""Character card management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from moribot.core.db import User
from moribot.core.i18n import translate

from ..deps import get_character_service, get_current_user, get_locale
from ..responses import ApiResponse, ok
from ..schemas import (
    CharacterAvatarOut,
    CharacterAvatarUploadRequest,
    CharacterCreateRequest,
    CharacterOut,
    CharacterUpdateRequest,
)
from ..services.character_service import CharacterService

router = APIRouter(prefix="/characters", tags=["characters"])


@router.get("", response_model=ApiResponse[list[CharacterOut]])
async def list_characters(
    _user: User = Depends(get_current_user),
    service: CharacterService = Depends(get_character_service),
) -> dict:
    """List every character card."""
    return ok(await service.list_characters())


@router.post("/avatar", response_model=ApiResponse[CharacterAvatarOut])
async def upload_avatar(
    payload: CharacterAvatarUploadRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    service: CharacterService = Depends(get_character_service),
) -> dict:
    """Persist a base64 image and return its public URL."""
    url = await service.save_avatar(payload.data_url, locale=get_locale(request))
    return ok(CharacterAvatarOut(url=url))


@router.post("", response_model=ApiResponse[CharacterOut])
async def create_character(
    payload: CharacterCreateRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    service: CharacterService = Depends(get_character_service),
) -> dict:
    """Create a character card."""
    locale = get_locale(request)
    character = await service.create_character(payload, locale=locale)
    return ok(character, message=translate("character.created", locale))


@router.get("/{character_id}", response_model=ApiResponse[CharacterOut])
async def get_character(
    character_id: int,
    request: Request,
    _user: User = Depends(get_current_user),
    service: CharacterService = Depends(get_character_service),
) -> dict:
    """Return one character card."""
    return ok(await service.get_character(character_id, locale=get_locale(request)))


@router.patch("/{character_id}", response_model=ApiResponse[CharacterOut])
async def update_character(
    character_id: int,
    payload: CharacterUpdateRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    service: CharacterService = Depends(get_character_service),
) -> dict:
    """Update a character card."""
    locale = get_locale(request)
    character = await service.update_character(character_id, payload, locale=locale)
    return ok(character, message=translate("character.updated", locale))


@router.delete("/{character_id}", response_model=ApiResponse[dict])
async def delete_character(
    character_id: int,
    request: Request,
    _user: User = Depends(get_current_user),
    service: CharacterService = Depends(get_character_service),
) -> dict:
    """Delete a character card and its local avatar."""
    locale = get_locale(request)
    await service.delete_character(character_id, locale=locale)
    return ok({}, message=translate("character.deleted", locale))
