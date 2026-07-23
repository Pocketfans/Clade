"""Safe command workflow coverage for performance baselines."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from ..performance_baseline import (
    BenchmarkCase,
    BenchmarkEnvironment,
    BenchmarkReport,
    SCHEMA_VERSION,
    read_report,
    write_report,
)
from ..performance_benchmark import (
    build_worker_environment,
    compare_report_files,
    generate_benchmark_report,
    probe_gpu_description,
)


def _case(case_id: str, species_count: int, turns: int) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        species_count=species_count,
        turns=turns,
        seed=42,
        wall_time_ms=10.0,
        cpu_time_ms=9.0,
        peak_python_memory_bytes=1_024,
        database_write_statements=2,
        database_rows_changed=2,
        save_size_bytes=512,
        save_duration_ms=1.0,
        load_duration_ms=2.0,
        ai_calls=0,
        ai_prompt_tokens=None,
        ai_completion_tokens=None,
        notes=("test evidence",),
    )


def _environment(name: str = "Test GPU") -> BenchmarkEnvironment:
    return BenchmarkEnvironment(
        platform="test-platform",
        python_version="3.12.10",
        processor="test-processor",
        logical_cpu_count=8,
        gpu=name,
    )


def _report(
    *,
    environment: BenchmarkEnvironment | None = None,
    wall_time_ms: float = 10.0,
) -> BenchmarkReport:
    case = _case("scale-10", 10, 1)
    case = BenchmarkCase(
        **{
            **case.to_dict(),
            "wall_time_ms": wall_time_ms,
            "stages": (),
            "notes": case.notes,
        }
    )
    return BenchmarkReport(
        schema_version=SCHEMA_VERSION,
        generated_at_utc="2026-07-23T00:00:00+00:00",
        commit_sha="abc123",
        environment=environment or _environment(),
        cases=(case,),
    )


def test_worker_environment_uses_temp_database_and_drops_secrets(
    tmp_path: Path,
) -> None:
    source = {
        "PATH": "test-path",
        "DATABASE_URL": "sqlite:///real-world.db",
        "AI_API_KEY": "must-not-propagate",
        "CLADE_ADMIN_TOKEN": "must-not-propagate",
        "OTHER_SECRET": "must-not-propagate",
    }
    database_path = tmp_path / "isolated.db"

    worker = build_worker_environment(source, database_path)

    assert worker["PATH"] == "test-path"
    assert worker["DATABASE_URL"] == (
        f"sqlite:///{database_path.resolve().as_posix()}"
    )
    assert worker["CLADE_BENCHMARK_ISOLATED"] == "1"
    assert worker["ENABLE_TURN_REPORT_LLM"] == "0"
    assert worker["LOG_TO_FILE"] == "0"
    assert "AI_API_KEY" not in worker
    assert "CLADE_ADMIN_TOKEN" not in worker
    assert "OTHER_SECRET" not in worker
    assert source["DATABASE_URL"] == "sqlite:///real-world.db"


def test_gpu_probe_records_name_and_video_memory() -> None:
    def successful_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="Test GPU, 8192\nSecond GPU, 4096\n",
        )

    assert probe_gpu_description(run=successful_run) == (
        "Test GPU (8192 MiB); Second GPU (4096 MiB)"
    )

    def failed_run(*_args, **_kwargs):
        raise FileNotFoundError("nvidia-smi unavailable")

    assert probe_gpu_description(run=failed_run) is None


def test_generate_report_runs_all_cases_and_writes_only_requested_path(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, Path]] = []
    dimensions = {
        "scale-10": (10, 1),
        "scale-100": (100, 1),
        "scale-500": (500, 1),
        "seeded-100-turn": (10, 100),
    }

    def fake_case_runner(scenario, workspace: Path) -> BenchmarkCase:
        calls.append((scenario.case_id, workspace))
        species_count, turns = dimensions[scenario.case_id]
        return _case(scenario.case_id, species_count, turns)

    output_path = tmp_path / "requested" / "report.json"
    report = generate_benchmark_report(
        output_path=output_path,
        commit_sha="tooling-sha",
        case_runner=fake_case_runner,
        environment=_environment(),
        generated_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
    )

    assert [case_id for case_id, _ in calls] == list(dimensions)
    assert len({workspace for _, workspace in calls}) == 4
    assert report.commit_sha == "tooling-sha"
    assert report.missing_required_case_ids() == ()
    assert read_report(output_path) == report
    assert all(not workspace.exists() for _, workspace in calls)
    assert list(tmp_path.rglob("*.db")) == []


def test_generate_report_refuses_to_overwrite_without_explicit_flag(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "baseline.json"
    output_path.write_text("existing evidence", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        generate_benchmark_report(
            output_path=output_path,
            commit_sha="tooling-sha",
            case_runner=lambda scenario, workspace: _case(
                scenario.case_id,
                scenario.species_count,
                scenario.turns,
            ),
            environment=_environment(),
        )

    assert output_path.read_text(encoding="utf-8") == "existing evidence"


def test_compare_report_files_returns_actionable_exit_codes(
    tmp_path: Path,
) -> None:
    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    write_report(_report(), baseline_path)
    write_report(_report(), current_path)

    code, summary = compare_report_files(baseline_path, current_path)
    assert code == 0
    assert "no regressions" in summary

    write_report(_report(wall_time_ms=30.0), current_path)
    code, summary = compare_report_files(baseline_path, current_path)
    assert code == 1
    assert "scale-10.wall_time_ms" in summary

    write_report(
        _report(environment=_environment("Different GPU")),
        current_path,
    )
    code, summary = compare_report_files(baseline_path, current_path)
    assert code == 2
    assert "not comparable" in summary
