"""CRUD and avatar storage for character cards."""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path

from moribot.core.errors import ConflictError, MoriError, NotFoundError
from moribot.core.i18n import DEFAULT_LOCALE, translate
from moribot.core.lifecycle import CoreLifecycle

from ..schemas import (
    CharacterCreateRequest,
    CharacterOut,
    CharacterUpdateRequest,
)

_AVATAR_RE = re.compile(
    r"^data:(image/(png|jpeg|webp|gif));base64,([A-Za-z0-9+/=\r\n]+)$",
)
_AVATAR_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_AVATAR_BYTES = 2 * 1024 * 1024


class CharacterService:
    """Business layer for role cards and their model overrides."""

    def __init__(self, core: CoreLifecycle) -> None:
        self.core = core
        self.db = core.db

    async def list_characters(self) -> list[CharacterOut]:
        return [self._to_out(record) for record in await self.db.list_character_cards()]

    async def get_character(self, character_id: int, *, locale: str) -> CharacterOut:
        record = await self.db.get_character_card(character_id)
        if record is None:
            raise NotFoundError(translate("character.not_found", locale))
        return self._to_out(record)

    async def create_character(
        self,
        payload: CharacterCreateRequest,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> CharacterOut:
        name = self._normalize_name(payload.name, locale)
        existing = await self.db.get_character_card_by_name(name)
        if existing is not None:
            raise ConflictError(translate("character.name_exists", locale))
        values = payload.model_dump()
        values["name"] = name
        for category, key in (
            ("chat", "chat_provider_id"),
            ("speech", "speech_provider_id"),
            ("image", "image_provider_id"),
        ):
            await self._validate_provider(values.get(key), category, locale)
        record = await self.db.create_character_card(values)
        return self._to_out(record)

    async def update_character(
        self,
        character_id: int,
        payload: CharacterUpdateRequest,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> CharacterOut:
        current = await self.db.get_character_card(character_id)
        if current is None:
            raise NotFoundError(translate("character.not_found", locale))

        values = payload.model_dump(exclude_unset=True)
        if "name" in values:
            if values["name"] is None:
                raise MoriError(translate("character.invalid_name", locale))
            name = self._normalize_name(values["name"], locale)
            existing = await self.db.get_character_card_by_name(name)
            if existing is not None and existing.id != character_id:
                raise ConflictError(translate("character.name_exists", locale))
            values["name"] = name

        for key in ("avatar", "description", "persona", "greeting"):
            if key in values and values[key] is None:
                values[key] = ""
        if values.get("enabled") is None:
            values.pop("enabled", None)

        for category, key in (
            ("chat", "chat_provider_id"),
            ("speech", "speech_provider_id"),
            ("image", "image_provider_id"),
        ):
            if key in values:
                await self._validate_provider(values[key], category, locale)

        record = await self.db.update_character_card(character_id, values)
        if record is None:
            raise NotFoundError(translate("character.not_found", locale))
        if "avatar" in values and values["avatar"] != current.avatar:
            self._delete_local_avatar(current.avatar)
        return self._to_out(record)

    async def delete_character(
        self,
        character_id: int,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        record = await self.db.get_character_card(character_id)
        if record is None:
            raise NotFoundError(translate("character.not_found", locale))
        await self.db.delete_character_card(character_id)
        self._delete_local_avatar(record.avatar)

    async def save_avatar(
        self,
        data_url: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> str:
        match = _AVATAR_RE.fullmatch(data_url.strip())
        if match is None:
            raise MoriError(translate("character.avatar_invalid", locale))
        content_type = match.group(1).lower()
        encoded = match.group(3)
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise MoriError(translate("character.avatar_invalid", locale)) from exc
        if not content:
            raise MoriError(translate("character.avatar_invalid", locale))
        if len(content) > _MAX_AVATAR_BYTES:
            raise MoriError(translate("character.avatar_too_large", locale))

        filename = f"{uuid.uuid4().hex}{_AVATAR_EXTENSIONS[content_type]}"
        target = self.core.paths.avatar_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return f"/avatars/{filename}"

    @staticmethod
    def _normalize_name(value: str, locale: str) -> str:
        name = value.strip()
        if not name:
            raise MoriError(translate("character.invalid_name", locale))
        return name

    async def _validate_provider(
        self,
        provider_id: int | None,
        category: str,
        locale: str,
    ) -> None:
        if provider_id is None:
            return
        provider = await self.db.get_model_provider(provider_id)
        if provider is None or provider.category != category:
            raise MoriError(
                translate("character.invalid_provider", locale, category=category)
            )

    def _delete_local_avatar(self, avatar: str) -> None:
        if not avatar.startswith("/avatars/"):
            return
        filename = Path(avatar).name
        if not filename:
            return
        target = self.core.paths.avatar_dir / filename
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _to_out(record) -> CharacterOut:
        return CharacterOut(
            id=record.id or 0,
            name=record.name,
            avatar=record.avatar,
            description=record.description,
            persona=record.persona,
            greeting=record.greeting,
            chat_provider_id=record.chat_provider_id,
            speech_provider_id=record.speech_provider_id,
            image_provider_id=record.image_provider_id,
            enabled=record.enabled,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
