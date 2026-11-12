"""Main model tool orchestration tests."""

from __future__ import annotations

from typing import Any

from moribot.core.provider import (
    ChatMessage,
    ChatProvider,
    GeneratedImage,
    ImageProvider,
    ModelGateway,
    ProviderManager,
    ProviderResponse,
    SpeechProvider,
    SpeechResult,
)


class FakeChatProvider(ChatProvider):
    def __init__(self) -> None:
        super().__init__("chat-1", model="fake-chat")
        self.calls: list[list[Any]] = []

    async def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ProviderResponse:
        self.calls.append(list(messages))
        if len(self.calls) == 1:
            return ProviderResponse(
                text="",
                tool_calls=[
                    {
                        "id": "call-speech",
                        "type": "function",
                        "function": {
                            "name": "generate_speech",
                            "arguments": '{"text": "hello out loud"}',
                        },
                    },
                    {
                        "id": "call-image",
                        "type": "function",
                        "function": {
                            "name": "generate_image",
                            "arguments": '{"prompt": "a green leaf", "size": "512x512"}',
                        },
                    },
                ],
            )
        return ProviderResponse(text="Here is your media.")


class FakeSpeechProvider(SpeechProvider):
    def __init__(self) -> None:
        super().__init__("speech-1", model="fake-tts")
        self.texts: list[str] = []

    async def synthesize(self, text: str, **kwargs: Any) -> SpeechResult:
        self.texts.append(text)
        return SpeechResult(audio=b"fake-audio", format="mp3", model=self.model)


class FakeImageProvider(ImageProvider):
    def __init__(self) -> None:
        super().__init__("image-1", model="fake-image")
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs: Any) -> list[GeneratedImage]:
        self.prompts.append(prompt)
        return [GeneratedImage(data=b"fake-image", mime_type="image/png")]


async def test_gateway_executes_speech_and_image_tools():
    manager = ProviderManager()
    chat = FakeChatProvider()
    speech = FakeSpeechProvider()
    images = FakeImageProvider()
    manager.register(chat, default=True)
    manager.register(speech, default=True)
    manager.register(images, default=True)

    gateway = ModelGateway(manager)
    tools = gateway.tool_definitions()
    assert {tool["function"]["name"] for tool in tools} == {
        "generate_speech",
        "generate_image",
    }

    reply = await gateway.chat([ChatMessage(role="user", content="Show and tell")])
    assert reply.text == "Here is your media."
    assert reply.speech is not None
    assert reply.speech.audio == b"fake-audio"
    assert reply.images[0].data == b"fake-image"
    assert speech.texts == ["hello out loud"]
    assert images.prompts == ["a green leaf"]
    assert len(chat.calls) == 2

    # The second chat call contains tool results for both generated media.
    tool_messages = [
        message
        for message in chat.calls[1]
        if isinstance(message, dict) and message.get("role") == "tool"
    ]
    assert len(tool_messages) == 2


async def test_gateway_omits_tools_when_media_models_are_missing():
    manager = ProviderManager()
    manager.register(FakeChatProvider(), default=True)
    gateway = ModelGateway(manager)
    assert gateway.tool_definitions() == []
