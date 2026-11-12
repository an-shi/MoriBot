"""Native Anthropic Messages API provider."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .base import ChatMessage, ChatProvider, ProviderError, ProviderResponse


class AnthropicChatProvider(ChatProvider):
    """Claude models through the native ``/v1/messages`` API."""

    provider_type = "anthropic"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.base_url = str(self.config.get("base_url", "https://api.anthropic.com/v1")).rstrip("/")
        self.api_key = str(self.config.get("api_key", "")).strip()
        self.version = str(self.config.get("anthropic_version", "2023-06-01"))
        try:
            self.timeout = max(5.0, float(self.config.get("timeout", 90)))
        except (TypeError, ValueError):
            self.timeout = 90.0
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.version,
        }

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers(),
                follow_redirects=True,
            )
        return self._client

    @staticmethod
    def _text_blocks(content: Any) -> list[dict[str, Any]]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []
        if isinstance(content, list):
            blocks = []
            for part in content:
                if isinstance(part, dict) and part.get("type") in {"text", "input_text"}:
                    blocks.append({"type": "text", "text": str(part.get("text", ""))})
            return blocks
        return []

    @classmethod
    def _convert_messages(
        cls,
        messages: list[ChatMessage] | list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        system_parts: list[str] = []
        converted: list[dict[str, Any]] = []

        def append(role: str, blocks: list[dict[str, Any]]) -> None:
            if not blocks:
                return
            if converted and converted[-1]["role"] == role:
                converted[-1]["content"].extend(blocks)
            else:
                converted.append({"role": role, "content": blocks})

        for message in messages:
            data = message.to_dict() if isinstance(message, ChatMessage) else dict(message)
            role = str(data.get("role", "user"))
            content = data.get("content", "")

            if role == "system":
                system_parts.extend(str(part.get("text", "")) for part in cls._text_blocks(content))
                continue

            if role == "tool":
                append(
                    "user",
                    [
                        {
                            "type": "tool_result",
                            "tool_use_id": str(data.get("tool_call_id", "")),
                            "content": str(content or ""),
                        }
                    ],
                )
                continue

            if role == "assistant" and data.get("tool_calls"):
                blocks = cls._text_blocks(content)
                for index, call in enumerate(data["tool_calls"]):
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") or {}
                    arguments = function.get("arguments", "{}")
                    try:
                        parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                    except json.JSONDecodeError:
                        parsed = {}
                    if not isinstance(parsed, dict):
                        parsed = {}
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": str(call.get("id") or f"tool_{index}"),
                            "name": str(function.get("name", "")),
                            "input": parsed,
                        }
                    )
                append("assistant", blocks)
                continue

            append("user" if role != "assistant" else "assistant", cls._text_blocks(content))

        return "\n\n".join(part for part in system_parts if part), converted

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        converted = []
        for tool in tools or []:
            function = tool.get("function") if isinstance(tool, dict) else None
            if not isinstance(function, dict):
                continue
            converted.append(
                {
                    "name": str(function.get("name", "")),
                    "description": str(function.get("description", "")),
                    "input_schema": function.get("parameters")
                    or {"type": "object", "properties": {}},
                }
            )
        return converted

    async def chat(
        self,
        messages: list[ChatMessage],
        **kwargs: Any,
    ) -> ProviderResponse:
        system_prompt, converted_messages = self._convert_messages(messages)
        max_tokens = kwargs.get("max_tokens", self.config.get("max_tokens", 2048))
        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            max_tokens = 2048

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": converted_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools := self._convert_tools(kwargs.get("tools")):
            payload["tools"] = tools
        if kwargs.get("temperature") is not None:
            payload["temperature"] = kwargs["temperature"]
        if kwargs.get("top_p") is not None:
            payload["top_p"] = kwargs["top_p"]
        if stop := kwargs.get("stop", self.config.get("stop")):
            payload["stop_sequences"] = stop if isinstance(stop, list) else [stop]

        client = await self._http()
        try:
            response = await client.post(f"{self.base_url}/messages", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Network error: {exc}") from exc
        if response.status_code >= 400:
            detail = " ".join(response.text.strip().split())[:400]
            raise ProviderError(f"HTTP {response.status_code}: {detail or 'request failed'}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("Provider returned non-JSON data") from exc

        content = data.get("content") or []
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for index, block in enumerate(content):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or f"tool_{index}"),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name", "")),
                            "arguments": json.dumps(block.get("input") or {}, ensure_ascii=False),
                        },
                    }
                )
        usage = data.get("usage") or {}
        return ProviderResponse(
            text="".join(text_parts),
            raw=data,
            usage={
                "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
                "completion_tokens": int(usage.get("output_tokens", 0) or 0),
            },
            tool_calls=tool_calls,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await super().close()
