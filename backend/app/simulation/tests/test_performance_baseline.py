from dataclasses import replace

import pytest

from ..performance_baseline import (
    REQUIRED_CASE_IDS,
    BenchmarkCase,
    BenchmarkEnvironment,
    BenchmarkReport,
    RegressionThresholds,
    StageBenchmark,
    compare_reports,
    read_report,
    write_report,
)


def _environment(*, processor: str = "test-cpu") -> BenchmarkEnvironment:
    return BenchmarkEnvironment(
        platform="test-platform",
        python_version="3.12.10",
        processor=processor,
        logical_cpu_count=8,
        gpu=None,
        notes=("GPU metrics unavailable",),
    )


def _stage(
    name: str = "core",
    *,
    mean_duration_ms: float = 10.0,
) -> StageBenchmark:
    return StageBenchmark(
        stage_name=name,
        sample_count=2,
        total_duration_ms=mean_duration_ms * 2,
        mean_duration_ms=mean_duration_ms,
        max_duration_ms=mean_duration_ms + 1,
    )


def _case(
    case_id: str = "scale-10",
    *,
    species_count: int = 10,
    turns: int = 1,
    wall_time_ms: float = 100.0,
    cpu_time_ms: float = 80.0,
    peak_python_memory_bytes: int | None = 10_000_000,
    database_write_statements: int | None = 10,
    save_duration_ms: float | None = 20.0,
    load_duration_ms: float | None = 20.0,
    stages: tuple[StageBenchmark, ...] | None = None,
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        species_count=species_count,
        turns=turns,
        seed=42,
        wall_time_ms=wall_time_ms,
        cpu_time_ms=cpu_time_ms,
        peak_python_memory_bytes=peak_python_memory_bytes,
        database_write_statements=database_write_statements,
        database_rows_changed=None,
        save_size_bytes=None,
        save_duration_ms=save_duration_ms,
        load_duration_ms=load_duration_ms,
        ai_calls=0,
        ai_prompt_tokens=None,
        ai_completion_tokens=None,
        stages=stages if stages is not None else (_stage(),),
        notes=("public AI disabled",),
    )


def _report(
    *cases: BenchmarkCase,
    environment: BenchmarkEnvironment | None = None,
) -> BenchmarkReport:
    return BenchmarkReport(
        schema_version=1,
        generated_at_utc="2026-07-23T09:00:00+00:00",
        commit_sha="abc123",
        environment=environment or _environment(),
        cases=cases or (_case(),),
    )


def test_report_json_round_trip_preserves_unicode_nulls_and_order() -> None:
    report = _report(
        _case("scale-10"),
        _case(
            "seeded-100-turn",
            species_count=10,
            turns=100,
            stages=(_stage("地图演化"), _stage("finalize")),
        ),
    )

    restored = BenchmarkReport.from_json(report.to_json())

    assert restored == report
    assert restored.cases[1].stages[0].stage_name == "地图演化"
    assert restored.cases[0].save_size_bytes is None
    assert '"GPU metrics unavailable"' in report.to_json()


def test_report_file_round_trip_uses_utf8(tmp_path) -> None:
    report = _report(
        _case(stages=(_stage("物种形成"),)),
    )
    report_path = tmp_path / "baseline.json"

    write_report(report, report_path)

    assert read_report(report_path) == report
    assert "物种形成" in report_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda: replace(_case(), wall_time_ms=-1),
            "wall_time_ms",
        ),
        (
            lambda: replace(_case(), turns=0),
            "turns",
        ),
        (
            lambda: replace(_case(), species_count=True),
            "species_count",
        ),
        (
            lambda: replace(
                _case(),
                database_write_statements=1.5,
            ),
            "database_write_statements",
        ),
        (
            lambda: replace(_stage(), sample_count=0),
            "sample_count",
        ),
        (
            lambda: replace(_stage(), total_duration_ms=5),
            "total_duration_ms",
        ),
        (
            lambda: _report(_case("same"), _case("same")),
            "duplicate case_id",
        ),
        (
            lambda: replace(_report(), schema_version=True),
            "schema_version",
        ),
        (
            lambda: replace(
                _report().environment,
                logical_cpu_count=True,
            ),
            "logical_cpu_count",
        ),
        (
            lambda: replace(
                _case(),
                stages=(_stage("same"), _stage("same")),
            ),
            "duplicate stage_name",
        ),
    ],
)
def test_contract_rejects_invalid_or_ambiguous_values(
    factory,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_from_dict_rejects_missing_required_fields() -> None:
    payload = _report().to_dict()
    del payload["commit_sha"]

    with pytest.raises(ValueError, match="commit_sha"):
        BenchmarkReport.from_dict(payload)


def test_complete_case_check_lists_only_missing_required_ids() -> None:
    report = _report(
        _case("scale-10"),
        _case("scale-500", species_count=500),
    )

    assert report.missing_required_case_ids() == (
        "scale-100",
        "seeded-100-turn",
    )
    assert set(REQUIRED_CASE_IDS) == {
        "scale-10",
        "scale-100",
        "scale-500",
        "seeded-100-turn",
    }


def test_comparison_is_inconclusive_across_different_environments() -> None:
    baseline = _report(_case(), environment=_environment(processor="cpu-a"))
    current = _report(
        replace(_case(), wall_time_ms=1_000),
        environment=_environment(processor="cpu-b"),
    )

    comparison = compare_reports(baseline, current)

    assert comparison.comparable is False
    assert comparison.regressions == ()
    assert comparison.skipped == ("environment identity differs",)


def test_comparison_reports_only_changes_above_ratio_and_noise_floors() -> None:
    baseline = _report(_case())
    current = _report(
        _case(
            wall_time_ms=121.0,
            cpu_time_ms=96.1,
            peak_python_memory_bytes=12_100_001,
            database_write_statements=13,
            save_duration_ms=24.9,
            load_duration_ms=25.0,
            stages=(_stage(mean_duration_ms=26.0),),
        )
    )

    comparison = compare_reports(
        baseline,
        current,
        RegressionThresholds(relative_increase=0.20),
    )

    assert comparison.comparable is True
    assert [regression.metric for regression in comparison.regressions] == [
        "cpu_time_ms",
        "database_write_statements",
        "peak_python_memory_bytes",
        "stage.core.mean_duration_ms",
        "wall_time_ms",
    ]
    assert "save_duration_ms" not in {
        regression.metric for regression in comparison.regressions
    }
    assert "load_duration_ms" not in {
        regression.metric for regression in comparison.regressions
    }


def test_comparison_skips_zero_missing_and_dimension_mismatches() -> None:
    baseline = _report(
        replace(
            _case(),
            wall_time_ms=0,
            peak_python_memory_bytes=None,
            stages=(),
        )
    )
    current = _report(
        replace(
            _case(),
            turns=2,
            wall_time_ms=500,
            peak_python_memory_bytes=50_000_000,
            stages=(),
        )
    )

    comparison = compare_reports(baseline, current)

    assert comparison.comparable is True
    assert comparison.regressions == ()
    assert comparison.skipped == (
        "scale-10: dimensions differ",
    )
