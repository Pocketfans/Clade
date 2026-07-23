import math
import time

import pytest

from app.security.deadline import DeadlineBudget, DeadlineExpired, StreamBudget


class ManualClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_deadline_budget_uses_original_start_and_clamps_each_phase() -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(60, started_at=90.0, clock=clock)
    assert budget.remaining() == pytest.approx(50.0)
    assert budget.phase_timeout(10.0) == pytest.approx(10.0)
    clock.now = 145.0
    assert budget.phase_timeout(10.0) == pytest.approx(5.0)
    clock.now = 150.0
    with pytest.raises(DeadlineExpired):
        budget.phase_timeout()


@pytest.mark.parametrize("value", [True, 0, -1, math.inf, math.nan, "60"])
def test_deadline_budget_rejects_invalid_timeout(value: object) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        DeadlineBudget.from_timeout(value)  # type: ignore[arg-type]


def test_wall_clock_changes_do_not_affect_monotonic_budget(monkeypatch) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(10.0, clock=clock)
    monkeypatch.setattr(time, "time", lambda: -9_999_999.0)
    clock.now = 104.0
    assert budget.remaining() == pytest.approx(6.0)


def test_stream_initial_idle_includes_queue_and_statuses_do_not_refresh() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(60.0, started_at=100.0, clock=clock)
    clock.now = 159.0
    assert budget.phase_timeout() == pytest.approx(1.0)
    clock.now = 160.0
    with pytest.raises(DeadlineExpired):
        budget.phase_timeout()


def test_real_content_opens_next_idle_window_when_consumer_resumes() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(60.0, started_at=100.0, clock=clock)
    clock.now = 120.0
    budget.mark_content()
    clock.now = 170.0
    assert budget.phase_timeout() == pytest.approx(60.0)
    clock.now = 230.0
    with pytest.raises(DeadlineExpired):
        budget.phase_timeout()


def test_stream_hard_deadline_never_resets() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(60.0, hard_timeout=600.0, clock=clock)
    for second in (50.0, 300.0, 599.0):
        clock.now = 100.0 + second
        budget.mark_content()
    clock.now = 700.0
    with pytest.raises(DeadlineExpired):
        budget.phase_timeout()
