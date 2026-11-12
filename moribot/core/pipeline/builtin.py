"""Built-in pipeline stages.

They are intentionally thin placeholders that document where normalization,
model invocation and platform replies belong. This keeps the foundation
functional without inventing product behavior ahead of time.
"""

from __future__ import annotations

import re

from loguru import logger

from ..event import MoriEvent
from ..provider import ProviderCategory
from .context import PipelineContext
from .stage import Stage, register_stage


@register_stage
class PreprocessStage(Stage):
    """Normalize raw event text before it reaches the model layer."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx

    async def process(self, event: MoriEvent) -> None:
        normalized = re.sub(r"\s+", " ", event.message).strip()
        event.message = normalized
        event.extras["text"] = normalized
        logger.debug(
            "[{}] {}: {}",
            event.platform_id or "core",
            event.sender_name or event.sender_id or "unknown",
            event.summary(),
        )


@register_stage
class ProcessStage(Stage):
    """Invoke the agent/provider layer when one is connected.

    The foundation only records the event. A later iteration will fetch the
    default provider from ``ctx.provider_manager`` and publish the generated
    reply into ``event.extras["reply"]``.
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx

    async def process(self, event: MoriEvent) -> None:
        provider = self.ctx.provider_manager.get_default(ProviderCategory.CHAT)
        if provider is None:
            logger.debug("No chat provider registered; skipping generation.")
            return
        logger.debug("Chat provider {} is available for generation.", provider.provider_id)


@register_stage
class RespondStage(Stage):
    """Deliver a reply to the originating platform when one exists."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx

    async def process(self, event: MoriEvent) -> None:
        reply = event.extras.get("reply")
        if not reply:
            return
        adapter = self.ctx.platform_manager.get(event.platform_id)
        if adapter is None:
            logger.warning("No platform adapter for {}.", event.platform_id or "<core>")
            return
        await adapter.send_message(event.session_id, str(reply))
