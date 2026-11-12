"""Category-aware provider registry and default selection."""

from __future__ import annotations

from loguru import logger

from .base import Provider, ProviderCategory
from .config import ProviderConfigSpec, build_provider


class ProviderManager:
    """Holds configured provider instances grouped by model role."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}
        self._defaults: dict[str, str] = {}

    def register(self, provider: Provider, *, default: bool = False) -> None:
        if provider.provider_id in self._providers:
            logger.warning("Provider {} is already registered; replacing it.", provider.provider_id)
        self._providers[provider.provider_id] = provider
        if default and provider.category:
            self._defaults[provider.category] = provider.provider_id
        logger.debug(
            "Registered provider {} ({}/{}).",
            provider.provider_id,
            provider.category,
            provider.provider_type,
        )

    def unregister(self, provider_id: str) -> Provider | None:
        provider = self._providers.pop(provider_id, None)
        for category, default_id in list(self._defaults.items()):
            if default_id == provider_id:
                self._defaults.pop(category, None)
        return provider

    def get(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def list(self, category: str | None = None) -> list[Provider]:
        providers = list(self._providers.values())
        if category:
            return [provider for provider in providers if provider.category == category]
        return providers

    def get_default(self, category: str) -> Provider | None:
        """Return the default provider for a role, falling back to the first."""
        default_id = self._defaults.get(category)
        if default_id:
            provider = self._providers.get(default_id)
            if provider is not None:
                return provider
        return next(
            (provider for provider in self._providers.values() if provider.category == category),
            None,
        )

    async def load_specs(self, specs: list[ProviderConfigSpec]) -> None:
        """Atomically replace all providers after a configuration change."""
        new_providers: dict[str, Provider] = {}
        new_defaults: dict[str, str] = {}

        for spec in specs:
            try:
                provider = build_provider(spec)
            except Exception:
                logger.exception("Failed to build model provider {}.", spec.id)
                continue
            new_providers[str(spec.id)] = provider
            if spec.is_default:
                new_defaults[spec.category] = str(spec.id)

        old_providers = self._providers
        self._providers = new_providers
        self._defaults = new_defaults

        for provider in old_providers.values():
            try:
                await provider.close()
            except Exception:
                logger.exception("Failed to close old provider {}.", provider.provider_id)
        logger.info(
            "Loaded {} model provider(s): chat={}, speech={}, image={}.",
            len(self._providers),
            len(self.list(ProviderCategory.CHAT)),
            len(self.list(ProviderCategory.SPEECH)),
            len(self.list(ProviderCategory.IMAGE)),
        )

    async def close_all(self) -> None:
        for provider in list(self._providers.values()):
            try:
                await provider.close()
            except Exception:
                logger.exception("Failed to close provider {}.", provider.provider_id)
        self._providers.clear()
        self._defaults.clear()

    def describe_all(self) -> list[dict]:
        return [provider.describe() for provider in self._providers.values()]

    def __len__(self) -> int:
        return len(self._providers)
