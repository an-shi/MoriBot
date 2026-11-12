"""Dashboard response envelope helpers."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Uniform envelope consumed by the dashboard client."""

    status: Literal["ok", "error"] = "ok"
    message: str | None = None
    data: T | None = None


def ok(data: Any = None, message: str | None = None) -> dict[str, Any]:
    """Build a successful envelope."""
    return {"status": "ok", "message": message, "data": data}


def error(message: str, data: Any = None) -> dict[str, Any]:
    """Build a failed envelope."""
    return {"status": "error", "message": message, "data": data}
