"""Configuration defaults for a fresh MoriBot installation."""

from __future__ import annotations

from typing import Any

CONFIG_VERSION = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "config_version": CONFIG_VERSION,
    "bot": {
        "name": "MoriBot",
        "description": "可扩展的 AI 助手后台控制器",
        "locale": "zh-CN",
        "log_level": "INFO",
    },
    "dashboard": {
        "host": "127.0.0.1",
        "port": 6186,
        # Generated on first start and persisted. Never ship a fixed secret.
        "jwt_secret": "",
        "token_expire_hours": 168,
        # Public origin used for MoriMobile pairing links, e.g.
        # "https://mori.example.com". Leave empty to infer from the request.
        "public_url": "",
        # Set when serving behind a reverse proxy or exposing the dashboard.
        # An empty list disables host validation (development default).
        "trusted_hosts": [],
        # Redirect plain HTTP to HTTPS. Enable after configuring TLS.
        "force_https": False,
        # Uvicorn proxy handling. Only trust forwarded headers from the
        # addresses listed here (the local reverse proxy by default).
        "proxy_headers": True,
        "forwarded_allow_ips": "127.0.0.1",
        # Direct TLS termination. Reverse proxies are recommended instead.
        "ssl_certfile": "",
        "ssl_keyfile": "",
        "cors_origins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
    },
    "provider": {
        "default_chat_provider_id": "",
        # Vendors such as MiniMax do not list speech/image models through
        # /models. These fallbacks can be edited in config.json without a code
        # change. Shape: {provider_type: {category: [model_id, ...]}}.
        "media_model_fallbacks": {
            "minimax": {
                "speech": ["speech-2.8-turbo", "speech-2.8-hd"],
                "image": [
                    "MiniMax-H3-Image",
                    "MiniMax-H3-Image-Highspeed",
                ],
            },
        },
    },
    "platform": {},
    "mobile": {
        "max_devices": 10,
        "pairing_code_ttl_minutes": 10,
    },
}
