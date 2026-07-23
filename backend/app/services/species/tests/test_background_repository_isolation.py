"""Repository isolation coverage for background species management."""

from __future__ import annotations

from .. import background
from ..background import BackgroundConfig, BackgroundSpeciesManager


class _RecordingReemergenceService:
    def __init__(self) -> None:
        self.calls: list[tuple[list[object], dict[str, float] | None]] = []
        self.events = [object()]

    def evaluate_reemergence(
        self,
        candidates: list[object],
        modifiers: dict[str, float] | None = None,
    ) -> list[object]:
        self.calls.append((candidates, modifiers))
        return self.events


def test_background_module_does_not_expose_species_repository_singleton() -> None:
    assert not hasattr(background, "species_repository")


def test_background_manager_delegates_reemergence_to_injected_service() -> None:
    service = _RecordingReemergenceService()
    manager = BackgroundSpeciesManager(
        BackgroundConfig(
            population_threshold=100,
            mass_extinction_threshold=0.5,
            promotion_quota=2,
        ),
        reemergence_service=service,
    )
    candidates = [object()]
    modifiers = {"temperature": 0.25}

    events = manager.evaluate_reemergence(candidates, modifiers)

    assert events is service.events
    assert service.calls == [(candidates, modifiers)]
