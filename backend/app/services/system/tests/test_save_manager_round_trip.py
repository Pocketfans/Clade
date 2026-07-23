"""Regression coverage for save/load core-state consistency."""

import importlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from ....core import database
from ....models.environment import MapState
from ....models.genus import Genus
from ....models.species import Species
from ....repositories.environment_repository import environment_repository
from ....repositories.species_repository import species_repository
from ..species_cache import get_species_cache
from ..save_manager import SaveManager


def test_history_repository_module_does_not_publish_singleton() -> None:
    module = importlib.import_module("app.repositories.history_repository")

    assert not hasattr(module, "history_repository")


def _species(
    lineage_code: str,
    *,
    population: int,
    carrying_capacity: int,
) -> Species:
    return Species(
        lineage_code=lineage_code,
        latin_name=f"{lineage_code.title()} testus",
        common_name=lineage_code.lower(),
        description=f"Round-trip test species {lineage_code}",
        morphology_stats={
            "population": population,
            "carrying_capacity": carrying_capacity,
            "body_length_cm": 12.5,
            "body_weight_g": 240.0,
        },
        abstract_traits={"mobility": 0.75},
        hidden_traits={"resilience": 0.6},
        ecological_vector=[0.1, 0.2, 0.3],
        created_turn=3,
        trophic_level=2.0,
        habitat_type="coastal",
        updated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )


def _core_state(turn_index: int) -> dict[str, Any]:
    map_state = environment_repository.get_state()
    assert map_state is not None

    species_state = []
    for species in sorted(
        species_repository.list_species(),
        key=lambda item: item.lineage_code,
    ):
        species_state.append(
            {
                "lineage_code": species.lineage_code,
                "latin_name": species.latin_name,
                "common_name": species.common_name,
                "description": species.description,
                "status": species.status,
                "created_turn": species.created_turn,
                "trophic_level": species.trophic_level,
                "habitat_type": species.habitat_type,
                "morphology_stats": species.morphology_stats,
                "abstract_traits": species.abstract_traits,
                "hidden_traits": species.hidden_traits,
                "ecological_vector": species.ecological_vector,
            }
        )

    return {
        "turn_index": turn_index,
        "map_state": {
            "turn_index": map_state.turn_index,
            "stage_name": map_state.stage_name,
            "stage_progress": map_state.stage_progress,
            "stage_duration": map_state.stage_duration,
            "sea_level": map_state.sea_level,
            "global_avg_temperature": map_state.global_avg_temperature,
            "extra_data": map_state.extra_data,
        },
        "species": species_state,
    }


def test_save_manager_reads_history_from_injected_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    history_repository = MagicMock()
    history_repository.list_turns.return_value = []
    genus_repository = MagicMock()
    genus_repository.list_all.return_value = []
    monkeypatch.setattr(species_repository, "list_species", lambda: [])
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: [])
    monkeypatch.setattr(environment_repository, "get_state", lambda: None)
    monkeypatch.setattr(environment_repository, "list_latest_habitats", lambda: [])

    manager = SaveManager(
        tmp_path / "saves",
        history_repository=history_repository,
        genus_repository=genus_repository,
    )

    save_dir = manager.save_game("injected-history", turn_index=3)

    assert (save_dir / "game_state.json.gz").is_file()
    history_repository.list_turns.assert_called_once_with(limit=1000)


def test_save_manager_uses_injected_genus_repository_for_save_and_load(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stored_genus = Genus(
        code="GEN-TEST",
        name_latin="Testus",
        name_common="test genus",
        genetic_distances={"SP-1": 0.2},
        gene_library={"trait": ["value"]},
        created_turn=2,
        updated_turn=3,
    )
    injected_genus_repository = MagicMock()
    injected_genus_repository.list_all.return_value = [stored_genus]
    history_repository = MagicMock()
    history_repository.list_turns.return_value = []

    monkeypatch.setattr(species_repository, "list_species", lambda: [])
    monkeypatch.setattr(species_repository, "clear_state", lambda: None)
    monkeypatch.setattr(environment_repository, "list_tiles", lambda: [])
    monkeypatch.setattr(environment_repository, "get_state", lambda: None)
    monkeypatch.setattr(
        environment_repository,
        "list_latest_habitats",
        lambda: [],
    )
    monkeypatch.setattr(environment_repository, "clear_state", lambda: None)

    manager = SaveManager(
        tmp_path / "saves",
        history_repository=history_repository,
        genus_repository=injected_genus_repository,
    )

    manager.save_game("injected-genus", turn_index=3)
    manager.load_game("injected-genus")

    injected_genus_repository.list_all.assert_called_once_with()
    injected_genus_repository.clear_state.assert_called_once_with()
    restored_genus = injected_genus_repository.upsert.call_args.args[0]
    assert restored_genus.model_dump() == stored_genus.model_dump()


def test_save_then_load_restores_identical_core_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A real save/load round trip must restore the saved core world state."""

    test_database_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(database, "engine", test_database_engine)
    SQLModel.metadata.create_all(test_database_engine)

    try:
        with Session(test_database_engine) as session:
            session.add(
                MapState(
                    id=1,
                    turn_index=12,
                    stage_name="海洋扩张期",
                    stage_progress=4,
                    stage_duration=9,
                    sea_level=42.5,
                    global_avg_temperature=18.75,
                    extra_data={"tectonic_activity": "stable"},
                )
            )
            session.add_all(
                [
                    _species("ALPHA", population=1_250, carrying_capacity=2_000),
                    _species("BETA", population=640, carrying_capacity=900),
                ]
            )
            session.commit()

        manager = SaveManager(tmp_path / "saves")
        expected = _core_state(turn_index=12)
        save_dir = manager.save_game("round-trip", turn_index=12)
        assert (save_dir / "game_state.json.gz").is_file()

        environment_repository.clear_state()
        species_repository.clear_state()
        with Session(test_database_engine) as session:
            session.add(
                MapState(
                    id=1,
                    turn_index=99,
                    stage_name="被污染的状态",
                    sea_level=-999.0,
                    global_avg_temperature=99.0,
                )
            )
            session.add(
                _species("INTRUDER", population=1, carrying_capacity=1)
            )
            session.commit()

        loaded = manager.load_game("round-trip")
        actual = _core_state(turn_index=loaded["turn_index"])

        assert actual == expected
    finally:
        get_species_cache().clear()
        test_database_engine.dispose()
