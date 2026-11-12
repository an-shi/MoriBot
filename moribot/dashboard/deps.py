"""FastAPI dependencies shared by dashboard routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from moribot.core.config import ConfigManager
from moribot.core.db import MobileDevice, User
from moribot.core.errors import AuthenticationError
from moribot.core.i18n import (
    DEFAULT_LOCALE,
    normalize_locale,
    parse_accept_language,
    translate,
)
from moribot.core.lifecycle import CoreLifecycle
from moribot.core.security import decode_access_token

from .rate_limit import LoginRateLimiter
from .services.auth_service import AuthService
from .services.mobile_service import MobileService
from .services.provider_service import ProviderConfigService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class MobileAuthContext:
    """Authenticated MoriMobile device and its owner account."""

    device: MobileDevice
    user: User


def get_core(request: Request) -> CoreLifecycle:
    return cast(CoreLifecycle, request.app.state.core)


def get_config(request: Request) -> ConfigManager:
    return cast(ConfigManager, request.app.state.config)


def get_auth_service(request: Request) -> AuthService:
    return cast(AuthService, request.app.state.auth_service)


def get_login_limiter(request: Request) -> LoginRateLimiter:
    return cast(LoginRateLimiter, request.app.state.login_limiter)


def get_mobile_limiter(request: Request) -> LoginRateLimiter:
    return cast(LoginRateLimiter, request.app.state.mobile_limiter)


def get_mobile_service(request: Request) -> MobileService:
    return cast(MobileService, request.app.state.mobile_service)


def get_provider_service(request: Request) -> ProviderConfigService:
    return cast(ProviderConfigService, request.app.state.provider_service)


async def get_mobile_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> MobileAuthContext:
    """Authenticate a MoriMobile HTTP request with a device token.

    This is deliberately separate from dashboard JWT authentication. Future
    business APIs for the phone should depend on this context, while admin
    operations continue to use ``get_current_user``.
    """
    locale = get_locale(request)
    token = credentials.credentials if credentials is not None else ""
    if not token:
        token = request.headers.get("x-mori-device-token", "").strip()
    if not token:
        raise AuthenticationError(translate("mobile.invalid_device_token", locale))

    service = get_mobile_service(request)
    device = await service.authenticate_device(token)
    if device is None:
        raise AuthenticationError(translate("mobile.invalid_device_token", locale))

    user = await get_core(request).db.get_user_by_id(device.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError(translate("auth.account_unavailable", locale))

    request.state.mobile_device = device
    return MobileAuthContext(device=device, user=user)


def get_locale(request: Request) -> str:
    """Resolve the request language.

    Precedence: explicit ``X-Mori-Locale`` header, ``Accept-Language``,
    configured default locale.
    """
    explicit = request.headers.get("x-mori-locale")
    if explicit:
        return normalize_locale(explicit)

    parsed = parse_accept_language(request.headers.get("accept-language"))
    if parsed:
        return parsed

    config = getattr(request.app.state, "config", None)
    if config is not None and hasattr(config, "locale"):
        return config.locale
    return DEFAULT_LOCALE


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """Resolve and validate the bearer token for a request.

    Args:
        request: Current request, used for cookie fallback and app state.
        credentials: Parsed ``Authorization: Bearer`` header when present.

    Returns:
        The authenticated, active account.

    Raises:
        AuthenticationError: When the token is missing, invalid or revoked.
    """
    locale = get_locale(request)
    token = credentials.credentials if credentials is not None else ""
    if not token:
        token = request.cookies.get("moribot_token", "")

    if not token:
        raise AuthenticationError(translate("common.unauthorized", locale))

    core = get_core(request)
    config = get_config(request)

    try:
        payload = decode_access_token(secret=config.jwt_secret, token=token)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(translate("auth.token_expired", locale)) from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError(translate("auth.token_invalid", locale)) from exc

    try:
        user_id = int(str(payload.get("sub", "")))
    except (TypeError, ValueError) as exc:
        raise AuthenticationError(translate("auth.token_invalid", locale)) from exc

    user = await core.db.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError(translate("auth.account_unavailable", locale))
    if int(payload.get("ver", 0)) != user.token_version:
        raise AuthenticationError(translate("auth.token_revoked", locale))

    request.state.user = user
    return user
