"""MoriMobile character listing and chat generation tests."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.core.provider import (
    ChatMessage,
    ChatProvider,
    ProviderResponse,
    SpeechProvider,
    SpeechResult,
)
from moribot.dashboard.app import create_app


class FakeChatProvider(ChatProvider):
    def __init__(self, provider_id: str) -> None:
        super().__init__(provider_id, model="fake-chat-model")
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ProviderResponse:
        self.calls.append(list(messages))
        return ProviderResponse(text="我在这里，慢慢说。", usage={"total_tokens": 12})


class FakeSpeechProvider(SpeechProvider):
    def __init__(self, provider_id: str) -> None:
        super().__init__(provider_id, model="fake-speech-model")
        self.texts: list[str] = []

    async def synthesize(self, text: str, **kwargs: Any) -> SpeechResult:
        self.texts.append(text)
        return SpeechResult(audio=b"fake-audio", format="mp3", model=self.model)


def _build_app(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    return create_app(paths=paths, config=config)


def _login(client: TestClient, app) -> dict[str, str]:
    credentials = app.state.core.initial_credentials
    assert credentials is not None
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials.password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _provider(
    client: TestClient,
    headers: dict[str, str],
    category: str,
    name: str,
    model: str,
) -> int:
    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "category": category,
            "name": name,
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": model,
            "options": {},
            "is_default": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def _pair(client: TestClient, headers: dict[str, str]) -> str:
    pairing = client.post("/api/v1/mobile/pairing-code", headers=headers)
    assert pairing.status_code == 200
    code = pairing.json()["data"]["code"]
    paired = client.post(
        "/api/v1/mobile/pair",
        json={"code": code, "device_name": "Pixel"},
    )
    assert paired.status_code == 200, paired.text
    return paired.json()["data"]["device_token"]


def _character(
    name: str,
    *,
    chat_provider_id: int,
    speech_provider_id: int | None = None,
) -> dict:
    return {
        "name": name,
        "avatar": "",
        "description": "安静的陪伴者",
        "persona": "温柔、真诚，回复简短自然。",
        "chat_provider_id": chat_provider_id,
        "speech_provider_id": speech_provider_id,
        "image_provider_id": None,
        "enabled": True,
    }


def test_mobile_character_list_and_chat_generation(tmp_path):
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        chat_id = _provider(client, headers, "chat", "Chat", "fake-chat-model")
        speech_id = _provider(client, headers, "speech", "Speech", "fake-speech-model")

        chat = FakeChatProvider(str(chat_id))
        speech = FakeSpeechProvider(str(speech_id))
        app.state.core.provider_manager.register(chat)
        app.state.core.provider_manager.register(speech)

        created = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("Mori", chat_provider_id=chat_id, speech_provider_id=speech_id),
        )
        assert created.status_code == 200, created.text
        character_id = created.json()["data"]["id"]

        disabled = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("Hidden", chat_provider_id=chat_id),
        )
        assert disabled.status_code == 200, disabled.text
        hidden_id = disabled.json()["data"]["id"]
        assert (
            client.patch(
                f"/api/v1/characters/{hidden_id}",
                headers=headers,
                json={"enabled": False},
            ).status_code
            == 200
        )

        device_token = _pair(client, headers)
        device_headers = {"Authorization": f"Bearer {device_token}"}

        listing = client.get("/api/v1/mobile/app/characters", headers=device_headers)
        assert listing.status_code == 200, listing.text
        characters = listing.json()["data"]
        assert [item["id"] for item in characters] == [character_id]
        assert characters[0]["chat_available"] is True
        assert characters[0]["speech_available"] is True

        unauthenticated = client.get(
            "/api/v1/mobile/app/characters",
            headers=headers,
        )
        assert unauthenticated.status_code == 401

        response = client.post(
            "/api/v1/mobile/app/chat",
            headers=device_headers,
            json={
                "character_id": character_id,
                "client_message_id": "local-42",
                "messages": [
                    {"role": "user", "content": "你好"},
                    {"role": "assistant", "content": "在的。"},
                    {"role": "user", "content": "今天有点累"},
                ],
                "speech": True,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["client_message_id"] == "local-42"
        assert data["character_id"] == character_id
        assert data["text"] == "我在这里，慢慢说。"
        assert data["chat_model"]["provider_id"] == str(chat_id)
        assert data["chat_model"]["model"] == "fake-chat-model"
        assert data["speech"]["mime_type"] == "audio/mpeg"
        assert data["speech"]["data_url"].startswith("data:audio/mpeg;base64,")
        assert speech.texts == ["我在这里，慢慢说。"]

        assert len(chat.calls) == 1
        sent = chat.calls[0]
        assert [message.role for message in sent] == [
            "system",
            "user",
            "assistant",
            "user",
        ]
        assert "Mori" in sent[0].content
        assert "安静的陪伴者" in sent[0].content
        assert "温柔、真诚" in sent[0].content

        hidden_chat = client.post(
            "/api/v1/mobile/app/chat",
            headers=device_headers,
            json={
                "character_id": hidden_id,
                "messages": [{"role": "user", "content": "在吗"}],
            },
        )
        assert hidden_chat.status_code == 404

        not_last_user = client.post(
            "/api/v1/mobile/app/chat",
            headers=device_headers,
            json={
                "character_id": character_id,
                "messages": [{"role": "assistant", "content": "我先说"}],
            },
        )
        assert not_last_user.status_code == 400
