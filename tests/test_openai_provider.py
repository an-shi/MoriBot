"""HTTP contract tests for the OpenAI-compatible provider adapters."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from moribot.core.provider import ChatMessage
from moribot.core.provider.openai_compatible import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleImageProvider,
    OpenAICompatibleSpeechProvider,
)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        self.rfile.read(length)

        if self.path.endswith("/chat/completions"):
            self._json(
                {
                    "choices": [{"message": {"role": "assistant", "content": "pong"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            )
            return
        if self.path.endswith("/audio/speech"):
            body = b"fake-mp3"
            self.send_response(200)
            self.send_header("content-type", "audio/mpeg")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.endswith("/images/generations"):
            self._json(
                {
                    "data": [
                        {
                            "b64_json": base64.b64encode(b"fake-png").decode("ascii"),
                            "revised_prompt": "a leaf",
                        }
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


def test_openai_compatible_chat_speech_and_image():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/v1"
    config = {"base_url": base_url, "api_key": "test-key"}

    chat = OpenAICompatibleChatProvider("1", model="test", config=config)
    speech = OpenAICompatibleSpeechProvider("2", model="tts", config=config)
    images = OpenAICompatibleImageProvider("3", model="image", config=config)

    async def run() -> None:
        try:
            reply = await chat.chat([ChatMessage(role="user", content="ping")])
            assert reply.text == "pong"
            assert reply.usage["completion_tokens"] == 1

            audio = await speech.synthesize("hello")
            assert audio.audio == b"fake-mp3"
            assert audio.format == "mp3"

            generated = await images.generate("a leaf")
            assert generated[0].data == b"fake-png"
            assert generated[0].revised_prompt == "a leaf"
        finally:
            await chat.close()
            await speech.close()
            await images.close()
            server.shutdown()
            thread.join(timeout=2)

    asyncio.run(run())
