"""Model list discovery and capability inference tests."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from moribot.core.provider.discovery import infer_capabilities, list_models


class _ModelsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/minimax/v1/models"):
            self._json(
                {
                    "data": [
                        {"id": "MiniMax-M3.1-Flash", "owned_by": "minimax"},
                        {"id": "MiniMax-M3", "owned_by": "minimax"},
                        {"id": "MiniMax-M2.7", "owned_by": "minimax"},
                        {"id": "MiniMax-M2.7-highspeed", "owned_by": "minimax"},
                        {"id": "MiniMax-M2.5", "owned_by": "minimax"},
                        {"id": "MiniMax-M2.1", "owned_by": "minimax"},
                        {"id": "MiniMax-M2", "owned_by": "minimax"},
                    ]
                }
            )
            return
        if self.path.startswith("/v1/models"):
            self._json(
                {
                    "data": [
                        {"id": "gpt-4o", "owned_by": "openai"},
                        {"id": "text-embedding-3-small", "owned_by": "openai"},
                        {"id": "tts-1", "owned_by": "openai"},
                        {"id": "dall-e-3", "owned_by": "openai"},
                        {"id": "canopylabs/orpheus-v1-english", "owned_by": "groq"},
                        {"id": "Kwai-Kolors/Kolors", "owned_by": "siliconflow"},
                        {"id": "doubao-seedream-4-0-250828", "owned_by": "volcengine"},
                        {"id": "black-forest-labs/FLUX.1-schnell", "owned_by": "together"},
                        {
                            "id": "anthropic/claude-sonnet-4",
                            "owned_by": "openrouter",
                            "architecture": {
                                "input_modalities": ["text", "image"],
                                "output_modalities": ["text"],
                                "supported_parameters": ["tools", "temperature"],
                            },
                            "context_length": 200000,
                        },
                    ]
                }
            )
            return
        if self.path.startswith("/v1beta/models"):
            self._json(
                {
                    "models": [
                        {
                            "name": "models/gemini-2.5-flash",
                            "displayName": "Gemini 2.5 Flash",
                            "inputTokenLimit": 1048576,
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/text-embedding-004",
                            "supportedGenerationMethods": ["embedContent"],
                        },
                    ]
                }
            )
            return
        self.send_response(404)
        self.end_headers()

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


def test_discover_openai_models_filters_and_infers_vision():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"

    async def run():
        try:
            models = await list_models(
                provider_type="openai_compatible",
                category="chat",
                base_url=base_url,
                api_key="test",
            )
            by_id = {model.id: model for model in models}
            assert "gpt-4o" in by_id
            assert "text-embedding-3-small" not in by_id
            assert "tts-1" not in by_id
            assert "dall-e-3" not in by_id
            assert "canopylabs/orpheus-v1-english" not in by_id
            assert "Kwai-Kolors/Kolors" not in by_id
            assert "doubao-seedream-4-0-250828" not in by_id
            assert "black-forest-labs/FLUX.1-schnell" not in by_id
            assert "image" in by_id["gpt-4o"].capabilities["input"]
            assert by_id["gpt-4o"].capabilities["tools"] is True

            openrouter = by_id["anthropic/claude-sonnet-4"]
            assert openrouter.capabilities["source"] == "api"
            assert openrouter.capabilities["context_window"] == 200000
            assert openrouter.capabilities["input"] == ["image", "text"]

            speech = await list_models(
                provider_type="openai_compatible",
                category="speech",
                base_url=base_url,
                api_key="test",
            )
            assert {model.id for model in speech} == {
                "tts-1",
                "canopylabs/orpheus-v1-english",
            }
            assert speech[0].capabilities["output"] == ["audio"]

            image = await list_models(
                provider_type="openai_compatible",
                category="image",
                base_url=base_url,
                api_key="test",
            )
            image_ids = {model.id for model in image}
            assert {
                "dall-e-3",
                "Kwai-Kolors/Kolors",
                "doubao-seedream-4-0-250828",
                "black-forest-labs/FLUX.1-schnell",
            } <= image_ids
            assert "gpt-4o" not in image_ids
        finally:
            server.shutdown()
            thread.join(timeout=2)

    asyncio.run(run())


def test_discover_gemini_models_and_capabilities():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1beta"

    async def run():
        try:
            models = await list_models(
                provider_type="google_gemini",
                category="chat",
                base_url=base_url,
                api_key="test",
            )
            assert [model.id for model in models] == ["gemini-2.5-flash"]
            assert models[0].capabilities["context_window"] == 1048576
            assert "image" in models[0].capabilities["input"]
        finally:
            server.shutdown()
            thread.join(timeout=2)

    asyncio.run(run())


def test_manual_capability_inference_still_reasonable():
    capabilities = infer_capabilities("chat", "openai_compatible", "some-vl-model")
    assert "image" in capabilities["input"]
    assert capabilities["tools"] is True
    assert capabilities["source"] == "heuristic"


def test_discovery_filters_retired_minimax_models_and_falls_back_for_media():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/minimax/v1"

    async def run():
        try:
            chat = await list_models(
                provider_type="minimax",
                category="chat",
                base_url=base_url,
                api_key="test",
            )
            assert {model.id for model in chat} == {"MiniMax-M3.1-Flash", "MiniMax-M3"}

            speech = await list_models(
                provider_type="minimax",
                category="speech",
                base_url=base_url,
                api_key="test",
                fallback_models={
                    "speech": ["speech-2.8-turbo", "speech-2.8-hd"],
                    "image": ["MiniMax-H3-Image", "MiniMax-H3-Image-Highspeed"],
                },
            )
            assert {model.id for model in speech} == {
                "speech-2.8-turbo",
                "speech-2.8-hd",
            }
            assert speech[0].capabilities["output"] == ["audio"]

            image = await list_models(
                provider_type="minimax",
                category="image",
                base_url=base_url,
                api_key="test",
                fallback_models={
                    "speech": ["speech-2.8-turbo", "speech-2.8-hd"],
                    "image": ["MiniMax-H3-Image", "MiniMax-H3-Image-Highspeed"],
                },
            )
            assert {model.id for model in image} == {
                "MiniMax-H3-Image",
                "MiniMax-H3-Image-Highspeed",
            }
            assert image[0].capabilities["output"] == ["image"]
        finally:
            server.shutdown()
            thread.join(timeout=2)

    asyncio.run(run())
