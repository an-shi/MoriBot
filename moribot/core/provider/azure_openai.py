"""Azure OpenAI deployment providers.

Azure uses deployment-specific paths and the ``api-key`` header instead of the
standard OpenAI ``Authorization: Bearer`` header.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from .openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleImageProvider,
    OpenAICompatibleSpeechProvider,
)


class _AzureMixin:
    provider_type = "azure_openai"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.base_url = str(self.config.get("base_url", "")).rstrip("/")
        self.api_version = str(self.config.get("api_version", "2024-10-21"))

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "api-key": self.api_key,
        }

    def _url(self, path: str) -> str:
        deployment = quote(self.model, safe="")
        return (
            f"{self.base_url}/openai/deployments/{deployment}/{path.lstrip('/')}"
            f"?api-version={quote(self.api_version, safe='')}"
        )


class AzureOpenAIChatProvider(_AzureMixin, OpenAICompatibleChatProvider):
    """Azure chat completions."""


class AzureOpenAISpeechProvider(_AzureMixin, OpenAICompatibleSpeechProvider):
    """Azure audio speech."""


class AzureOpenAIImageProvider(_AzureMixin, OpenAICompatibleImageProvider):
    """Azure image generations."""
