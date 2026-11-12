"""Pairing and lifecycle management for MoriMobile devices."""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from datetime import timedelta
from urllib.parse import quote

from moribot.core.config import ConfigManager
from moribot.core.db import BaseDatabase, MobileDevice, User, utcnow
from moribot.core.errors import MoriError, NotFoundError
from moribot.core.i18n import DEFAULT_LOCALE, translate
from moribot.core.platform.mobile_adapter import MobilePlatformAdapter

from ..schemas import MobileDeviceOut, MobilePairOut, PairingCodeOut

PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8
DEVICE_TOKEN_PREFIX = "mm_"


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_pairing_code(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def _display_pairing_code(raw_code: str) -> str:
    midpoint = len(raw_code) // 2
    return f"{raw_code[:midpoint]}-{raw_code[midpoint:]}"


class MobileService:
    """Create pairing codes, enroll devices and authenticate WebSockets."""

    def __init__(
        self,
        db: BaseDatabase,
        config: ConfigManager,
        adapter: MobilePlatformAdapter,
    ) -> None:
        self.db = db
        self.config = config
        self.adapter = adapter

    def server_url(self, request_base_url: str) -> str:
        """Return the public origin used inside a pairing URI."""
        configured = str(self.config.get("dashboard.public_url", "")).strip()
        if configured:
            return configured.rstrip("/")
        return request_base_url.rstrip("/")

    async def create_pairing_code(
        self,
        user: User,
        *,
        request_base_url: str,
        locale: str = DEFAULT_LOCALE,
    ) -> PairingCodeOut:
        """Generate a single-use, short-lived pairing code."""
        if user.id is None:
            raise MoriError(translate("auth.account_data_error", locale), status_code=500)

        try:
            ttl_minutes = int(self.config.get("mobile.pairing_code_ttl_minutes", 10))
        except (TypeError, ValueError):
            ttl_minutes = 10
        ttl_minutes = max(1, min(ttl_minutes, 60))
        expires_at = utcnow() + timedelta(minutes=ttl_minutes)

        raw_code = "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))
        await self.db.create_mobile_pairing_code(
            user_id=user.id,
            code_hash=_hash_secret(raw_code),
            expires_at=expires_at,
        )

        display_code = _display_pairing_code(raw_code)
        server = self.server_url(request_base_url)
        pairing_uri = (
            f"morimobile://pair?server={quote(server, safe='')}&code={quote(display_code, safe='')}"
        )
        return PairingCodeOut(
            code=display_code,
            expires_at=expires_at,
            pairing_uri=pairing_uri,
            server_url=server,
        )

    async def pair_device(
        self,
        *,
        code: str,
        device_name: str,
        locale: str = DEFAULT_LOCALE,
    ) -> MobilePairOut:
        """Consume a pairing code and issue a long-lived device token."""
        name = " ".join(device_name.split())
        if not name or len(name) > 64:
            raise MoriError(translate("mobile.device_name_required", locale))

        normalized_code = _normalize_pairing_code(code)
        if len(normalized_code) != PAIRING_CODE_LENGTH:
            raise MoriError(translate("mobile.invalid_pairing_code", locale))

        pairing_code = await self.db.consume_mobile_pairing_code(
            _hash_secret(normalized_code),
            utcnow(),
        )
        if pairing_code is None:
            raise MoriError(translate("mobile.invalid_pairing_code", locale))

        try:
            max_devices = int(self.config.get("mobile.max_devices", 10))
        except (TypeError, ValueError):
            max_devices = 10
        max_devices = max(1, min(max_devices, 50))
        if await self.db.count_mobile_devices(pairing_code.user_id) >= max_devices:
            raise MoriError(translate("mobile.too_many_devices", locale))

        token = f"{DEVICE_TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
        device = await self.db.create_mobile_device(
            user_id=pairing_code.user_id,
            name=name,
            token_hash=_hash_secret(token),
        )
        return MobilePairOut(
            device_token=token,
            device=self._device_out(device),
        )

    async def authenticate_device(self, token: str) -> MobileDevice | None:
        """Resolve a device token to an active device."""
        if not token:
            return None
        device = await self.db.get_mobile_device_by_token_hash(_hash_secret(token))
        if device is None or not device.is_active or device.revoked_at is not None:
            return None
        return device

    async def touch_device(self, device_id: str) -> None:
        await self.db.touch_mobile_device(device_id)

    async def list_devices(self, user: User) -> list[MobileDeviceOut]:
        if user.id is None:
            return []
        devices = await self.db.list_mobile_devices(user.id)
        return [self._device_out(device) for device in devices]

    async def revoke_device(
        self,
        user: User,
        device_id: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        if user.id is None:
            raise NotFoundError(translate("mobile.device_not_found", locale))
        revoked = await self.db.revoke_mobile_device(user.id, device_id)
        if not revoked:
            raise NotFoundError(translate("mobile.device_not_found", locale))
        await self.adapter.disconnect_device(
            device_id,
            reason=translate("mobile.revoked_message", locale),
        )

    async def send_to_device(
        self,
        user: User,
        device_id: str,
        text: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        """Send a text message from the dashboard to a paired device."""
        if user.id is None:
            raise NotFoundError(translate("mobile.device_not_found", locale))

        device = await self.db.get_mobile_device(device_id)
        if (
            device is None
            or device.user_id != user.id
            or not device.is_active
            or device.revoked_at is not None
        ):
            raise NotFoundError(translate("mobile.device_not_found", locale))

        delivered = await self.adapter.send_payload(
            device_id,
            {
                "type": "message",
                "id": str(uuid.uuid4()),
                "text": text,
                "source": "dashboard",
                "timestamp": time.time(),
            },
        )
        if not delivered:
            raise MoriError(translate("mobile.device_offline", locale), status_code=409)

    def _device_out(self, device: MobileDevice) -> MobileDeviceOut:
        return MobileDeviceOut(
            id=device.id,
            name=device.name,
            online=self.adapter.is_online(device.id),
            created_at=device.created_at,
            last_seen_at=device.last_seen_at,
            revoked_at=device.revoked_at,
        )
