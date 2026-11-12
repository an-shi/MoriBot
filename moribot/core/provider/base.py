"""Provider abstraction.

Concrete providers (OpenAI-compatible, Anthropic, Gemini, ...) will implement
``Provider.chat``. Keeping the interface independent from SDKs is what lets
MoriBot add model vendors without touching the pipeline.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(slots=True)
class ChatMessage:
    """A normalized chat message."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(slots=True)
class ProviderResponse:
    """A non-streaming provider result."""

    text: str
    raw: Any = None
    usage: dict[str, Any] = field(default_factory=dict)


class Provider(abc.ABC):
    """Base class shared by every model provider."""

    provider_type: ClassVar[str] = "base"

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

    @property
    def display_name(self) -> str:
        return str(self.config.get("name") or self.provider_id)

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
        """Yield response chunks. Providers may override for native streaming."""
        response = await self.chat(messages, **kwargs)
        yield response.text

    async def close(self) -> None:
        """Release provider resources such as HTTP clients."""
        return None

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "name": self.display_name,
            "type": self.provider_type,
            "model": self.model,
        }
