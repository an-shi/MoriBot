"""Authentication endpoints."""

from __future__ import annotations

import asyncio
import math

from fastapi import APIRouter, Depends, Request

from moribot.core.db import User
from moribot.core.errors import MoriError
from moribot.core.i18n import translate

from ..deps import get_auth_service, get_current_user, get_locale, get_login_limiter
from ..rate_limit import LoginRateLimiter
from ..responses import ApiResponse, ok
from ..schemas import ChangePasswordRequest, LoginRequest, TokenData, UserOut
from ..services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/login", response_model=ApiResponse[TokenData])
async def login(
    payload: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    limiter: LoginRateLimiter = Depends(get_login_limiter),
) -> dict:
    """Exchange username and password for an access token."""
    locale = get_locale(request)
    key = _client_key(request)
    retry_after = await limiter.retry_after(key)
    if retry_after is not None:
        seconds = max(1, math.ceil(retry_after))
        raise MoriError(
            translate("auth.rate_limited", locale, seconds=seconds),
            status_code=429,
            data={"retry_after": seconds},
        )

    try:
        token_data = await service.login(payload.username, payload.password, locale)
    except MoriError:
        await limiter.register_failure(key)
        # Constant-ish delay makes automated guessing less profitable without
        # penalizing a successful login.
        await asyncio.sleep(0.35)
        raise

    await limiter.reset(key)
    return ok(token_data, message=translate("auth.login_success", locale))


@router.get("/me", response_model=ApiResponse[UserOut])
async def me(user: User = Depends(get_current_user)) -> dict:
    """Return the currently authenticated account."""
    return ok(UserOut.model_validate(user))


@router.post("/logout", response_model=ApiResponse[dict])
async def logout(
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict:
    """Client-side logout acknowledgement.

    Access tokens are stateless; the client discards the token. A server-side
    revocation list can be added later without changing this contract.
    """
    return ok({}, message=translate("auth.logout_success", get_locale(request)))


@router.post("/change-password", response_model=ApiResponse[TokenData])
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """Change the current password and return a refreshed token."""
    locale = get_locale(request)
    token_data = await service.change_password(
        user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        confirm_password=payload.confirm_password,
        locale=locale,
    )
    return ok(token_data, message=translate("auth.password_updated", locale))
