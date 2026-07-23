"""Repository-isolation coverage for the map snapshot stage."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

from ..stages import SaveMapSnapshotStage


class _RecordingSpeciesRepository:
    def __init__(self, species: list[object]) -> None:
        self.species = species
        self.list_calls = 0

    def list_species(self) -> list[object]:
        self.list_calls += 1
        return self.species


class _RecordingMapManager:
    def __init__(self) -> None:
        self.snapshot_calls: list[tuple[list[object], dict[str, object]]] = []

    def snapshot_habitats(self, species: list[object], **kwargs: object) -> None:
        self.snapshot_calls.append((species, kwargs))


class _RecordingTileMortality:
    def __init__(self, tile_survivors: dict[str, dict[str, int]]) -> None:
        self.tile_survivors = tile_survivors
        self.get_survivors_calls = 0

    def get_all_species_tile_survivors(self) -> dict[str, dict[str, int]]:
        self.get_survivors_calls += 1
        return self.tile_survivors


def test_save_map_snapshot_stage_uses_injected_species_repository(
    monkeypatch,
) -> None:
    repository_species = [SimpleNamespace(lineage_code="SP-A")]
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )
    global_repository = _RecordingSpeciesRepository(repository_species)
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_repository,
    )

    injected_repository = _RecordingSpeciesRepository(repository_species)
    tile_survivors = {"SP-A": {"tile-1": 12}}
    tile_mortality = _RecordingTileMortality(tile_survivors)
    map_manager = _RecordingMapManager()
    context = SimpleNamespace(
        all_tiles=[object()],
        turn_index=7,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(
        _use_tile_based_mortality=True,
        tile_mortality=tile_mortality,
        map_manager=map_manager,
        species_repository=injected_repository,
    )

    asyncio.run(SaveMapSnapshotStage().execute(context, engine))

    assert injected_repository.list_calls == 1
    assert global_repository.list_calls == 0
    assert tile_mortality.get_survivors_calls == 1
    assert map_manager.snapshot_calls == [
        (
            repository_species,
            {
                "turn_index": 7,
                "tile_survivors": tile_survivors,
                "reproduction_gains": {},
            },
        )
    ]
