"""Persistent conversations and model generation for MoriMobile.

MoriBot is the source of truth for characters, conversations, messages and
generated media. The phone sends only a new message; the server loads the
stored history, builds the model context, persists both sides of the exchange
and returns the updated records. Local phone storage is therefore a cache.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from loguru import logger

from moribot.core.db import (
    CharacterCard,
    Conversation,
    ConversationMessage,
    MobileDevice,
    User,
)
from moribot.core.errors import MoriError, NotFoundError
from moribot.core.i18n import DEFAULT_LOCALE, translate
from moribot.core.lifecycle import CoreLifecycle
from moribot.core.provider import (
    ChatMessage,
    GeneratedImage,
    ModelReply,
    ProviderCategory,
    ProviderError,
    SpeechResult,
)

from ..schemas import (
    CharacterOut,
    MobileCharacterOut,
    MobileConversationCreate,
    MobileConversationOut,
    MobileConversationPageOut,
    MobileConversationUpdate,
    MobileImageOut,
    MobileMessageOut,
    MobileMessagePageOut,
    MobileSendMessageOut,
    MobileSendMessageRequest,
    MobileSpeechOut,
)
from .character_service import CharacterService

MAX_PAGE_SIZE = 100
MAX_CONTEXT_MESSAGES = 100
MAX_CONTEXT_CHARS = 60_000
MAX_TITLE_CHARS = 40
MAX_DELETE_SCAN = 1_000_000
MEDIA_URL_PREFIX = "/api/v1/mobile/app/media/"

_MEDIA_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/opus": ".opus",
    "audio/ogg": ".ogg",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/pcm": ".pcm",
    "audio/webm": ".webm",
}


class MobileChatService:
    """Resolve character cards, store conversations and generate replies."""

    def __init__(self, core: CoreLifecycle, characters: CharacterService) -> None:
        self.core = core
        self.db = core.db
        self.characters = characters
        self._locks: dict[str, asyncio.Lock] = {}

    async def list_characters(self) -> list[MobileCharacterOut]:
        """Return enabled character cards with their available media roles."""
        records = await self.characters.list_characters()
        return [
            self._character_out(character)
            for character in records
            if character.enabled
        ]

    async def list_conversations(
        self,
        user: User,
        *,
        character_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MobileConversationPageOut:
        """List conversations owned by the account, most recent first."""
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)
        records = await self.db.list_conversations(
            self._user_id(user),
            character_id=character_id,
            limit=limit + 1,
            offset=offset,
        )
        has_more = len(records) > limit
        records = records[:limit]
        characters = await self._character_map()
        return MobileConversationPageOut(
            conversations=[
                self._conversation_out(record, characters.get(record.character_id))
                for record in records
            ],
            has_more=has_more,
        )

    async def create_conversation(
        self,
        user: User,
        device: MobileDevice,
        payload: MobileConversationCreate,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> MobileConversationOut:
        """Create an empty conversation bound to a character."""
        character = await self.db.get_character_card(payload.character_id)
        if character is None or not character.enabled:
            raise NotFoundError(translate("mobile.character_unavailable", locale))

        record = await self.db.create_conversation(
            {
                "user_id": self._user_id(user),
                "character_id": character.id or payload.character_id,
                "device_id": device.id,
                "character_name": character.name,
                "character_avatar": character.avatar,
                "title": payload.title.strip()[:100],
            }
        )
        logger.bind(source="mobile").info(
            "Created conversation {} for character {} (device {}).",
            record.id,
            record.character_id,
            device.id,
        )
        return self._conversation_out(record, character)

    async def get_conversation(
        self,
        user: User,
        conversation_id: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> MobileConversationOut:
        record = await self._owned_conversation(user, conversation_id, locale)
        character = await self.db.get_character_card(record.character_id)
        return self._conversation_out(record, character)

    async def update_conversation(
        self,
        user: User,
        conversation_id: str,
        payload: MobileConversationUpdate,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> MobileConversationOut:
        record = await self._owned_conversation(user, conversation_id, locale)
        title = payload.title.strip()
        if not title:
            raise MoriError(translate("mobile.conversation_title_required", locale))
        updated = await self.db.update_conversation(record.id, {"title": title[:100]})
        if updated is None:
            raise NotFoundError(translate("mobile.conversation_not_found", locale))
        character = await self.db.get_character_card(updated.character_id)
        return self._conversation_out(updated, character)

    async def delete_conversation(
        self,
        user: User,
        conversation_id: str,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> None:
        record = await self._owned_conversation(user, conversation_id, locale)
        lock = self._locks.setdefault(record.id, asyncio.Lock())
        async with lock:
            messages, _ = await self.db.list_conversation_messages(
                record.id,
                limit=MAX_DELETE_SCAN,
            )
            deleted = await self.db.delete_conversation(record.id)
            if not deleted:
                raise NotFoundError(translate("mobile.conversation_not_found", locale))
            for message in messages:
                await self._delete_message_media(self._user_id(user), message)

    async def list_messages(
        self,
        user: User,
        conversation_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
        after_id: int | None = None,
        locale: str = DEFAULT_LOCALE,
    ) -> MobileMessagePageOut:
        """Return one page of history in ascending message-id order."""
        if before_id is not None and after_id is not None:
            raise MoriError(translate("mobile.message_cursor_conflict", locale))
        await self._owned_conversation(user, conversation_id, locale)
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        messages, has_more = await self.db.list_conversation_messages(
            conversation_id,
            limit=limit,
            before_id=before_id,
            after_id=after_id,
        )
        return MobileMessagePageOut(
            messages=[self._message_out(message) for message in messages],
            has_more=has_more,
            earliest_id=messages[0].id if messages else None,
            latest_id=messages[-1].id if messages else None,
        )

    async def send_message(
        self,
        user: User,
        device: MobileDevice,
        conversation_id: str,
        payload: MobileSendMessageRequest,
        *,
        locale: str = DEFAULT_LOCALE,
    ) -> MobileSendMessageOut:
        """Persist a user message, generate a reply and persist both."""
        conversation = await self._owned_conversation(user, conversation_id, locale)
        character = await self.db.get_character_card(conversation.character_id)
        if character is None or not character.enabled:
            raise NotFoundError(translate("mobile.character_unavailable", locale))

        content = payload.content.strip()
        if not content:
            raise MoriError(translate("mobile.chat_message_empty", locale))
        if len(content) > 8000:
            raise MoriError(translate("mobile.chat_message_too_long", locale))

        client_message_id = payload.client_message_id.strip() or uuid.uuid4().hex
        lock = self._locks.setdefault(conversation.id, asyncio.Lock())
        async with lock:
            existing = await self.db.list_conversation_messages_by_client_id(
                conversation.id,
                client_message_id,
            )
            if existing:
                user_message = next(
                    (message for message in existing if message.role == "user"),
                    None,
                )
                assistant_message = next(
                    (message for message in existing if message.role == "assistant"),
                    None,
                )
                if user_message is None or assistant_message is None:
                    raise MoriError(
                        translate("mobile.message_processing", locale),
                        status_code=409,
                    )
                fresh = await self.db.get_conversation(conversation.id) or conversation
                return MobileSendMessageOut(
                    conversation=self._conversation_out(fresh, character),
                    user_message=self._message_out(user_message),
                    assistant_message=self._message_out(assistant_message),
                )

            history, _ = await self.db.list_conversation_messages(
                conversation.id,
                limit=MAX_CONTEXT_MESSAGES,
            )
            messages = self._build_context(character, history, content, locale)

            manager = self.core.provider_manager
            chat_provider = manager.resolve(
                ProviderCategory.CHAT,
                character.chat_provider_id,
            )
            if chat_provider is None:
                raise MoriError(
                    translate("mobile.chat_model_missing", locale),
                    status_code=409,
                )
            speech_provider = manager.resolve(
                ProviderCategory.SPEECH,
                character.speech_provider_id,
            )
            if payload.speech and speech_provider is None:
                raise MoriError(
                    translate("mobile.speech_model_missing", locale),
                    status_code=409,
                )

            try:
                reply = await self.core.model_gateway.chat(
                    messages,
                    chat_provider_id=character.chat_provider_id,
                    speech_provider_id=character.speech_provider_id,
                    image_provider_id=character.image_provider_id,
                )
                if payload.speech and reply.speech is None and reply.text.strip():
                    reply.speech = await self.core.model_gateway.speak(
                        reply.text.strip(),
                        provider_id=character.speech_provider_id,
                    )
            except ProviderError as exc:
                raise MoriError(
                    translate("mobile.chat_failed", locale, detail=str(exc)[:300]),
                    status_code=502,
                ) from exc

            media = await self._persist_media(self._user_id(user), reply)
            try:
                exchange = await self.db.append_conversation_exchange(
                    conversation.id,
                    user_values={
                        "role": "user",
                        "content": content,
                        "client_message_id": client_message_id,
                    },
                    assistant_values={
                        "role": "assistant",
                        "content": reply.text.strip(),
                        "client_message_id": client_message_id,
                        "provider_id": chat_provider.provider_id,
                        "model": chat_provider.model,
                        "media": media,
                    },
                    title=self._title_from_content(content) if not conversation.title else "",
                )
            except Exception:
                await self._remove_media_files(self._user_id(user), media)
                raise

            if exchange is None:
                await self._remove_media_files(self._user_id(user), media)
                raise NotFoundError(translate("mobile.conversation_not_found", locale))

            user_message, assistant_message, updated = exchange
            logger.bind(source="mobile").info(
                "Generated conversation reply: conversation={} device={} provider={} "
                "history={} chars={}",
                conversation.id,
                device.id,
                chat_provider.provider_id,
                len(history),
                len(reply.text),
            )
            return MobileSendMessageOut(
                conversation=self._conversation_out(updated, character),
                user_message=self._message_out(user_message),
                assistant_message=self._message_out(assistant_message),
            )

    def media_path(self, user: User, filename: str) -> Path | None:
        """Resolve an authenticated media file inside the user's directory."""
        name = Path(filename).name
        if not name or name != filename:
            return None
        path = self.core.paths.media_dir / str(self._user_id(user)) / name
        return path if path.is_file() else None

    async def _owned_conversation(
        self,
        user: User,
        conversation_id: str,
        locale: str,
    ) -> Conversation:
        record = await self.db.get_conversation(conversation_id)
        if record is None or record.user_id != self._user_id(user):
            raise NotFoundError(translate("mobile.conversation_not_found", locale))
        return record

    async def _character_map(self) -> dict[int, CharacterCard]:
        records = await self.db.list_character_cards()
        return {
            record.id: record
            for record in records
            if record.id is not None
        }

    def _character_out(self, character: CharacterOut) -> MobileCharacterOut:
        manager = self.core.provider_manager
        return MobileCharacterOut(
            id=character.id,
            name=character.name,
            avatar=character.avatar,
            description=character.description,
            chat_available=(
                manager.resolve(ProviderCategory.CHAT, character.chat_provider_id)
                is not None
            ),
            speech_available=(
                manager.resolve(ProviderCategory.SPEECH, character.speech_provider_id)
                is not None
            ),
            image_available=(
                manager.resolve(ProviderCategory.IMAGE, character.image_provider_id)
                is not None
            ),
            updated_at=character.updated_at,
        )

    @staticmethod
    def _conversation_out(
        record: Conversation,
        character: CharacterCard | None,
    ) -> MobileConversationOut:
        return MobileConversationOut(
            id=record.id,
            character_id=record.character_id,
            character_name=character.name if character else record.character_name,
            character_avatar=character.avatar if character else "",
            character_available=bool(character and character.enabled),
            title=record.title,
            last_message_preview=record.last_message_preview,
            last_message_at=record.last_message_at,
            message_count=record.message_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _message_out(record: ConversationMessage) -> MobileMessageOut:
        speech: MobileSpeechOut | None = None
        images: list[MobileImageOut] = []
        for item in record.media or []:
            if not isinstance(item, dict):
                continue
            media_type = str(item.get("type", ""))
            url = str(item.get("url", ""))
            if not url:
                continue
            if media_type == "audio" and speech is None:
                speech = MobileSpeechOut(
                    url=url,
                    mime_type=str(item.get("mime_type", "audio/mpeg")),
                    format=str(item.get("format", "mp3")),
                    byte_length=int(item.get("byte_length", 0) or 0),
                )
            elif media_type == "image":
                images.append(
                    MobileImageOut(
                        url=url,
                        mime_type=str(item.get("mime_type", "image/png")),
                    )
                )
        return MobileMessageOut(
            id=record.id or 0,
            conversation_id=record.conversation_id,
            role=record.role,
            content=record.content,
            speech=speech,
            images=images,
            client_message_id=record.client_message_id,
            provider_id=record.provider_id,
            model=record.model,
            created_at=record.created_at,
        )

    @staticmethod
    def _build_context(
        character: CharacterCard,
        history: list[ConversationMessage],
        content: str,
        locale: str,
    ) -> list[ChatMessage]:
        selected: list[ChatMessage] = []
        total_chars = 0
        for message in reversed(history):
            if len(selected) >= MAX_CONTEXT_MESSAGES:
                break
            if selected and total_chars + len(message.content) > MAX_CONTEXT_CHARS:
                break
            selected.append(ChatMessage(role=message.role, content=message.content))
            total_chars += len(message.content)
        selected.reverse()
        return [
            ChatMessage(
                role="system",
                content=MobileChatService._system_prompt(character, locale),
            ),
            *selected,
            ChatMessage(role="user", content=content),
        ]

    @staticmethod
    def _system_prompt(character: CharacterCard, locale: str) -> str:
        parts = [translate("mobile.chat_system_prompt", locale, name=character.name)]
        if character.description.strip():
            parts.append(character.description.strip())
        if character.persona.strip():
            parts.append(character.persona.strip())
        return "\n\n".join(parts)

    @staticmethod
    def _title_from_content(content: str) -> str:
        title = content.strip().splitlines()[0].strip()
        if len(title) > MAX_TITLE_CHARS:
            return f"{title[:MAX_TITLE_CHARS]}…"
        return title

    async def _persist_media(
        self,
        user_id: int,
        reply: ModelReply,
    ) -> list[dict]:
        media: list[dict] = []
        if reply.speech is not None:
            item = await self._save_speech(user_id, reply.speech)
            if item is not None:
                media.append(item)
        for image in reply.images:
            item = await self._save_image(user_id, image)
            if item is not None:
                media.append(item)
        return media

    async def _save_speech(self, user_id: int, speech: SpeechResult) -> dict | None:
        if not speech.audio:
            return None
        mime_type = speech.mime_type or "audio/mpeg"
        extension = _MEDIA_EXTENSIONS.get(mime_type)
        if extension is None:
            extension = _MEDIA_EXTENSIONS.get(f"audio/{speech.format}", ".bin")
        filename = f"{uuid.uuid4().hex}{extension}"
        target = self._media_dir(user_id) / filename
        await asyncio.to_thread(target.write_bytes, speech.audio)
        return {
            "type": "audio",
            "url": f"{MEDIA_URL_PREFIX}{filename}",
            "mime_type": mime_type,
            "format": speech.format or "mp3",
            "byte_length": len(speech.audio),
        }

    async def _save_image(self, user_id: int, image: GeneratedImage) -> dict | None:
        mime_type = image.mime_type or "image/png"
        if image.data:
            extension = _MEDIA_EXTENSIONS.get(mime_type, ".bin")
            filename = f"{uuid.uuid4().hex}{extension}"
            target = self._media_dir(user_id) / filename
            await asyncio.to_thread(target.write_bytes, image.data)
            return {
                "type": "image",
                "url": f"{MEDIA_URL_PREFIX}{filename}",
                "mime_type": mime_type,
            }
        if image.url:
            return {
                "type": "image",
                "url": image.url,
                "mime_type": mime_type,
            }
        return None

    def _media_dir(self, user_id: int) -> Path:
        target = self.core.paths.media_dir / str(user_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    async def _delete_message_media(
        self,
        user_id: int,
        message: ConversationMessage,
    ) -> None:
        await self._remove_media_files(user_id, message.media or [])

    async def _remove_media_files(self, user_id: int, media: list[dict]) -> None:
        for item in media:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", ""))
            if not url.startswith(MEDIA_URL_PREFIX):
                continue
            name = Path(url.rsplit("/", 1)[-1]).name
            if not name:
                continue
            target = self.core.paths.media_dir / str(user_id) / name
            try:
                await asyncio.to_thread(target.unlink, missing_ok=True)
            except OSError:
                logger.warning("Failed to delete media file {}.", target)

    def _user_id(self, user: User) -> int:
        if user.id is None:
            raise MoriError(
                translate("auth.account_data_error", DEFAULT_LOCALE),
                status_code=500,
            )
        return user.id
