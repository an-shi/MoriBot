"""Scheduled model availability checks and system settings tests."""

from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.dashboard.app import create_app
from moribot.dashboard.services.model_health import ModelHealthScheduler


def _build_app(tmp_path):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    return create_app(paths=paths, config=config), paths, config


def _login(client, app) -> dict[str, str]:
    credentials = app.state.core.initial_credentials
    assert credentials is not None
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials.password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_system_settings_and_manual_health_run(tmp_path):
    app, _, config = _build_app(tmp_path)
    with TestClient(app) as client:
        headers = _login(client, app)

        settings = client.get("/api/v1/system/settings", headers=headers)
        assert settings.status_code == 200
        health = settings.json()["data"]["health_check"]
        assert health["enabled"] is False
        assert health["times"] == ["09:00"]

        updated = client.patch(
            "/api/v1/system/settings",
            headers=headers,
            json={
                "health_check": {
                    "enabled": True,
                    "times": ["21:15", "08:30", "08:30"],
                }
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["data"]["health_check"]["times"] == ["08:30", "21:15"]
        assert config.get("provider.health_check.enabled") is True
        assert config.get("provider.health_check.times") == ["08:30", "21:15"]

        invalid = client.patch(
            "/api/v1/system/settings",
            headers=headers,
            json={"health_check": {"enabled": True, "times": ["25:00"]}},
        )
        assert invalid.status_code == 400
        empty = client.patch(
            "/api/v1/system/settings",
            headers=headers,
            json={"health_check": {"enabled": True, "times": []}},
        )
        assert empty.status_code == 400

        disabled = client.patch(
            "/api/v1/system/settings",
            headers=headers,
            json={"health_check": {"enabled": False, "times": []}},
        )
        assert disabled.status_code == 200
        assert disabled.json()["data"]["health_check"]["times"] == []

        run = client.post("/api/v1/system/model-health/run", headers=headers)
        assert run.status_code == 200
        assert run.json()["data"] == {"checked": 0, "available": 0, "failed": 0}


class _FakeProviderService:
    def __init__(self) -> None:
        self.calls = 0

    async def run_health_checks(self, *, locale: str):
        self.calls += 1
        return []


def test_scheduler_runs_each_daily_slot_once(tmp_path):
    config = ConfigManager(tmp_path / "config.json")
    config.load()
    config.set("provider.health_check.enabled", True)
    config.set("provider.health_check.times", ["09:00", "21:00"])
    config.set("provider.health_check.last_runs", {})
    config.save()

    service = _FakeProviderService()
    scheduler = ModelHealthScheduler(config, service, interval_seconds=3600)

    async def run():
        first = await scheduler._tick(datetime(2026, 11, 13, 9, 0, 10))
        duplicate = await scheduler._tick(datetime(2026, 11, 13, 9, 0, 50))
        wrong_slot = await scheduler._tick(datetime(2026, 11, 13, 10, 0, 0))
        evening = await scheduler._tick(datetime(2026, 11, 13, 21, 0, 5))
        next_day = await scheduler._tick(datetime(2026, 11, 14, 9, 0, 1))
        return first, duplicate, wrong_slot, evening, next_day

    first, duplicate, wrong_slot, evening, next_day = asyncio.run(run())
    assert first is True
    assert duplicate is False
    assert wrong_slot is False
    assert evening is True
    assert next_day is True
    assert service.calls == 3
    last_runs = config.get("provider.health_check.last_runs")
    assert last_runs == {"09:00": "2026-11-14", "21:00": "2026-11-13"}
