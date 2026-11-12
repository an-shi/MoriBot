"""Reverse-proxy, TLS and host-validation tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from moribot.core.config import ConfigManager
from moribot.core.paths import AppPaths
from moribot.dashboard.app import create_app


def _build_app(tmp_path, **dashboard_overrides):
    paths = AppPaths.resolve(tmp_path)
    paths.ensure()
    config = ConfigManager(paths.config_file)
    config.load()
    for key, value in dashboard_overrides.items():
        config.set(f"dashboard.{key}", value)
    config.save()
    return create_app(paths=paths, config=config)


def test_force_https_and_hsts(tmp_path):
    http_app = _build_app(tmp_path / "http", force_https=True)
    with TestClient(http_app, base_url="http://testserver") as client:
        redirected = client.get(
            "/api/v1/system/health",
            follow_redirects=False,
        )
        assert redirected.status_code == 308
        assert redirected.headers["location"].startswith("https://")

    https_app = _build_app(tmp_path / "https", force_https=True)
    with TestClient(https_app, base_url="https://testserver") as client:
        secure = client.get("/api/v1/system/health")
        assert secure.status_code == 200
        assert secure.headers["strict-transport-security"] == "max-age=31536000"


def test_trusted_hosts_reject_unlisted_host(tmp_path):
    app = _build_app(tmp_path, trusted_hosts=["mori.example.com"])
    with TestClient(app) as client:
        allowed = client.get(
            "/api/v1/system/health",
            headers={"Host": "mori.example.com"},
        )
        assert allowed.status_code == 200

        rejected = client.get(
            "/api/v1/system/health",
            headers={"Host": "evil.example.com"},
        )
        assert rejected.status_code == 400


def test_security_headers_are_present(tmp_path):
    app = _build_app(tmp_path)
    with TestClient(app) as client:
        response = client.get("/api/v1/system/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "SAMEORIGIN"
        assert response.headers["referrer-policy"] == "same-origin"
        assert "camera=()" in response.headers["permissions-policy"]
