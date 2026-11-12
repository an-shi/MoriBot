"""API router assembly."""

from __future__ import annotations

from fastapi import APIRouter

from . import auth, mobile, system

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
api_router.include_router(auth.router)
api_router.include_router(system.router)
api_router.include_router(mobile.router)

__all__ = ["API_V1_PREFIX", "api_router"]
