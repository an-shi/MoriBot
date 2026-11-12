"""JWT access-token helpers."""

from __future__ import annotations

import datetime as dt
import secrets
from typing import Any

import jwt

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "moribot"


def create_access_token(
    *,
    secret: str,
    user_id: int,
    username: str,
    role: str,
    token_version: int,
    expires_hours: int,
) -> tuple[str, int]:
    """Create a signed access token.

    Args:
        secret: Server signing secret.
        user_id: Database identifier of the account.
        username: Account name.
        role: Authorization role.
        token_version: Incremented on password changes to revoke old tokens.
        expires_hours: Token lifetime in hours.

    Returns:
        A ``(token, expires_in_seconds)`` tuple.
    """
    now = dt.datetime.now(dt.UTC)
    expires_in = max(1, expires_hours) * 3600
    payload: dict[str, Any] = {
        "iss": JWT_ISSUER,
        "sub": str(user_id),
        "username": username,
        "role": role,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(seconds=expires_in)).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    token = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(*, secret: str, token: str) -> dict[str, Any]:
    """Decode and validate a token.

    Args:
        secret: Server signing secret.
        token: Encoded JWT.

    Returns:
        The decoded claims.

    Raises:
        jwt.ExpiredSignatureError: When the token has expired.
        jwt.InvalidTokenError: When the token is malformed or invalid.
    """
    return jwt.decode(
        token,
        secret,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
    )
