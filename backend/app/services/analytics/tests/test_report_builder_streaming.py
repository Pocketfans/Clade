from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app.simulation.environment import ParsedPressure
from app.services.analytics.report_builder import ReportBuilder
from app.services.analytics.report_builder_v2 import ReportBuilderV2
from app.services.analytics.turn_report import TurnReportService
from app.simulation.stages import BuildReportStage


class InterruptedStreamRouter:
    def __init__(self, partial: str) -> None:
        self.partial = partial

    async def astream(self, capability: str, payload: dict[str, Any]):
        yield {"type": "status", "state": "receiving"}
        yield self.partial
        yield {
            "type": "status",
            "state": "interrupted",
            "reason": "outbound_timeout",
            "partial": True,
        }

    async def astream_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ):
        yield {"type": "status", "state": "receiving"}
        yield self.partial
        yield {
            "type": "status",
            "state": "interrupted",
            "reason": "outbound_timeout",
            "partial": True,
        }


class CompleteStreamRouter:
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks

    async def astream(self, capability: str, payload: dict[str, Any]):
        for chunk in self.chunks:
            yield chunk
        yield {"type": "status", "state": "completed"}

    async def astream_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ):
        for chunk in self.chunks:
            yield chunk
        yield {"type": "status", "state": "completed"}


class OrderedAwaitable:
    def __init__(self, order: list[str], label: str) -> None:
        self.order = order
        self.label = label
        self.awaited = False

    def __await__(self):
        async def complete() -> None:
            self.awaited = True
            self.order.append(self.label)

        return complete().__await__()


def _pressure() -> ParsedPressure:
    return ParsedPressure(
        kind="drought",
        intensity=4,
        affected_tiles=[1],
        narrative="持续干旱使可用水源减少",
    )


@pytest.mark.asyncio
async def test_v1_displays_partial_stream_but_returns_complete_fallback() -> None:
    partial = "UNFINISHED_V1_NARRATIVE_" + "x" * 100
    shown: list[str] = []
    events: list[tuple[str, str, str]] = []
    builder = ReportBuilder(InterruptedStreamRouter(partial))

    report = await builder.build_turn_narrative_async(
        species=[],
        pressures=[_pressure()],
        stream_callback=lambda chunk: shown.append(chunk),
        event_callback=lambda *event: events.append(event),
    )

    assert shown == [partial]
    assert "**环境压力**" in report
    assert partial not in report
    assert [event for event in events if event[0] == "ai_stream_interrupted"] == [
        ("ai_stream_interrupted", "回合报告 interrupted", "AI")
    ]
    assert all(partial not in message and "outbound_timeout" not in message for _, message, _ in events)


@pytest.mark.asyncio
async def test_v2_displays_partial_stream_but_returns_complete_fallback() -> None:
    partial = "UNFINISHED_V2_NARRATIVE_" + "y" * 100
    shown: list[str] = []
    events: list[tuple[str, str, str]] = []
    builder = ReportBuilderV2(InterruptedStreamRouter(partial))

    report = await builder.build_turn_narrative_async(
        species=[],
        pressures=[_pressure()],
        turn_index=7,
        stream_callback=lambda chunk: shown.append(chunk),
        event_callback=lambda *event: events.append(event),
    )

    assert shown == [partial]
    assert "## 🕐 第 7 回合" in report
    assert partial not in report
    assert [event for event in events if event[0] == "ai_stream_interrupted"] == [
        ("ai_stream_interrupted", "第7回合报告 interrupted", "AI")
    ]
    assert all(partial not in message and "outbound_timeout" not in message for _, message, _ in events)


class EventEmittingReportBuilder:
    def __init__(self) -> None:
        self.event_callback: Callable[[str, str, str], None] | None = None
        self.fallback = "完整规则备用报告：" + "z" * 60

    async def build_turn_narrative_async(self, **kwargs: Any) -> str:
        self.event_callback = kwargs.get("event_callback")
        assert self.event_callback is not None
        self.event_callback(
            "ai_stream_interrupted",
            "回合报告 interrupted",
            "AI",
        )
        return self.fallback


@pytest.mark.asyncio
async def test_turn_report_service_bridges_builder_events(monkeypatch, tmp_path) -> None:
    settings = SimpleNamespace(
        ui_config_path=tmp_path / "missing-settings.json",
        enable_turn_report_llm=True,
    )
    monkeypatch.setattr("app.services.analytics.turn_report.get_settings", lambda: settings)
    builder = EventEmittingReportBuilder()
    events: list[tuple[str, str, str]] = []

    def emit_event(event_type: str, message: str, category: str) -> None:
        events.append((event_type, message, category))
        if event_type == "ai_stream_interrupted":
            raise RuntimeError("downstream event consumer failed")

    service = TurnReportService(
        report_builder=builder,
        environment_repository=object(),
        trophic_service=object(),
        emit_event_fn=emit_event,
    )

    report = await service.build_report(
        turn_index=3,
        mortality_results=[],
        pressures=[],
        branching_events=[],
        all_species=[],
    )

    assert report.narrative == builder.fallback
    assert builder.event_callback is not None
    assert [event for event in events if event[0] == "ai_stream_interrupted"] == [
        ("ai_stream_interrupted", "回合报告 interrupted", "AI")
    ]
    assert all(event_type != "ai_stream_complete" for event_type, _, _ in events)
    assert all(message != "✅ AI 叙事生成完成" for _, message, _ in events)


class SuccessfulReportBuilder:
    def __init__(self, terminal_event: str | None) -> None:
        self.terminal_event = terminal_event
        self.narrative = "完整 AI 报告：" + "a" * 60

    async def build_turn_narrative_async(self, **kwargs: Any) -> str:
        if self.terminal_event is not None:
            event_callback = kwargs.get("event_callback")
            assert event_callback is not None
            event_callback(self.terminal_event, "回合报告 complete", "AI")
        return self.narrative


@pytest.mark.parametrize("terminal_event", [None, "ai_stream_complete"])
@pytest.mark.asyncio
async def test_turn_report_service_keeps_normal_ai_completion(
    terminal_event: str | None,
    monkeypatch,
    tmp_path,
) -> None:
    settings = SimpleNamespace(
        ui_config_path=tmp_path / "missing-settings.json",
        enable_turn_report_llm=True,
    )
    monkeypatch.setattr("app.services.analytics.turn_report.get_settings", lambda: settings)
    builder = SuccessfulReportBuilder(terminal_event)
    events: list[tuple[str, str, str]] = []
    service = TurnReportService(
        report_builder=builder,
        environment_repository=object(),
        trophic_service=object(),
        emit_event_fn=lambda *event: events.append(event),
    )

    report = await service.build_report(
        turn_index=4,
        mortality_results=[],
        pressures=[],
        branching_events=[],
        all_species=[],
    )

    assert report.narrative == builder.narrative
    assert ("info", "✅ AI 叙事生成完成", "报告") in events


@pytest.mark.parametrize(
    ("length", "uses_fallback"),
    [(0, True), (5, True), (50, True), (51, False)],
)
@pytest.mark.asyncio
async def test_v2_only_accepts_complete_narratives_longer_than_50_chars(
    length: int,
    uses_fallback: bool,
) -> None:
    narrative = "n" * length
    builder = ReportBuilderV2(CompleteStreamRouter([narrative] if narrative else []))

    report = await builder.build_turn_narrative_async(
        species=[],
        pressures=[_pressure()],
        turn_index=8,
    )

    if uses_fallback:
        assert "## 🕐 第 8 回合" in report
        assert report != narrative
    else:
        assert report == narrative


@pytest.mark.asyncio
async def test_v2_awaits_heartbeat_and_stream_awaitables_in_order() -> None:
    chunks = [f"chunk-{index:02d}-data-" for index in range(1, 6)]
    order: list[str] = []
    heartbeat_futures: list[asyncio.Future[None]] = []
    stream_awaitables: list[OrderedAwaitable] = []

    def heartbeat_callback(count: int) -> asyncio.Future[None]:
        order.append(f"heartbeat-called:{count}")
        future = asyncio.get_running_loop().create_future()
        heartbeat_futures.append(future)

        def complete() -> None:
            order.append(f"heartbeat-awaited:{count}")
            future.set_result(None)

        asyncio.get_running_loop().call_soon(complete)
        return future

    def stream_callback(chunk: str) -> OrderedAwaitable:
        order.append(f"stream-called:{chunk}")
        awaitable = OrderedAwaitable(order, f"stream-awaited:{chunk}")
        stream_awaitables.append(awaitable)
        return awaitable

    builder = ReportBuilderV2(CompleteStreamRouter(chunks))

    report = await builder.build_turn_narrative_async(
        species=[],
        pressures=[_pressure()],
        turn_index=9,
        stream_callback=stream_callback,
        heartbeat_callback=heartbeat_callback,
    )

    assert report == "".join(chunks)
    assert heartbeat_futures and all(future.done() for future in heartbeat_futures)
    assert stream_awaitables and all(item.awaited for item in stream_awaitables)
    assert order[-4:] == [
        "heartbeat-called:5",
        "heartbeat-awaited:5",
        "stream-called:chunk-05-data-",
        "stream-awaited:chunk-05-data-",
    ]


_SECRET_SENTINEL = "DO_NOT_EXPOSE_REPORT_EXCEPTION_SENTINEL"


class RaisingReportRouter:
    async def astream(self, capability: str, payload: dict[str, Any]):
        raise RuntimeError(_SECRET_SENTINEL)
        yield  # pragma: no cover - keeps this an async generator

    async def astream_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ):
        raise RuntimeError(_SECRET_SENTINEL)
        yield  # pragma: no cover - keeps this an async generator


@pytest.mark.parametrize("builder_type", [ReportBuilder, ReportBuilderV2])
@pytest.mark.asyncio
async def test_report_builders_redact_upstream_exception_logs(
    builder_type: type[ReportBuilder] | type[ReportBuilderV2],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    builder = builder_type(RaisingReportRouter())
    kwargs: dict[str, Any] = {
        "species": [],
        "pressures": [_pressure()],
        "stream_callback": lambda _chunk: None,
    }
    if builder_type is ReportBuilderV2:
        kwargs["turn_index"] = 11

    report = await builder.build_turn_narrative_async(**kwargs)

    assert report
    assert _SECRET_SENTINEL not in report
    assert _SECRET_SENTINEL not in caplog.text


class RaisingReportBuilder:
    async def build_turn_narrative_async(self, **_kwargs: Any) -> str:
        raise RuntimeError(_SECRET_SENTINEL)


@pytest.mark.asyncio
async def test_turn_report_service_redacts_upstream_exception_from_log_and_event(
    monkeypatch,
    tmp_path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = SimpleNamespace(
        ui_config_path=tmp_path / "missing-settings.json",
        enable_turn_report_llm=True,
    )
    monkeypatch.setattr("app.services.analytics.turn_report.get_settings", lambda: settings)
    events: list[tuple[str, str, str]] = []
    service = TurnReportService(
        report_builder=RaisingReportBuilder(),
        environment_repository=object(),
        trophic_service=object(),
        emit_event_fn=lambda *event: events.append(event),
    )
    caplog.set_level(logging.DEBUG, logger="app.services.analytics.turn_report")

    report = await service.build_report(
        turn_index=12,
        mortality_results=[],
        pressures=[],
        branching_events=[],
        all_species=[],
    )

    assert report.narrative
    assert _SECRET_SENTINEL not in caplog.text
    assert all(_SECRET_SENTINEL not in message for _, message, _ in events)


@pytest.mark.asyncio
async def test_build_report_stage_redacts_service_exception_log(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class RaisingTurnReportService:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def build_report(self, **_kwargs: Any) -> Any:
            raise RuntimeError(_SECRET_SENTINEL)

    monkeypatch.setattr(
        "app.simulation.stages.TurnReportService",
        RaisingTurnReportService,
    )
    ctx = SimpleNamespace(
        command=SimpleNamespace(auto_reports=True),
        turn_index=13,
        species_batch=[],
        all_species=[],
        combined_results=[],
        pressures=[],
        branching_events=[],
        background_summary=[],
        reemergence_events=[],
        major_events=[],
        map_changes=[],
        migration_events=[],
        plugin_data={},
        modifiers={},
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(report_builder=object(), trophic_service=object())
    caplog.set_level(logging.DEBUG, logger="app.simulation.stages")

    await BuildReportStage().execute(ctx, engine)

    assert _SECRET_SENTINEL not in caplog.text
