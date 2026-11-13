"""Abstract database interface and shared SQLAlchemy plumbing."""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from .models import CharacterCard, MobileDevice, MobilePairingCode, ModelProvider, User, utcnow


class BaseDatabase(abc.ABC):
    """Async database handle with a stable account-oriented API."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        connect_args = {"timeout": 30} if database_url.startswith("sqlite") else {}
        self.engine = create_async_engine(
            database_url,
            echo=False,
            future=True,
            connect_args=connect_args,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        if database_url.startswith("sqlite"):
            # WAL keeps readers from blocking the dispatcher and dashboard
            # while a write is in flight.
            @event.listens_for(self.engine.sync_engine, "connect")
            def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    async def initialize(self) -> None:
        """Create tables if they do not exist."""
        async with self.engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

    async def dispose(self) -> None:
        """Close pooled connections during shutdown."""
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an async session that commits on success and rolls back on error."""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # -- Accounts ---------------------------------------------------------

    @abc.abstractmethod
    async def count_users(self) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_user_by_id(self, user_id: int) -> User | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_user_by_username(self, username: str) -> User | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_first_admin(self) -> User | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str = "",
        role: str = "admin",
    ) -> User:
        raise NotImplementedError

    @abc.abstractmethod
    async def update_user_password(self, user_id: int, password_hash: str) -> User | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def record_login(self, user_id: int) -> None:
        raise NotImplementedError

    # -- MoriMobile -------------------------------------------------------

    @abc.abstractmethod
    async def create_mobile_pairing_code(
        self,
        *,
        user_id: int,
        code_hash: str,
        expires_at: datetime,
    ) -> MobilePairingCode:
        raise NotImplementedError

    @abc.abstractmethod
    async def consume_mobile_pairing_code(
        self,
        code_hash: str,
        now: datetime,
    ) -> MobilePairingCode | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def count_mobile_devices(self, user_id: int) -> int:
        raise NotImplementedError

    @abc.abstractmethod
    async def create_mobile_device(
        self,
        *,
        user_id: int,
        name: str,
        token_hash: str,
    ) -> MobileDevice:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_mobile_device(self, device_id: str) -> MobileDevice | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_mobile_device_by_token_hash(self, token_hash: str) -> MobileDevice | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def list_mobile_devices(self, user_id: int) -> list[MobileDevice]:
        raise NotImplementedError

    @abc.abstractmethod
    async def revoke_mobile_device(self, user_id: int, device_id: str) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def touch_mobile_device(self, device_id: str) -> None:
        raise NotImplementedError

    # -- Model providers --------------------------------------------------

    @abc.abstractmethod
    async def list_model_providers(self, category: str | None = None) -> list[ModelProvider]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_model_provider(self, provider_id: int) -> ModelProvider | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def create_model_provider(self, values: dict[str, Any]) -> ModelProvider:
        raise NotImplementedError

    @abc.abstractmethod
    async def update_model_provider(
        self,
        provider_id: int,
        values: dict[str, Any],
    ) -> ModelProvider | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_model_provider(self, provider_id: int) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def set_default_model_provider(
        self,
        category: str,
        provider_id: int,
    ) -> ModelProvider | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_default_model_provider(self, category: str) -> ModelProvider | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def record_model_provider_test(
        self,
        provider_id: int,
        ok: bool,
        message: str,
    ) -> None:
        raise NotImplementedError

    # -- Character cards --------------------------------------------------

    @abc.abstractmethod
    async def list_character_cards(self) -> list[CharacterCard]:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_character_card(self, character_id: int) -> CharacterCard | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def get_character_card_by_name(self, name: str) -> CharacterCard | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def create_character_card(self, values: dict[str, Any]) -> CharacterCard:
        raise NotImplementedError

    @abc.abstractmethod
    async def update_character_card(
        self,
        character_id: int,
        values: dict[str, Any],
    ) -> CharacterCard | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def delete_character_card(self, character_id: int) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    async def clear_character_provider_refs(self, provider_id: int) -> None:
        raise NotImplementedError

    async def _count_users(self) -> int:
        """Shared count implementation for subclasses."""
        async with self.session() as session:
            result = await session.execute(select(func.count()).select_from(User))
            return int(result.scalar_one())

    async def _find_user(self, **filters) -> User | None:
        """Shared single-user lookup for subclasses."""
        async with self.session() as session:
            result = await session.execute(select(User).filter_by(**filters).limit(1))
            return result.scalar_one_or_none()

    @staticmethod
    def _touch(user: User) -> None:
        user.updated_at = utcnow()
