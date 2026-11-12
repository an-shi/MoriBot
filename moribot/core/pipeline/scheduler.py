"""Ordered, onion-model pipeline scheduler."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import cast

from loguru import logger

from ..event import MoriEvent
from .bootstrap import ensure_builtin_stages_registered
from .context import PipelineContext
from .stage import Stage, registered_stages

STAGE_ORDER: tuple[str, ...] = (
    "PreprocessStage",
    "ProcessStage",
    "RespondStage",
)


class PipelineScheduler:
    """Instantiate stages once and run each event through the chain."""

    def __init__(
        self,
        ctx: PipelineContext,
        stage_classes: list[type[Stage]] | None = None,
    ) -> None:
        ensure_builtin_stages_registered()
        classes = list(stage_classes) if stage_classes is not None else registered_stages()
        rank = {name: index for index, name in enumerate(STAGE_ORDER)}
        classes.sort(key=lambda cls: rank.get(cls.__name__, len(rank)))
        self.ctx = ctx
        self._stage_classes = classes
        self.stages: list[Stage] = []

    async def initialize(self) -> None:
        """Create and initialize every stage instance."""
        self.stages = []
        for stage_class in self._stage_classes:
            stage = stage_class()
            await stage.initialize(self.ctx)
            self.stages.append(stage)
        logger.debug("Pipeline initialized with {} stage(s).", len(self.stages))

    async def execute(self, event: MoriEvent) -> None:
        """Run an event through the pipeline."""
        if event.is_stopped():
            return
        await self._process_stages(event)

    async def _process_stages(self, event: MoriEvent, from_stage: int = 0) -> None:
        for index in range(from_stage, len(self.stages)):
            stage = self.stages[index]
            result = stage.process(event)

            if isinstance(result, AsyncGenerator):
                generator = cast(AsyncGenerator[None, None], result)
                async for _ in generator:
                    if event.is_stopped():
                        break
                    await self._process_stages(event, index + 1)
                    if event.is_stopped():
                        break
                # The generator delegated to later stages itself; do not fall
                # through to the outer loop or they would run a second time.
                return
            else:
                await result
                if event.is_stopped():
                    logger.debug(
                        "Stage {} stopped event propagation.",
                        stage.__class__.__name__,
                    )
                    break
