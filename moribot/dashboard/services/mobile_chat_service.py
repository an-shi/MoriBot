"""Conversation generation for MoriMobile.

MoriBot deliberately does not store conversations. The phone keeps the history
and sends the current context with every request; this service only resolves
the bound character card, calls the model gateway and returns one reply.
"""

from __future__ import annotations

import base64
import uuid

from loguru import logger

from moribot.core.db import MobileDevice, utcnow
from moribot.core.errors import MoriError, NotFoundError
from moribot.core.i18n import DEFAULT_LOCALE, translate
from moribot.core.lifecycle import CoreLifecycle
from moribot.core.provider import (
    ChatMessage,
    GeneratedImage,
    ProviderCategory,
    ProviderError,
    SpeechResult,
)

from ..schemas import (
    CharacterOut,
    MobileCharacterOut,
    MobileChatMessageIn,
    MobileChatModelOut,
    MobileChatOut,
    MobileChatRequest,
    MobileImageOut,
    MobileSpeechOut,
)
from .character_service import CharacterService

MAX_MESSAGES = 200
MAX_MESSAGE_CHARS = 8000


class MobileChatService:
    """Resolve character cards and generate one mobile conversation reply."""

    def __init__(self, core: CoreLifecycle, characters: CharacterService) -> None:
        self.core = core
        self.db = core.db
        self.characters = characters

    async def list_characters(self) -> list[MobileCharacterOut]:
        """Return enabled character cards with their available media roles."""
        characters = await self.characters.list_characters()
        return [
            self._character_out(character)
            for character in characters
            if character.enabled
        ]

    async def generate(
        self,
        payload: MobileChatRequest,
        *,
        device: MobileDevice,
        locale: str = DEFAULT_LOCALE,
    ) -> MobileChatOut:
        """Generate a reply for the supplied conversation snapshot."""
        record = await self.db.get_character_card(payload.character_id)
        if record is None or not record.enabled:
            raise NotFoundError(translate("mobile.character_unavailable", locale))

        conversation = self._normalize_messages(payload.messages, locale)
        if conversation[-1].role != "user":
            raise MoriError(translate("mobile.chat_last_message_user", locale))

        manager = self.core.provider_manager
        chat_provider = manager.resolve(ProviderCategory.CHAT, record.chat_provider_id)
        if chat_provider is None:
            raise MoriError(
                translate("mobile.chat_model_missing", locale),
                status_code=409,
            )

        speech_provider = manager.resolve(
            ProviderCategory.SPEECH,
            record.speech_provider_id,
        )
        if payload.speech and speech_provider is None:
            raise MoriError(
                translate("mobile.speech_model_missing", locale),
                status_code=409,
            )

        messages = [
            ChatMessage(
                role="system",
                content=self._system_prompt(
                    record.name,
                    record.description,
                    record.persona,
                    locale,
                ),
            ),
            *conversation,
        ]

        try:
            reply = await self.core.model_gateway.chat(
                messages,
                chat_provider_id=record.chat_provider_id,
                speech_provider_id=record.speech_provider_id,
                image_provider_id=record.image_provider_id,
            )
            if payload.speech and reply.speech is None and reply.text.strip():
                reply.speech = await self.core.model_gateway.speak(
                    reply.text.strip(),
                    provider_id=record.speech_provider_id,
                )
        except ProviderError as exc:
            raise MoriError(
                translate("mobile.chat_failed", locale, detail=str(exc)[:300]),
                status_code=502,
            ) from exc

        client_message_id = payload.client_message_id.strip() or uuid.uuid4().hex
        logger.bind(source="mobile").info(
            "Generated chat reply: character={} device={} provider={} messages={} chars={}",
            record.id,
            device.id,
            chat_provider.provider_id,
            len(conversation),
            len(reply.text),
        )
        return MobileChatOut(
            client_message_id=client_message_id,
            character_id=record.id or payload.character_id,
            text=reply.text,
            speech=self._speech_out(reply.speech),
            images=[self._image_out(image) for image in reply.images],
            chat_model=MobileChatModelOut(
                provider_id=chat_provider.provider_id,
                model=chat_provider.model,
            ),
            created_at=utcnow(),
        )

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
    def _normalize_messages(
        items: list[MobileChatMessageIn],
        locale: str,
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        for item in items:
            content = item.content.strip()
            if not content:
                raise MoriError(translate("mobile.chat_message_empty", locale))
            if len(content) > MAX_MESSAGE_CHARS:
                raise MoriError(translate("mobile.chat_message_too_long", locale))
            messages.append(ChatMessage(role=item.role, content=content))
        if len(messages) > MAX_MESSAGES:
            raise MoriError(translate("mobile.chat_too_many_messages", locale))
        return messages

    @staticmethod
    def _system_prompt(name: str, description: str, persona: str, locale: str) -> str:
        parts = [translate("mobile.chat_system_prompt", locale, name=name)]
        if description.strip():
            parts.append(description.strip())
        if persona.strip():
            parts.append(persona.strip())
        return "\n\n".join(parts)

    @staticmethod
    def _speech_out(speech: SpeechResult | None) -> MobileSpeechOut | None:
        if speech is None:
            return None
        encoded = base64.b64encode(speech.audio).decode("ascii")
        return MobileSpeechOut(
            mime_type=speech.mime_type,
            format=speech.format,
            data_url=f"data:{speech.mime_type};base64,{encoded}",
            byte_length=len(speech.audio),
        )

    @staticmethod
    def _image_out(image: GeneratedImage) -> MobileImageOut:
        data_url = None
        if image.data:
            encoded = base64.b64encode(image.data).decode("ascii")
            data_url = f"data:{image.mime_type};base64,{encoded}"
        return MobileImageOut(
            mime_type=image.mime_type,
            data_url=data_url,
            url=image.url,
        )
