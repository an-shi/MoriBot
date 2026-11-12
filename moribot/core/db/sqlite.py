"""SQLite implementation of the MoriBot database."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import func, update
from sqlmodel import select

from .base import BaseDatabase
from .models import MobileDevice, MobilePairingCode, User, utcnow


class SQLiteDatabase(BaseDatabase):
    """Small, single-file database suitable for self-hosted deployments."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        super().__init__(f"sqlite+aiosqlite:///{path.as_posix()}")

    async def count_users(self) -> int:
        return await self._count_users()

    async def get_user_by_id(self, user_id: int) -> User | None:
        async with self.session() as session:
            return await session.get(User, user_id)

    async def get_user_by_username(self, username: str) -> User | None:
        return await self._find_user(username=username)

    async def get_first_admin(self) -> User | None:
        async with self.session() as session:
            result = await session.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
            return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str = "",
        role: str = "admin",
    ) -> User:
        user = User(
            username=username,
            password_hash=password_hash,
            display_name=display_name or username,
            role=role,
        )
        async with self.session() as session:
            session.add(user)
            await session.flush()
            await session.refresh(user)
        return user

    async def update_user_password(self, user_id: int, password_hash: str) -> User | None:
        async with self.session() as session:
            user = await session.get(User, user_id)
            if user is None:
                return None
            user.password_hash = password_hash
            user.token_version += 1
            self._touch(user)
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    async def record_login(self, user_id: int) -> None:
        async with self.session() as session:
            user = await session.get(User, user_id)
            if user is None:
                return
            user.last_login_at = utcnow()
            self._touch(user)
            session.add(user)

    async def create_mobile_pairing_code(
        self,
        *,
        user_id: int,
        code_hash: str,
        expires_at: datetime,
    ) -> MobilePairingCode:
        pairing_code = MobilePairingCode(
            user_id=user_id,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        async with self.session() as session:
            session.add(pairing_code)
            await session.flush()
            await session.refresh(pairing_code)
        return pairing_code

    async def consume_mobile_pairing_code(
        self,
        code_hash: str,
        now: datetime,
    ) -> MobilePairingCode | None:
        async with self.session() as session:
            # Consume atomically so two concurrent pairing attempts cannot
            # redeem the same one-time code.
            result = await session.execute(
                update(MobilePairingCode)
                .where(MobilePairingCode.code_hash == code_hash)
                .where(MobilePairingCode.used_at.is_(None))
                .where(MobilePairingCode.expires_at > now)
                .values(used_at=now, updated_at=now)
            )
            if not result.rowcount:
                return None

            query = await session.execute(
                select(MobilePairingCode).where(MobilePairingCode.code_hash == code_hash).limit(1)
            )
            return query.scalar_one_or_none()

    async def count_mobile_devices(self, user_id: int) -> int:
        async with self.session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(MobileDevice)
                .where(MobileDevice.user_id == user_id)
                .where(MobileDevice.is_active.is_(True))
            )
            return int(result.scalar_one())

    async def create_mobile_device(
        self,
        *,
        user_id: int,
        name: str,
        token_hash: str,
    ) -> MobileDevice:
        device = MobileDevice(
            user_id=user_id,
            name=name,
            token_hash=token_hash,
        )
        async with self.session() as session:
            session.add(device)
            await session.flush()
            await session.refresh(device)
        return device

    async def get_mobile_device(self, device_id: str) -> MobileDevice | None:
        async with self.session() as session:
            return await session.get(MobileDevice, device_id)

    async def get_mobile_device_by_token_hash(self, token_hash: str) -> MobileDevice | None:
        async with self.session() as session:
            result = await session.execute(
                select(MobileDevice).where(MobileDevice.token_hash == token_hash).limit(1)
            )
            return result.scalar_one_or_none()

    async def list_mobile_devices(self, user_id: int) -> list[MobileDevice]:
        async with self.session() as session:
            result = await session.execute(
                select(MobileDevice)
                .where(MobileDevice.user_id == user_id)
                .order_by(MobileDevice.created_at.desc())
            )
            return list(result.scalars().all())

    async def revoke_mobile_device(self, user_id: int, device_id: str) -> bool:
        async with self.session() as session:
            result = await session.execute(
                select(MobileDevice)
                .where(MobileDevice.id == device_id)
                .where(MobileDevice.user_id == user_id)
                .limit(1)
            )
            device = result.scalar_one_or_none()
            if device is None:
                return False
            device.is_active = False
            device.revoked_at = utcnow()
            self._touch(device)
            session.add(device)
            return True

    async def touch_mobile_device(self, device_id: str) -> None:
        async with self.session() as session:
            device = await session.get(MobileDevice, device_id)
            if device is None:
                return
            device.last_seen_at = utcnow()
            self._touch(device)
            session.add(device)
