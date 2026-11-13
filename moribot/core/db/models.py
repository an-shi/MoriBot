"""Database tables.

Runtime data lives in a single SQLite database so the whole data directory can
be exported and restored as one unit. Conversation messages are stored here;
generated audio and images are stored under the data directory as files and
referenced from the message records.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import JSON, Field, SQLModel


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


class ModelProvider(TimestampMixin, SQLModel, table=True):
    """A configured model endpoint for chat, speech or image generation."""

    __tablename__ = "model_providers"
    __table_args__ = (
        UniqueConstraint("category", "name", name="uix_model_provider_category_name"),
    )

    id: int | None = Field(default=None, primary_key=True)
    category: str = Field(max_length=16, index=True, nullable=False)
    name: str = Field(max_length=64, nullable=False)
    provider_type: str = Field(default="openai_compatible", max_length=32, nullable=False)
    base_url: str = Field(max_length=512, nullable=False)
    api_key_encrypted: str = Field(default="", max_length=2048, nullable=False)
    model: str = Field(max_length=128, nullable=False)
    options: dict = Field(default_factory=dict, sa_type=JSON)
    capabilities: dict = Field(default_factory=dict, sa_type=JSON)
    is_default: bool = Field(default=False, nullable=False)
    enabled: bool = Field(default=True, nullable=False)
    last_test_ok: bool | None = Field(default=None)
    last_test_message: str = Field(default="", max_length=512)
    last_tested_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=False),
    )


class CharacterCard(TimestampMixin, SQLModel, table=True):
    """A persona card with optional per-category model overrides."""

    __tablename__ = "character_cards"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=64, unique=True, index=True, nullable=False)
    avatar: str = Field(default="", max_length=512, nullable=False)
    description: str = Field(default="", max_length=1000, nullable=False)
    persona: str = Field(default="", max_length=20000, nullable=False)
    chat_provider_id: int | None = Field(default=None, index=True)
    speech_provider_id: int | None = Field(default=None, index=True)
    image_provider_id: int | None = Field(default=None, index=True)
    enabled: bool = Field(default=True, nullable=False)


class Conversation(TimestampMixin, SQLModel, table=True):
    """A persistent chat thread owned by an account.

    Conversations belong to the account rather than a single device, so all
    paired devices of the same user can read the same history. Character name
    is snapshotted so history stays readable after a card is renamed or
    deleted.
    """

    __tablename__ = "conversations"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        max_length=32,
    )
    user_id: int = Field(index=True, nullable=False)
    character_id: int = Field(index=True, nullable=False)
    device_id: str = Field(default="", max_length=64, index=True)
    character_name: str = Field(default="", max_length=64)
    character_avatar: str = Field(default="", max_length=512)
    title: str = Field(default="", max_length=100)
    last_message_preview: str = Field(default="", max_length=200)
    last_message_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=False),
    )
    message_count: int = Field(default=0, nullable=False)


class ConversationMessage(TimestampMixin, SQLModel, table=True):
    """One persisted user or assistant message.

    ``media`` is a JSON list of generated media descriptors. Audio and image
    bytes live under ``data/media/<user_id>/`` and the descriptors store the
    authenticated API URL instead of embedding base64 in the database.
    """

    __tablename__ = "conversation_messages"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(index=True, max_length=32, nullable=False)
    role: str = Field(max_length=16, nullable=False)
    content: str = Field(default="", nullable=False)
    client_message_id: str = Field(default="", max_length=128, index=True)
    provider_id: str = Field(default="", max_length=64)
    model: str = Field(default="", max_length=128)
    media: list = Field(default_factory=list, sa_type=JSON)
