"""Shared runtime exceptions."""

from __future__ import annotations

from typing import Any


class MoriError(Exception):
    """Base exception carrying an HTTP-friendly message and status code."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        data: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.data = data


class AuthenticationError(MoriError):
    """Raised when credentials are missing or invalid."""

    def __init__(self, message: str = "请先登录", *, data: Any = None) -> None:
        super().__init__(message, status_code=401, data=data)


class PermissionDeniedError(MoriError):
    """Raised when an authenticated account lacks permission."""

    def __init__(self, message: str = "没有操作权限", *, data: Any = None) -> None:
        super().__init__(message, status_code=403, data=data)


class NotFoundError(MoriError):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "资源不存在", *, data: Any = None) -> None:
        super().__init__(message, status_code=404, data=data)


class ConflictError(MoriError):
    """Raised when a request conflicts with current state."""

    def __init__(self, message: str, *, data: Any = None) -> None:
        super().__init__(message, status_code=409, data=data)
