from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError

from .. import performance_measurement
from ..performance_measurement import (
    MeasurementEvidence,
    SqlWriteCounter,
    StageMetricAccumulator,
    capture_environment,
    measure_benchmark_case,
)
from ..pipeline import PipelineMetrics, StageMetrics


def _metrics(*stages: tuple[str, float]) -> PipelineMetrics:
    return PipelineMetrics(
        total_duration_ms=sum(duration for _, duration in stages),
        stage_metrics=[
            StageMetrics(stage_name=name, duration_ms=duration)
            for name, duration in stages
        ],
    )


def test_stage_accumulator_preserves_first_seen_order_and_aggregates() -> None:
    accumulator = StageMetricAccumulator()

    accumulator.add(_metrics(("fetch", 10.0), ("update", 20.0)))
    accumulator.add(_metrics(("update", 30.0), ("fetch", 14.0)))

    stages = accumulator.to_benchmarks()

    assert [stage.stage_name for stage in stages] == ["fetch", "update"]
    assert stages[0].sample_count == 2
    assert stages[0].total_duration_ms == 24.0
    assert stages[0].mean_duration_ms == 12.0
    assert stages[0].max_duration_ms == 14.0
    assert stages[1].sample_count == 2
    assert stages[1].total_duration_ms == 50.0
    assert stages[1].mean_duration_ms == 25.0
    assert stages[1].max_duration_ms == 30.0


def test_stage_accumulator_rejects_negative_pipeline_duration() -> None:
    accumulator = StageMetricAccumulator()

    with pytest.raises(ValueError, match="duration"):
        accumulator.add(_metrics(("invalid", -1.0)))


@pytest.mark.asyncio
async def test_measure_case_uses_injected_clocks_memory_and_evidence() -> None:
    calls: list[str] = []

    class FakeMemoryProbe:
        def start(self) -> None:
            calls.append("memory_start")

        def finish(self) -> int:
            calls.append("memory_finish")
            return 12_345

    async def workload() -> MeasurementEvidence:
        calls.append("workload")
        return MeasurementEvidence(
            pipeline_metrics=(
                _metrics(("fetch", 10.0), ("update", 20.0)),
                _metrics(("fetch", 14.0), ("update", 30.0)),
            ),
            save_size_bytes=4_096,
            save_duration_ms=7.0,
            load_duration_ms=8.0,
            ai_calls=0,
            ai_prompt_tokens=None,
            ai_completion_tokens=None,
            notes=("AI disabled",),
        )

    wall_values = iter((10.0, 10.25))
    cpu_values = iter((2.0, 2.05))
    measured = await measure_benchmark_case(
        case_id="scale-10",
        species_count=10,
        turns=2,
        seed=42,
        workload=workload,
        wall_clock=lambda: next(wall_values),
        cpu_clock=lambda: next(cpu_values),
        memory_probe=FakeMemoryProbe(),
    )

    assert measured.wall_time_ms == 250.0
    assert measured.cpu_time_ms == pytest.approx(50.0)
    assert measured.peak_python_memory_bytes == 12_345
    assert measured.database_write_statements is None
    assert measured.database_rows_changed is None
    assert measured.save_size_bytes == 4_096
    assert [stage.stage_name for stage in measured.stages] == [
        "fetch",
        "update",
    ]
    assert measured.notes == (
        "AI disabled",
        "database metrics unavailable",
    )
    assert calls == ["memory_start", "workload", "memory_finish"]


@pytest.mark.asyncio
async def test_measure_case_finishes_memory_probe_when_clock_fails() -> None:
    calls: list[str] = []

    class FakeMemoryProbe:
        def start(self) -> None:
            calls.append("memory_start")

        def finish(self) -> int:
            calls.append("memory_finish")
            return 0

    async def workload() -> MeasurementEvidence:
        raise AssertionError("workload must not run")

    def failing_wall_clock() -> float:
        raise RuntimeError("clock unavailable")

    with pytest.raises(RuntimeError, match="clock unavailable"):
        await measure_benchmark_case(
            case_id="scale-10",
            species_count=10,
            turns=1,
            seed=42,
            workload=workload,
            wall_clock=failing_wall_clock,
            memory_probe=FakeMemoryProbe(),
        )

    assert calls == ["memory_start", "memory_finish"]


def test_sql_write_counter_counts_dml_rows_and_detaches() -> None:
    database_engine = create_engine("sqlite://")
    with database_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        )

    counter = SqlWriteCounter(database_engine)
    with counter:
        with database_engine.begin() as connection:
            connection.execute(
                text("INSERT INTO sample (value) VALUES (:value)"),
                [{"value": "a"}, {"value": "b"}],
            )
            connection.execute(text("SELECT * FROM sample"))
            connection.execute(
                text("UPDATE sample SET value = 'c' WHERE id = 1")
            )

    assert counter.write_statements == 2
    assert counter.rows_changed == 3
    assert counter.active is False

    with database_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO sample (value) VALUES ('after')")
        )

    assert counter.write_statements == 2
    assert counter.rows_changed == 3
    database_engine.dispose()


def test_sql_write_counter_detaches_and_stops_counting_after_error() -> None:
    database_engine = create_engine("sqlite://")
    with database_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        )
    counter = SqlWriteCounter(database_engine)

    with pytest.raises(RuntimeError, match="workload failed"):
        with counter:
            with database_engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO sample (value) VALUES ('before')")
                )
            raise RuntimeError("workload failed")

    count_after_error = counter.write_statements
    assert counter.active is False
    with database_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO sample (value) VALUES ('after')")
        )
    assert counter.write_statements == count_after_error
    database_engine.dispose()


def test_sql_write_counter_does_not_count_failed_dml() -> None:
    database_engine = create_engine("sqlite://")
    with database_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        )
        connection.execute(
            text("INSERT INTO sample (id, value) VALUES (1, 'existing')")
        )
    counter = SqlWriteCounter(database_engine)

    with counter:
        with pytest.raises(IntegrityError):
            with database_engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO sample (id, value) "
                        "VALUES (1, 'duplicate')"
                    )
                )

    assert counter.write_statements == 0
    assert counter.rows_changed == 0
    assert counter.active is False
    database_engine.dispose()


def test_sql_write_counter_cleans_up_partial_listener_attachment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_engine = create_engine("sqlite://")
    counter = SqlWriteCounter(database_engine)
    real_listen = event.listen
    real_remove = event.remove
    attached: list[str] = []
    removed: list[str] = []

    def fake_listen(target, name, listener) -> None:
        if name == "handle_error":
            raise RuntimeError("listener unavailable")
        real_listen(target, name, listener)
        attached.append(name)

    def tracking_remove(target, name, listener) -> None:
        real_remove(target, name, listener)
        removed.append(name)

    monkeypatch.setattr(performance_measurement.event, "listen", fake_listen)
    monkeypatch.setattr(
        performance_measurement.event,
        "remove",
        tracking_remove,
    )

    with pytest.raises(RuntimeError, match="listener unavailable"):
        counter.__enter__()

    assert attached == ["before_cursor_execute", "after_cursor_execute"]
    assert removed == ["after_cursor_execute", "before_cursor_execute"]
    assert counter.active is False
    database_engine.dispose()


def test_capture_environment_uses_nullable_best_effort_gpu_probe() -> None:
    detected = capture_environment(gpu_probe=lambda: "Test GPU")

    assert detected.platform
    assert detected.python_version
    assert detected.logical_cpu_count is None or (
        detected.logical_cpu_count > 0
    )
    assert detected.gpu == "Test GPU"
    assert detected.notes == ()

    unavailable = capture_environment(
        gpu_probe=lambda: (_ for _ in ()).throw(
            RuntimeError("driver unavailable")
        )
    )
    assert unavailable.gpu is None
    assert unavailable.notes == ("GPU identity unavailable",)
