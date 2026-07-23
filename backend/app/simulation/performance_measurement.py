"""Opt-in measurement helpers for isolated performance benchmarks."""

from __future__ import annotations

import os
import platform
import time
import tracemalloc
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from sqlalchemy import event
from sqlalchemy.engine import Engine

from .performance_baseline import (
    BenchmarkCase,
    BenchmarkEnvironment,
    StageBenchmark,
)
from .pipeline import PipelineMetrics


@dataclass(frozen=True)
class MeasurementEvidence:
    pipeline_metrics: tuple[PipelineMetrics, ...] = ()
    save_size_bytes: int | None = None
    save_duration_ms: float | None = None
    load_duration_ms: float | None = None
    ai_calls: int = 0
    ai_prompt_tokens: int | None = None
    ai_completion_tokens: int | None = None
    notes: tuple[str, ...] = ()


class StageMetricAccumulator:
    """Aggregate existing PipelineMetrics without changing the pipeline."""

    def __init__(self) -> None:
        self._order: list[str] = []
        self._durations: dict[str, list[float]] = {}

    def add(self, metrics: PipelineMetrics) -> None:
        for stage in metrics.stage_metrics:
            duration = float(stage.duration_ms)
            if duration < 0:
                raise ValueError("stage duration must be non-negative")
            if stage.stage_name not in self._durations:
                self._order.append(stage.stage_name)
                self._durations[stage.stage_name] = []
            self._durations[stage.stage_name].append(duration)

    def to_benchmarks(self) -> tuple[StageBenchmark, ...]:
        benchmarks = []
        for stage_name in self._order:
            durations = self._durations[stage_name]
            total = sum(durations)
            benchmarks.append(
                StageBenchmark(
                    stage_name=stage_name,
                    sample_count=len(durations),
                    total_duration_ms=total,
                    mean_duration_ms=total / len(durations),
                    max_duration_ms=max(durations),
                )
            )
        return tuple(benchmarks)


def _statement_verb(statement: str) -> str:
    remaining = statement.lstrip()
    while remaining:
        if remaining.startswith("--"):
            _, separator, remaining = remaining.partition("\n")
            if not separator:
                return ""
            remaining = remaining.lstrip()
            continue
        if remaining.startswith("/*"):
            end = remaining.find("*/", 2)
            if end < 0:
                return ""
            remaining = remaining[end + 2:].lstrip()
            continue
        break
    return remaining.split(None, 1)[0].upper() if remaining else ""


class SqlWriteCounter:
    """Count successful DML only while attached to one SQLAlchemy engine."""

    _WRITE_VERBS = {"INSERT", "UPDATE", "DELETE", "REPLACE"}

    def __init__(self, database_engine: Engine) -> None:
        self.database_engine = database_engine
        self.write_statements = 0
        self._rows_changed = 0
        self._rows_known = True
        self._pending_rows: dict[int, int | None] = {}
        self.active = False
        self._before_listener = self._before_cursor_execute
        self._after_listener = self._after_cursor_execute
        self._error_listener = self._handle_error
        self._attached_listeners: list[tuple[str, Callable[..., Any]]] = []

    @property
    def rows_changed(self) -> int | None:
        return self._rows_changed if self._rows_known else None

    def _before_cursor_execute(
        self,
        _connection,
        _cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        if _statement_verb(statement) not in self._WRITE_VERBS:
            return
        self.write_statements += 1
        fallback_rows = None
        if executemany:
            try:
                fallback_rows = len(parameters)
            except TypeError:
                pass
        self._pending_rows[id(context)] = fallback_rows

    def _after_cursor_execute(
        self,
        _connection,
        cursor,
        _statement,
        _parameters,
        context,
        _executemany,
    ) -> None:
        context_id = id(context)
        if context_id not in self._pending_rows:
            return
        fallback_rows = self._pending_rows.pop(context_id)
        rowcount = cursor.rowcount
        if rowcount is not None and rowcount >= 0:
            self._rows_changed += int(rowcount)
        elif fallback_rows is not None:
            self._rows_changed += fallback_rows
        else:
            self._rows_known = False

    def _handle_error(self, exception_context) -> None:
        execution_context = exception_context.execution_context
        if execution_context is None:
            return
        context_id = id(execution_context)
        if context_id in self._pending_rows:
            self._pending_rows.pop(context_id)
            self.write_statements -= 1

    def __enter__(self) -> "SqlWriteCounter":
        if self.active:
            raise RuntimeError("SQL write counter is already active")
        self.write_statements = 0
        self._rows_changed = 0
        self._rows_known = True
        self._pending_rows.clear()
        self._attached_listeners.clear()

        listeners = (
            ("before_cursor_execute", self._before_listener),
            ("after_cursor_execute", self._after_listener),
            ("handle_error", self._error_listener),
        )
        try:
            for name, listener in listeners:
                event.listen(self.database_engine, name, listener)
                self._attached_listeners.append((name, listener))
        except Exception:
            for name, listener in reversed(self._attached_listeners):
                try:
                    event.remove(self.database_engine, name, listener)
                except Exception:
                    pass
            self._attached_listeners.clear()
            raise
        self.active = True
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        cleanup_errors: list[Exception] = []
        try:
            for name, listener in reversed(self._attached_listeners):
                try:
                    event.remove(self.database_engine, name, listener)
                except Exception as error:
                    cleanup_errors.append(error)
        finally:
            self._attached_listeners.clear()
            self._pending_rows.clear()
            self.active = False
        if cleanup_errors and _exc_type is None:
            raise cleanup_errors[0]


class MemoryProbe(Protocol):
    def start(self) -> None: ...

    def finish(self) -> int: ...


class PythonMemoryProbe:
    """Measure Python allocations without leaving tracing enabled."""

    def __init__(self) -> None:
        self._active = False
        self._owns_tracer = False

    def start(self) -> None:
        if self._active:
            raise RuntimeError("memory probe is already active")
        self._owns_tracer = not tracemalloc.is_tracing()
        if self._owns_tracer:
            tracemalloc.start()
        else:
            tracemalloc.reset_peak()
        self._active = True

    def finish(self) -> int:
        if not self._active:
            raise RuntimeError("memory probe is not active")
        try:
            _, peak_bytes = tracemalloc.get_traced_memory()
            return peak_bytes
        finally:
            if self._owns_tracer:
                tracemalloc.stop()
            self._active = False
            self._owns_tracer = False


def capture_environment(
    *,
    gpu_probe: Callable[[], str | None] | None = None,
) -> BenchmarkEnvironment:
    notes: list[str] = []
    gpu = None
    if gpu_probe is not None:
        try:
            detected = gpu_probe()
            gpu = detected.strip() if detected and detected.strip() else None
        except Exception:
            gpu = None
    if gpu is None:
        notes.append("GPU identity unavailable")

    return BenchmarkEnvironment(
        platform=platform.platform(),
        python_version=platform.python_version(),
        processor=platform.processor() or None,
        logical_cpu_count=os.cpu_count(),
        gpu=gpu,
        notes=tuple(notes),
    )


async def measure_benchmark_case(
    *,
    case_id: str,
    species_count: int,
    turns: int,
    seed: int,
    workload: Callable[[], Awaitable[MeasurementEvidence]],
    database_engine: Engine | None = None,
    wall_clock: Callable[[], float] = time.perf_counter,
    cpu_clock: Callable[[], float] = time.process_time,
    memory_probe: MemoryProbe | None = None,
) -> BenchmarkCase:
    probe = memory_probe or PythonMemoryProbe()
    write_counter = (
        SqlWriteCounter(database_engine)
        if database_engine is not None
        else None
    )
    database_context = (
        write_counter if write_counter is not None else nullcontext()
    )

    probe.start()
    try:
        wall_started = wall_clock()
        cpu_started = cpu_clock()
        try:
            with database_context:
                evidence = await workload()
        finally:
            cpu_finished = cpu_clock()
            wall_finished = wall_clock()
    finally:
        peak_memory_bytes = probe.finish()

    if not isinstance(evidence, MeasurementEvidence):
        raise TypeError("workload must return MeasurementEvidence")

    accumulator = StageMetricAccumulator()
    for metrics in evidence.pipeline_metrics:
        accumulator.add(metrics)

    notes = list(evidence.notes)
    if write_counter is None:
        notes.append("database metrics unavailable")

    return BenchmarkCase(
        case_id=case_id,
        species_count=species_count,
        turns=turns,
        seed=seed,
        wall_time_ms=(wall_finished - wall_started) * 1000,
        cpu_time_ms=(cpu_finished - cpu_started) * 1000,
        peak_python_memory_bytes=peak_memory_bytes,
        database_write_statements=(
            write_counter.write_statements
            if write_counter is not None
            else None
        ),
        database_rows_changed=(
            write_counter.rows_changed
            if write_counter is not None
            else None
        ),
        save_size_bytes=evidence.save_size_bytes,
        save_duration_ms=evidence.save_duration_ms,
        load_duration_ms=evidence.load_duration_ms,
        ai_calls=evidence.ai_calls,
        ai_prompt_tokens=evidence.ai_prompt_tokens,
        ai_completion_tokens=evidence.ai_completion_tokens,
        stages=accumulator.to_benchmarks(),
        notes=tuple(notes),
    )
