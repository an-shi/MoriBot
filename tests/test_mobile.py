"""MoriMobile pairing and WebSocket gateway tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.dashboard.app import create_app


def _build_app(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    return create_app(paths=paths, config=config), paths


def _login(client: TestClient, app) -> str:
    credentials = app.state.core.initial_credentials
    assert credentials is not None
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials.password},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_pairing_and_mobile_websocket_flow(tmp_path):
    app, _ = _build_app(tmp_path)

    with TestClient(app) as client:
        access_token = _login(client, app)
        headers = {"Authorization": f"Bearer {access_token}"}

        pairing = client.post("/api/v1/mobile/pairing-code", headers=headers)
        assert pairing.status_code == 200
        pairing_data = pairing.json()["data"]
        assert "morimobile://pair?" in pairing_data["pairing_uri"]

        invalid = client.post(
            "/api/v1/mobile/pair",
            json={"code": "AAAA-AAAA", "device_name": "Phone"},
        )
        assert invalid.status_code == 400

        paired = client.post(
            "/api/v1/mobile/pair",
            json={"code": pairing_data["code"], "device_name": "Pixel"},
        )
        assert paired.status_code == 200
        pair_data = paired.json()["data"]
        device_token = pair_data["device_token"]
        device_id = pair_data["device"]["id"]

        # Pairing codes are single use.
        reused = client.post(
            "/api/v1/mobile/pair",
            json={"code": pairing_data["code"], "device_name": "Pixel 2"},
        )
        assert reused.status_code == 400

        app_me = client.get(
            "/api/v1/mobile/app/me",
            headers={"Authorization": f"Bearer {device_token}"},
        )
        assert app_me.status_code == 200
        assert app_me.json()["data"]["device"]["id"] == device_id
        assert app_me.json()["data"]["user"]["username"] == "admin"

        header_auth = client.get(
            "/api/v1/mobile/app/me",
            headers={"X-Mori-Device-Token": device_token},
        )
        assert header_auth.status_code == 200

        dashboard_token_is_not_a_device = client.get(
            "/api/v1/mobile/app/me",
            headers=headers,
        )
        assert dashboard_token_is_not_a_device.status_code == 401

        devices = client.get("/api/v1/mobile/devices", headers=headers)
        assert devices.status_code == 200
        device_list = devices.json()["data"]
        assert len(device_list) == 1
        assert device_list[0]["name"] == "Pixel"
        assert device_list[0]["online"] is False

        with client.websocket_connect(
            "/api/v1/mobile/ws",
            headers={"Authorization": f"Bearer {device_token}"},
        ) as websocket:
            hello = websocket.receive_json()
            assert hello["type"] == "hello"
            assert hello["protocol"] == 1
            assert hello["device_id"] == device_id

            devices_online = client.get("/api/v1/mobile/devices", headers=headers)
            assert devices_online.json()["data"][0]["online"] is True

            websocket.send_json(
                {
                    "type": "message",
                    "text": "hello from the phone",
                    "client_message_id": "msg-1",
                }
            )
            ack = websocket.receive_json()
            assert ack["type"] == "ack"
            assert ack["client_message_id"] == "msg-1"

            websocket.send_json({"type": "ping"})
            pong = websocket.receive_json()
            assert pong["type"] == "pong"

            sent = client.post(
                f"/api/v1/mobile/devices/{device_id}/message",
                headers=headers,
                json={"text": "reply from dashboard"},
            )
            assert sent.status_code == 200
            downstream = websocket.receive_json()
            assert downstream["type"] == "message"
            assert downstream["text"] == "reply from dashboard"

        offline = client.post(
            f"/api/v1/mobile/devices/{device_id}/message",
            headers=headers,
            json={"text": "are you there?"},
        )
        assert offline.status_code == 409

        revoked = client.post(
            f"/api/v1/mobile/devices/{device_id}/revoke",
            headers=headers,
        )
        assert revoked.status_code == 200

        devices_after = client.get("/api/v1/mobile/devices", headers=headers)
        assert devices_after.json()["data"][0]["revoked_at"] is not None

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/v1/mobile/ws",
                headers={"Authorization": f"Bearer {device_token}"},
            ) as websocket:
                websocket.receive_json()


def test_mobile_websocket_requires_a_valid_device_token(tmp_path):
    app, _ = _build_app(tmp_path)

    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/mobile/ws") as websocket:
                websocket.receive_json()

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/v1/mobile/ws",
                headers={"Authorization": "Bearer mm_invalid"},
            ) as websocket:
                websocket.receive_json()
