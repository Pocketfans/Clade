"""Environment-repository isolation for report construction."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from ..stages import BuildReportStage


@pytest.mark.asyncio
async def test_build_report_uses_engine_environment_repository(monkeypatch) -> None:
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    stages_module = importlib.import_module("app.simulation.stages")
    injected_repository = object()
    global_repository = object()
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_repository,
    )
    received_repositories: list[object] = []
    report = object()

    class _RecordingTurnReportService:
        def __init__(self, *, environment_repository, **_kwargs) -> None:
            received_repositories.append(environment_repository)

        async def build_report(self, **_kwargs):
            return report

    monkeypatch.setattr(
        stages_module,
        "TurnReportService",
        _RecordingTurnReportService,
    )
    context = SimpleNamespace(
        command=SimpleNamespace(auto_reports=True),
        turn_index=7,
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
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        environment_repository=injected_repository,
        report_builder=object(),
        trophic_service=object(),
    )

    await BuildReportStage().execute(context, engine)

    assert received_repositories == [injected_repository]
    assert context.report is report


@pytest.mark.asyncio
async def test_skipped_report_does_not_require_environment_repository() -> None:
    context = SimpleNamespace(
        command=SimpleNamespace(auto_reports=False),
        turn_index=8,
        species_batch=[],
        all_species=[],
        combined_results=[],
        branching_events=[],
        major_events=[],
        plugin_data={},
    )

    await BuildReportStage().execute(context, SimpleNamespace())

    assert context.report.turn_index == 8
