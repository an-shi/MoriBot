"""Character diary settings, generation and API tests."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.core.provider import ChatMessage, ChatProvider, ProviderResponse
from moribot.dashboard.app import create_app


class FakeDiaryChatProvider(ChatProvider):
    def __init__(self, provider_id: str) -> None:
        super().__init__(provider_id, model="fake-diary-model")
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ProviderResponse:
        self.calls.append(list(messages))
        system = messages[0].content if messages else ""
        if "角色日记生成器" in system:
            return ProviderResponse(text="今天和对方聊了聊公园，心情很安静。")
        return ProviderResponse(text="我在听。")


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


def _provider(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "category": "chat",
            "name": "Chat",
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "fake-diary-model",
            "options": {},
            "is_default": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


def _pair(client: TestClient, headers: dict[str, str]) -> str:
    pairing = client.post("/api/v1/mobile/pairing-code", headers=headers)
    code = pairing.json()["data"]["code"]
    paired = client.post(
        "/api/v1/mobile/pair",
        json={"code": code, "device_name": "Pixel"},
    )
    assert paired.status_code == 200, paired.text
    return paired.json()["data"]["device_token"]


def _character(chat_id: int) -> dict:
    return {
        "name": "Mori",
        "avatar": "",
        "description": "安静的陪伴者",
        "persona": "温柔、真诚，喜欢记录日常。",
        "chat_provider_id": chat_id,
        "speech_provider_id": None,
        "image_provider_id": None,
        "diary_enabled": True,
        "diary_time": "23:30",
        "enabled": True,
    }


def test_diary_settings_character_override_generation_and_mobile_list(tmp_path):
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        chat_id = _provider(client, headers)
        provider = FakeDiaryChatProvider(str(chat_id))
        app.state.core.provider_manager.register(provider)

        created = client.post("/api/v1/characters", headers=headers, json=_character(chat_id))
        assert created.status_code == 200, created.text
        character = created.json()["data"]
        assert character["diary_enabled"] is True
        assert character["diary_time"] == "23:30"

        invalid_time = client.patch(
            f"/api/v1/characters/{character['id']}",
            headers=headers,
            json={"diary_time": "25:00"},
        )
        assert invalid_time.status_code == 400

        updated = client.patch(
            f"/api/v1/characters/{character['id']}",
            headers=headers,
            json={"diary_enabled": False, "diary_time": "22:45"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["diary_enabled"] is False
        assert updated.json()["data"]["diary_time"] == "22:45"

        settings = client.patch(
            "/api/v1/system/settings",
            headers=headers,
            json={
                "health_check": {"enabled": False, "times": []},
                "diary": {"enabled": True, "time": "21:30"},
            },
        )
        assert settings.status_code == 200, settings.text
        assert settings.json()["data"]["diary"] == {"enabled": True, "time": "21:30"}

        device_token = _pair(client, headers)
        device_headers = {"Authorization": f"Bearer {device_token}"}
        conversation = client.post(
            "/api/v1/mobile/app/conversations",
            headers=device_headers,
            json={"character_id": character["id"]},
        )
        assert conversation.status_code == 200, conversation.text
        conversation_id = conversation.json()["data"]["id"]
        sent = client.post(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            json={"content": "今天去了公园", "client_message_id": "diary-1"},
        )
        assert sent.status_code == 200, sent.text

        generated = client.post(
            "/api/v1/diaries/generate",
            headers=headers,
            json={"character_id": character["id"]},
        )
        assert generated.status_code == 200, generated.text
        diary = generated.json()["data"]
        assert diary["character_id"] == character["id"]
        assert diary["character_name"] == "Mori"
        assert diary["content"] == "今天和对方聊了聊公园，心情很安静。"
        assert diary["source_message_count"] == 2

        listed = client.get(
            f"/api/v1/diaries?character_id={character['id']}",
            headers=headers,
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["data"]] == [diary["id"]]

        mobile_listed = client.get(
            f"/api/v1/mobile/app/diaries?character_id={character['id']}",
            headers=device_headers,
        )
        assert mobile_listed.status_code == 200
        assert mobile_listed.json()["data"][0]["content"] == diary["content"]

        deleted = client.delete(
            f"/api/v1/diaries/{diary['id']}",
            headers=headers,
        )
        assert deleted.status_code == 200
        empty = client.get("/api/v1/diaries", headers=headers)
        assert empty.json()["data"] == []
