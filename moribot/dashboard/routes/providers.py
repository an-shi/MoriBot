"""Model provider configuration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from moribot.core.db import User
from moribot.core.i18n import translate

from ..deps import get_current_user, get_locale, get_provider_service
from ..responses import ApiResponse, ok
from ..schemas import (
    ProviderCatalogOut,
    ProviderCreateRequest,
    ProviderModelsOut,
    ProviderModelsRequest,
    ProviderOut,
    ProviderTestResult,
    ProviderUpdateRequest,
)
from ..services.provider_service import ProviderConfigService

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/catalog", response_model=ApiResponse[ProviderCatalogOut])
async def provider_catalog(
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Return supported adapter types and vendor presets for the UI."""
    return ok(service.catalog())


@router.post("/models", response_model=ApiResponse[ProviderModelsOut])
async def provider_models(
    payload: ProviderModelsRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Fetch the real model list and capabilities from the vendor."""
    return ok(await service.list_models(payload, locale=get_locale(request)))


@router.get("", response_model=ApiResponse[list[ProviderOut]])
async def list_providers(
    category: str | None = Query(default=None),
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """List configured chat, speech and image providers."""
    return ok(await service.list_providers(category))


@router.post("", response_model=ApiResponse[ProviderOut])
async def create_provider(
    payload: ProviderCreateRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Create a model provider for one of the three roles."""
    locale = get_locale(request)
    provider = await service.create_provider(payload, locale=locale)
    return ok(provider, message=translate("provider.created", locale))


@router.get("/{provider_id}", response_model=ApiResponse[ProviderOut])
async def get_provider(
    provider_id: int,
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Return one model provider."""
    return ok(await service.get_provider(provider_id))


@router.patch("/{provider_id}", response_model=ApiResponse[ProviderOut])
async def update_provider(
    provider_id: int,
    payload: ProviderUpdateRequest,
    request: Request,
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Update a model provider; an empty API key preserves the stored key."""
    locale = get_locale(request)
    provider = await service.update_provider(provider_id, payload, locale=locale)
    return ok(provider, message=translate("provider.updated", locale))


@router.delete("/{provider_id}", response_model=ApiResponse[dict])
async def delete_provider(
    provider_id: int,
    request: Request,
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Delete a model provider."""
    locale = get_locale(request)
    await service.delete_provider(provider_id, locale=locale)
    return ok({}, message=translate("provider.deleted", locale))


@router.post("/{provider_id}/default", response_model=ApiResponse[ProviderOut])
async def set_default_provider(
    provider_id: int,
    request: Request,
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Set a provider as the default for its category."""
    locale = get_locale(request)
    provider = await service.set_default(provider_id, locale=locale)
    return ok(provider, message=translate("provider.default_set", locale))


@router.post("/{provider_id}/test", response_model=ApiResponse[ProviderTestResult])
async def test_provider(
    provider_id: int,
    request: Request,
    _user: User = Depends(get_current_user),
    service: ProviderConfigService = Depends(get_provider_service),
) -> dict:
    """Perform a small real request against the configured model endpoint."""
    return ok(await service.test_provider(provider_id, locale=get_locale(request)))
