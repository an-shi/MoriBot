"""MoriMobile pairing, device management and the secure WebSocket gateway."""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketState

from moribot import __version__
from moribot.core.db import User
from moribot.core.errors import MoriError
from moribot.core.event import EventType, MoriEvent
from moribot.core.i18n import parse_accept_language, translate
from moribot.core.platform.mobile_adapter import MobileConnection

from ..deps import (
    MobileAuthContext,
    get_current_user,
    get_locale,
    get_mobile_auth_context,
    get_mobile_chat_service,
    get_mobile_limiter,
    get_mobile_service,
)
from ..rate_limit import LoginRateLimiter
from ..responses import ApiResponse, ok
from ..schemas import (
    MobileCharacterOut,
    MobileChatOut,
    MobileChatRequest,
    MobileDeviceOut,
    MobilePairOut,
    MobilePairRequest,
    MobileSelfOut,
    MobileSendRequest,
    PairingCodeOut,
    UserOut,
)
from ..services.mobile_chat_service import MobileChatService
from ..services.mobile_service import MobileService

router = APIRouter(prefix="/mobile", tags=["mobile"])

PROTOCOL_VERSION = 1
MAX_INBOUND_BYTES = 64 * 1024
MAX_TEXT_CHARS = 8000
HEARTBEAT_SECONDS = 25
RECEIVE_TIMEOUT_SECONDS = 75


def _client_key(request: Request) -> str:
    if request.client is not None and request.client.host:
        return f"mobile-pair:{request.client.host}"
    return "mobile-pair:unknown"


def _device_token(websocket: WebSocket) -> str:
    authorization = websocket.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return websocket.headers.get("x-mori-device-token", "").strip()


def _origin_allowed(websocket: WebSocket) -> bool:
    """Reject browser origins that are not explicitly trusted.

    Native mobile clients normally send no Origin header, so the device token
    remains the primary authentication mechanism.
    """
    origin = websocket.headers.get("origin", "").strip()
    if not origin:
        return True

    config = websocket.app.state.config
    parsed = urlparse(origin)
    host = websocket.headers.get("host", "")
    if parsed.netloc and parsed.netloc == host:
        return True

    allowed = {str(value).rstrip("/") for value in config.cors_origins}
    public_url = str(config.get("dashboard.public_url", "")).strip().rstrip("/")
    if public_url:
        allowed.add(public_url)
    return origin.rstrip("/") in allowed


@router.post("/pairing-code", response_model=ApiResponse[PairingCodeOut])
async def create_pairing_code(
    request: Request,
    user: User = Depends(get_current_user),
    service: MobileService = Depends(get_mobile_service),
) -> dict:
    """Create a one-time code that the mobile app can redeem."""
    locale = get_locale(request)
    pairing = await service.create_pairing_code(
        user,
        request_base_url=str(request.base_url),
        locale=locale,
    )
    return ok(pairing, message=translate("mobile.pairing_code_created", locale))


@router.get("/devices", response_model=ApiResponse[list[MobileDeviceOut]])
async def list_devices(
    user: User = Depends(get_current_user),
    service: MobileService = Depends(get_mobile_service),
) -> dict:
    """List devices paired by the signed-in account."""
    return ok(await service.list_devices(user))


@router.post("/devices/{device_id}/revoke", response_model=ApiResponse[dict])
async def revoke_device(
    device_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    service: MobileService = Depends(get_mobile_service),
) -> dict:
    """Revoke a device token and immediately disconnect its WebSocket."""
    locale = get_locale(request)
    await service.revoke_device(user, device_id, locale=locale)
    return ok({}, message=translate("mobile.device_revoked", locale))


@router.post("/devices/{device_id}/message", response_model=ApiResponse[dict])
async def send_device_message(
    device_id: str,
    payload: MobileSendRequest,
    request: Request,
    user: User = Depends(get_current_user),
    service: MobileService = Depends(get_mobile_service),
) -> dict:
    """Send a text message from the dashboard to a connected device."""
    locale = get_locale(request)
    await service.send_to_device(user, device_id, payload.text, locale=locale)
    return ok({}, message=translate("mobile.message_sent", locale))


@router.post("/pair", response_model=ApiResponse[MobilePairOut])
async def pair_device(
    payload: MobilePairRequest,
    request: Request,
    service: MobileService = Depends(get_mobile_service),
    limiter: LoginRateLimiter = Depends(get_mobile_limiter),
) -> dict:
    """Redeem a pairing code for a long-lived device token.

    This endpoint is intentionally unauthenticated but requires a valid
    single-use code. Failures are rate limited per client address.
    """
    locale = get_locale(request)
    key = _client_key(request)
    retry_after = await limiter.retry_after(key)
    if retry_after is not None:
        seconds = max(1, math.ceil(retry_after))
        raise MoriError(
            translate("mobile.pairing_rate_limited", locale, seconds=seconds),
            status_code=429,
            data={"retry_after": seconds},
        )

    try:
        result = await service.pair_device(
            code=payload.code,
            device_name=payload.device_name,
            locale=locale,
        )
    except MoriError:
        await limiter.register_failure(key)
        await asyncio.sleep(0.25)
        raise

    await limiter.reset(key)
    return ok(result, message=translate("mobile.device_paired", locale))


@router.get("/app/me", response_model=ApiResponse[MobileSelfOut])
async def mobile_app_me(
    auth: MobileAuthContext = Depends(get_mobile_auth_context),
    service: MobileService = Depends(get_mobile_service),
) -> dict:
    """Authenticate a MoriMobile HTTP business call.

    The phone uses this endpoint with its device token to verify that the token
    is still valid and to obtain the owner account and current device record.
    """
    return ok(
        MobileSelfOut(
            device=service.device_out(auth.device),
            user=UserOut.model_validate(auth.user),
            server_version=__version__,
            protocol=PROTOCOL_VERSION,
        )
    )


@router.get("/app/characters", response_model=ApiResponse[list[MobileCharacterOut]])
async def mobile_characters(
    _auth: MobileAuthContext = Depends(get_mobile_auth_context),
    service: MobileChatService = Depends(get_mobile_chat_service),
) -> dict:
    """List enabled character cards that the phone can start a chat with."""
    return ok(await service.list_characters())


@router.post("/app/chat", response_model=ApiResponse[MobileChatOut])
async def mobile_chat(
    payload: MobileChatRequest,
    request: Request,
    auth: MobileAuthContext = Depends(get_mobile_auth_context),
    service: MobileChatService = Depends(get_mobile_chat_service),
) -> dict:
    """Generate one assistant reply for a character and a conversation snapshot.

    MoriBot does not persist conversations. The phone sends its local history
    and replaces it after receiving the reply.
    """
    result = await service.generate(
        payload,
        device=auth.device,
        locale=get_locale(request),
    )
    return ok(result)


@router.websocket("/ws")
async def mobile_websocket(websocket: WebSocket) -> None:
    """Persistent, authenticated message channel for MoriMobile.

    Authentication uses ``Authorization: Bearer <device_token>`` or
    ``X-Mori-Device-Token: <device_token>``. The token is only ever sent from
    the phone to the server; the server stores a SHA-256 hash.
    """
    token = _device_token(websocket)
    if not token:
        await websocket.close(code=1008)
        return
    if not _origin_allowed(websocket):
        await websocket.close(code=1008)
        return

    app = websocket.app
    service: MobileService = app.state.mobile_service
    config = app.state.config
    if bool(config.get("dashboard.force_https", False)) and websocket.url.scheme not in {
        "https",
        "wss",
    }:
        await websocket.close(code=1008)
        return
    device = await service.authenticate_device(token)
    if device is None:
        await websocket.close(code=1008)
        return

    locale = (
        parse_accept_language(websocket.headers.get("accept-language"))
        or service.config.locale
    )

    await websocket.accept()
    await service.touch_device(device.id)

    send_lock = asyncio.Lock()
    adapter = service.adapter

    async def send_json(payload: dict[str, Any]) -> None:
        async with send_lock:
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            await websocket.send_json(payload)

    async def close_connection(code: int, reason: str) -> None:
        async with send_lock:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=code, reason=reason)

    connection: MobileConnection = await adapter.register_connection(
        device_id=device.id,
        device_name=device.name,
        send_payload=send_json,
        close=close_connection,
    )

    async def heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                await send_json({"type": "ping", "timestamp": time.time()})
        except (asyncio.CancelledError, WebSocketDisconnect):
            raise
        except Exception:
            return

    heartbeat_task = asyncio.create_task(heartbeat(), name=f"mobile-heartbeat-{device.id}")

    try:
        await send_json(
            {
                "type": "hello",
                "protocol": PROTOCOL_VERSION,
                "server": "MoriBot",
                "server_version": __version__,
                "device_id": device.id,
                "device_name": device.name,
                "heartbeat_seconds": HEARTBEAT_SECONDS,
                "max_text_chars": MAX_TEXT_CHARS,
            }
        )

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=RECEIVE_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                await send_json({"type": "error", "message": "Heartbeat timeout"})
                break

            if len(raw.encode("utf-8")) > MAX_INBOUND_BYTES:
                await send_json(
                    {
                        "type": "error",
                        "code": "message_too_large",
                        "message": translate("mobile.message_too_large", locale),
                    }
                )
                break

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await send_json(
                    {
                        "type": "error",
                        "code": "invalid_message",
                        "message": translate("mobile.invalid_message", locale),
                    }
                )
                continue

            if not isinstance(data, dict):
                await send_json(
                    {
                        "type": "error",
                        "code": "invalid_message",
                        "message": translate("mobile.invalid_message", locale),
                    }
                )
                continue

            message_type = str(data.get("type", ""))
            if message_type == "message":
                text = data.get("text")
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS:
                    await send_json(
                        {
                            "type": "error",
                            "code": "invalid_message",
                            "message": translate("mobile.invalid_message", locale),
                        }
                    )
                    continue

                client_message_id = str(data.get("client_message_id", ""))
                event = MoriEvent(
                    type=EventType.MESSAGE,
                    platform_id=adapter.adapter_id,
                    platform_name="MoriMobile",
                    session_id=device.id,
                    sender_id=device.id,
                    sender_name=device.name,
                    message=text.strip(),
                    raw=data,
                    extras={
                        "mobile_device_id": device.id,
                        "client_message_id": client_message_id,
                    },
                )
                await app.state.core.event_bus.put(event)
                await send_json(
                    {
                        "type": "ack",
                        "client_message_id": client_message_id,
                        "timestamp": time.time(),
                    }
                )
            elif message_type == "ping":
                await send_json({"type": "pong", "timestamp": time.time()})
            elif message_type == "pong":
                continue
            else:
                await send_json(
                    {
                        "type": "error",
                        "code": "unsupported_message",
                        "message": translate("mobile.invalid_message", locale),
                    }
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("MoriMobile WebSocket error for device {}.", device.id)
        try:
            await send_json(
                {
                    "type": "error",
                    "code": "server_error",
                    "message": translate("common.server_error", locale),
                }
            )
        except Exception:
            pass
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        adapter.unregister_connection(device.id, connection)
