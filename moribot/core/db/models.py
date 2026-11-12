"""Database tables.

Only the dashboard account table exists in the foundation. Conversation,
provider and platform tables will be added as those modules are built.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Return a naive UTC timestamp suitable for SQLite storage."""
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin(SQLModel):
    created_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        sa_type=DateTime(timezone=False),
    )
    updated_at: datetime = Field(
        default_factory=utcnow,
        nullable=False,
        sa_type=DateTime(timezone=False),
        sa_column_kwargs={"onupdate": utcnow},
    )


class User(TimestampMixin, SQLModel, table=True):
    """A dashboard account."""

    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(max_length=64, unique=True, index=True, nullable=False)
    password_hash: str = Field(max_length=255, nullable=False)
    display_name: str = Field(default="", max_length=64, nullable=False)
    role: str = Field(default="admin", max_length=32, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    token_version: int = Field(default=0, nullable=False)
    last_login_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=False),
    )


class MobileDevice(TimestampMixin, SQLModel, table=True):
    """A phone or tablet paired with MoriMobile."""

    __tablename__ = "mobile_devices"

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        max_length=36,
    )
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    name: str = Field(max_length=64, nullable=False)
    token_hash: str = Field(max_length=64, unique=True, index=True, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    last_seen_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=False))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=False))


class MobilePairingCode(TimestampMixin, SQLModel, table=True):
    """A short-lived, single-use code used by the mobile app to pair."""

    __tablename__ = "mobile_pairing_codes"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    code_hash: str = Field(max_length=64, unique=True, index=True, nullable=False)
    expires_at: datetime = Field(nullable=False, sa_type=DateTime(timezone=False))
    used_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=False))
