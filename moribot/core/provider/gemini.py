"""Native Google Gemini generateContent provider."""

from __future__ import annotations

import base64
import json
from typing import Any
from urllib.parse import quote

import httpx

from .base import (
    ChatMessage,
    ChatProvider,
    GeneratedImage,
    ImageProvider,
    ProviderError,
    ProviderResponse,
)


class _GeminiMixin:
    provider_type = "google_gemini"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.base_url = str(
            self.config.get("base_url", "https://generativelanguage.googleapis.com/v1beta")
        ).rstrip("/")
        self.api_key = str(self.config.get("api_key", "")).strip()
        try:
            self.timeout = max(5.0, float(self.config.get("timeout", 90)))
        except (TypeError, ValueError):
            self.timeout = 90.0
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key
        return headers

    def _model_name(self) -> str:
        return self.model.removeprefix("models/").strip() or "gemini-2.5-flash"

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers(),
                follow_redirects=True,
            )
        return self._client

    async def _request(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        model = quote(self._model_name(), safe="-_.")
        url = f"{self.base_url}/models/{model}:{action}"
        client = await self._http()
        try:
            response = await client.post(url, json=payload)
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

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await super().close()


class GeminiChatProvider(_GeminiMixin, ChatProvider):
    """Gemini chat with native function calling."""

    def _convert_messages(
        self,
        messages: list[ChatMessage] | list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        contents: list[dict[str, Any]] = []

        def append(role: str, parts: list[dict[str, Any]]) -> None:
            if not parts:
                return
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"].extend(parts)
            else:
                contents.append({"role": role, "parts": parts})

        for message in messages:
            data = message.to_dict() if isinstance(message, ChatMessage) else dict(message)
            role = str(data.get("role", "user"))
            content = data.get("content", "")

            if role == "system":
                system_parts.append(str(content or ""))
                continue
            if role == "tool":
                append(
                    "user",
                    [
                        {
                            "functionResponse": {
                                "name": str(data.get("name") or "tool"),
                                "response": {"result": str(content or "")},
                            }
                        }
                    ],
                )
                continue
            if role == "assistant" and data.get("tool_calls"):
                parts: list[dict[str, Any]] = []
                if content:
                    parts.append({"text": str(content)})
                for call in data["tool_calls"]:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") or {}
                    arguments = function.get("arguments", "{}")
                    try:
                        args = json.loads(arguments) if isinstance(arguments, str) else arguments
                    except json.JSONDecodeError:
                        args = {}
                    parts.append(
                        {
                            "functionCall": {
                                "name": str(function.get("name", "")),
                                "args": args if isinstance(args, dict) else {},
                            }
                        }
                    )
                append("model", parts)
                continue

            append("model" if role == "assistant" else "user", [{"text": str(content or "")}])

        return "\n\n".join(part for part in system_parts if part), contents

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        declarations = []
        for tool in tools or []:
            function = tool.get("function") if isinstance(tool, dict) else None
            if not isinstance(function, dict):
                continue
            declarations.append(
                {
                    "name": str(function.get("name", "")),
                    "description": str(function.get("description", "")),
                    "parameters": function.get("parameters")
                    or {"type": "object", "properties": {}},
                }
            )
        return [{"functionDeclarations": declarations}] if declarations else []

    async def chat(
        self,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> ProviderResponse:
        system_prompt, contents = self._convert_messages(messages)
        generation_config: dict[str, Any] = {}
        temperature = kwargs.get("temperature", self.config.get("temperature"))
        if temperature is not None:
            generation_config["temperature"] = temperature
        max_tokens = kwargs.get(
            "max_tokens",
            kwargs.get("max_completion_tokens", self.config.get("max_tokens")),
        )
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = int(max_tokens)
        top_p = kwargs.get("top_p", self.config.get("top_p"))
        if top_p is not None:
            generation_config["topP"] = top_p
        stop = kwargs.get("stop", self.config.get("stop"))
        if stop:
            generation_config["stopSequences"] = stop if isinstance(stop, list) else [stop]

        payload: dict[str, Any] = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if generation_config:
            payload["generationConfig"] = generation_config
        if tools := self._convert_tools(kwargs.get("tools")):
            payload["tools"] = tools

        data = await self._request("generateContent", payload)
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("Gemini returned no candidates")
        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for index, part in enumerate(parts):
            if not isinstance(part, dict):
                continue
            if "text" in part:
                text_parts.append(str(part.get("text", "")))
            function_call = part.get("functionCall") or part.get("function_call")
            if isinstance(function_call, dict):
                tool_calls.append(
                    {
                        "id": f"gemini-tool-{index}",
                        "type": "function",
                        "function": {
                            "name": str(function_call.get("name", "")),
                            "arguments": json.dumps(
                                function_call.get("args") or {},
                                ensure_ascii=False,
                            ),
                        },
                    }
                )
        usage_meta = data.get("usageMetadata") or {}
        return ProviderResponse(
            text="".join(text_parts),
            raw=data,
            usage={
                "prompt_tokens": int(usage_meta.get("promptTokenCount", 0) or 0),
                "completion_tokens": int(usage_meta.get("candidatesTokenCount", 0) or 0),
            },
            tool_calls=tool_calls,
        )


class GeminiImageProvider(_GeminiMixin, ImageProvider):
    """Gemini image generation (e.g. gemini-2.5-flash-image)."""

    async def generate(self, prompt: str, **kwargs: Any) -> list[GeneratedImage]:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        data = await self._request("generateContent", payload)
        images: list[GeneratedImage] = []
        for candidate in data.get("candidates") or []:
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                if not isinstance(part, dict):
                    continue
                inline = part.get("inlineData") or part.get("inline_data")
                if isinstance(inline, dict) and inline.get("data"):
                    try:
                        raw = base64.b64decode(str(inline["data"]))
                    except (ValueError, TypeError):
                        continue
                    images.append(
                        GeneratedImage(
                            data=raw,
                            mime_type=str(
                                inline.get("mimeType") or inline.get("mime_type") or "image/png"
                            ),
                        )
                    )
                file_data = part.get("fileData") or part.get("file_data")
                if isinstance(file_data, dict) and file_data.get("fileUri"):
                    images.append(GeneratedImage(url=str(file_data["fileUri"])))
        if not images:
            raise ProviderError("Gemini returned no images")
        return images
