"""Provider contracts for chat, speech and image models.

The main chat model can call the configured speech and image providers through
tool definitions exposed by higher-level services. Providers themselves stay
small transport wrappers: configuration, retries and orchestration belong to
the service layer.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar


class ProviderCategory(StrEnum):
    """The three model roles supported by MoriBot."""

    CHAT = "chat"
    SPEECH = "speech"
    IMAGE = "image"


@dataclass(slots=True)
class ChatMessage:
    """A normalized chat message."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class ProviderResponse:
    """A non-streaming chat result."""

    text: str
    raw: Any = None
    usage: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SpeechResult:
    """Generated audio bytes and metadata."""

    audio: bytes
    mime_type: str = "audio/mpeg"
    format: str = "mp3"
    model: str = ""


@dataclass(slots=True)
class GeneratedImage:
    """One generated image, either inline bytes or a remote URL."""

    data: bytes | None = None
    url: str | None = None
    mime_type: str = "image/png"
    revised_prompt: str = ""


class ProviderError(Exception):
    """A provider request failed in a user-actionable way."""


class Provider:
    """Base class shared by every configured model provider."""

    provider_type: ClassVar[str] = "base"
    category: ClassVar[str] = ""

    def __init__(
        self,
        provider_id: str,
        *,
        model: str = "",
        config: dict[str, Any] | None = None,
    ) -> None:
        self.provider_id = provider_id
        self.model = model
        self.config = dict(config or {})
        self.capabilities = dict(self.config.get("capabilities", {}) or {})

    @property
    def display_name(self) -> str:
        return str(self.config.get("name") or self.provider_id)

    async def close(self) -> None:
        """Release provider resources such as HTTP clients."""
        return None

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "name": self.display_name,
            "type": self.provider_type,
            "category": self.category,
            "model": self.model,
            "capabilities": self.capabilities,
        }


class ChatProvider(Provider, abc.ABC):
    """Conversation model provider."""

    category = ProviderCategory.CHAT

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> ProviderResponse:
        """Generate a complete response for the given conversation."""
        raise NotImplementedError

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Yield response chunks. Override for native streaming."""
        response = await self.chat(messages, **kwargs)
        yield response.text


class SpeechProvider(Provider, abc.ABC):
    """Text-to-speech provider."""

    category = ProviderCategory.SPEECH

    @abc.abstractmethod
    async def synthesize(self, text: str, **kwargs: Any) -> SpeechResult:
        """Generate audio for the supplied text."""
        raise NotImplementedError


class ImageProvider(Provider, abc.ABC):
    """Image generation provider."""

    category = ProviderCategory.IMAGE

    @abc.abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> list[GeneratedImage]:
        """Generate one or more images for the prompt."""
        raise NotImplementedError
