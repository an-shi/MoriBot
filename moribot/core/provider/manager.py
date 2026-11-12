"""Provider registry and default-selection logic."""

from __future__ import annotations

from loguru import logger

from .base import Provider


class ProviderManager:
    """Owns registered provider instances for the lifetime of the process."""

    def __init__(self, default_provider_id: str = "") -> None:
        self._providers: dict[str, Provider] = {}
        self.default_provider_id = default_provider_id.strip()

    def register(self, provider: Provider) -> None:
        if provider.provider_id in self._providers:
            logger.warning("Provider {} is already registered; replacing it.", provider.provider_id)
        self._providers[provider.provider_id] = provider
        logger.debug("Registered provider {} ({})", provider.provider_id, provider.provider_type)

    def unregister(self, provider_id: str) -> Provider | None:
        return self._providers.pop(provider_id, None)

    def get(self, provider_id: str) -> Provider | None:
        return self._providers.get(provider_id)

    def set_default(self, provider_id: str) -> None:
        self.default_provider_id = provider_id.strip()

    @property
    def providers(self) -> list[Provider]:
        return list(self._providers.values())

    def get_default(self) -> Provider | None:
        """Return the configured default, or the first registered provider."""
        if self.default_provider_id:
            provider = self._providers.get(self.default_provider_id)
            if provider is not None:
                return provider
            logger.warning(
                "Configured default provider {} is not registered.",
                self.default_provider_id,
            )
        return next(iter(self._providers.values()), None)

    async def close_all(self) -> None:
        for provider in list(self._providers.values()):
            try:
                await provider.close()
            except Exception:
                logger.exception("Failed to close provider {}.", provider.provider_id)
        self._providers.clear()

    def describe_all(self) -> list[dict]:
        return [provider.describe() for provider in self._providers.values()]

    def __len__(self) -> int:
        return len(self._providers)
