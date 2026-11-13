"""Discover real model lists and capabilities from provider APIs.

The result is normalized so the dashboard can show a dropdown and the chat
layer can make decisions such as whether a model accepts images or supports
tool calls. When a vendor does not expose modality metadata, conservative
name-based heuristics are used and marked as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from .base import ProviderCategory, ProviderError

_VISION_MARKERS = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-4-turbo",
    "gpt-5",
    "o3",
    "o4",
    "claude",
    "gemini",
    "vision",
    "vl",
    "multimodal",
    "llava",
    "pixtral",
)
_REASONING_MARKERS = (
    "o1",
    "o3",
    "o4",
    "r1",
    "reasoner",
    "thinking",
    "qwq",
    "deepseek-r1",
)
_TOOL_EXCLUDES = ("embedding", "whisper", "tts", "dall-e", "image", "moderation", "rerank")
_CHAT_EXCLUDES = _TOOL_EXCLUDES + (
    "stable-diffusion",
    "flux",
    "kolors",
    "seedream",
    "sdxl",
    "imagen",
    "orpheus",
    "cosyvoice",
    "kokoro",
    "playai",
)
_SPEECH_MARKERS = (
    "tts",
    "speech",
    "audio",
    "orpheus",
    "cosyvoice",
    "kokoro",
    "playai",
    "sonic",
)
_IMAGE_MARKERS = (
    "image",
    "dall-e",
    "stable-diffusion",
    "flux",
    "kolors",
    "seedream",
    "sdxl",
    "imagen",
)


@dataclass(slots=True)
class ModelInfo:
    id: str
    name: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    owned_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "capabilities": self.capabilities,
            "owned_by": self.owned_by,
        }


def _context_window(raw: dict[str, Any] | None) -> int:
    if not isinstance(raw, dict):
        return 0
    for key in (
        "context_length",
        "context_window",
        "max_context_length",
        "max_input_tokens",
        "inputTokenLimit",
        "input_token_limit",
    ):
        value = raw.get(key)
        if value is None:
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def infer_capabilities(
    category: str,
    provider_type: str,
    model_id: str,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer a normalized capability object for a model."""
    lower = model_id.lower()
    raw = raw if isinstance(raw, dict) else {}
    source = "heuristic"

    if category == ProviderCategory.SPEECH:
        return {
            "input": ["text"],
            "output": ["audio"],
            "tools": False,
            "reasoning": False,
            "context_window": 0,
            "source": source,
        }
    if category == ProviderCategory.IMAGE:
        return {
            "input": ["text"],
            "output": ["image"],
            "tools": False,
            "reasoning": False,
            "context_window": 0,
            "source": source,
        }

    input_modalities = ["text"]
    output_modalities = ["text"]
    tools = not any(marker in lower for marker in _TOOL_EXCLUDES)
    reasoning = any(marker in lower for marker in _REASONING_MARKERS)

    architecture = raw.get("architecture")
    if isinstance(architecture, dict):
        input_modalities = [
            str(item) for item in architecture.get("input_modalities", []) if isinstance(item, str)
        ] or input_modalities
        output_modalities = [
            str(item) for item in architecture.get("output_modalities", []) if isinstance(item, str)
        ] or output_modalities
        supported = architecture.get("supported_parameters")
        if isinstance(supported, list):
            tools = "tools" in supported or "tool_choice" in supported
        source = "api"

    for key in ("input_modalities", "inputModalities"):
        value = raw.get(key)
        if isinstance(value, list) and value:
            input_modalities = [str(item).lower() for item in value]
            source = "api"
    for key in ("output_modalities", "outputModalities"):
        value = raw.get(key)
        if isinstance(value, list) and value:
            output_modalities = [str(item).lower() for item in value]
            source = "api"

    if "image" not in input_modalities and any(marker in lower for marker in _VISION_MARKERS):
        input_modalities.append("image")
    if "audio" not in input_modalities and ("realtime" in lower or "audio" in lower):
        input_modalities.append("audio")
    if "image" in output_modalities or any(
        marker in lower for marker in ("dall-e", "stable-diffusion", "flux")
    ):
        output_modalities = ["image"]
        tools = False

    return {
        "input": sorted(set(input_modalities)),
        "output": sorted(set(output_modalities)),
        "tools": tools,
        "reasoning": reasoning,
        "context_window": _context_window(raw),
        "source": source,
    }


def _category_relevant(category: str, model_id: str) -> bool:
    lower = model_id.lower()
    if category == ProviderCategory.CHAT:
        return not any(marker in lower for marker in _CHAT_EXCLUDES)
    if category == ProviderCategory.SPEECH:
        return any(marker in lower for marker in _SPEECH_MARKERS)
    return any(marker in lower for marker in _IMAGE_MARKERS)


def _filter_models(
    category: str,
    models: list[ModelInfo],
    *,
    fallback_to_all: bool = True,
    retired_prefixes: list[str] | None = None,
) -> list[ModelInfo]:
    prefixes = tuple(prefix.lower() for prefix in (retired_prefixes or ()) if prefix)
    if prefixes:
        models = [model for model in models if not model.id.lower().startswith(prefixes)]
    relevant = [model for model in models if _category_relevant(category, model.id)]
    # A custom gateway may expose names our heuristics do not recognise.
    if relevant:
        return relevant
    return models if fallback_to_all else []


def _fallback_models(category: str, model_ids: list[str]) -> list[ModelInfo]:
    """Build models from a user-editable fallback list in config.json."""
    return [
        ModelInfo(
            id=model_id,
            name=model_id,
            capabilities=infer_capabilities(category, "fallback", model_id),
            owned_by="",
        )
        for model_id in model_ids
        if isinstance(model_id, str) and model_id.strip()
    ]


def _openai_headers(api_key: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def _get_json(
    url: str,
    *,
    headers: dict[str, str],
    request_timeout: float = 30.0,
) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=request_timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise ProviderError(f"Network error: {exc}") from exc
    if response.status_code >= 400:
        detail = " ".join(response.text.strip().split())[:300]
        raise ProviderError(f"HTTP {response.status_code}: {detail or 'request failed'}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError("Provider returned non-JSON data") from exc
    if not isinstance(data, dict):
        raise ProviderError("Provider returned an unexpected JSON payload")
    return data


async def list_models(
    *,
    provider_type: str,
    category: str,
    base_url: str,
    api_key: str,
    options: dict[str, Any] | None = None,
    fallback_models: dict[str, list[str]] | None = None,
    retired_model_prefixes: list[str] | None = None,
) -> list[ModelInfo]:
    """Fetch and normalize a provider's model list."""
    options = options or {}
    base = base_url.rstrip("/")
    timeout = 30.0
    try:
        timeout = max(5.0, float(options.get("timeout", 30)))
    except (TypeError, ValueError):
        pass

    if provider_type == "anthropic":
        data = await _get_json(
            f"{base}/models?limit=1000",
            headers={
                "x-api-key": api_key,
                "anthropic-version": str(options.get("anthropic_version", "2023-06-01")),
            },
            request_timeout=timeout,
        )
        raw_models = data.get("data") or []
        models = []
        for raw in raw_models:
            if not isinstance(raw, dict):
                continue
            model_id = str(raw.get("id", "")).strip()
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=str(raw.get("display_name") or model_id),
                    capabilities=infer_capabilities(category, provider_type, model_id, raw),
                    owned_by=str(raw.get("type") or "anthropic"),
                )
            )
        return _filter_models(category, models, retired_prefixes=retired_model_prefixes)

    if provider_type == "google_gemini":
        data = await _get_json(
            f"{base}/models?pageSize=1000",
            headers={"x-goog-api-key": api_key},
            request_timeout=timeout,
        )
        models = []
        for raw in data.get("models") or []:
            if not isinstance(raw, dict):
                continue
            model_id = str(raw.get("name", "")).removeprefix("models/")
            methods = raw.get("supportedGenerationMethods") or []
            if not model_id or (methods and "generateContent" not in methods):
                continue
            capabilities = infer_capabilities(category, provider_type, model_id, raw)
            if category == ProviderCategory.IMAGE and "image" not in model_id.lower():
                continue
            if category == ProviderCategory.CHAT and "embedding" in model_id.lower():
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=str(raw.get("displayName") or model_id),
                    capabilities=capabilities,
                    owned_by="google",
                )
            )
        return _filter_models(category, models, retired_prefixes=retired_model_prefixes)

    if provider_type == "elevenlabs":
        data = await _get_json(
            f"{base}/models",
            headers={"xi-api-key": api_key},
            request_timeout=timeout,
        )
        models = []
        for raw in data.get("models") or data.get("data") or []:
            if not isinstance(raw, dict):
                continue
            model_id = str(raw.get("model_id") or raw.get("id") or "").strip()
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=str(raw.get("name") or model_id),
                    capabilities=infer_capabilities(category, provider_type, model_id, raw),
                    owned_by="elevenlabs",
                )
            )
        return models

    if provider_type == "azure_openai":
        api_version = str(options.get("api_version", "2024-10-21"))
        data = await _get_json(
            f"{base}/openai/models?api-version={quote(api_version, safe='')}",
            headers={"api-key": api_key},
            request_timeout=timeout,
        )
    else:
        data = await _get_json(
            f"{base}/models",
            headers=_openai_headers(api_key),
            request_timeout=timeout,
        )

    raw_models = data.get("data") or data.get("models") or []
    models = []
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        model_id = str(raw.get("id") or raw.get("name") or "").strip()
        if not model_id:
            continue
        models.append(
            ModelInfo(
                id=model_id,
                name=str(raw.get("name") or model_id),
                capabilities=infer_capabilities(category, provider_type, model_id, raw),
                owned_by=str(raw.get("owned_by") or ""),
            )
        )
    if provider_type == "minimax" and category in (
        ProviderCategory.SPEECH,
        ProviderCategory.IMAGE,
    ):
        relevant = _filter_models(
            category,
            models,
            fallback_to_all=False,
            retired_prefixes=retired_model_prefixes,
        )
        if relevant:
            return relevant
        fallback_ids = (fallback_models or {}).get(category, [])
        return _fallback_models(category, fallback_ids)
    return _filter_models(category, models, retired_prefixes=retired_model_prefixes)
