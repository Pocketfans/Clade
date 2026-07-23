"""Deterministic core scenarios used only by the performance benchmark."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, func, select

from ..core import database
from ..models.environment import MapState
from ..models.species import Species
from ..repositories.environment_repository import EnvironmentRepository
from ..repositories.species_repository import SpeciesRepository
from ..schemas.requests import TurnCommand
from ..services.geo.map_evolution import MapEvolutionService
from ..services.system.save_manager import SaveManager
from .engine import SimulationEngine
from .performance_baseline import BenchmarkCase
from .performance_measurement import (
    MeasurementEvidence,
    measure_benchmark_case,
)
from .pipeline import Pipeline, PipelineConfig, PipelineMetrics
from .stages import (
    FetchSpeciesStage,
    FinalizeStage,
    MapEvolutionStage,
    ParsePressuresStage,
)


@dataclass(frozen=True)
class BenchmarkScenario:
    case_id: str
    species_count: int
    turns: int
    seed: int

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must not be empty")
        if self.species_count <= 0:
            raise ValueError("species_count must be positive")
        if self.turns <= 0:
            raise ValueError("turns must be positive")


BENCHMARK_SCENARIOS = (
    BenchmarkScenario("scale-10", species_count=10, turns=1, seed=42),
    BenchmarkScenario("scale-100", species_count=100, turns=1, seed=42),
    BenchmarkScenario("scale-500", species_count=500, turns=1, seed=42),
    BenchmarkScenario(
        "seeded-100-turn",
        species_count=10,
        turns=100,
        seed=42,
    ),
)


def create_deterministic_species(
    *,
    species_count: int,
    seed: int,
) -> tuple[Species, ...]:
    if species_count <= 0:
        raise ValueError("species_count must be positive")

    rng = random.Random(seed)
    generated = []
    created_at = datetime(2000, 1, 1)
    habitat_types = ("terrestrial", "marine", "freshwater", "aerial")
    diet_types = ("autotroph", "herbivore", "omnivore", "carnivore")

    for index in range(species_count):
        population = rng.randint(10_000, 1_000_000)
        body_weight = round(rng.uniform(0.1, 5_000.0), 6)
        generated.append(
            Species(
                lineage_code=f"BENCH-{index:04d}",
                latin_name=f"Benchmarkus determinis {index}",
                common_name=f"Benchmark Species {index}",
                description="Deterministic offline benchmark species.",
                morphology_stats={
                    "population": population,
                    "body_weight_g": body_weight,
                    "adult_size_cm": round(rng.uniform(0.01, 500.0), 6),
                },
                abstract_traits={
                    "adaptability": round(rng.uniform(0.1, 1.0), 6),
                    "mobility": round(rng.uniform(0.1, 1.0), 6),
                },
                hidden_traits={
                    "resilience": round(rng.uniform(0.1, 1.0), 6),
                },
                ecological_vector=[
                    round(rng.uniform(-1.0, 1.0), 6) for _ in range(8)
                ],
                status="alive",
                created_turn=0,
                updated_at=created_at + timedelta(seconds=index),
                trophic_level=round(1.0 + (index % 4) * 0.75, 2),
                habitat_type=habitat_types[index % len(habitat_types)],
                diet_type=diet_types[index % len(diet_types)],
            )
        )

    return tuple(generated)


def _create_seeded_map_evolution(seed: int) -> MapEvolutionService:
    caller_state = random.getstate()
    try:
        random.seed(seed)
        return MapEvolutionService(width=8, height=4)
    finally:
        random.setstate(caller_state)


def initialize_scenario_database(
    database_engine: Engine,
    scenario: BenchmarkScenario,
) -> MapEvolutionService:
    """Initialize a fresh engine and refuse to overwrite existing core state."""

    SQLModel.metadata.create_all(database_engine)
    with Session(database_engine) as session:
        nonempty_tables = [
            table.name
            for table in SQLModel.metadata.sorted_tables
            if session.exec(
                select(func.count()).select_from(table)
            ).one()
        ]
        if nonempty_tables:
            raise ValueError(
                "benchmark database must be empty; found data in: "
                + ", ".join(nonempty_tables)
            )

    map_evolution = _create_seeded_map_evolution(scenario.seed)
    species = create_deterministic_species(
        species_count=scenario.species_count,
        seed=scenario.seed,
    )
    with Session(database_engine) as session:
        session.add_all(species)
        session.add(
            MapState(
                id=1,
                turn_index=0,
                sea_level=0.0,
                global_avg_temperature=15.0,
                stage_name=map_evolution.current_stage_name,
                stage_progress=map_evolution.stage_progress,
                stage_duration=map_evolution.stage_duration,
            )
        )
        session.commit()
    return map_evolution


def _build_core_engine(
    map_evolution: MapEvolutionService,
) -> SimulationEngine:
    simulation_engine = SimulationEngine.__new__(SimulationEngine)
    simulation_engine.species_repository = SpeciesRepository()
    simulation_engine.environment_repository = EnvironmentRepository()
    simulation_engine.turn_counter = 0
    simulation_engine._event_callback = None
    simulation_engine.environment = SimpleNamespace(
        parse_pressures=lambda pressures: pressures,
        apply_pressures=lambda pressures: {"temperature": 1.0},
    )
    simulation_engine.escalation_service = SimpleNamespace(
        register=lambda pressures, turn_index: [],
    )
    simulation_engine.map_evolution = map_evolution
    simulation_engine.map_manager = SimpleNamespace(
        reclassify_terrain_by_sea_level=lambda sea_level: None,
    )
    simulation_engine._use_tectonic_system = False
    simulation_engine._use_embedding_integration = False
    simulation_engine._pipeline = Pipeline(
        [
            ParsePressuresStage(),
            MapEvolutionStage(),
            FetchSpeciesStage(),
            FinalizeStage(),
        ],
        PipelineConfig(
            continue_on_error=False,
            emit_stage_events=False,
            validate_dependencies=False,
        ),
    )
    simulation_engine._pipeline_mode = "performance-benchmark"
    simulation_engine._last_pipeline_metrics = None
    return simulation_engine


async def run_deterministic_scenario(
    scenario: BenchmarkScenario,
    database_engine: Engine,
    *,
    save_root: Path,
) -> BenchmarkCase:
    """Measure one scenario in the already-configured isolated app database."""

    if os.environ.get("CLADE_BENCHMARK_ISOLATED") != "1":
        raise RuntimeError(
            "scenario must run in an explicit isolated benchmark process"
        )
    if database.engine is not database_engine:
        raise ValueError(
            "benchmark engine must be configured as the current app engine"
        )

    python_random_state = random.getstate()
    numpy_random_state = np.random.get_state()
    try:
        map_evolution = initialize_scenario_database(
            database_engine,
            scenario,
        )
        random.seed(scenario.seed)
        np.random.seed(scenario.seed)
        simulation_engine = _build_core_engine(map_evolution)

        async def workload() -> MeasurementEvidence:
            metrics: list[PipelineMetrics] = []
            command = TurnCommand(rounds=1)
            for _ in range(scenario.turns):
                await simulation_engine.run_turn_with_pipeline(command)
                current_metrics = simulation_engine.get_pipeline_metrics()
                if current_metrics is None:
                    raise RuntimeError("core pipeline did not expose metrics")
                metrics.append(current_metrics)

            if simulation_engine.turn_counter != scenario.turns:
                raise RuntimeError(
                    "core pipeline did not complete every requested turn"
                )

            save_manager = SaveManager(save_root)
            save_started = time.perf_counter()
            save_directory = save_manager.save_game(
                f"benchmark-{scenario.case_id}",
                turn_index=scenario.turns,
            )
            save_duration_ms = (
                time.perf_counter() - save_started
            ) * 1000
            save_size_bytes = sum(
                path.stat().st_size
                for path in save_directory.rglob("*")
                if path.is_file()
            )

            load_started = time.perf_counter()
            loaded = save_manager.load_game(
                f"benchmark-{scenario.case_id}"
            )
            load_duration_ms = (
                time.perf_counter() - load_started
            ) * 1000
            if loaded.get("turn_index") != scenario.turns:
                raise RuntimeError("save/load restored the wrong turn")
            if loaded.get("species_count") != scenario.species_count:
                raise RuntimeError(
                    "save/load restored the wrong species count"
                )

            return MeasurementEvidence(
                pipeline_metrics=tuple(metrics),
                save_size_bytes=save_size_bytes,
                save_duration_ms=save_duration_ms,
                load_duration_ms=load_duration_ms,
                ai_calls=0,
                notes=(
                    "deterministic core pipeline",
                    "AI and embedding integration disabled",
                    "save/load round trip measured",
                ),
            )

        return await measure_benchmark_case(
            case_id=scenario.case_id,
            species_count=scenario.species_count,
            turns=scenario.turns,
            seed=scenario.seed,
            workload=workload,
            database_engine=database_engine,
        )
    finally:
        random.setstate(python_random_state)
        np.random.set_state(numpy_random_state)
