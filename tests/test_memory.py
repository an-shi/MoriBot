"""Memory engine wiring: recall injection, ingest queueing and settings."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import httpx
from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.memory import MemoryClient, MemoryRecall, MemoryServiceSettings
from moribot.core.paths import AppPaths
from moribot.core.provider import ChatMessage, ChatProvider, ProviderResponse
from moribot.dashboard.app import create_app


class FakeChatProvider(ChatProvider):
    def __init__(self, provider_id: str) -> None:
        super().__init__(provider_id, model="fake-chat-model")
        self.calls: list[list[ChatMessage]] = []

    async def chat(self, messages: list[ChatMessage], **kwargs: Any) -> ProviderResponse:
        self.calls.append(list(messages))
        return ProviderResponse(text="我记得你喜欢绿茶。")


class FakeMemory:
    ingest_enabled = True

    def __init__(self) -> None:
        self.recall_calls: list[dict[str, Any]] = []
        self.ingest_calls: list[dict[str, Any]] = []
        self.ingested = threading.Event()

    async def recall(self, **kwargs: Any) -> MemoryRecall:
        self.recall_calls.append(kwargs)
        return MemoryRecall(
            text="- [用户明确表达 · preference] 用户喜欢喝绿茶",
            items=1,
            tokens=18,
            available=True,
        )

    async def ingest(self, **kwargs: Any) -> bool:
        self.ingest_calls.append(kwargs)
        self.ingested.set()
        return True


class FakeServiceManager:
    def __init__(self) -> None:
        self.settings = MemoryServiceSettings(enabled=True)
        self.base_url = "http://memory.test"
        self.requests: list[dict[str, Any]] = []

    async def ensure_started(self) -> bool:
        return True

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        self.requests.append({"method": method, "path": path, **kwargs})
        if path == "context":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": {
                        "context": "- [用户明确表达 · fact] 用户住在上海",
                        "context_tokens": 12,
                        "items": [{"id": "mem-1"}],
                    },
                },
            )
        return httpx.Response(200, json={"status": "ok", "data": {"task_id": "task-1"}})


def _build_app(tmp_path, *, memory: bool = False):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    return create_app(paths=paths, config=config, memory=memory), paths


def _login(client: TestClient, app) -> dict[str, str]:
    credentials = app.state.core.initial_credentials
    assert credentials is not None
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials.password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _seed_chat(
    client: TestClient,
    app,
    headers: dict[str, str],
) -> tuple[int, str, dict[str, str], ChatProvider]:
    provider = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "category": "chat",
            "name": "Chat",
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test",
            "model": "fake-chat-model",
            "options": {},
            "is_default": True,
        },
    )
    assert provider.status_code == 200, provider.text
    provider_id = provider.json()["data"]["id"]
    chat_provider = FakeChatProvider(str(provider_id))
    app.state.core.provider_manager.register(chat_provider)

    character = client.post(
        "/api/v1/characters",
        headers=headers,
        json={
            "name": "Mori",
            "avatar": "",
            "description": "安静的陪伴者",
            "persona": "温柔、真诚，回复简短自然。",
            "chat_provider_id": provider_id,
            "speech_provider_id": None,
            "image_provider_id": None,
            "enabled": True,
        },
    )
    assert character.status_code == 200, character.text
    character_id = character.json()["data"]["id"]

    pairing = client.post("/api/v1/mobile/pairing-code", headers=headers)
    code = pairing.json()["data"]["code"]
    paired = client.post(
        "/api/v1/mobile/pair",
        json={"code": code, "device_name": "Pixel"},
    )
    device_headers = {"Authorization": f"Bearer {paired.json()['data']['device_token']}"}
    conversation = client.post(
        "/api/v1/mobile/app/conversations",
        headers=device_headers,
        json={"character_id": character_id},
    )
    assert conversation.status_code == 200, conversation.text
    return (
        character_id,
        conversation.json()["data"]["id"],
        device_headers,
        chat_provider,
    )


def test_mobile_chat_injects_recall_and_queues_ingest(tmp_path):
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        character_id, conversation_id, device_headers, chat = _seed_chat(
            client, app, headers
        )
        memory = FakeMemory()
        app.state.mobile_chat_service.memory = memory

        response = client.post(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            json={"content": "我今天想喝点茶", "client_message_id": "memory-1"},
        )
        assert response.status_code == 200, response.text

        assert len(memory.recall_calls) == 1
        recall = memory.recall_calls[0]
        assert recall["user_id"] == "admin"
        assert recall["character_id"] == str(character_id)
        assert recall["conversation_id"] == conversation_id
        assert recall["query"] == "我今天想喝点茶"
        assert "用户喜欢喝绿茶" in chat.calls[0][0].content
        assert "不是用户本轮输入" in chat.calls[0][0].content

        assert memory.ingested.wait(2), "memory ingest was not queued"
        ingest = memory.ingest_calls[0]
        assert ingest["character_id"] == str(character_id)
        assert ingest["character_name"] == "Mori"
        assert ingest["conversation_id"] == conversation_id
        assert [message["role"] for message in ingest["messages"]] == ["user", "assistant"]
        assert ingest["messages"][0]["content"] == "我今天想喝点茶"

        retried = client.post(
            f"/api/v1/mobile/app/conversations/{conversation_id}/messages",
            headers=device_headers,
            json={"content": "我今天想喝点茶", "client_message_id": "memory-1"},
        )
        assert retried.status_code == 200
        time.sleep(0.1)
        assert len(memory.ingest_calls) == 1


def test_memory_client_sends_principal_headers_and_payloads(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    manager = FakeServiceManager()
    client = MemoryClient(manager, config)

    recall = client.config.get("memory.recall.limit")
    assert recall == 8

    import asyncio

    result = asyncio.run(
        client.recall(
            user_id="admin",
            character_id="7",
            conversation_id="conv-7",
            query="我喜欢什么",
        )
    )
    assert result.available is True
    assert result.items == 1
    request = manager.requests[0]
    assert request["path"] == "context"
    assert request["headers"]["X-Mori-User-Id"] == "admin"
    assert request["headers"]["X-Mori-Character-Id"] == "7"
    assert request["headers"]["X-Mori-Conversation-Id"] == "conv-7"
    assert request["headers"]["X-Mori-Role"] == "service"
    assert request["headers"]["Content-Type"] == "application/json"
    payload = json.loads(request["content"])
    assert payload["mode"] == "recall"
    assert payload["record_access"] is True

    queued = asyncio.run(
        client.ingest(
            user_id="admin",
            character_id="7",
            character_name="吃白饭的大肥鱼",
            conversation_id="conv-7",
            messages=[{"id": "1", "role": "user", "content": "我喜欢绿茶"}],
        )
    )
    assert queued is True
    ingest_request = manager.requests[1]
    assert ingest_request["path"] == "conversations/ingest"
    assert "X-Mori-Character-Name" not in ingest_request["headers"]
    ingest_payload = json.loads(ingest_request["content"])
    assert ingest_payload["async_mode"] is True
    assert ingest_payload["character_id"] == "7"
    assert ingest_payload["character_name"] == "吃白饭的大肥鱼"
    assert ingest_payload["messages"][0]["content"] == "我喜欢绿茶"


def test_memory_settings_are_exposed_and_can_be_disabled(tmp_path):
    app, _ = _build_app(tmp_path)
    assert app.state.mobile_chat_service.memory is app.state.memory_client
    with TestClient(app) as client:
        headers = _login(client, app)
        settings = client.get("/api/v1/system/settings", headers=headers)
        assert settings.status_code == 200
        assert settings.json()["data"]["memory"] == {"enabled": False, "auto_start": True}

        updated = client.patch(
            "/api/v1/system/settings",
            headers=headers,
            json={
                "health_check": {"enabled": False, "times": []},
                "memory": {"enabled": False, "auto_start": False},
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["memory"] == {"enabled": False, "auto_start": False}

        info = client.get("/api/v1/system/info", headers=headers)
        assert info.status_code == 200
        memory = info.json()["data"]["memory"]
        assert memory["enabled"] is False
        assert memory["running"] is False
