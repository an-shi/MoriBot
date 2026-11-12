"""End-to-end authentication tests against the real ASGI app."""

from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.dashboard.app import create_app


def _build_app(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    return create_app(paths=paths, config=config), paths


def test_config_is_created_with_a_stable_jwt_secret(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()

    first = ConfigManager(paths.config_file)
    first.load()
    secret = first.get("dashboard.jwt_secret")
    assert secret
    assert paths.config_file.is_file()

    second = ConfigManager(paths.config_file)
    second.load()
    assert second.get("dashboard.jwt_secret") == secret


def test_auth_errors_follow_accept_language(tmp_path):
    app, _ = _build_app(tmp_path)

    with TestClient(app) as client:
        chinese = client.get("/api/v1/system/info")
        assert chinese.status_code == 401
        assert chinese.json()["message"] == "请先登录"

        english = client.get(
            "/api/v1/system/info",
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        assert english.status_code == 401
        assert english.json()["message"] == "Authentication required"

        override = client.get(
            "/api/v1/system/info",
            headers={
                "Accept-Language": "zh-CN",
                "X-Mori-Locale": "en-US",
            },
        )
        assert override.json()["message"] == "Authentication required"


def test_login_me_and_password_change(tmp_path):
    app, paths = _build_app(tmp_path)

    with TestClient(app) as client:
        credentials = app.state.core.initial_credentials
        assert credentials is not None
        assert credentials.username == "admin"
        assert (paths.data_dir / "initial_admin.txt").is_file()

        health = client.get("/api/v1/system/health")
        assert health.status_code == 200
        assert health.json()["data"]["status"] == "ok"

        public = client.get("/api/v1/system/public")
        assert public.status_code == 200
        assert public.json()["data"]["name"] == "MoriBot"

        wrong = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "definitely-wrong"},
        )
        assert wrong.status_code == 401
        assert wrong.json()["status"] == "error"

        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": credentials.password},
        )
        assert login.status_code == 200
        token_data = login.json()["data"]
        token = token_data["access_token"]
        assert token_data["user"]["username"] == "admin"

        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["data"]["username"] == "admin"

        info = client.get("/api/v1/system/info", headers=headers)
        assert info.status_code == 200
        assert info.json()["data"]["providers"] == 0

        export = client.get("/api/v1/system/backup/export", headers=headers)
        assert export.status_code == 200
        assert export.headers["content-type"].startswith("application/zip")
        with zipfile.ZipFile(io.BytesIO(export.content)) as archive:
            assert "manifest.json" in archive.namelist()
            assert "moribot.db" in archive.namelist()

        no_auth = client.get("/api/v1/system/info")
        assert no_auth.status_code == 401

        new_password = "MoriBot-New-Password-2026"
        changed = client.post(
            "/api/v1/auth/change-password",
            headers=headers,
            json={
                "current_password": credentials.password,
                "new_password": new_password,
                "confirm_password": new_password,
            },
        )
        assert changed.status_code == 200
        assert changed.json()["data"]["access_token"]

        # Changing the password bumps token_version, revoking the old token.
        revoked = client.get("/api/v1/auth/me", headers=headers)
        assert revoked.status_code == 401

        old_login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": credentials.password},
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": new_password},
        )
        assert new_login.status_code == 200
        assert not (paths.data_dir / "initial_admin.txt").exists()
