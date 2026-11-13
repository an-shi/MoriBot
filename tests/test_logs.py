"""Regular runtime and business API log tests."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.logging import LogEntry
from moribot.core.paths import AppPaths
from moribot.dashboard.app import create_app


def _build_app(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    return create_app(paths=paths, config=config)


def _login(client, app) -> dict[str, str]:
    credentials = app.state.core.initial_credentials
    assert credentials is not None
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials.password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_recent_logs_filters_and_download(tmp_path):
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)
        client.get("/api/v1/providers", headers=headers)

        broker = app.state.log_broker
        access_entry = None
        for _ in range(20):
            access_entry = next(
                (
                    entry
                    for entry in broker.recent(limit=1000)
                    if entry.source == "http" and "/api/v1/providers" in entry.message
                ),
                None,
            )
            if access_entry is not None:
                break
            time.sleep(0.05)
        assert access_entry is not None
        assert "200" in access_entry.message
        assert "user:admin" in access_entry.message

        now = time.time()
        broker = app.state.log_broker
        broker.publish(
            LogEntry(
                time=now - 3,
                level="INFO",
                source="app",
                message="runtime started",
                module="test.runtime",
                line=10,
            )
        )
        broker.publish(
            LogEntry(
                time=now - 2,
                level="WARNING",
                source="http",
                message="GET /api/v1/providers -> 401 (9 ms)",
                module="http",
                line=0,
            )
        )
        broker.publish(
            LogEntry(
                time=now - 1,
                level="ERROR",
                source="app",
                message="provider failed",
                module="test.provider",
                line=20,
            )
        )

        all_logs = client.get("/api/v1/system/logs?limit=1000", headers=headers)
        assert all_logs.status_code == 200
        entries = all_logs.json()["data"]["entries"]
        messages = {entry["message"] for entry in entries}
        assert {"runtime started", "provider failed"} <= messages

        errors = client.get(
            "/api/v1/system/logs?level=ERROR&limit=1000",
            headers=headers,
        )
        assert errors.status_code == 200
        assert all(
            entry["level"] in {"ERROR", "CRITICAL"} for entry in errors.json()["data"]["entries"]
        )

        api_logs = client.get(
            "/api/v1/system/logs?source=http&limit=1000",
            headers=headers,
        )
        assert api_logs.status_code == 200
        assert all(entry["source"] == "http" for entry in api_logs.json()["data"]["entries"])

        searched = client.get(
            "/api/v1/system/logs?q=provider&limit=1000",
            headers=headers,
        )
        assert searched.status_code == 200
        assert any("provider" in entry["message"] for entry in searched.json()["data"]["entries"])

        (app.state.paths.log_dir / "moribot.log").write_text(
            "test log line\n",
            encoding="utf-8",
        )
        download = client.get("/api/v1/system/logs/download", headers=headers)
        assert download.status_code == 200
        assert "text/plain" in download.headers["content-type"]
        assert b"test log line" in download.content
