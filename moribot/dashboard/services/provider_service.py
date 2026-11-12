"""CRUD, validation and connectivity tests for model providers."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from moribot.core.db import ModelProvider
from moribot.core.errors import ConflictError, MoriError, NotFoundError
from moribot.core.i18n import DEFAULT_LOCALE, translate
from moribot.core.lifecycle import CoreLifecycle
from moribot.core.provider import (
    ChatMessage,
    ProviderCategory,
    ProviderError,
    SpeechProvider,
    ImageProvider,
)
from moribot.core.provider.manager import ProviderManager

from ..schemas import ProviderCreateRequest, ProviderOut, ProviderTestResult, ProviderUpdateRequest

_VALID_CATEGORIES = {category.value for category in ProviderCategory}
_VALID_SPEECH_FORMATS = {"mp3", "opus", "aac", "flac", "wav", "pcm"}


class ProviderConfigService:
    """Business layer for the three model roles."""

    def __init__(self, core: CoreLifecycle) -> None:
        self.core = core
        self.db = core.db
        self.secret_box = core.secret_box
        self.manager: ProviderManager = core.provider_manager

    async def list_providers(self, category: str | None = None) -> list[ProviderOut]:
        records = await self.db.list_model_providers(category=category)
        return [self._to_out(record) for record in records]

    async def get_provider(self, provider_id: int) -> ProviderOut:
        record = await self.db.get_model_provider(provider_id)
        if record is None:
            raise NotFoundError(translate("provider.not_found", self.core.config.locale))
        return self._to_out(record)

    async def create_provider(
        self,
        payload: ProviderCreateRequest,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> ProviderOut:
        category = self._validate_category(payload.category, locale)
        name = payload.name.strip()
        model = payload.model.strip()
        if not name or not model:
            raise MoriError(translate("provider.invalid_options", locale, detail="name/model"))
        base_url = self._normalize_base_url(payload.base_url, locale)

        existing = await self.db.list_model_providers(category=category)
        if any(record.name.lower() == name.lower() for record in existing):
            raise ConflictError(translate("provider.name_exists", locale))
        if payload.is_default and not payload.enabled:
            raise MoriError(translate("provider.invalid_options", locale, detail="default"))

        options = self._normalize_options(category, payload.options, locale)
        values = {
            "category": category,
            "name": name,
            "provider_type": payload.provider_type,
            "base_url": base_url,
            "api_key_encrypted": self.secret_box.encrypt(payload.api_key.strip()),
            "model": model,
            "options": options,
            "is_default": False,
            "enabled": payload.enabled,
        }
        record = await self.db.create_model_provider(values)
        if record.id is None:
            raise MoriError(translate("provider.created", locale), status_code=500)

        if (payload.is_default or not existing) and payload.enabled:
            record = (
                await self.db.set_default_model_provider(category, record.id)
                or await self.db.get_model_provider(record.id)
            )
        else:
            await self._ensure_default(category)
            record = await self.db.get_model_provider(record.id) or record
        await self.core.reload_providers()
        return self._to_out(record)

    async def update_provider(
        self,
        provider_id: int,
        payload: ProviderUpdateRequest,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> ProviderOut:
        record = await self.db.get_model_provider(provider_id)
        if record is None:
            raise NotFoundError(translate("provider.not_found", locale))

        values: dict = {}
        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                raise MoriError(translate("provider.invalid_options", locale, detail="name"))
            siblings = await self.db.list_model_providers(category=record.category)
            if any(
                sibling.id != provider_id and sibling.name.lower() == name.lower()
                for sibling in siblings
            ):
                raise ConflictError(translate("provider.name_exists", locale))
            values["name"] = name
        if payload.base_url is not None:
            values["base_url"] = self._normalize_base_url(payload.base_url, locale)
        if payload.model is not None:
            model = payload.model.strip()
            if not model:
                raise MoriError(translate("provider.invalid_options", locale, detail="model"))
            values["model"] = model
        if payload.options is not None:
            values["options"] = self._normalize_options(record.category, payload.options, locale)
        if payload.api_key:
            values["api_key_encrypted"] = self.secret_box.encrypt(payload.api_key.strip())
        if payload.enabled is not None:
            values["enabled"] = payload.enabled
        will_enable = payload.enabled if payload.enabled is not None else record.enabled
        if payload.is_default is True and not will_enable:
            raise MoriError(translate("provider.invalid_options", locale, detail="default"))
        if payload.enabled is False and record.is_default and payload.is_default is None:
            values["is_default"] = False

        updated = await self.db.update_model_provider(provider_id, values)
        if updated is None:
            raise NotFoundError(translate("provider.not_found", locale))

        if payload.is_default is True:
            updated = (
                await self.db.set_default_model_provider(record.category, provider_id) or updated
            )
        elif payload.is_default is False:
            updated = await self.db.update_model_provider(provider_id, {"is_default": False}) or updated

        await self._ensure_default(record.category)
        updated = await self.db.get_model_provider(provider_id) or updated
        await self.core.reload_providers()
        return self._to_out(updated)

    async def delete_provider(
        self,
        provider_id: int,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        record = await self.db.get_model_provider(provider_id)
        if record is None:
            raise NotFoundError(translate("provider.not_found", locale))
        category = record.category
        await self.db.delete_model_provider(provider_id)
        await self._ensure_default(category)
        await self.core.reload_providers()

    async def set_default(
        self,
        provider_id: int,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> ProviderOut:
        record = await self.db.get_model_provider(provider_id)
        if record is None:
            raise NotFoundError(translate("provider.not_found", locale))
        updated = await self.db.set_default_model_provider(record.category, provider_id)
        if updated is None:
            raise NotFoundError(translate("provider.not_found", locale))
        await self.core.reload_providers()
        return self._to_out(updated)

    async def test_provider(
        self,
        provider_id: int,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> ProviderTestResult:
        record = await self.db.get_model_provider(provider_id)
        if record is None:
            raise NotFoundError(translate("provider.not_found", locale))

        provider = self.manager.get(str(provider_id))
        if provider is None:
            await self.core.reload_providers()
            provider = self.manager.get(str(provider_id))
        if provider is None:
            result = ProviderTestResult(
                ok=False,
                message=translate("provider.test_unavailable", locale),
            )
            await self.db.record_model_provider_test(provider_id, False, result.message)
            return result

        started = time.monotonic()
        try:
            if provider.category == ProviderCategory.CHAT:
                response = await provider.chat(
                    [ChatMessage(role="user", content="Reply with exactly: pong")],
                    temperature=0,
                    max_tokens=16,
                )
                preview = response.text.strip()[:160]
            elif isinstance(provider, SpeechProvider):
                audio = await provider.synthesize("MoriBot voice test.")
                preview = translate(
                    "provider.speech_preview",
                    locale,
                    bytes=len(audio.audio),
                )
            elif isinstance(provider, ImageProvider):
                images = await provider.generate(
                    "A simple green leaf icon on a white background"
                )
                preview = translate(
                    "provider.image_preview",
                    locale,
                    count=len(images),
                )
            else:
                raise ProviderError("Unsupported provider category")
        except Exception as exc:
            message = translate(
                "provider.test_failed",
                locale,
                detail=str(exc)[:300],
            )
            await self.db.record_model_provider_test(provider_id, False, message)
            return ProviderTestResult(
                ok=False,
                message=message,
                latency_ms=int((time.monotonic() - started) * 1000),
            )

        latency = int((time.monotonic() - started) * 1000)
        message = translate("provider.test_ok", locale, latency_ms=latency)
        await self.db.record_model_provider_test(provider_id, True, message)
        return ProviderTestResult(
            ok=True,
            message=message,
            latency_ms=latency,
            preview=preview,
        )

    @staticmethod
    def _validate_category(category: str, locale: str) -> str:
        if category not in _VALID_CATEGORIES:
            raise MoriError(translate("provider.invalid_options", locale, detail="category"))
        return category

    async def _ensure_default(self, category: str) -> None:
        """Pick an enabled provider if the category has no usable default."""
        current = await self.db.get_default_model_provider(category)
        if current is not None:
            return
        candidates = [
            record
            for record in await self.db.list_model_providers(category=category)
            if record.enabled and record.id is not None
        ]
        if candidates:
            await self.db.set_default_model_provider(category, candidates[0].id)

    @staticmethod
    def _normalize_base_url(value: str, locale: str) -> str:
        base_url = value.strip().rstrip("/")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MoriError(translate("provider.invalid_base_url", locale))
        return base_url

    @staticmethod
    def _normalize_options(category: str, options: dict, locale: str) -> dict:
        result = dict(options or {})

        def number(key: str, kind: type, minimum: float | None = None) -> None:
            if key not in result or result[key] in (None, ""):
                return
            try:
                value = kind(result[key])
            except (TypeError, ValueError) as exc:
                raise MoriError(
                    translate("provider.invalid_options", locale, detail=key)
                ) from exc
            if minimum is not None and value < minimum:
                raise MoriError(translate("provider.invalid_options", locale, detail=key))
            result[key] = value

        if category == ProviderCategory.CHAT:
            number("temperature", float, 0)
            number("max_tokens", int, 1)
            number("max_completion_tokens", int, 1)
            number("top_p", float, 0)
        elif category == ProviderCategory.SPEECH:
            number("speed", float, 0.1)
            response_format = str(result.get("response_format", "mp3")).lower()
            if response_format not in _VALID_SPEECH_FORMATS:
                raise MoriError(
                    translate("provider.invalid_options", locale, detail="response_format")
                )
            result["response_format"] = response_format
        elif category == ProviderCategory.IMAGE:
            number("n", int, 1)
            if int(result.get("n", 1)) > 4:
                raise MoriError(translate("provider.invalid_options", locale, detail="n"))
        return result

    def _to_out(self, record: ModelProvider) -> ProviderOut:
        api_key = ""
        try:
            api_key = self.secret_box.decrypt(record.api_key_encrypted)
        except Exception:
            api_key = ""
        hint = f"••••{api_key[-4:]}" if len(api_key) >= 4 else ""
        return ProviderOut(
            id=record.id or 0,
            category=record.category,
            name=record.name,
            provider_type=record.provider_type,
            base_url=record.base_url,
            model=record.model,
            options=dict(record.options or {}),
            is_default=record.is_default,
            enabled=record.enabled,
            api_key_set=bool(api_key),
            api_key_hint=hint,
            last_test_ok=record.last_test_ok,
            last_test_message=record.last_test_message,
            last_tested_at=record.last_tested_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
