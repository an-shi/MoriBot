"""MiniMax native chat, speech and image adapters.

MiniMax chat and H3 image generation are OpenAI-compatible, while synchronous
speech synthesis uses the native ``/t2a_v2`` endpoint and returns hex-encoded
audio inside a JSON envelope.
"""

from __future__ import annotations

from typing import Any

from .base import ProviderError, SpeechProvider, SpeechResult
from .openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleImageProvider,
    _OpenAICompatibleProvider,
)

_SPEECH_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "pcm": "audio/pcm",
    "flac": "audio/flac",
}


class MiniMaxChatProvider(OpenAICompatibleChatProvider):
    """MiniMax's OpenAI-compatible chat completions endpoint."""

    provider_type = "minimax"


class MiniMaxImageProvider(OpenAICompatibleImageProvider):
    """MiniMax H3 image generations endpoint."""

    provider_type = "minimax"


class MiniMaxSpeechProvider(_OpenAICompatibleProvider, SpeechProvider):
    """Synchronous MiniMax text-to-audio endpoint."""

    provider_type = "minimax"

    async def synthesize(self, text: str, **kwargs: Any) -> SpeechResult:
        audio_format = str(
            kwargs.get(
                "output_format",
                kwargs.get(
                    "response_format",
                    self.config.get("output_format", self.config.get("response_format", "mp3")),
                ),
            )
        ).lower()
        if audio_format not in _SPEECH_MIME_TYPES:
            audio_format = "mp3"

        voice_id = str(
            kwargs.get("voice_id")
            or kwargs.get("voice")
            or self.config.get("voice_id")
            or self.config.get("voice")
            or "English_expressive_narrator"
        )
        voice_setting: dict[str, Any] = {"voice_id": voice_id, "vol": 1, "pitch": 0}
        speed = kwargs.get("speed", self.config.get("speed"))
        if speed is not None:
            voice_setting["speed"] = speed

        payload: dict[str, Any] = {
            "model": self.model,
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": voice_setting,
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": audio_format,
                "channel": 1,
            },
        }
        params: dict[str, str] | None = None
        group_id = str(self.config.get("group_id", "")).strip()
        if group_id:
            params = {"GroupId": group_id}

        data = await self._request_json(
            "POST",
            "t2a_v2",
            json=payload,
            params=params,
        )
        base_resp = data.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code not in (0, None):
            message = str(base_resp.get("status_msg") or "unknown error")
            raise ProviderError(f"MiniMax error {status_code}: {message}")

        audio_hex = (data.get("data") or {}).get("audio")
        if not isinstance(audio_hex, str) or not audio_hex:
            raise ProviderError("MiniMax returned empty audio data")
        try:
            audio = bytes.fromhex(audio_hex)
        except ValueError as exc:
            raise ProviderError("MiniMax returned invalid hex audio data") from exc
        if not audio:
            raise ProviderError("MiniMax returned empty audio data")

        return SpeechResult(
            audio=audio,
            mime_type=_SPEECH_MIME_TYPES[audio_format],
            format=audio_format,
            model=self.model,
        )
