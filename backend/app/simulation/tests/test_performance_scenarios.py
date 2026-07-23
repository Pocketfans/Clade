"""Deterministic, isolated performance scenario coverage."""

from __future__ import annotations

import random

import numpy as np
import pytest
from sqlmodel import SQLModel, Session, create_engine, func, select

from ...core import database
from ...models.environment import EnvironmentEvent, MapState
from ...models.species import Species
from ...services.system.species_cache import get_species_cache
from ..performance_scenarios import (
    BENCHMARK_SCENARIOS,
    create_deterministic_species,
    initialize_scenario_database,
    run_deterministic_scenario,
)


def _numpy_states_equal(first: tuple, second: tuple) -> bool:
    return (
        first[0] == second[0]
        and np.array_equal(first[1], second[1])
        and first[2:] == second[2:]
    )


@pytest.fixture(autouse=True)
def _clear_isolated_process_cache():
    yield
    get_species_cache().clear()


def test_benchmark_scenario_matrix_is_stable() -> None:
    dimensions = [
        (scenario.case_id, scenario.species_count, scenario.turns, scenario.seed)
        for scenario in BENCHMARK_SCENARIOS
    ]

    assert dimensions == [
        ("scale-10", 10, 1, 42),
        ("scale-100", 100, 1, 42),
        ("scale-500", 500, 1, 42),
        ("seeded-100-turn", 10, 100, 42),
    ]


def test_species_generation_is_repeatable_and_seed_sensitive() -> None:
    first = create_deterministic_species(species_count=10, seed=42)
    repeated = create_deterministic_species(species_count=10, seed=42)
    changed = create_deterministic_species(species_count=10, seed=43)

    assert [species.model_dump() for species in repeated] == [
        species.model_dump() for species in first
    ]
    assert [species.model_dump() for species in changed] != [
        species.model_dump() for species in first
    ]
    assert len({species.lineage_code for species in first}) == 10
    assert all(species.status == "alive" for species in first)
    assert all(
        species.morphology_stats["population"] > 0 for species in first
    )


def test_database_initialization_refuses_existing_core_state(tmp_path) -> None:
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'scenario.db'}",
        connect_args={"check_same_thread": False},
    )
    scenario = BENCHMARK_SCENARIOS[0]
    try:
        initialize_scenario_database(database_engine, scenario)

        with Session(database_engine) as session:
            species_count = session.exec(
                select(func.count(Species.id))
            ).one()
            map_state = session.get(MapState, 1)
        assert species_count == 10
        assert map_state is not None
        assert map_state.turn_index == 0

        with pytest.raises(ValueError, match="empty"):
            initialize_scenario_database(database_engine, scenario)
    finally:
        database_engine.dispose()


def test_database_initialization_refuses_other_existing_app_data(
    tmp_path,
) -> None:
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'nonempty.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(database_engine)
    with Session(database_engine) as session:
        session.add(
            EnvironmentEvent(
                turn_index=0,
                description="existing data",
                pressures={},
            )
        )
        session.commit()

    try:
        with pytest.raises(ValueError, match="environment_events"):
            initialize_scenario_database(
                database_engine,
                BENCHMARK_SCENARIOS[0],
            )
    finally:
        database_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    BENCHMARK_SCENARIOS[:3],
    ids=lambda scenario: scenario.case_id,
)
async def test_scale_scenario_runs_measured_core_pipeline_in_isolation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    scenario,
) -> None:
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'scale.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", database_engine)
    monkeypatch.setenv("CLADE_BENCHMARK_ISOLATED", "1")
    python_state = random.getstate()
    numpy_state = np.random.get_state()

    try:
        measured = await run_deterministic_scenario(
            scenario,
            database_engine,
            save_root=tmp_path / "saves",
        )
        with Session(database_engine) as session:
            species_count = session.exec(
                select(func.count(Species.id))
            ).one()
            map_state = session.get(MapState, 1)
    finally:
        database_engine.dispose()

    assert measured.case_id == scenario.case_id
    assert measured.species_count == scenario.species_count
    assert measured.turns == 1
    assert measured.seed == scenario.seed
    assert measured.ai_calls == 0
    assert measured.database_write_statements is not None
    assert measured.database_write_statements > 0
    assert measured.database_rows_changed is not None
    assert measured.save_size_bytes is not None
    assert measured.save_size_bytes > 0
    assert measured.save_duration_ms is not None
    assert measured.save_duration_ms >= 0
    assert measured.load_duration_ms is not None
    assert measured.load_duration_ms >= 0
    assert measured.stages
    assert all(stage.sample_count == 1 for stage in measured.stages)
    assert measured.notes == (
        "deterministic core pipeline",
        "AI and embedding integration disabled",
        "save/load round trip measured",
    )
    assert species_count == scenario.species_count
    assert map_state is not None
    assert map_state.turn_index == 1
    assert random.getstate() == python_state
    assert _numpy_states_equal(np.random.get_state(), numpy_state)


@pytest.mark.asyncio
async def test_seeded_scenario_completes_and_aggregates_100_turns(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'long-run.db'}",
        connect_args={"check_same_thread": False},
    )
    monkeypatch.setattr(database, "engine", database_engine)
    monkeypatch.setenv("CLADE_BENCHMARK_ISOLATED", "1")

    try:
        measured = await run_deterministic_scenario(
            BENCHMARK_SCENARIOS[-1],
            database_engine,
            save_root=tmp_path / "saves",
        )
        with Session(database_engine) as session:
            map_state = session.get(MapState, 1)
    finally:
        database_engine.dispose()

    assert measured.case_id == "seeded-100-turn"
    assert measured.turns == 100
    assert measured.ai_calls == 0
    assert measured.save_size_bytes is not None
    assert measured.save_size_bytes > 0
    assert measured.save_duration_ms is not None
    assert measured.load_duration_ms is not None
    assert measured.stages
    assert all(stage.sample_count == 100 for stage in measured.stages)
    assert map_state is not None
    assert map_state.turn_index == 100


@pytest.mark.asyncio
async def test_scenario_runner_requires_explicit_process_isolation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'guard.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(database_engine)
    monkeypatch.setattr(database, "engine", database_engine)
    monkeypatch.delenv("CLADE_BENCHMARK_ISOLATED", raising=False)

    try:
        with pytest.raises(RuntimeError, match="isolated benchmark process"):
            await run_deterministic_scenario(
                BENCHMARK_SCENARIOS[0],
                database_engine,
                save_root=tmp_path / "saves",
            )
        with Session(database_engine) as session:
            assert session.exec(select(func.count(Species.id))).one() == 0
    finally:
        database_engine.dispose()
