"""Character card CRUD, provider overrides and avatar tests."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.dashboard.app import create_app

_TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2n0kAAAAASUVORK5CYII="
)


def _build_app(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    return create_app(paths=paths, config=config), paths


def _login(client, app) -> dict[str, str]:
    credentials = app.state.core.initial_credentials
    assert credentials is not None
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials.password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _provider(client, headers, category: str, name: str, model: str, default: bool = False):
    response = client.post(
        "/api/v1/providers",
        headers=headers,
        json={
            "category": category,
            "name": name,
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-secret",
            "model": model,
            "options": {},
            "is_default": default,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _character(name: str, **overrides):
    payload = {
        "name": name,
        "avatar": "",
        "description": "测试角色",
        "persona": "你是一个测试角色。",
        "greeting": "你好。",
        "chat_provider_id": None,
        "speech_provider_id": None,
        "image_provider_id": None,
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def test_character_crud_model_overrides_and_provider_cleanup(tmp_path):
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        default_chat = _provider(client, headers, "chat", "Chat Default", "gpt-main", True)
        extra_chat = _provider(client, headers, "chat", "Chat Extra", "gpt-extra")
        speech = _provider(client, headers, "speech", "Speech", "tts-1", True)
        image = _provider(client, headers, "image", "Image", "image-1", True)

        followed = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("跟随默认"),
        )
        assert followed.status_code == 200, followed.text
        followed_data = followed.json()["data"]
        assert followed_data["chat_provider_id"] is None
        assert followed_data["speech_provider_id"] is None
        assert followed_data["image_provider_id"] is None

        customized = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character(
                "自定义模型",
                chat_provider_id=extra_chat["id"],
                speech_provider_id=speech["id"],
                image_provider_id=image["id"],
            ),
        )
        assert customized.status_code == 200, customized.text
        custom_data = customized.json()["data"]
        assert custom_data["chat_provider_id"] == extra_chat["id"]

        duplicate = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("跟随默认"),
        )
        assert duplicate.status_code == 409

        wrong_category = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("错误模型", chat_provider_id=speech["id"]),
        )
        assert wrong_category.status_code == 400

        switched = client.patch(
            f"/api/v1/characters/{custom_data['id']}",
            headers=headers,
            json={"chat_provider_id": None, "enabled": False},
        )
        assert switched.status_code == 200
        assert switched.json()["data"]["chat_provider_id"] is None
        assert switched.json()["data"]["enabled"] is False

        deleted_provider = client.delete(
            f"/api/v1/providers/{extra_chat['id']}",
            headers=headers,
        )
        assert deleted_provider.status_code == 200
        listed = client.get("/api/v1/characters", headers=headers)
        assert listed.status_code == 200
        by_name = {item["name"]: item for item in listed.json()["data"]}
        assert by_name["自定义模型"]["chat_provider_id"] is None
        assert by_name["自定义模型"]["speech_provider_id"] == speech["id"]
        assert default_chat["is_default"] is True


def test_character_avatar_upload_and_cleanup(tmp_path):
    app, paths = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        created = client.post(
            "/api/v1/characters",
            headers=headers,
            json=_character("头像角色"),
        )
        assert created.status_code == 200
        character_id = created.json()["data"]["id"]

        upload = client.post(
            "/api/v1/characters/avatar",
            headers=headers,
            json={"data_url": f"data:image/png;base64,{_TINY_PNG}"},
        )
        assert upload.status_code == 200, upload.text
        url = upload.json()["data"]["url"]
        assert url.startswith("/avatars/") and url.endswith(".png")
        image_response = client.get(url)
        assert image_response.status_code == 200
        assert image_response.content == base64.b64decode(_TINY_PNG)

        updated = client.patch(
            f"/api/v1/characters/{character_id}",
            headers=headers,
            json={"avatar": url},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["avatar"] == url

        avatar_file = paths.avatar_dir / url.rsplit("/", 1)[-1]
        assert avatar_file.is_file()

        deleted = client.delete(
            f"/api/v1/characters/{character_id}",
            headers=headers,
        )
        assert deleted.status_code == 200
        assert not avatar_file.exists()
