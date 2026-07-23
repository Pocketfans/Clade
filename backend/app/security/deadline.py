from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

Clock = Callable[[], float]


class DeadlineExpired(TimeoutError):
    """The caller-owned monotonic budget has no time remaining."""


class TimeoutBudget(Protocol):
    def remaining(self) -> float:
        raise NotImplementedError

    def phase_timeout(self, limit: float | None = None) -> float:
        raise NotImplementedError


def _positive_finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timeout must be a positive finite number")
    normalized = float(value)
    if normalized <= 0 or not math.isfinite(normalized):
        raise ValueError("timeout must be a positive finite number")
    return normalized


@dataclass(frozen=True)
class DeadlineBudget:
    deadline: float
    clock: Clock = field(default=time.monotonic, compare=False, repr=False)

    @classmethod
    def from_timeout(
        cls,
        timeout: float,
        *,
        started_at: float | None = None,
        clock: Clock = time.monotonic,
    ) -> "DeadlineBudget":
        normalized = _positive_finite(timeout)
        start = clock() if started_at is None else started_at
        return cls(deadline=start + normalized, clock=clock)

    def remaining(self) -> float:
        return max(0.0, self.deadline - self.clock())

    def phase_timeout(self, limit: float | None = None) -> float:
        remaining = self.remaining()
        if remaining <= 0:
            raise DeadlineExpired
        return remaining if limit is None else min(remaining, limit)


@dataclass
class StreamBudget:
    idle_timeout: float
    hard_deadline: float
    initial_idle_deadline: float
    clock: Clock = field(default=time.monotonic, repr=False)
    _idle_deadline: float | None = None
    _content_started: bool = False

    @classmethod
    def from_timeouts(
        cls,
        idle_timeout: float,
        *,
        hard_timeout: float = 600.0,
        started_at: float | None = None,
        clock: Clock = time.monotonic,
    ) -> "StreamBudget":
        idle = _positive_finite(idle_timeout)
        hard = _positive_finite(hard_timeout)
        start = clock() if started_at is None else started_at
        return cls(idle, start + hard, start + idle, clock)

    @property
    def content_started(self) -> bool:
        return self._content_started

    def mark_content(self) -> None:
        self._content_started = True
        self._idle_deadline = None

    def remaining(self) -> float:
        now = self.clock()
        if not self._content_started:
            idle_deadline = self.initial_idle_deadline
        else:
            if self._idle_deadline is None:
                self._idle_deadline = now + self.idle_timeout
            idle_deadline = self._idle_deadline
        return max(0.0, min(idle_deadline, self.hard_deadline) - now)

    def phase_timeout(self, limit: float | None = None) -> float:
        remaining = self.remaining()
        if remaining <= 0:
            raise DeadlineExpired
        return remaining if limit is None else min(remaining, limit)
