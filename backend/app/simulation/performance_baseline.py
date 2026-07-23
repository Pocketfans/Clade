"""Versioned performance evidence and environment-aware comparisons."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
REQUIRED_CASE_IDS = (
    "scale-10",
    "scale-100",
    "scale-500",
    "seeded-100-turn",
)


def _require_fields(
    payload: dict[str, Any],
    fields: tuple[str, ...],
    context: str,
) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(
            f"{context} missing required fields: {', '.join(missing)}"
        )


def _validate_non_negative(
    name: str,
    value: int | float | None,
    *,
    optional: bool = False,
) -> None:
    if value is None:
        if optional:
            return
        raise ValueError(f"{name} must not be null")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(float(value)) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _validate_integer(
    name: str,
    value: int | None,
    *,
    positive: bool = False,
    optional: bool = False,
) -> None:
    if value is None:
        if optional:
            return
        raise ValueError(f"{name} must not be null")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be {qualifier}")


@dataclass(frozen=True)
class BenchmarkEnvironment:
    platform: str
    python_version: str
    processor: str | None
    logical_cpu_count: int | None
    gpu: str | None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.platform:
            raise ValueError("platform must not be empty")
        if not self.python_version:
            raise ValueError("python_version must not be empty")
        _validate_integer(
            "logical_cpu_count",
            self.logical_cpu_count,
            positive=True,
            optional=True,
        )

    def identity(self) -> tuple:
        return (
            self.platform,
            self.python_version,
            self.processor,
            self.logical_cpu_count,
            self.gpu,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkEnvironment":
        fields = (
            "platform",
            "python_version",
            "processor",
            "logical_cpu_count",
            "gpu",
            "notes",
        )
        _require_fields(payload, fields, "environment")
        return cls(
            platform=payload["platform"],
            python_version=payload["python_version"],
            processor=payload["processor"],
            logical_cpu_count=payload["logical_cpu_count"],
            gpu=payload["gpu"],
            notes=tuple(payload["notes"]),
        )


@dataclass(frozen=True)
class StageBenchmark:
    stage_name: str
    sample_count: int
    total_duration_ms: float
    mean_duration_ms: float
    max_duration_ms: float

    def __post_init__(self) -> None:
        if not self.stage_name:
            raise ValueError("stage_name must not be empty")
        _validate_integer("sample_count", self.sample_count, positive=True)
        for name in (
            "total_duration_ms",
            "mean_duration_ms",
            "max_duration_ms",
        ):
            _validate_non_negative(name, getattr(self, name))
        if self.max_duration_ms < self.mean_duration_ms:
            raise ValueError(
                "max_duration_ms must be at least mean_duration_ms"
            )
        if self.total_duration_ms < self.max_duration_ms:
            raise ValueError(
                "total_duration_ms must be at least max_duration_ms"
            )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StageBenchmark":
        fields = (
            "stage_name",
            "sample_count",
            "total_duration_ms",
            "mean_duration_ms",
            "max_duration_ms",
        )
        _require_fields(payload, fields, "stage")
        return cls(**{field: payload[field] for field in fields})


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    species_count: int
    turns: int
    seed: int
    wall_time_ms: float
    cpu_time_ms: float
    peak_python_memory_bytes: int | None
    database_write_statements: int | None
    database_rows_changed: int | None
    save_size_bytes: int | None
    save_duration_ms: float | None
    load_duration_ms: float | None
    ai_calls: int
    ai_prompt_tokens: int | None
    ai_completion_tokens: int | None
    stages: tuple[StageBenchmark, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.case_id:
            raise ValueError("case_id must not be empty")
        _validate_integer(
            "species_count",
            self.species_count,
            positive=True,
        )
        _validate_integer("turns", self.turns, positive=True)
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")

        for name in ("wall_time_ms", "cpu_time_ms"):
            _validate_non_negative(name, getattr(self, name))
        _validate_integer("ai_calls", self.ai_calls)
        for name in (
            "peak_python_memory_bytes",
            "database_write_statements",
            "database_rows_changed",
            "save_size_bytes",
            "ai_prompt_tokens",
            "ai_completion_tokens",
        ):
            _validate_integer(
                name,
                getattr(self, name),
                optional=True,
            )
        for name in (
            "save_duration_ms",
            "load_duration_ms",
        ):
            _validate_non_negative(
                name,
                getattr(self, name),
                optional=True,
            )

        stage_names = [stage.stage_name for stage in self.stages]
        if len(stage_names) != len(set(stage_names)):
            raise ValueError("duplicate stage_name in benchmark case")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["stages"] = [asdict(stage) for stage in self.stages]
        result["notes"] = list(self.notes)
        return result

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkCase":
        fields = (
            "case_id",
            "species_count",
            "turns",
            "seed",
            "wall_time_ms",
            "cpu_time_ms",
            "peak_python_memory_bytes",
            "database_write_statements",
            "database_rows_changed",
            "save_size_bytes",
            "save_duration_ms",
            "load_duration_ms",
            "ai_calls",
            "ai_prompt_tokens",
            "ai_completion_tokens",
            "stages",
            "notes",
        )
        _require_fields(payload, fields, "case")
        values = {field: payload[field] for field in fields}
        values["stages"] = tuple(
            StageBenchmark.from_dict(stage) for stage in payload["stages"]
        )
        values["notes"] = tuple(payload["notes"])
        return cls(**values)


@dataclass(frozen=True)
class BenchmarkReport:
    schema_version: int
    generated_at_utc: str
    commit_sha: str
    environment: BenchmarkEnvironment
    cases: tuple[BenchmarkCase, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise ValueError(
                f"schema_version must be {SCHEMA_VERSION}"
            )
        if not self.commit_sha:
            raise ValueError("commit_sha must not be empty")
        try:
            generated_at = datetime.fromisoformat(self.generated_at_utc)
        except ValueError as exc:
            raise ValueError("generated_at_utc must be ISO-8601") from exc
        if (
            generated_at.tzinfo is None
            or generated_at.utcoffset() != timezone.utc.utcoffset(None)
        ):
            raise ValueError("generated_at_utc must include UTC timezone")

        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("duplicate case_id in benchmark report")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at_utc": self.generated_at_utc,
            "commit_sha": self.commit_sha,
            "environment": asdict(self.environment),
            "cases": [case.to_dict() for case in self.cases],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )

    def missing_required_case_ids(self) -> tuple[str, ...]:
        present = {case.case_id for case in self.cases}
        return tuple(
            case_id
            for case_id in REQUIRED_CASE_IDS
            if case_id not in present
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchmarkReport":
        fields = (
            "schema_version",
            "generated_at_utc",
            "commit_sha",
            "environment",
            "cases",
        )
        _require_fields(payload, fields, "report")
        return cls(
            schema_version=payload["schema_version"],
            generated_at_utc=payload["generated_at_utc"],
            commit_sha=payload["commit_sha"],
            environment=BenchmarkEnvironment.from_dict(
                payload["environment"]
            ),
            cases=tuple(
                BenchmarkCase.from_dict(case) for case in payload["cases"]
            ),
        )

    @classmethod
    def from_json(cls, source: str) -> "BenchmarkReport":
        try:
            payload = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValueError("benchmark report must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("benchmark report root must be an object")
        return cls.from_dict(payload)


def write_report(report: BenchmarkReport, path: Path) -> None:
    path.write_text(report.to_json() + "\n", encoding="utf-8")


def read_report(path: Path) -> BenchmarkReport:
    return BenchmarkReport.from_json(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RegressionThresholds:
    relative_increase: float = 0.20
    timing_noise_floor_ms: float = 5.0
    memory_noise_floor_bytes: int = 1024 * 1024
    count_noise_floor: int = 1

    def __post_init__(self) -> None:
        for name in (
            "relative_increase",
            "timing_noise_floor_ms",
            "memory_noise_floor_bytes",
            "count_noise_floor",
        ):
            _validate_non_negative(name, getattr(self, name))


@dataclass(frozen=True)
class PerformanceRegression:
    case_id: str
    metric: str
    baseline: float
    current: float
    relative_increase: float


@dataclass(frozen=True)
class BenchmarkComparison:
    comparable: bool
    regressions: tuple[PerformanceRegression, ...]
    skipped: tuple[str, ...]


def _compare_metric(
    regressions: list[PerformanceRegression],
    skipped: list[str],
    *,
    case_id: str,
    metric: str,
    baseline: int | float | None,
    current: int | float | None,
    noise_floor: int | float,
    thresholds: RegressionThresholds,
) -> None:
    if baseline is None or current is None:
        skipped.append(f"{case_id}.{metric}: unavailable")
        return
    if baseline <= 0:
        skipped.append(f"{case_id}.{metric}: zero baseline")
        return

    delta = float(current) - float(baseline)
    relative_increase = delta / float(baseline)
    if (
        relative_increase > thresholds.relative_increase
        and delta > noise_floor
    ):
        regressions.append(
            PerformanceRegression(
                case_id=case_id,
                metric=metric,
                baseline=float(baseline),
                current=float(current),
                relative_increase=relative_increase,
            )
        )


def compare_reports(
    baseline: BenchmarkReport,
    current: BenchmarkReport,
    thresholds: RegressionThresholds | None = None,
) -> BenchmarkComparison:
    thresholds = thresholds or RegressionThresholds()
    if baseline.environment.identity() != current.environment.identity():
        return BenchmarkComparison(
            comparable=False,
            regressions=(),
            skipped=("environment identity differs",),
        )

    regressions: list[PerformanceRegression] = []
    skipped: list[str] = []
    current_cases = {case.case_id: case for case in current.cases}

    for baseline_case in baseline.cases:
        current_case = current_cases.get(baseline_case.case_id)
        if current_case is None:
            skipped.append(f"{baseline_case.case_id}: missing current case")
            continue
        if (
            baseline_case.species_count != current_case.species_count
            or baseline_case.turns != current_case.turns
            or baseline_case.seed != current_case.seed
        ):
            skipped.append(f"{baseline_case.case_id}: dimensions differ")
            continue

        timing_metrics = (
            "wall_time_ms",
            "cpu_time_ms",
            "save_duration_ms",
            "load_duration_ms",
        )
        for metric in timing_metrics:
            _compare_metric(
                regressions,
                skipped,
                case_id=baseline_case.case_id,
                metric=metric,
                baseline=getattr(baseline_case, metric),
                current=getattr(current_case, metric),
                noise_floor=thresholds.timing_noise_floor_ms,
                thresholds=thresholds,
            )

        _compare_metric(
            regressions,
            skipped,
            case_id=baseline_case.case_id,
            metric="peak_python_memory_bytes",
            baseline=baseline_case.peak_python_memory_bytes,
            current=current_case.peak_python_memory_bytes,
            noise_floor=thresholds.memory_noise_floor_bytes,
            thresholds=thresholds,
        )
        _compare_metric(
            regressions,
            skipped,
            case_id=baseline_case.case_id,
            metric="database_write_statements",
            baseline=baseline_case.database_write_statements,
            current=current_case.database_write_statements,
            noise_floor=thresholds.count_noise_floor,
            thresholds=thresholds,
        )

        current_stages = {
            stage.stage_name: stage for stage in current_case.stages
        }
        for baseline_stage in baseline_case.stages:
            current_stage = current_stages.get(baseline_stage.stage_name)
            if current_stage is None:
                skipped.append(
                    f"{baseline_case.case_id}.stage."
                    f"{baseline_stage.stage_name}: unavailable"
                )
                continue
            _compare_metric(
                regressions,
                skipped,
                case_id=baseline_case.case_id,
                metric=(
                    f"stage.{baseline_stage.stage_name}."
                    "mean_duration_ms"
                ),
                baseline=baseline_stage.mean_duration_ms,
                current=current_stage.mean_duration_ms,
                noise_floor=thresholds.timing_noise_floor_ms,
                thresholds=thresholds,
            )

    regressions.sort(key=lambda regression: (
        regression.case_id,
        regression.metric,
    ))
    return BenchmarkComparison(
        comparable=True,
        regressions=tuple(regressions),
        skipped=tuple(skipped),
    )
