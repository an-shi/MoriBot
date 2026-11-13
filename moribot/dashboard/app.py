"""FastAPI application factory for the MoriBot dashboard."""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from moribot import __version__
from moribot.core.config import ConfigManager
from moribot.core.errors import MoriError
from moribot.core.i18n import translate
from moribot.core.lifecycle import CoreLifecycle
from moribot.core.logging import LogBroker, setup_logging
from moribot.core.paths import AppPaths

from .deps import get_locale
from .rate_limit import LoginRateLimiter
from .responses import error
from .routes import API_V1_PREFIX, api_router
from .services.auth_service import AuthService
from .services.character_service import CharacterService
from .services.mobile_chat_service import MobileChatService
from .services.mobile_service import MobileService
from .services.model_health import ModelHealthScheduler
from .services.provider_service import ProviderConfigService


def _register_dashboard(app: FastAPI, dist: Path | None) -> None:
    """Serve the built SPA and fall back to index.html for client routes."""
    if dist is None or not (dist / "index.html").is_file():
        @app.get("/", include_in_schema=False)
        async def missing_dashboard() -> dict[str, Any]:
            return {
                "name": app.state.core.config.bot_name,
                "version": __version__,
                "api": API_V1_PREFIX,
                "docs": "/api/docs",
                "dashboard": "not built. Run `pnpm dev` in dashboard/ or build it with `pnpm build`.",
            }

        return

    resolved_dist = dist.resolve()
    assets_dir = resolved_dist / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="dashboard-assets",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        # API 404s must stay JSON instead of silently returning index.html.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        candidate = (resolved_dist / full_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(resolved_dist):
            return FileResponse(candidate)
        return FileResponse(resolved_dist / "index.html")


def create_app(
    *,
    paths: AppPaths | None = None,
    config: ConfigManager | None = None,
    log_broker: LogBroker | None = None,
    reset_password: bool = False,
) -> FastAPI:
    """Build the ASGI application.

    Args:
        paths: Optional pre-resolved runtime paths.
        config: Optional loaded configuration.
        log_broker: Optional broker shared with the CLI for future live logs.
        reset_password: Reset the administrator password during startup. The
            CLI performs this before serving; the flag remains available for
            embedding MoriBot in another process.

    Returns:
        A configured FastAPI application.
    """
    load_dotenv()
    resolved_paths = paths or AppPaths.resolve()
    resolved_paths.ensure()

    resolved_config = config or ConfigManager(resolved_paths.config_file)
    if config is None:
        resolved_config.load()

    broker = log_broker or LogBroker()
    log_level = os.environ.get("MORIBOT_LOG_LEVEL") or resolved_config.log_level
    setup_logging(resolved_paths, log_level, broker)

    lifecycle = CoreLifecycle(
        resolved_paths,
        resolved_config,
        reset_password=reset_password,
    )
    auth_service = AuthService(lifecycle.db, resolved_config, resolved_paths)
    mobile_service = MobileService(
        lifecycle.db,
        resolved_config,
        lifecycle.mobile_adapter,
    )
    provider_service = ProviderConfigService(lifecycle)
    character_service = CharacterService(lifecycle)
    mobile_chat_service = MobileChatService(lifecycle, character_service)
    health_scheduler = ModelHealthScheduler(resolved_config, provider_service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            await lifecycle.initialize()
            await lifecycle.start()
            await health_scheduler.start()
            logger.info(
                "{} v{} dashboard API ready at {}",
                resolved_config.bot_name,
                __version__,
                API_V1_PREFIX,
            )
            yield
        finally:
            await health_scheduler.stop()
            await lifecycle.stop()

    app = FastAPI(
        title=f"{resolved_config.bot_name} API",
        description="MoriBot dashboard and control API",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )

    app.state.paths = resolved_paths
    app.state.config = resolved_config
    app.state.core = lifecycle
    app.state.auth_service = auth_service
    app.state.mobile_service = mobile_service
    app.state.provider_service = provider_service
    app.state.character_service = character_service
    app.state.mobile_chat_service = mobile_chat_service
    app.state.model_health_scheduler = health_scheduler
    app.state.login_limiter = LoginRateLimiter()
    app.state.mobile_limiter = LoginRateLimiter()
    app.state.log_broker = broker

    if resolved_config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved_config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    trusted_hosts = resolved_config.get("dashboard.trusted_hosts", [])
    if isinstance(trusted_hosts, list) and trusted_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[str(host) for host in trusted_hosts if str(host).strip()],
        )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    force_https = bool(resolved_config.get("dashboard.force_https", False))

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        # Uvicorn's ProxyHeadersMiddleware rewrites the scheme only for
        # trusted proxy addresses, so request.url.scheme is the safe source
        # of truth here.
        scheme = request.url.scheme
        if force_https and scheme != "https":
            return RedirectResponse(
                request.url.replace(scheme="https"),
                status_code=308,
            )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        if scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000",
            )
        return response

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        path = request.url.path
        is_business_api = path.startswith("/api/v1/") and path not in {
            "/api/v1/system/health",
            "/api/v1/system/public",
        }
        if (
            not is_business_api
            or path.startswith("/api/v1/system/logs")
            or request.method == "OPTIONS"
        ):
            return await call_next(request)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.bind(source="http").exception(
                "{} {} failed",
                request.method,
                path,
            )
            raise

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        status = response.status_code
        level = "ERROR" if status >= 500 else "WARNING" if status >= 400 else "INFO"
        user = getattr(request.state, "user", None)
        device = getattr(request.state, "mobile_device", None)
        if user is not None:
            actor = f"user:{getattr(user, 'username', '')}"
        elif device is not None:
            actor = f"device:{getattr(device, 'name', '')}"
        else:
            actor = "anonymous"
        client = request.client.host if request.client is not None else "-"
        logger.bind(source="http").log(
            level,
            "{} {} -> {} ({} ms) actor={} ip={}",
            request.method,
            path,
            status,
            elapsed_ms,
            actor,
            client,
        )
        return response

    @app.exception_handler(MoriError)
    async def mori_error_handler(_request: Request, exc: MoriError) -> JSONResponse:
        return JSONResponse(
            error(exc.message, exc.data),
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        locale = get_locale(request)
        details = []
        for item in exc.errors():
            location = [
                str(part)
                for part in item.get("loc", ())
                if part not in ("body", "query", "path")
            ]
            details.append(
                {
                    "field": ".".join(location),
                    "message": str(item.get("msg", "invalid value")),
                }
            )
        return JSONResponse(
            error(translate("common.invalid_request", locale), {"errors": details}),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        locale = get_locale(request)
        detail = exc.detail
        if exc.status_code == 404:
            payload = error(translate("common.not_found", locale))
        elif isinstance(detail, str):
            payload = error(detail)
        else:
            payload = error(translate("common.request_failed", locale), detail)
        return JSONResponse(payload, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.opt(exception=exc).error(
            "Unhandled error while processing {} {}",
            request.method,
            request.url.path,
        )
        return JSONResponse(
            error(translate("common.server_error", get_locale(request))),
            status_code=500,
        )

    app.include_router(api_router)
    app.mount(
        "/avatars",
        StaticFiles(directory=resolved_paths.avatar_dir),
        name="character-avatars",
    )
    _register_dashboard(app, resolved_paths.webui_dist)
    return app
