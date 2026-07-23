"""Safe command-line workflow for generating and comparing performance data."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from .performance_baseline import (
    BenchmarkCase,
    BenchmarkEnvironment,
    BenchmarkReport,
    SCHEMA_VERSION,
    compare_reports,
    read_report,
    write_report,
)
from .performance_measurement import capture_environment
from .performance_scenarios import (
    BENCHMARK_SCENARIOS,
    BenchmarkScenario,
    run_deterministic_scenario,
)


CaseRunner = Callable[[BenchmarkScenario, Path], BenchmarkCase]


def build_worker_environment(
    source: Mapping[str, str],
    database_path: Path,
) -> dict[str, str]:
    """Create a child environment without forwarding application secrets."""

    sensitive_markers = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
    worker = {
        key: value
        for key, value in source.items()
        if not any(marker in key.upper() for marker in sensitive_markers)
    }
    worker.update(
        {
            "DATABASE_URL": (
                f"sqlite:///{database_path.resolve().as_posix()}"
            ),
            "CLADE_BENCHMARK_ISOLATED": "1",
            "ENABLE_TURN_REPORT_LLM": "0",
            "ALLOW_FAKE_EMBEDDINGS": "0",
            "LOG_TO_FILE": "0",
            "LOG_TO_CONSOLE": "0",
            "PYTHONHASHSEED": "42",
        }
    )
    return worker


def probe_gpu_description(
    *,
    run: Callable[..., object] = subprocess.run,
) -> str | None:
    """Return NVIDIA name and total video memory when nvidia-smi exists."""

    try:
        completed = run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(completed, "returncode", 1) != 0:
        return None

    descriptions = []
    for raw_line in str(getattr(completed, "stdout", "")).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        name, separator, memory = line.rpartition(",")
        if not separator or not name.strip() or not memory.strip():
            continue
        descriptions.append(
            f"{name.strip()} ({memory.strip()} MiB)"
        )
    return "; ".join(descriptions) or None


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve_commit_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_repository_root(),
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError("unable to resolve the current Git commit")
    return completed.stdout.strip()


def _run_case_subprocess(
    scenario: BenchmarkScenario,
    workspace: Path,
) -> BenchmarkCase:
    workspace.mkdir(parents=True, exist_ok=False)
    database_path = workspace / "scenario.db"
    save_root = workspace / "saves"
    case_path = workspace / "case.json"
    environment = build_worker_environment(os.environ, database_path)
    command = [
        sys.executable,
        "-m",
        "app.simulation.performance_benchmark",
        "_worker",
        "--case-id",
        scenario.case_id,
        "--database",
        str(database_path),
        "--save-root",
        str(save_root),
        "--output",
        str(case_path),
    ]
    completed = subprocess.run(
        command,
        cwd=_repository_root() / "backend",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"benchmark worker failed for {scenario.case_id}: "
            f"{details[-2000:]}"
        )
    if not case_path.is_file():
        raise RuntimeError(
            f"benchmark worker produced no result for {scenario.case_id}"
        )
    try:
        payload = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"benchmark worker produced invalid JSON for {scenario.case_id}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("benchmark case result must be an object")
    return BenchmarkCase.from_dict(payload)


def _validate_case(
    scenario: BenchmarkScenario,
    case: BenchmarkCase,
) -> None:
    actual = (
        case.case_id,
        case.species_count,
        case.turns,
        case.seed,
    )
    expected = (
        scenario.case_id,
        scenario.species_count,
        scenario.turns,
        scenario.seed,
    )
    if actual != expected:
        raise ValueError(
            f"benchmark case dimensions differ: {actual!r} != {expected!r}"
        )
    required_optional_metrics = (
        case.peak_python_memory_bytes,
        case.database_write_statements,
        case.database_rows_changed,
        case.save_size_bytes,
        case.save_duration_ms,
        case.load_duration_ms,
    )
    if any(metric is None for metric in required_optional_metrics):
        raise ValueError(
            f"benchmark case {case.case_id} lacks a required measurement"
        )
    if case.ai_calls != 0:
        raise ValueError(
            f"benchmark case {case.case_id} unexpectedly called AI"
        )


def generate_benchmark_report(
    *,
    output_path: Path,
    commit_sha: str | None = None,
    overwrite: bool = False,
    case_runner: CaseRunner = _run_case_subprocess,
    environment: BenchmarkEnvironment | None = None,
    generated_at: datetime | None = None,
) -> BenchmarkReport:
    output_path = output_path.resolve()
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"benchmark output already exists: {output_path}"
        )

    cases = []
    with TemporaryDirectory(prefix="clade-benchmark-") as temp_directory:
        temporary_root = Path(temp_directory)
        for scenario in BENCHMARK_SCENARIOS:
            case = case_runner(
                scenario,
                temporary_root / scenario.case_id,
            )
            _validate_case(scenario, case)
            cases.append(case)

    timestamp = generated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    timestamp = timestamp.astimezone(timezone.utc)
    report = BenchmarkReport(
        schema_version=SCHEMA_VERSION,
        generated_at_utc=timestamp.isoformat(),
        commit_sha=commit_sha or _resolve_commit_sha(),
        environment=environment
        or capture_environment(gpu_probe=probe_gpu_description),
        cases=tuple(cases),
    )
    missing = report.missing_required_case_ids()
    if missing:
        raise ValueError(
            "benchmark report is incomplete: " + ", ".join(missing)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(report, output_path)
    return report


def compare_report_files(
    baseline_path: Path,
    current_path: Path,
) -> tuple[int, str]:
    baseline = read_report(baseline_path)
    current = read_report(current_path)
    comparison = compare_reports(baseline, current)
    if not comparison.comparable:
        return (
            2,
            "Reports are not comparable: "
            + "; ".join(comparison.skipped),
        )
    if comparison.regressions:
        lines = ["Performance regressions detected:"]
        for regression in comparison.regressions:
            lines.append(
                f"- {regression.case_id}.{regression.metric}: "
                f"{regression.baseline:.3f} -> "
                f"{regression.current:.3f} "
                f"(+{regression.relative_increase:.1%})"
            )
        return 1, "\n".join(lines)
    return 0, "Comparable reports: no regressions detected."


def _scenario_by_id(case_id: str) -> BenchmarkScenario:
    for scenario in BENCHMARK_SCENARIOS:
        if scenario.case_id == case_id:
            return scenario
    raise ValueError(f"unknown benchmark case: {case_id}")


def _run_worker(
    *,
    case_id: str,
    database_path: Path,
    save_root: Path,
    output_path: Path,
) -> None:
    from ..core import database

    database_path = database_path.resolve()
    workspace = database_path.parent
    save_root = save_root.resolve()
    output_path = output_path.resolve()
    if (
        not save_root.is_relative_to(workspace)
        or not output_path.is_relative_to(workspace)
    ):
        raise ValueError("worker paths must stay inside its workspace")
    configured_database = Path(str(database.engine.url.database)).resolve()
    if configured_database != database_path:
        raise ValueError("worker database does not match DATABASE_URL")

    case = asyncio.run(
        run_deterministic_scenario(
            _scenario_by_id(case_id),
            database.engine,
            save_root=save_root,
        )
    )
    output_path.write_text(
        json.dumps(
            case.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or compare Clade performance baselines."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--commit-sha")
    generate.add_argument("--overwrite", action="store_true")

    compare = commands.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--current", type=Path, required=True)

    worker = commands.add_parser("_worker")
    worker.add_argument("--case-id", required=True)
    worker.add_argument("--database", type=Path, required=True)
    worker.add_argument("--save-root", type=Path, required=True)
    worker.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "generate":
            report = generate_benchmark_report(
                output_path=arguments.output,
                commit_sha=arguments.commit_sha,
                overwrite=arguments.overwrite,
            )
            print(
                f"Wrote {len(report.cases)} benchmark cases to "
                f"{arguments.output.resolve()}"
            )
            return 0
        if arguments.command == "compare":
            exit_code, summary = compare_report_files(
                arguments.baseline,
                arguments.current,
            )
            print(summary)
            return exit_code
        _run_worker(
            case_id=arguments.case_id,
            database_path=arguments.database,
            save_root=arguments.save_root,
            output_path=arguments.output,
        )
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Performance benchmark failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
