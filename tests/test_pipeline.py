"""Pipeline behavior tests, kept independent from concrete managers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import cast

from moribot.core.event import MoriEvent
from moribot.core.pipeline import PipelineContext, PipelineScheduler, Stage


async def test_onion_model_runs_post_processing_after_later_stages():
    calls: list[str] = []

    class Outer(Stage):
        async def initialize(self, ctx: PipelineContext) -> None:
            self.ctx = ctx

        async def process(self, event: MoriEvent) -> AsyncGenerator[None, None]:
            calls.append("outer-in")
            yield
            calls.append("outer-out")

    class Inner(Stage):
        async def initialize(self, ctx: PipelineContext) -> None:
            self.ctx = ctx

        async def process(self, event: MoriEvent) -> None:
            calls.append("inner")

    ctx = cast(PipelineContext, SimpleNamespace())
    scheduler = PipelineScheduler(ctx, [Outer, Inner])
    await scheduler.initialize()
    await scheduler.execute(MoriEvent(message="hello"))

    assert calls == ["outer-in", "inner", "outer-out"]


async def test_stopping_stage_halts_propagation():
    calls: list[str] = []

    class Stop(Stage):
        async def initialize(self, ctx: PipelineContext) -> None:
            self.ctx = ctx

        async def process(self, event: MoriEvent) -> None:
            calls.append("stop")
            event.stop()

    class After(Stage):
        async def initialize(self, ctx: PipelineContext) -> None:
            self.ctx = ctx

        async def process(self, event: MoriEvent) -> None:
            calls.append("after")

    ctx = cast(PipelineContext, SimpleNamespace())
    scheduler = PipelineScheduler(ctx, [Stop, After])
    await scheduler.initialize()
    await scheduler.execute(MoriEvent(message="hello"))

    assert calls == ["stop"]
