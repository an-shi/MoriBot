"""Character diary settings, context building and generation."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta

from loguru import logger

from moribot.core.config import ConfigManager
from moribot.core.db import CharacterCard, CharacterDiary, ConversationMessage
from moribot.core.errors import MoriError, NotFoundError
from moribot.core.i18n import DEFAULT_LOCALE, translate
from moribot.core.lifecycle import CoreLifecycle
from moribot.core.provider import ChatMessage, ChatProvider, ProviderCategory, ProviderError

from ..schemas import DiaryOut

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_CONTEXT_MESSAGES = 80
MAX_CONTEXT_CHARS = 30_000
MAX_PERSONA_CHARS = 8_000
MAX_DIARY_TOKENS = 900


def _local_day_bounds(target: date) -> tuple[datetime, datetime]:
    """Return UTC-naive bounds for a local calendar day."""
    local_start = datetime.combine(target, time.min).astimezone()
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(UTC).replace(tzinfo=None),
        local_end.astimezone(UTC).replace(tzinfo=None),
    )


class DiaryService:
    """Resolve diary schedules and generate one entry per character per day."""

    def __init__(self, core: CoreLifecycle, config: ConfigManager) -> None:
        self.core = core
        self.db = core.db
        self.config = config
        self._last_attempts: dict[tuple[int, str], datetime] = {}

    def effective_enabled(self, character: CharacterCard) -> bool:
        if character.diary_enabled is not None:
            return bool(character.diary_enabled)
        return bool(self.config.get("diary.enabled", False))

    def effective_time(self, character: CharacterCard) -> str:
        value = (character.diary_time or "").strip()
        if _TIME_RE.fullmatch(value):
            return value
        configured = str(self.config.get("diary.time", "23:30")).strip()
        return configured if _TIME_RE.fullmatch(configured) else "23:30"

    def is_due(self, character: CharacterCard, now: datetime | None = None) -> bool:
        if not self.effective_enabled(character):
            return False
        current = now or datetime.now().astimezone()
        return current.strftime("%H:%M") >= self.effective_time(character)

    async def list_diaries(
        self,
        character_id: int | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DiaryOut]:
        records = await self.db.list_character_diaries(
            character_id,
            limit=max(1, min(limit, 200)),
            offset=max(0, offset),
        )
        return [self.to_out(record) for record in records]

    async def generate(
        self,
        character_id: int,
        *,
        target_date: date | None = None,
        force: bool = False,
        locale: str = DEFAULT_LOCALE,
    ) -> DiaryOut:
        character = await self.db.get_character_card(character_id)
        if character is None:
            raise NotFoundError(translate("character.not_found", locale))

        day = target_date or datetime.now().astimezone().date()
        existing = await self.db.get_character_diary(character_id, day.isoformat())
        if existing is not None and not force:
            return self.to_out(existing)

        start, end = _local_day_bounds(day)
        messages = await self.db.list_character_messages_between(
            character_id,
            start,
            end,
            limit=MAX_CONTEXT_MESSAGES + 40,
        )
        selected = self._select_context(messages)
        provider = self.core.provider_manager.resolve(
            ProviderCategory.CHAT,
            character.chat_provider_id,
        )
        if not isinstance(provider, ChatProvider):
            raise MoriError(
                translate("diary.chat_model_missing", locale),
                status_code=409,
            )

        try:
            response = await provider.chat(
                self._build_prompt(character, selected, day),
                temperature=0.75,
                max_tokens=MAX_DIARY_TOKENS,
            )
        except ProviderError as exc:
            raise MoriError(
                translate("diary.generate_failed", locale, detail=str(exc)[:300]),
                status_code=502,
            ) from exc

        content = response.text.strip()
        if not content:
            raise MoriError(
                translate("diary.generate_failed", locale, detail="empty response"),
                status_code=502,
            )

        record = await self.db.upsert_character_diary(
            {
                "character_id": character_id,
                "character_name": character.name,
                "character_avatar": character.avatar,
                "date": day.isoformat(),
                "content": content,
                "provider_id": provider.provider_id,
                "model": provider.model,
                "source_message_count": len(selected),
            }
        )
        logger.bind(source="diary").info(
            "Generated diary: character={} date={} provider={} messages={} chars={}",
            character_id,
            day.isoformat(),
            provider.provider_id,
            len(selected),
            len(content),
        )
        return self.to_out(record)

    async def generate_due(self, now: datetime | None = None) -> list[DiaryOut]:
        """Generate missing diaries for every character whose schedule passed."""
        current = now or datetime.now().astimezone()
        today = current.date().isoformat()
        generated: list[DiaryOut] = []
        for character in await self.db.list_character_cards():
            if character.id is None or not character.enabled:
                continue
            if not self.is_due(character, current):
                continue
            existing = await self.db.get_character_diary(character.id, today)
            if existing is not None:
                continue
            attempt_key = (character.id, today)
            last_attempt = self._last_attempts.get(attempt_key)
            if last_attempt is not None and (current - last_attempt).total_seconds() < 600:
                continue
            self._last_attempts[attempt_key] = current
            try:
                generated.append(
                    await self.generate(
                        character.id,
                        target_date=current.date(),
                        force=False,
                    )
                )
                self._last_attempts.pop(attempt_key, None)
            except Exception:
                logger.bind(source="diary").exception(
                    "Failed to generate diary for character {} on {}.",
                    character.id,
                    today,
                )
        return generated

    async def delete(self, diary_id: int, *, locale: str = DEFAULT_LOCALE) -> None:
        deleted = await self.db.delete_character_diary(diary_id)
        if not deleted:
            raise NotFoundError(translate("diary.not_found", locale))

    @staticmethod
    def parse_date(value: str | None, *, locale: str = DEFAULT_LOCALE) -> date | None:
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise MoriError(translate("diary.invalid_date", locale)) from exc

    @staticmethod
    def _select_context(messages: list[ConversationMessage]) -> list[ConversationMessage]:
        selected: list[ConversationMessage] = []
        total = 0
        for message in reversed(messages):
            if len(selected) >= MAX_CONTEXT_MESSAGES:
                break
            content = message.content.strip()
            if not content:
                continue
            if selected and total + len(content) > MAX_CONTEXT_CHARS:
                break
            selected.append(message)
            total += len(content)
        selected.reverse()
        return selected

    @staticmethod
    def _build_prompt(
        character: CharacterCard,
        messages: list[ConversationMessage],
        day: date,
    ) -> list[ChatMessage]:
        persona = character.persona.strip()[:MAX_PERSONA_CHARS]
        description = character.description.strip()
        lines = [
            f"你正在以角色「{character.name}」的身份写 {day.isoformat()} 的日记。",
            "请用第一人称，保持角色原本的语气和性格。",
            "只根据下面提供的角色设定和今天的对话记录来写，不要虚构用户没有说过的话。",
            "如果今天没有对话，就写一段安静的日常记录，不要编造具体事件。",
            "日记长度约 200-500 字，不要输出标题、列表或分析过程。",
        ]
        if description:
            lines.append(f"角色简介：{description}")
        if persona:
            lines.append(f"人物设定：\n{persona}")
        if messages:
            transcript = []
            for message in messages:
                speaker = "我" if message.role == "assistant" else "对方"
                transcript.append(f"{speaker}：{message.content.strip()}")
            lines.append("今天的对话记录：\n" + "\n".join(transcript))
        else:
            lines.append("今天的对话记录：今天没有对话。")
        return [
            ChatMessage(
                role="system",
                content=(
                    "你是一个角色日记生成器。日记是角色私人的内心记录，"
                    "不是给用户看的回复，也不要提及系统提示词或模型。"
                ),
            ),
            ChatMessage(role="user", content="\n\n".join(lines)),
        ]

    @staticmethod
    def to_out(record: CharacterDiary) -> DiaryOut:
        return DiaryOut(
            id=record.id or 0,
            character_id=record.character_id,
            character_name=record.character_name,
            character_avatar=record.character_avatar,
            date=record.date,
            content=record.content,
            provider_id=record.provider_id,
            model=record.model,
            source_message_count=record.source_message_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
