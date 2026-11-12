"""Pipeline stage contract and registry."""

from __future__ import annotations

import abc
from collections.abc import AsyncGenerator

from ..event import MoriEvent
from .context import PipelineContext


class Stage(abc.ABC):
    """One step of the message pipeline.

    Returning an async generator enables the onion model: code before ``yield``
    runs on the way in, code after ``yield`` runs after all later stages finish.
    Returning ``None`` continues to the next stage without a post-processing
    hook.
    """

    @abc.abstractmethod
    async def initialize(self, ctx: PipelineContext) -> None:
        """Prepare the stage with shared dependencies."""
        raise NotImplementedError

    @abc.abstractmethod
    async def process(
        self,
        event: MoriEvent,
    ) -> None | AsyncGenerator[None, None]:
        """Process an event or delegate to later stages."""
        raise NotImplementedError


_registered_stages: list[type[Stage]] = []


def register_stage(cls: type[Stage]) -> type[Stage]:
    """Register a stage class for automatic pipeline assembly."""
    if cls not in _registered_stages:
        _registered_stages.append(cls)
    return cls


def registered_stages() -> list[type[Stage]]:
    """Return a copy of the global registration order."""
    return list(_registered_stages)
