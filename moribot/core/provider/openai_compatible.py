"""OpenAI-compatible chat, speech and image providers.

Most self-hosted gateways (OpenAI, Azure-compatible proxies, OneAPI, NewAPI,
vLLM, LM Studio, etc.) expose these three endpoint families. Keeping one
adapter per category avoids a provider matrix while still supporting custom
base URLs and model names.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
from loguru import logger

from .base import (
    ChatMessage,
    ChatProvider,
    GeneratedImage,
    ImageProvider,
    ProviderError,
    ProviderResponse,
    SpeechProvider,
    SpeechResult,
)

_CHAT_OPTION_KEYS = (
    "temperature",
    "max_tokens",
    "max_completion_tokens",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "stop",
    "seed",
)
_SPEECH_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}


class _OpenAICompatibleProvider:
    """Shared HTTP plumbing for OpenAI-compatible endpoints."""

    provider_type = "openai_compatible"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.base_url = str(self.config.get("base_url", "")).rstrip("/")
        self.api_key = str(self.config.get("api_key", "")).strip()
        try:
            self.timeout = max(5.0, float(self.config.get("timeout", 90)))
        except (TypeError, ValueError):
            self.timeout = 90.0
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=self._headers(),
            )
        return self._client

    async def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = await self._http()
        try:
            response = await client.request(method, self._url(path), **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error: {exc}") from exc

        if response.status_code >= 400:
            detail = " ".join(response.text.strip().split())[:400]
            raise ProviderError(f"HTTP {response.status_code}: {detail or 'request failed'}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("Provider returned non-JSON data") from exc
        if not isinstance(data, dict):
            raise ProviderError("Provider returned an unexpected JSON payload")
        return data

    async def _request_bytes(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> tuple[bytes, str]:
        client = await self._http()
        try:
            response = await client.request(method, self._url(path), **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error: {exc}") from exc

        if response.status_code >= 400:
            detail = " ".join(response.text.strip().split())[:400]
            raise ProviderError(f"HTTP {response.status_code}: {detail or 'request failed'}")
        return response.content, response.headers.get("content-type", "").split(";")[0]

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await super().close()


class OpenAICompatibleChatProvider(_OpenAICompatibleProvider, ChatProvider):
    """Chat completions endpoint."""

    async def chat(
        self,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> ProviderResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                message.to_dict() if isinstance(message, ChatMessage) else dict(message)
                for message in messages
            ],
        }
        for key in _CHAT_OPTION_KEYS:
            value = kwargs.get(key, self.config.get(key))
            if value is not None:
                payload[key] = value
        if tools := kwargs.get("tools"):
            payload["tools"] = tools
        if tool_choice := kwargs.get("tool_choice"):
            payload["tool_choice"] = tool_choice

        data = await self._request_json("POST", "chat/completions", json=payload)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("Provider returned no chat choices")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") in {"text", "output_text"}
            )
        return ProviderResponse(
            text=str(content),
            raw=data,
            usage=data.get("usage") or {},
            tool_calls=list(message.get("tool_calls") or []),
        )


class OpenAICompatibleSpeechProvider(_OpenAICompatibleProvider, SpeechProvider):
    """Audio speech endpoint."""

    async def synthesize(self, text: str, **kwargs: Any) -> SpeechResult:
        audio_format = str(
            kwargs.get("response_format", self.config.get("response_format", "mp3"))
        ).lower()
        payload: dict[str, Any] = {
            "model": self.model,
            "input": text,
            "voice": kwargs.get("voice", self.config.get("voice", "alloy")),
            "response_format": audio_format,
        }
        speed = kwargs.get("speed", self.config.get("speed"))
        if speed is not None:
            payload["speed"] = speed

        audio, content_type = await self._request_bytes(
            "POST",
            "audio/speech",
            json=payload,
        )
        if not audio:
            raise ProviderError("Provider returned empty audio data")
        return SpeechResult(
            audio=audio,
            mime_type=content_type or _SPEECH_MIME_TYPES.get(audio_format, "audio/mpeg"),
            format=audio_format,
            model=self.model,
        )


class OpenAICompatibleImageProvider(_OpenAICompatibleProvider, ImageProvider):
    """Image generations endpoint."""

    async def generate(self, prompt: str, **kwargs: Any) -> list[GeneratedImage]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "n": int(kwargs.get("n", self.config.get("n", 1)) or 1),
            "size": kwargs.get("size", self.config.get("size", "1024x1024")),
        }
        for key in ("quality", "style", "background", "response_format"):
            value = kwargs.get(key, self.config.get(key))
            if value is not None:
                payload[key] = value

        data = await self._request_json("POST", "images/generations", json=payload)
        entries = data.get("data") or []
        if not entries:
            raise ProviderError("Provider returned no images")

        images: list[GeneratedImage] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            image_bytes: bytes | None = None
            encoded = entry.get("b64_json")
            if isinstance(encoded, str) and encoded:
                try:
                    image_bytes = base64.b64decode(encoded)
                except (ValueError, TypeError):
                    logger.warning("Image provider returned invalid base64 data.")
            url = entry.get("url")
            images.append(
                GeneratedImage(
                    data=image_bytes,
                    url=str(url) if url else None,
                    revised_prompt=str(entry.get("revised_prompt", "")),
                )
            )
        if not images:
            raise ProviderError("Provider returned no usable images")
        return images
