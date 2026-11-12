"""Supported provider adapters and vendor presets.

Most vendors expose an OpenAI-compatible API. Those vendors share one adapter
and differ only by base URL/model defaults. Vendors with incompatible wire
protocols get a native adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import ProviderCategory


@dataclass(frozen=True, slots=True)
class ProviderTypeSpec:
    id: str
    name: str
    description: str
    categories: tuple[str, ...]
    default_base_url: str = ""
    api_key_required: bool = True
    docs_url: str = ""


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    id: str
    name: str
    provider_type: str
    categories: tuple[str, ...]
    base_url: str
    models: dict[str, tuple[str, ...]]
    docs_url: str = ""
    api_key_required: bool = True
    voice: str = ""


PROVIDER_TYPES: dict[str, ProviderTypeSpec] = {
    "openai_compatible": ProviderTypeSpec(
        id="openai_compatible",
        name="OpenAI Compatible",
        description=(
            "OpenAI-compatible chat, speech and image endpoints. Also covers "
            "DeepSeek, Qwen, Kimi, GLM, MiniMax, Doubao, OpenRouter, Groq, "
            "Mistral, xAI, Ollama, LM Studio and similar services."
        ),
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        default_base_url="",
        docs_url="https://platform.openai.com/docs/api-reference",
    ),
    "azure_openai": ProviderTypeSpec(
        id="azure_openai",
        name="Azure OpenAI",
        description="Azure OpenAI deployments using the api-key header and deployment paths.",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        default_base_url="https://your-resource.openai.azure.com",
        docs_url="https://learn.microsoft.com/azure/ai-services/openai/",
    ),
    "anthropic": ProviderTypeSpec(
        id="anthropic",
        name="Anthropic Claude",
        description="Native Anthropic Messages API with tool use.",
        categories=(ProviderCategory.CHAT,),
        default_base_url="https://api.anthropic.com/v1",
        docs_url="https://docs.anthropic.com/en/api/messages",
    ),
    "google_gemini": ProviderTypeSpec(
        id="google_gemini",
        name="Google Gemini",
        description="Native Gemini generateContent API for chat and image models.",
        categories=(ProviderCategory.CHAT, ProviderCategory.IMAGE),
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        docs_url="https://ai.google.dev/api/generate-content",
    ),
    "elevenlabs": ProviderTypeSpec(
        id="elevenlabs",
        name="ElevenLabs",
        description="Native ElevenLabs text-to-speech API.",
        categories=(ProviderCategory.SPEECH,),
        default_base_url="https://api.elevenlabs.io/v1",
        docs_url="https://elevenlabs.io/docs/api-reference/text-to-speech",
    ),
    "minimax": ProviderTypeSpec(
        id="minimax",
        name="MiniMax",
        description="Native MiniMax chat, synchronous T2A speech and H3 image generation.",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        default_base_url="https://api.minimax.io/v1",
        docs_url="https://platform.minimax.io/docs/api-reference/api-overview",
    ),
}


def _models(**items: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    return {
        ProviderCategory.CHAT: items.get("chat", ()),
        ProviderCategory.SPEECH: items.get("speech", ()),
        ProviderCategory.IMAGE: items.get("image", ()),
    }


PROVIDER_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        id="openai",
        name="OpenAI",
        provider_type="openai_compatible",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        base_url="https://api.openai.com/v1",
        models=_models(
            chat=("gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini"),
            speech=("tts-1", "tts-1-hd", "gpt-4o-mini-tts"),
            image=("gpt-image-1", "dall-e-3"),
        ),
        docs_url="https://platform.openai.com/docs/models",
    ),
    ProviderPreset(
        id="azure",
        name="Azure OpenAI",
        provider_type="azure_openai",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        base_url="https://your-resource.openai.azure.com",
        models=_models(
            chat=("your-chat-deployment",),
            speech=("your-tts-deployment",),
            image=("your-image-deployment",),
        ),
        docs_url="https://learn.microsoft.com/azure/ai-services/openai/",
    ),
    ProviderPreset(
        id="anthropic",
        name="Anthropic Claude",
        provider_type="anthropic",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.anthropic.com/v1",
        models=_models(chat=("claude-sonnet-4-5", "claude-opus-4-1", "claude-3-7-sonnet-latest")),
        docs_url="https://docs.anthropic.com/en/docs/about-claude/models",
    ),
    ProviderPreset(
        id="gemini",
        name="Google Gemini",
        provider_type="google_gemini",
        categories=(ProviderCategory.CHAT, ProviderCategory.IMAGE),
        base_url="https://generativelanguage.googleapis.com/v1beta",
        models=_models(
            chat=("gemini-2.5-pro", "gemini-2.5-flash"),
            image=("gemini-2.5-flash-image",),
        ),
        docs_url="https://ai.google.dev/gemini-api/docs/models",
    ),
    ProviderPreset(
        id="elevenlabs",
        name="ElevenLabs",
        provider_type="elevenlabs",
        categories=(ProviderCategory.SPEECH,),
        base_url="https://api.elevenlabs.io/v1",
        models=_models(speech=("eleven_multilingual_v2", "eleven_turbo_v2_5")),
        docs_url="https://elevenlabs.io/docs/models",
        voice="21m00Tcm4TlvDq8ikWAM",
    ),
    ProviderPreset(
        id="deepseek",
        name="DeepSeek",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.deepseek.com/v1",
        models=_models(chat=("deepseek-chat", "deepseek-reasoner")),
        docs_url="https://api-docs.deepseek.com/",
    ),
    ProviderPreset(
        id="qwen",
        name="通义千问 / DashScope",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=_models(chat=("qwen-plus", "qwen-max", "qwen3-max")),
        docs_url="https://help.aliyun.com/zh/model-studio/",
    ),
    ProviderPreset(
        id="moonshot",
        name="Moonshot / Kimi",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.moonshot.cn/v1",
        models=_models(chat=("kimi-k2-0905-preview", "moonshot-v1-8k")),
        docs_url="https://platform.moonshot.cn/docs/",
    ),
    ProviderPreset(
        id="zhipu",
        name="智谱 GLM",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://open.bigmodel.cn/api/paas/v4",
        models=_models(chat=("glm-4.5", "glm-4.5-air", "glm-4-plus")),
        docs_url="https://open.bigmodel.cn/dev/api",
    ),
    ProviderPreset(
        id="minimax",
        name="MiniMax（国际）",
        provider_type="minimax",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        base_url="https://api.minimax.io/v1",
        models=_models(
            chat=("MiniMax-M3.1-Flash", "MiniMax-M3"),
            speech=("speech-2.8-turbo", "speech-2.8-hd"),
            image=("MiniMax-H3-Image", "MiniMax-H3-Image-Highspeed"),
        ),
        docs_url="https://platform.minimax.io/docs/api-reference/api-overview",
        voice="English_expressive_narrator",
    ),
    ProviderPreset(
        id="minimax-cn",
        name="MiniMax（国内）",
        provider_type="minimax",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        base_url="https://api.minimax.cn/v1",
        models=_models(
            chat=("MiniMax-M3.1-Flash", "MiniMax-M3"),
            speech=("speech-2.8-turbo", "speech-2.8-hd"),
            image=("MiniMax-H3-Image", "MiniMax-H3-Image-Highspeed"),
        ),
        docs_url="https://platform.minimaxi.com/docs/api-reference/api-overview",
        voice="male-qn-qingse",
    ),
    ProviderPreset(
        id="doubao",
        name="火山方舟 / 豆包",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT, ProviderCategory.IMAGE),
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        models=_models(
            chat=("ep-your-endpoint-id",),
            image=(
                "doubao-seedream-5-0-lite-260128",
                "doubao-seedream-4-0-250828",
            ),
        ),
        docs_url="https://www.volcengine.com/docs/82379",
    ),
    ProviderPreset(
        id="siliconflow",
        name="SiliconFlow 硅基流动",
        provider_type="openai_compatible",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        base_url="https://api.siliconflow.cn/v1",
        models=_models(
            chat=("Qwen/Qwen3-8B", "deepseek-ai/DeepSeek-V3"),
            speech=("FunAudioLLM/CosyVoice2-0.5B",),
            image=(
                "black-forest-labs/FLUX.1-schnell",
                "Kwai-Kolors/Kolors",
                "Qwen/Qwen-Image",
            ),
        ),
        docs_url="https://docs.siliconflow.cn/",
        voice="FunAudioLLM/CosyVoice2-0.5B:alex",
    ),
    ProviderPreset(
        id="deepinfra",
        name="DeepInfra",
        provider_type="openai_compatible",
        categories=(ProviderCategory.IMAGE,),
        base_url="https://api.deepinfra.com/v1/openai",
        models=_models(
            image=(
                "black-forest-labs/FLUX-1-schnell",
                "black-forest-labs/FLUX-2-klein-4b",
            )
        ),
        docs_url="https://docs.deepinfra.com/apis/image-generation",
    ),
    ProviderPreset(
        id="openrouter",
        name="OpenRouter",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://openrouter.ai/api/v1",
        models=_models(chat=("openai/gpt-4.1-mini", "anthropic/claude-sonnet-4")),
        docs_url="https://openrouter.ai/docs",
    ),
    ProviderPreset(
        id="groq",
        name="Groq",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT, ProviderCategory.SPEECH),
        base_url="https://api.groq.com/openai/v1",
        models=_models(
            chat=("llama-3.3-70b-versatile", "openai/gpt-oss-120b"),
            speech=("canopylabs/orpheus-v1-english", "canopylabs/orpheus-arabic-saudi"),
        ),
        docs_url="https://console.groq.com/docs",
        voice="troy",
    ),
    ProviderPreset(
        id="mistral",
        name="Mistral AI",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.mistral.ai/v1",
        models=_models(chat=("mistral-large-latest", "mistral-small-latest")),
        docs_url="https://docs.mistral.ai/",
    ),
    ProviderPreset(
        id="xai",
        name="xAI Grok",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.x.ai/v1",
        models=_models(chat=("grok-4", "grok-3-mini")),
        docs_url="https://docs.x.ai/",
    ),
    ProviderPreset(
        id="together",
        name="Together AI",
        provider_type="openai_compatible",
        categories=(
            ProviderCategory.CHAT,
            ProviderCategory.SPEECH,
            ProviderCategory.IMAGE,
        ),
        base_url="https://api.together.xyz/v1",
        models=_models(
            chat=("meta-llama/Llama-3.3-70B-Instruct-Turbo",),
            speech=(
                "hexgrad/Kokoro-82M",
                "cartesia/sonic-3",
                "canopylabs/orpheus-3b-0.1-ft",
            ),
            image=("black-forest-labs/FLUX.1-schnell", "black-forest-labs/FLUX.2-dev"),
        ),
        docs_url="https://docs.together.ai/",
        voice="af_heart",
    ),
    ProviderPreset(
        id="perplexity",
        name="Perplexity",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.perplexity.ai",
        models=_models(chat=("sonar-pro", "sonar")),
        docs_url="https://docs.perplexity.ai/",
    ),
    ProviderPreset(
        id="qianfan",
        name="百度千帆",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://qianfan.baidubce.com/v2",
        models=_models(chat=("ernie-4.5-turbo-128k",)),
        docs_url="https://cloud.baidu.com/doc/WENXINWORKSHOP/",
    ),
    ProviderPreset(
        id="hunyuan",
        name="腾讯混元",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.hunyuan.cloud.tencent.com/v1",
        models=_models(chat=("hunyuan-turbos-latest",)),
        docs_url="https://cloud.tencent.com/document/product/1729",
    ),
    ProviderPreset(
        id="spark",
        name="讯飞星火",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://spark-api-open.xf-yun.com/v1",
        models=_models(chat=("generalv3.5", "4.0Ultra")),
        docs_url="https://www.xfyun.cn/doc/spark/",
    ),
    ProviderPreset(
        id="nvidia",
        name="NVIDIA NIM",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://integrate.api.nvidia.com/v1",
        models=_models(chat=("meta/llama-3.1-70b-instruct",)),
        docs_url="https://docs.nvidia.com/nim/",
    ),
    ProviderPreset(
        id="cerebras",
        name="Cerebras",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="https://api.cerebras.ai/v1",
        models=_models(chat=("llama-3.3-70b",)),
        docs_url="https://inference-docs.cerebras.ai/",
    ),
    ProviderPreset(
        id="ollama",
        name="Ollama",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="http://127.0.0.1:11434/v1",
        models=_models(chat=("llama3.2", "qwen3")),
        api_key_required=False,
    ),
    ProviderPreset(
        id="lmstudio",
        name="LM Studio",
        provider_type="openai_compatible",
        categories=(ProviderCategory.CHAT,),
        base_url="http://127.0.0.1:1234/v1",
        models=_models(chat=("local-model",)),
        api_key_required=False,
    ),
)


def provider_type_supports(provider_type: str, category: str) -> bool:
    spec = PROVIDER_TYPES.get(provider_type)
    return spec is not None and category in spec.categories


def get_provider_type(provider_type: str) -> ProviderTypeSpec | None:
    return PROVIDER_TYPES.get(provider_type)


def catalog_payload() -> dict[str, Any]:
    return {
        "types": [
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "categories": list(spec.categories),
                "default_base_url": spec.default_base_url,
                "api_key_required": spec.api_key_required,
                "docs_url": spec.docs_url,
            }
            for spec in PROVIDER_TYPES.values()
        ],
        "presets": [
            {
                "id": preset.id,
                "name": preset.name,
                "provider_type": preset.provider_type,
                "categories": list(preset.categories),
                "base_url": preset.base_url,
                "models": {
                    category: list(models) for category, models in preset.models.items() if models
                },
                "docs_url": preset.docs_url,
                "api_key_required": preset.api_key_required,
                "voice": preset.voice,
            }
            for preset in PROVIDER_PRESETS
        ],
    }
