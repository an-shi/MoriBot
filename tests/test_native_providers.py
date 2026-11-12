"""HTTP contract tests for native provider adapters."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from moribot.core.provider import ChatMessage
from moribot.core.provider.anthropic import AnthropicChatProvider
from moribot.core.provider.azure_openai import AzureOpenAIChatProvider
from moribot.core.provider.elevenlabs import ElevenLabsSpeechProvider
from moribot.core.provider.gemini import GeminiChatProvider, GeminiImageProvider


class _Handler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        raw_body = self.rfile.read(length)
        try:
            body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            body = {}
        type(self).requests.append({"path": self.path, "body": body, "headers": dict(self.headers)})

        if self.path.endswith("/messages"):
            self._json(
                {
                    "content": [
                        {"type": "text", "text": "claude reply"},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "generate_image",
                            "input": {"prompt": "leaf"},
                        },
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 7},
                }
            )
            return
        if ":generateContent" in self.path:
            if "image" in self.path:
                encoded = base64.b64encode(b"gemini-image").decode("ascii")
                self._json(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "image/png",
                                                "data": encoded,
                                            }
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                )
            else:
                self._json(
                    {
                        "candidates": [
                            {
                                "content": {
                                    "parts": [
                                        {"text": "gemini reply"},
                                        {
                                            "functionCall": {
                                                "name": "generate_speech",
                                                "args": {"text": "hello"},
                                            }
                                        },
                                    ]
                                }
                            }
                        ],
                        "usageMetadata": {
                            "promptTokenCount": 3,
                            "candidatesTokenCount": 4,
                        },
                    }
                )
            return
        if "/chat/completions" in self.path:
            self._json(
                {
                    "choices": [{"message": {"role": "assistant", "content": "azure reply"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                }
            )
            return
        if "/text-to-speech/" in self.path:
            audio = b"elevenlabs-audio"
            self.send_response(200)
            self.send_header("content-type", "audio/mpeg")
            self.send_header("content-length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
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


def test_native_providers_http_contracts():
    _Handler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_port}"

    anthropic = AnthropicChatProvider(
        "a",
        model="claude-test",
        config={"base_url": f"{root}/v1", "api_key": "anthropic-key"},
    )
    gemini = GeminiChatProvider(
        "g",
        model="gemini-test",
        config={"base_url": f"{root}/v1beta", "api_key": "gemini-key"},
    )
    gemini_image = GeminiImageProvider(
        "gi",
        model="gemini-2.5-flash-image",
        config={"base_url": f"{root}/v1beta", "api_key": "gemini-key"},
    )
    azure = AzureOpenAIChatProvider(
        "az",
        model="deployment-name",
        config={"base_url": root, "api_key": "azure-key", "api_version": "2024-10-21"},
    )
    eleven = ElevenLabsSpeechProvider(
        "e",
        model="eleven_multilingual_v2",
        config={"base_url": f"{root}/v1", "api_key": "eleven-key"},
    )

    async def run() -> None:
        try:
            reply = await anthropic.chat([ChatMessage(role="user", content="hi")])
            assert reply.text == "claude reply"
            assert reply.tool_calls[0]["function"]["name"] == "generate_image"
            assert reply.usage["completion_tokens"] == 7

            gemini_reply = await gemini.chat([ChatMessage(role="user", content="hi")])
            assert gemini_reply.text == "gemini reply"
            assert gemini_reply.tool_calls[0]["function"]["name"] == "generate_speech"

            generated = await gemini_image.generate("a leaf")
            assert generated[0].data == b"gemini-image"

            azure_reply = await azure.chat([ChatMessage(role="user", content="hi")])
            assert azure_reply.text == "azure reply"

            audio = await eleven.synthesize("hello")
            assert audio.audio == b"elevenlabs-audio"
            assert audio.format == "mp3"
        finally:
            await anthropic.close()
            await gemini.close()
            await gemini_image.close()
            await azure.close()
            await eleven.close()
            server.shutdown()
            thread.join(timeout=2)

    asyncio.run(run())

    by_path = {request["path"]: request for request in _Handler.requests}
    assert by_path["/v1/messages"]["headers"]["x-api-key"] == "anthropic-key"
    assert by_path["/v1/messages"]["headers"]["anthropic-version"] == "2023-06-01"
    assert any(path.startswith("/openai/deployments/deployment-name/") for path in by_path)
    azure_request = next(
        request
        for path, request in by_path.items()
        if path.startswith("/openai/deployments/deployment-name/")
    )
    assert azure_request["headers"]["api-key"] == "azure-key"
    assert "api-version=2024-10-21" in azure_request["path"]
    eleven_request = next(
        request for path, request in by_path.items() if "/text-to-speech/" in path
    )
    assert eleven_request["headers"]["xi-api-key"] == "eleven-key"
