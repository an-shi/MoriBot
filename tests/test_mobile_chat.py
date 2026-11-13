"""MoriMobile conversation persistence, history and media tests."""

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
        return ProviderResponse(text=f"回复 {len(self.calls)}", usage={"total_tokens": 12})


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
    return create_app(paths=paths, config=config), paths


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


def test_mobile_conversation_survives_restart(tmp_path):
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        chat_id = _provider(client, headers, "chat", "Chat", "fake-chat-model")
        chat = FakeChatProvider(str(chat_id))
        app.state.core.provider_manager.register(chat)

        created = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("Mori", chat_provider_id=chat_id),
        )
        assert created.status_code == 200, created.text
        character_id = created.json()["data"]["id"]

        device_token = _pair(client, headers)
        device_headers = {"Authorization": f"Bearer {device_token}"}

        conversation_response = client.post(
            "/api/v1/mobile/app/conversations",
            headers=device_headers,
            json={"character_id": character_id},
        )
        assert conversation_response.status_code == 200
        conversation_id = conversation_response.json()["data"]["id"]

        sent = client.post(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            json={"content": "持久化测试", "client_message_id": "restart-1"},
        )
        assert sent.status_code == 200, sent.text

    restarted, _ = _build_app(tmp_path)
    with TestClient(restarted) as client:
        device_headers = {"Authorization": f"Bearer {device_token}"}
        conversations = client.get(
            "/api/v1/mobile/app/conversations",
            headers=device_headers,
        )
        assert conversations.status_code == 200, conversations.text
        items = conversations.json()["data"]["conversations"]
        assert len(items) == 1
        assert items[0]["id"] == conversation_id
        assert items[0]["message_count"] == 2

        messages = client.get(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
        )
        assert messages.status_code == 200
        rows = messages.json()["data"]["messages"]
        assert [row["role"] for row in rows] == ["user", "assistant"]
        assert rows[0]["content"] == "持久化测试"
        assert rows[1]["content"] == "回复 1"


def test_mobile_conversations_messages_and_media(tmp_path):
    app, paths = _build_app(tmp_path)
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

        hidden = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("Hidden", chat_provider_id=chat_id),
        )
        assert hidden.status_code == 200, hidden.text
        hidden_id = hidden.json()["data"]["id"]
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
        hidden_conversation = client.post(
            "/api/v1/mobile/app/conversations",
            headers=device_headers,
            json={"character_id": hidden_id},
        )
        assert hidden_conversation.status_code == 404

        listing = client.get("/api/v1/mobile/app/characters", headers=device_headers)
        assert listing.status_code == 200, listing.text
        characters = listing.json()["data"]
        assert [item["id"] for item in characters] == [character_id]
        assert characters[0]["chat_available"] is True
        assert characters[0]["speech_available"] is True

        unauthenticated = client.get("/api/v1/mobile/app/characters", headers=headers)
        assert unauthenticated.status_code == 401

        conversation_response = client.post(
            "/api/v1/mobile/app/conversations",
            headers=device_headers,
            json={"character_id": character_id},
        )
        assert conversation_response.status_code == 200, conversation_response.text
        conversation = conversation_response.json()["data"]
        conversation_id = conversation["id"]
        assert conversation["title"] == ""
        assert conversation["message_count"] == 0
        assert conversation["character_available"] is True

        first = client.post(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            json={
                "content": "你好",
                "client_message_id": "local-1",
                "speech": True,
            },
        )
        assert first.status_code == 200, first.text
        first_data = first.json()["data"]
        assert first_data["conversation"]["title"] == "你好"
        assert first_data["conversation"]["message_count"] == 2
        assert first_data["conversation"]["last_message_preview"] == "回复 1"
        assert first_data["user_message"]["role"] == "user"
        assert first_data["user_message"]["content"] == "你好"
        assert first_data["assistant_message"]["role"] == "assistant"
        assert first_data["assistant_message"]["content"] == "回复 1"
        assert first_data["assistant_message"]["speech"]["mime_type"] == "audio/mpeg"
        speech_url = first_data["assistant_message"]["speech"]["url"]
        assert speech_url.startswith("/api/v1/mobile/app/media/")
        assert speech.texts == ["回复 1"]
        assert [message.role for message in chat.calls[0]] == ["system", "user"]
        assert "Mori" in chat.calls[0][0].content
        assert "安静的陪伴者" in chat.calls[0][0].content

        media_files = list(paths.media_dir.glob("*/*.mp3"))
        assert len(media_files) == 1
        media = client.get(speech_url, headers=device_headers)
        assert media.status_code == 200
        assert media.content == b"fake-audio"
        assert client.get(speech_url).status_code == 401

        second = client.post(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            json={
                "content": "继续",
                "client_message_id": "local-2",
                "speech": False,
            },
        )
        assert second.status_code == 200, second.text
        second_data = second.json()["data"]
        assert second_data["conversation"]["message_count"] == 4
        assert [message.role for message in chat.calls[1]] == [
            "system",
            "user",
            "assistant",
            "user",
        ]
        assert chat.calls[1][1].content == "你好"
        assert chat.calls[1][2].content == "回复 1"
        assert chat.calls[1][3].content == "继续"

        retried = client.post(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            json={
                "content": "继续",
                "client_message_id": "local-2",
                "speech": False,
            },
        )
        assert retried.status_code == 200, retried.text
        retried_data = retried.json()["data"]
        assert len(chat.calls) == 2
        assert retried_data["user_message"]["id"] == second_data["user_message"]["id"]
        assert (
            retried_data["assistant_message"]["id"]
            == second_data["assistant_message"]["id"]
        )

        conversations = client.get(
            "/api/v1/mobile/app/conversations",
            headers=device_headers,
        )
        assert conversations.status_code == 200
        conversation_page = conversations.json()["data"]
        assert conversation_page["has_more"] is False
        assert len(conversation_page["conversations"]) == 1
        assert conversation_page["conversations"][0]["id"] == conversation_id
        assert conversation_page["conversations"][0]["message_count"] == 4

        detail = client.get(
            f"/api/v1/mobile/app/conversations/{conversation_id}",
            headers=device_headers,
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["last_message_preview"] == "回复 2"

        latest = client.get(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            params={"limit": 3},
        )
        assert latest.status_code == 200, latest.text
        latest_data = latest.json()["data"]
        assert [item["role"] for item in latest_data["messages"]] == [
            "assistant",
            "user",
            "assistant",
        ]
        assert latest_data["has_more"] is True
        assert latest_data["earliest_id"] == latest_data["messages"][0]["id"]
        assert latest_data["latest_id"] == latest_data["messages"][-1]["id"]

        older = client.get(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            params={"before_id": latest_data["earliest_id"]},
        )
        assert older.status_code == 200
        older_data = older.json()["data"]
        assert [item["role"] for item in older_data["messages"]] == ["user"]
        assert older_data["messages"][0]["content"] == "你好"
        assert older_data["has_more"] is False

        newer = client.get(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            params={"after_id": older_data["latest_id"], "limit": 2},
        )
        assert newer.status_code == 200
        assert len(newer.json()["data"]["messages"]) == 2

        conflict = client.get(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            params={"before_id": 1, "after_id": 1},
        )
        assert conflict.status_code == 400

        renamed = client.patch(
            f"/api/v1/mobile/app/conversations/{conversation_id}",
            headers=device_headers,
            json={"title": "晚间聊天"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["data"]["title"] == "晚间聊天"

        deleted = client.delete(
            f"/api/v1/mobile/app/conversations/{conversation_id}",
            headers=device_headers,
        )
        assert deleted.status_code == 200
        assert (
            client.get(
                f"/api/v1/mobile/app/conversations/{conversation_id}",
                headers=device_headers,
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
                headers=device_headers,
            ).status_code
            == 404
        )
        assert list(paths.media_dir.glob("*/*.mp3")) == []
        assert client.get(speech_url, headers=device_headers).status_code == 404
