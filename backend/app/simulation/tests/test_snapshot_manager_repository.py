"""Repository isolation tests for world snapshot creation."""

import importlib
from types import SimpleNamespace

from ..snapshot import SnapshotManager, SnapshotMetadata, WorldSnapshot


class _RecordingEnvironmentRepository:
    def __init__(self, *, tiles=None, habitats=None):
        self.tiles = list(tiles or [])
        self.habitats = list(habitats or [])
        self.list_tiles_calls = 0
        self.latest_habitats_calls = 0
        self.saved_states = []

    def list_tiles(self):
        self.list_tiles_calls += 1
        return self.tiles

    def latest_habitats(self):
        self.latest_habitats_calls += 1
        return self.habitats

    def save_state(self, state):
        self.saved_states.append(state)


class _RecordingSpeciesRepository:
    def __init__(self, species=None):
        self.species = list(species or [])
        self.list_species_calls = 0

    def list_species(self):
        self.list_species_calls += 1
        return self.species


def test_create_snapshot_uses_engine_repositories(tmp_path, monkeypatch):
    """World data must come from the repositories attached to this engine."""
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    species_repository_module = importlib.import_module(
        "app.repositories.species_repository"
    )

    tile = SimpleNamespace(id=11, x=2, y=3)
    habitat = SimpleNamespace(
        id=12,
        species_id=7,
        tile_id=11,
        population=25,
    )
    species = SimpleNamespace(
        id=7,
        lineage_code="SP007",
        common_name="Test species",
        status="alive",
    )
    injected_environment_repository = _RecordingEnvironmentRepository(
        tiles=[tile],
        habitats=[habitat],
    )
    global_environment_repository = _RecordingEnvironmentRepository()
    injected_species_repository = _RecordingSpeciesRepository([species])
    global_species_repository = _RecordingSpeciesRepository()
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_environment_repository,
    )
    monkeypatch.setattr(
        species_repository_module,
        "species_repository",
        global_species_repository,
    )

    engine = SimpleNamespace(
        environment_repository=injected_environment_repository,
        species_repository=injected_species_repository,
        _random_seed=123,
        _current_mode="standard",
    )
    context = SimpleNamespace(turn_index=5, current_map_state=None)

    snapshot = SnapshotManager(tmp_path).create_snapshot(
        context,
        engine,
        custom_id="repository-isolation",
    )

    assert injected_environment_repository.list_tiles_calls == 1
    assert injected_environment_repository.latest_habitats_calls == 1
    assert injected_species_repository.list_species_calls == 1
    assert global_environment_repository.list_tiles_calls == 0
    assert global_environment_repository.latest_habitats_calls == 0
    assert global_species_repository.list_species_calls == 0
    assert snapshot.tiles[0]["id"] == 11
    assert snapshot.habitats[0]["population"] == 25
    assert snapshot.species[0]["lineage_code"] == "SP007"


def test_restore_snapshot_uses_engine_environment_repository(tmp_path, monkeypatch):
    """Restored map state must be written through this engine's repository."""
    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    injected_environment_repository = _RecordingEnvironmentRepository()
    global_environment_repository = _RecordingEnvironmentRepository()
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_environment_repository,
    )
    map_state = {"sea_level": 3.5, "turn_index": 8}
    snapshot = WorldSnapshot(
        metadata=SnapshotMetadata(
            snapshot_id="restore-repository-isolation",
            created_at="2026-07-22T00:00:00",
            turn_index=8,
            random_seed=321,
            mode="standard",
        ),
        map_state=map_state,
    )
    engine = SimpleNamespace(
        environment_repository=injected_environment_repository,
        _random_seed=0,
        _current_mode="standard",
    )

    context = SnapshotManager(tmp_path).restore_snapshot(snapshot, engine)

    assert injected_environment_repository.saved_states == [map_state]
    assert global_environment_repository.saved_states == []
    assert context.turn_index == 8
