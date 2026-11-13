"""SQLite implementation of the MoriBot database."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, func, update
from sqlmodel import select

from .base import BaseDatabase
from .models import (
    CharacterCard,
    Conversation,
    ConversationMessage,
    MobileDevice,
    MobilePairingCode,
    ModelProvider,
    User,
    utcnow,
)


class SQLiteDatabase(BaseDatabase):
    """Small, single-file database suitable for self-hosted deployments."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = path
        super().__init__(f"sqlite+aiosqlite:///{path.as_posix()}")

    async def initialize(self) -> None:
        await super().initialize()
        # create_all does not add columns to an existing table. Apply the
        # small additive migration needed by installations created before
        # model capabilities were introduced.
        async with self.engine.begin() as connection:
            result = await connection.exec_driver_sql("PRAGMA table_info(model_providers)")
            columns = {row[1] for row in result.fetchall()}
            if "capabilities" not in columns:
                await connection.exec_driver_sql(
                    "ALTER TABLE model_providers ADD COLUMN capabilities JSON"
                )

            # Character cards originally shipped with a greeting column. It is
            # no longer part of the model; drop it from existing databases.
            result = await connection.exec_driver_sql("PRAGMA table_info(character_cards)")
            character_columns = {row[1] for row in result.fetchall()}
            if "greeting" in character_columns:
                await connection.exec_driver_sql("ALTER TABLE character_cards DROP COLUMN greeting")

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

    # -- Model providers --------------------------------------------------

    async def list_model_providers(self, category: str | None = None) -> list[ModelProvider]:
        async with self.session() as session:
            statement = select(ModelProvider).order_by(
                ModelProvider.category,
                ModelProvider.created_at,
            )
            if category:
                statement = statement.where(ModelProvider.category == category)
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def get_model_provider(self, provider_id: int) -> ModelProvider | None:
        async with self.session() as session:
            return await session.get(ModelProvider, provider_id)

    async def create_model_provider(self, values: dict) -> ModelProvider:
        provider = ModelProvider(**values)
        async with self.session() as session:
            session.add(provider)
            await session.flush()
            await session.refresh(provider)
        return provider

    async def update_model_provider(
        self,
        provider_id: int,
        values: dict,
    ) -> ModelProvider | None:
        async with self.session() as session:
            provider = await session.get(ModelProvider, provider_id)
            if provider is None:
                return None
            for key, value in values.items():
                setattr(provider, key, value)
            self._touch(provider)
            session.add(provider)
            await session.flush()
            await session.refresh(provider)
            return provider

    async def delete_model_provider(self, provider_id: int) -> bool:
        async with self.session() as session:
            provider = await session.get(ModelProvider, provider_id)
            if provider is None:
                return False
            await session.delete(provider)
            return True

    async def set_default_model_provider(
        self,
        category: str,
        provider_id: int,
    ) -> ModelProvider | None:
        async with self.session() as session:
            provider = await session.get(ModelProvider, provider_id)
            if provider is None or provider.category != category:
                return None
            await session.execute(
                update(ModelProvider)
                .where(ModelProvider.category == category)
                .values(is_default=False)
            )
            provider.is_default = True
            provider.updated_at = utcnow()
            session.add(provider)
            await session.flush()
            await session.refresh(provider)
            return provider

    async def get_default_model_provider(self, category: str) -> ModelProvider | None:
        async with self.session() as session:
            result = await session.execute(
                select(ModelProvider)
                .where(ModelProvider.category == category)
                .where(ModelProvider.is_default.is_(True))
                .where(ModelProvider.enabled.is_(True))
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def record_model_provider_test(
        self,
        provider_id: int,
        ok: bool,
        message: str,
    ) -> None:
        async with self.session() as session:
            provider = await session.get(ModelProvider, provider_id)
            if provider is None:
                return
            provider.last_test_ok = ok
            provider.last_test_message = message[:512]
            provider.last_tested_at = utcnow()
            self._touch(provider)
            session.add(provider)

    # -- Character cards --------------------------------------------------

    async def list_character_cards(self) -> list[CharacterCard]:
        async with self.session() as session:
            result = await session.execute(
                select(CharacterCard).order_by(CharacterCard.created_at.asc())
            )
            return list(result.scalars().all())

    async def get_character_card(self, character_id: int) -> CharacterCard | None:
        async with self.session() as session:
            return await session.get(CharacterCard, character_id)

    async def get_character_card_by_name(self, name: str) -> CharacterCard | None:
        async with self.session() as session:
            result = await session.execute(
                select(CharacterCard).where(CharacterCard.name == name).limit(1)
            )
            return result.scalar_one_or_none()

    async def create_character_card(self, values: dict) -> CharacterCard:
        character = CharacterCard(**values)
        async with self.session() as session:
            session.add(character)
            await session.flush()
            await session.refresh(character)
        return character

    async def update_character_card(
        self,
        character_id: int,
        values: dict,
    ) -> CharacterCard | None:
        async with self.session() as session:
            character = await session.get(CharacterCard, character_id)
            if character is None:
                return None
            for key, value in values.items():
                setattr(character, key, value)
            self._touch(character)
            session.add(character)
            await session.flush()
            await session.refresh(character)
            return character

    async def delete_character_card(self, character_id: int) -> bool:
        async with self.session() as session:
            character = await session.get(CharacterCard, character_id)
            if character is None:
                return False
            await session.delete(character)
            return True

    async def clear_character_provider_refs(self, provider_id: int) -> None:
        async with self.session() as session:
            for column in (
                CharacterCard.chat_provider_id,
                CharacterCard.speech_provider_id,
                CharacterCard.image_provider_id,
            ):
                await session.execute(
                    update(CharacterCard)
                    .where(column == provider_id)
                    .values({column.key: None, "updated_at": utcnow()})
                )

    # -- Conversations ----------------------------------------------------

    async def create_conversation(self, values: dict) -> Conversation:
        conversation = Conversation(**values)
        async with self.session() as session:
            session.add(conversation)
            await session.flush()
            await session.refresh(conversation)
        return conversation

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        async with self.session() as session:
            return await session.get(Conversation, conversation_id)

    async def list_conversations(
        self,
        user_id: int,
        *,
        character_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        async with self.session() as session:
            statement = select(Conversation).where(Conversation.user_id == user_id)
            if character_id is not None:
                statement = statement.where(Conversation.character_id == character_id)
            statement = (
                statement.order_by(
                    Conversation.updated_at.desc(),
                    Conversation.created_at.desc(),
                )
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def update_conversation(
        self,
        conversation_id: str,
        values: dict,
    ) -> Conversation | None:
        async with self.session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                return None
            for key, value in values.items():
                setattr(conversation, key, value)
            self._touch(conversation)
            session.add(conversation)
            await session.flush()
            await session.refresh(conversation)
            return conversation

    async def delete_conversation(self, conversation_id: str) -> bool:
        async with self.session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                return False
            await session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.conversation_id == conversation_id
                )
            )
            await session.delete(conversation)
            return True

    async def list_conversation_messages(
        self,
        conversation_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
        after_id: int | None = None,
    ) -> tuple[list[ConversationMessage], bool]:
        if before_id is not None and after_id is not None:
            raise ValueError("before_id and after_id are mutually exclusive")

        fetch = max(1, limit) + 1
        async with self.session() as session:
            statement = select(ConversationMessage).where(
                ConversationMessage.conversation_id == conversation_id
            )
            if before_id is not None:
                statement = (
                    statement.where(ConversationMessage.id < before_id)
                    .order_by(ConversationMessage.id.desc())
                    .limit(fetch)
                )
            elif after_id is not None:
                statement = (
                    statement.where(ConversationMessage.id > after_id)
                    .order_by(ConversationMessage.id.asc())
                    .limit(fetch)
                )
            else:
                statement = statement.order_by(ConversationMessage.id.desc()).limit(fetch)

            result = await session.execute(statement)
            messages = list(result.scalars().all())

        has_more = len(messages) > limit
        if after_id is not None:
            if has_more:
                messages = messages[:limit]
        else:
            messages.reverse()
            if has_more:
                messages = messages[1:]
        return messages, has_more

    async def list_conversation_messages_by_client_id(
        self,
        conversation_id: str,
        client_message_id: str,
    ) -> list[ConversationMessage]:
        if not client_message_id:
            return []
        async with self.session() as session:
            result = await session.execute(
                select(ConversationMessage)
                .where(
                    ConversationMessage.conversation_id == conversation_id,
                    ConversationMessage.client_message_id == client_message_id,
                )
                .order_by(ConversationMessage.id.asc())
            )
            return list(result.scalars().all())

    async def append_conversation_exchange(
        self,
        conversation_id: str,
        *,
        user_values: dict,
        assistant_values: dict,
        title: str = "",
    ) -> tuple[ConversationMessage, ConversationMessage, Conversation] | None:
        async with self.session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                return None

            user_message = ConversationMessage(
                conversation_id=conversation_id,
                **user_values,
            )
            assistant_message = ConversationMessage(
                conversation_id=conversation_id,
                **assistant_values,
            )
            session.add_all((user_message, assistant_message))
            await session.flush()

            conversation.message_count += 2
            conversation.last_message_at = assistant_message.created_at or utcnow()
            preview = assistant_message.content.strip() or user_message.content.strip()
            conversation.last_message_preview = preview[:200]
            if not conversation.title and title:
                conversation.title = title[:100]
            self._touch(conversation)
            session.add(conversation)
            await session.flush()

            await session.refresh(user_message)
            await session.refresh(assistant_message)
            await session.refresh(conversation)
            return user_message, assistant_message, conversation
