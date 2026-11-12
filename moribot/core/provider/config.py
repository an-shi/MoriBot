"""Convert persisted provider rows into provider instances."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from ..db import ModelProvider
from ..security import SecretBox, SecretBoxError
from .base import Provider, ProviderCategory, ProviderError
from .openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleImageProvider,
    OpenAICompatibleSpeechProvider,
)


@dataclass(frozen=True, slots=True)
class ProviderConfigSpec:
    """Decrypted, transport-ready provider configuration."""

    id: int
    category: str
    name: str
    provider_type: str
    base_url: str
    api_key: str
    model: str
    options: dict[str, Any]
    is_default: bool


def spec_from_record(record: ModelProvider, secret_box: SecretBox) -> ProviderConfigSpec | None:
    """Build a spec, skipping a record whose encrypted key is unreadable."""
    if record.id is None:
        return None
    try:
        api_key = secret_box.decrypt(record.api_key_encrypted)
    except SecretBoxError:
        logger.error("Cannot decrypt the API key for model provider {}.", record.id)
        api_key = ""
    return ProviderConfigSpec(
        id=record.id,
        category=record.category,
        name=record.name,
        provider_type=record.provider_type,
        base_url=record.base_url,
        api_key=api_key,
        model=record.model,
        options=dict(record.options or {}),
        is_default=record.is_default,
    )


def build_provider(spec: ProviderConfigSpec) -> Provider:
    """Instantiate the concrete provider for a spec."""
    config = {
        **spec.options,
        "name": spec.name,
        "base_url": spec.base_url,
        "api_key": spec.api_key,
    }
    provider_id = str(spec.id)
    if spec.provider_type != "openai_compatible":
        raise ProviderError(f"Unsupported provider type: {spec.provider_type}")

    if spec.category == ProviderCategory.CHAT:
        return OpenAICompatibleChatProvider(provider_id, model=spec.model, config=config)
    if spec.category == ProviderCategory.SPEECH:
        return OpenAICompatibleSpeechProvider(provider_id, model=spec.model, config=config)
    if spec.category == ProviderCategory.IMAGE:
        return OpenAICompatibleImageProvider(provider_id, model=spec.model, config=config)
    raise ProviderError(f"Unsupported provider category: {spec.category}")
