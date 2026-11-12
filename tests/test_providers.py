"""Model provider configuration CRUD and secret storage tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.core.provider import ProviderCategory
from moribot.dashboard.app import create_app


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


def _provider_payload(category: str, name: str, model: str) -> dict:
    return {
        "category": category,
        "name": name,
        "provider_type": "openai_compatible",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test-secret-1234",
        "model": model,
        "options": {},
    }


def test_provider_crud_defaults_and_encrypted_keys(tmp_path):
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)

        created = []
        for category, name, model in (
            ("chat", "Main", "gpt-4.1-mini"),
            ("speech", "Voice", "tts-1"),
            ("image", "Images", "gpt-image-1"),
        ):
            response = client.post(
                "/api/v1/providers",
                headers=headers,
                json=_provider_payload(category, name, model),
            )
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert data["category"] == category
            assert data["api_key_set"] is True
            assert data["api_key_hint"].endswith("1234")
            assert "sk-test-secret" not in response.text
            created.append(data)

        providers = client.get("/api/v1/providers", headers=headers).json()["data"]
        assert len(providers) == 3
        assert all(item["is_default"] for item in providers)

        manager = app.state.core.provider_manager
        assert manager.get_default(ProviderCategory.CHAT) is not None
        assert manager.get_default(ProviderCategory.SPEECH) is not None
        assert manager.get_default(ProviderCategory.IMAGE) is not None

        record = client.portal.call(
            app.state.core.db.get_model_provider,
            created[0]["id"],
        )
        assert record is not None
        assert record.api_key_encrypted != "sk-test-secret-1234"
        assert app.state.core.secret_box.decrypt(record.api_key_encrypted) == "sk-test-secret-1234"

        updated = client.patch(
            f"/api/v1/providers/{created[0]['id']}",
            headers=headers,
            json={"name": "Main updated", "api_key": ""},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["name"] == "Main updated"
        assert updated.json()["data"]["api_key_set"] is True

        duplicate = client.post(
            "/api/v1/providers",
            headers=headers,
            json=_provider_payload("chat", "Main updated", "another-model"),
        )
        assert duplicate.status_code == 409

        changed = client.post(
            f"/api/v1/providers/{created[1]['id']}/default",
            headers=headers,
        )
        assert changed.status_code == 200
        assert changed.json()["data"]["is_default"] is True

        deleted = client.delete(
            f"/api/v1/providers/{created[0]['id']}",
            headers=headers,
        )
        assert deleted.status_code == 200
        assert len(client.get("/api/v1/providers", headers=headers).json()["data"]) == 2


def test_provider_validation_rejects_invalid_base_url(tmp_path):
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        payload = _provider_payload("chat", "Bad", "model")
        payload["base_url"] = "ftp://example.com"
        response = client.post("/api/v1/providers", headers=headers, json=payload)
        assert response.status_code == 400


def test_provider_catalog_and_native_type_validation(tmp_path):
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)

        catalog = client.get("/api/v1/providers/catalog", headers=headers)
        assert catalog.status_code == 200
        type_ids = {item["id"] for item in catalog.json()["data"]["types"]}
        assert {
            "openai_compatible",
            "anthropic",
            "google_gemini",
            "azure_openai",
            "elevenlabs",
        } <= type_ids

        anthropic = _provider_payload("chat", "Claude", "claude-sonnet-4-5")
        anthropic["provider_type"] = "anthropic"
        anthropic["base_url"] = "https://api.anthropic.com/v1"
        created = client.post("/api/v1/providers", headers=headers, json=anthropic)
        assert created.status_code == 200
        assert created.json()["data"]["provider_type"] == "anthropic"

        image_with_claude = _provider_payload("image", "Claude Image", "claude")
        image_with_claude["provider_type"] = "anthropic"
        rejected = client.post("/api/v1/providers", headers=headers, json=image_with_claude)
        assert rejected.status_code == 400
