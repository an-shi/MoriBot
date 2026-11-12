"""Native ElevenLabs text-to-speech provider."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .base import ProviderError, SpeechProvider, SpeechResult


class ElevenLabsSpeechProvider(SpeechProvider):
    """ElevenLabs text-to-speech endpoint."""

    provider_type = "elevenlabs"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.base_url = str(self.config.get("base_url", "https://api.elevenlabs.io/v1")).rstrip("/")
        self.api_key = str(self.config.get("api_key", "")).strip()
        try:
            self.timeout = max(5.0, float(self.config.get("timeout", 90)))
        except (TypeError, ValueError):
            self.timeout = 90.0
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "xi-api-key": self.api_key,
                },
                follow_redirects=True,
            )
        return self._client

    async def synthesize(self, text: str, **kwargs: Any) -> SpeechResult:
        voice_id = str(
            kwargs.get("voice_id")
            or kwargs.get("voice")
            or self.config.get("voice_id")
            or self.config.get("voice")
            or "21m00Tcm4TlvDq8ikWAM"
        )
        output_format = str(
            kwargs.get("output_format")
            or self.config.get("output_format")
            or self.config.get("response_format")
            or "mp3"
        )
        if "_" not in output_format:
            output_format = {
                "mp3": "mp3_44100_128",
                "opus": "opus_48000_64",
                "pcm": "pcm_44100",
                "ulaw": "ulaw_8000",
            }.get(output_format, "mp3_44100_128")
        payload: dict[str, Any] = {
            "text": text,
            "model_id": self.model or "eleven_multilingual_v2",
        }
        if voice_settings := self.config.get("voice_settings"):
            payload["voice_settings"] = voice_settings

        client = await self._http()
        try:
            response = await client.post(
                f"{self.base_url}/text-to-speech/{quote(voice_id, safe='')}",
                params={"output_format": output_format},
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error: {exc}") from exc
        if response.status_code >= 400:
            detail = " ".join(response.text.strip().split())[:400]
            raise ProviderError(f"HTTP {response.status_code}: {detail or 'request failed'}")
        if not response.content:
            raise ProviderError("ElevenLabs returned empty audio data")

        audio_format = output_format.split("_", 1)[0] or "mp3"
        mime = {
            "mp3": "audio/mpeg",
            "opus": "audio/opus",
            "pcm": "audio/pcm",
            "ulaw": "audio/basic",
        }.get(audio_format, "audio/mpeg")
        return SpeechResult(
            audio=response.content,
            mime_type=mime,
            format=audio_format,
            model=self.model,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await super().close()
