"""Regression coverage for simulation turn transaction boundaries."""

import importlib
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from ...core import database
from ...models.environment import MapState
from ...repositories.environment_repository import EnvironmentRepository
from ...schemas.requests import TurnCommand
from ..engine import SimulationEngine
from ..pipeline import Pipeline, PipelineConfig
from ..stages import BuildReportStage, FinalizeStage, MapEvolutionStage, ParsePressuresStage


@pytest.mark.asyncio
async def test_finalize_stage_uses_engine_environment_repository(monkeypatch):
    """Finalize reads and saves the next turn through the engine repository."""

    class RecordingRepository:
        def __init__(self, state):
            self.state = state
            self.calls = []

        def get_state(self):
            self.calls.append("get_state")
            return self.state

        def save_state(self, state):
            self.calls.append(("save_state", state))
            return state

    environment_repository_module = importlib.import_module(
        "app.repositories.environment_repository"
    )
    injected_state = SimpleNamespace(turn_index=0)
    global_state = SimpleNamespace(turn_index=99)
    injected_repository = RecordingRepository(injected_state)
    global_repository = RecordingRepository(global_state)
    monkeypatch.setattr(
        environment_repository_module,
        "environment_repository",
        global_repository,
    )
    context = SimpleNamespace(
        turn_index=4,
        emit_event=lambda *_args: None,
    )
    engine = SimpleNamespace(environment_repository=injected_repository)

    await FinalizeStage().execute(context, engine)

    assert injected_state.turn_index == 5
    assert injected_repository.calls == [
        "get_state",
        ("save_state", injected_state),
    ]
    assert global_state.turn_index == 99
    assert global_repository.calls == []


def _database_snapshot(engine) -> dict[str, list[dict]]:
    """Return a stable snapshot of every table in the isolated test database."""

    table_names = inspect(engine).get_table_names()
    with engine.connect() as connection:
        return {
            table_name: [dict(row) for row in connection.execute(
                text(f"SELECT * FROM {table_name} ORDER BY rowid")
            ).mappings()]
            for table_name in table_names
        }


@pytest.mark.asyncio
async def test_core_stage_failure_keeps_turn_counter_and_database_unchanged(monkeypatch):
    """A failed core stage must leave the whole turn as if it never started."""

    test_database_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(database, "engine", test_database_engine)
    SQLModel.metadata.create_all(test_database_engine)

    with Session(test_database_engine) as session:
        session.add(MapState(id=1, turn_index=4, sea_level=0.0, global_avg_temperature=15.0))
        session.commit()

    simulation_engine = SimulationEngine.__new__(SimulationEngine)
    simulation_engine.environment_repository = EnvironmentRepository()
    simulation_engine.turn_counter = 4
    simulation_engine._event_callback = None
    simulation_engine.environment = SimpleNamespace(
        parse_pressures=lambda pressures: [],
        apply_pressures=lambda pressures: {"warming": 1.0},
    )
    simulation_engine.escalation_service = SimpleNamespace(
        register=lambda pressures, turn_index: [],
    )
    simulation_engine.map_evolution = SimpleNamespace(
        advance=lambda events, turn_index, modifiers, state: [],
        calculate_climate_changes=lambda modifiers, state: (1.0, 1.0),
    )
    simulation_engine.map_manager = SimpleNamespace(
        reclassify_terrain_by_sea_level=lambda sea_level: (_ for _ in ()).throw(
            RuntimeError("forced map reclassification failure")
        )
    )
    simulation_engine._use_tectonic_system = False
    simulation_engine._pipeline = Pipeline(
        [ParsePressuresStage(), MapEvolutionStage()],
        PipelineConfig(
            continue_on_error=False,
            emit_stage_events=False,
            validate_dependencies=False,
        ),
    )

    initial_turn_counter = simulation_engine.turn_counter
    initial_database_state = _database_snapshot(test_database_engine)

    await simulation_engine.run_turn_with_pipeline(TurnCommand(rounds=1))

    failures = []
    if simulation_engine.turn_counter != initial_turn_counter:
        failures.append(
            f"turn counter changed from {initial_turn_counter} to {simulation_engine.turn_counter}"
        )

    current_database_state = _database_snapshot(test_database_engine)
    if current_database_state != initial_database_state:
        failures.append("database state changed after the failed core stage")

    assert not failures, "\n".join(failures)


@pytest.mark.asyncio
async def test_successful_turn_commits_database_and_advances_counter_once(monkeypatch):
    """A successful core turn must commit its writes and advance both turn indexes once."""

    test_database_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(database, "engine", test_database_engine)
    SQLModel.metadata.create_all(test_database_engine)

    with Session(test_database_engine) as session:
        session.add(MapState(id=1, turn_index=4, sea_level=0.0, global_avg_temperature=15.0))
        session.commit()

    simulation_engine = SimulationEngine.__new__(SimulationEngine)
    simulation_engine.environment_repository = EnvironmentRepository()
    simulation_engine.turn_counter = 4
    simulation_engine._event_callback = None
    simulation_engine.environment = SimpleNamespace(
        parse_pressures=lambda pressures: [],
        apply_pressures=lambda pressures: {"warming": 1.0},
    )
    simulation_engine.escalation_service = SimpleNamespace(
        register=lambda pressures, turn_index: [],
    )
    simulation_engine.map_evolution = SimpleNamespace(
        advance=lambda events, turn_index, modifiers, state: [],
        calculate_climate_changes=lambda modifiers, state: (1.0, 1.0),
    )
    simulation_engine.map_manager = SimpleNamespace(
        reclassify_terrain_by_sea_level=lambda sea_level: None,
    )
    simulation_engine._use_tectonic_system = False
    simulation_engine._pipeline = Pipeline(
        [ParsePressuresStage(), MapEvolutionStage(), FinalizeStage()],
        PipelineConfig(
            continue_on_error=False,
            emit_stage_events=False,
            validate_dependencies=False,
        ),
    )

    initial_database_state = _database_snapshot(test_database_engine)

    await simulation_engine.run_turn_with_pipeline(TurnCommand(rounds=1))

    assert simulation_engine.turn_counter == 5
    assert _database_snapshot(test_database_engine) != initial_database_state

    with Session(test_database_engine) as session:
        persisted_map_state = session.get(MapState, 1)

        assert persisted_map_state is not None
        assert persisted_map_state.turn_index == 5
        assert persisted_map_state.sea_level == 1.0
        assert persisted_map_state.global_avg_temperature == 16.0


@pytest.mark.asyncio
async def test_degradable_failure_commits_core_state_and_advances_counter(monkeypatch):
    """An auxiliary output failure must not roll back a completed core turn."""

    class FailingReportStage(BuildReportStage):
        async def execute(self, ctx, engine):
            raise RuntimeError("forced report failure")

    test_database_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(database, "engine", test_database_engine)
    SQLModel.metadata.create_all(test_database_engine)

    with Session(test_database_engine) as session:
        session.add(MapState(id=1, turn_index=4, sea_level=0.0, global_avg_temperature=15.0))
        session.commit()

    simulation_engine = SimulationEngine.__new__(SimulationEngine)
    simulation_engine.environment_repository = EnvironmentRepository()
    simulation_engine.turn_counter = 4
    simulation_engine._event_callback = None
    simulation_engine.environment = SimpleNamespace(
        parse_pressures=lambda pressures: [],
        apply_pressures=lambda pressures: {"warming": 1.0},
    )
    simulation_engine.escalation_service = SimpleNamespace(
        register=lambda pressures, turn_index: [],
    )
    simulation_engine.map_evolution = SimpleNamespace(
        advance=lambda events, turn_index, modifiers, state: [],
        calculate_climate_changes=lambda modifiers, state: (1.0, 1.0),
    )
    simulation_engine.map_manager = SimpleNamespace(
        reclassify_terrain_by_sea_level=lambda sea_level: None,
    )
    simulation_engine._use_tectonic_system = False
    simulation_engine._pipeline = Pipeline(
        [
            ParsePressuresStage(),
            MapEvolutionStage(),
            FailingReportStage(),
            FinalizeStage(),
        ],
        PipelineConfig(
            continue_on_error=False,
            emit_stage_events=False,
            validate_dependencies=False,
        ),
    )

    await simulation_engine.run_turn_with_pipeline(TurnCommand(rounds=1))

    assert simulation_engine.turn_counter == 5
    assert simulation_engine._last_pipeline_metrics.degraded_stages == ["构建报告"]

    with Session(test_database_engine) as session:
        persisted_map_state = session.get(MapState, 1)

        assert persisted_map_state is not None
        assert persisted_map_state.turn_index == 5
        assert persisted_map_state.sea_level == 1.0
        assert persisted_map_state.global_avg_temperature == 16.0
