"""Repository-isolation coverage for the background-management stage."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from .. import stages as stages_module
from ..stages import BackgroundManagementStage


class _RecordingBackgroundManager:
    def __init__(self) -> None:
        self.candidates = [object()]
        self.events = [object()]
        self.reemergence_calls: list[tuple[list[object], dict[str, float]]] = []

    def summarize(self, _results: list[object]) -> list[object]:
        return []

    def detect_mass_extinction(self, _results: list[object]) -> bool:
        return True

    def promote_candidates(self, _results: list[object]) -> list[object]:
        return self.candidates

    def evaluate_reemergence(
        self,
        candidates: list[object],
        modifiers: dict[str, float],
    ) -> list[object]:
        self.reemergence_calls.append((candidates, modifiers))
        return self.events


class _UnexpectedStageOwnedReemergenceService:
    def __init__(self, _repository: object) -> None:
        raise AssertionError(
            "BackgroundManagementStage must not construct ReemergenceService"
        )


def test_background_management_stage_uses_injected_background_manager(
    monkeypatch,
) -> None:
    manager = _RecordingBackgroundManager()
    modifiers = {"temperature": 0.25}
    context = SimpleNamespace(
        background_results=[],
        combined_results=[],
        modifiers=modifiers,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(background_manager=manager)
    monkeypatch.setattr(
        stages_module,
        "ReemergenceService",
        _UnexpectedStageOwnedReemergenceService,
        raising=False,
    )

    asyncio.run(BackgroundManagementStage().execute(context, engine))

    assert manager.reemergence_calls == [(manager.candidates, modifiers)]
    assert context.reemergence_events is manager.events
