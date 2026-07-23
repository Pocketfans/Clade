# Phase 3B End-to-End Time Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every ordinary AI request obey one end-to-end configured time budget, while streamed requests use a real-content idle timeout plus a 600-second hard limit and never treat partial output as a complete business result.

**Architecture:** Add small monotonic-clock budget types and extract the existing four-slot bounded daemon runner into shared security infrastructure. Pass one ordinary deadline through queueing, DNS, approved-IP dialing, HTTP phases, retry backoff, and Embedding retries; pass one stream budget through queueing and the guarded stream, refreshing idle time only after real model content. Model routing publishes explicit terminal states, helpers return completion metadata, and business/UI consumers fall back on interrupted streams without discarding already displayed text.

**Tech Stack:** Python 3.12, FastAPI, asyncio, httpx/httpcore, pytest/pytest-asyncio, React 18, TypeScript 5.5, Vitest, Testing Library.

## Global Constraints

- Preserve database schema, save format, gameplay, simulation rules, provider selection, load-balancing strategy, retry counts, and retry backoff formulas.
- Do not add a user setting or dependency. Existing `timeout` is an ordinary total budget and a stream real-content idle timeout.
- A normal request budget starts at the logical entry and includes local preparation, semaphore queueing, DNS, all approved-IP attempts, TLS, writes, reads, parsing, retry sleeps, and later attempts.
- A stream's initial idle window starts at the logical entry and includes queueing through first real model content. Later idle windows measure only waits for upstream content; local consumer work does not count as upstream idle but always consumes the 600-second hard limit.
- Only non-empty real model content refreshes stream idle time. Status events, UI/server heartbeats, SSE comments, empty lines, and protocol-only events do not.
- The stream hard deadline is exactly 600 seconds from logical entry and includes queueing.
- A stream never retries. A normal request retries only existing `outbound_connect_failed` and `outbound_timeout` cases, using the existing maximum and backoff formula.
- At most four expired blocking workers may remain alive. They retain their slots until they exit and cannot update caches, statistics, success events, or caller state afterward.
- Preserve Phase 2C URL policy, DNS approval, approved-IP-only dialing, Host/SNI/certificate semantics, proxy and redirect rejection, response byte limits, fixed public errors, log redaction, cancellation propagation, and exactly-once cleanup.
- Tests must use fake clocks, fake resolvers, recording backends, or in-memory streams. Never access the public network or place a real credential in code, logs, fixtures, or docs.
- Follow red-green-refactor. Every production behavior change starts with a focused failing test and ends with a focused commit.
- Run backend commands from `backend` with `$PYTHON = "E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe"`.
- Run frontend commands from `frontend`; the current `node_modules` is already present.

---

## File Structure and Ownership

| File | Responsibility after Phase 3B |
|---|---|
| `backend/app/security/deadline.py` | Monotonic ordinary and stream budgets; no I/O, logging, config, or retry policy |
| `backend/app/security/bounded_runner.py` | Four-slot sync/async daemon execution for unkillable blocking calls |
| `backend/app/security/safe_http.py` | Probe-specific 10/15-second contracts using the shared runner |
| `backend/app/security/pinned_transport.py` | Approved-IP dialing and per-operation timeout clamping to remaining budget |
| `backend/app/security/runtime_http.py` | Guarded JSON/stream HTTP, DNS execution, limits, error mapping, and cleanup |
| `backend/app/ai/model_router.py` | Logical budget creation, semaphore queueing, retry orchestration, stream parsing, and terminal events |
| `backend/app/services/system/embedding.py` | One budget per remote logical Embedding chunk, shared across its retries/backoff |
| `backend/app/ai/streaming_helper.py` | Heartbeats only, `StreamOutcome`, event bridging, and no competing timers |
| `backend/app/services/analytics/report_builder.py` | Use complete streamed narrative or the existing complete fallback report |
| `backend/app/services/analytics/report_builder_v2.py` | Same complete-versus-interrupted contract for V2 narrative |
| `backend/app/services/species/speciation.py` | Use complete batch JSON or existing rule fallback; no hard-coded wrapper timer |
| `backend/app/services/analytics/critical_analyzer.py` | Heartbeat wrapper call without an outer request timeout |
| `backend/app/services/analytics/focus_processor.py` | Heartbeat wrapper call without an outer request timeout |
| `backend/app/services/species/hybridization.py` | Heartbeat wrapper call without an outer request timeout |
| `frontend/src/components/TurnProgressOverlay.tsx` | Show interrupted-stream warning without incrementing successful completion |

### Deterministic Test Helper Contract

The examples below use small local fakes. Implement them in the named test file before the test that consumes them; do not import test helpers across modules.

| Test file | Required local helpers |
|---|---|
| `backend/app/security/tests/test_pinned_transport.py` | Copy the six-line `ManualClock` from Task 1. Add `AdvancingSyncBackend`/`AdvancingAsyncBackend` by extending the existing recording backends: each `connect_tcp()` appends its timeout to `connect_timeouts`, advances the clock by the next configured amount, raises the next configured connect error when present, and otherwise returns the existing recording stream. Use the existing `_validated()`, `_request()`, response-close helpers, and two documentation-only IPs rather than inventing network fixtures. |
| `backend/app/security/tests/test_runtime_http.py` | Copy `ManualClock`. Add `AdvancingPolicy(RecordingPolicy)` whose `validate()` advances by `dns_seconds`, plus `AdvancingSyncStream`/`AdvancingAsyncStream` subclasses whose `read()` advances by the next value before delegating; `_advancing_stream(mode, clock, read_advances)` selects the matching class. Extend `_runtime_client()` only with the optional `runner` injection needed by the tests. |
| `backend/app/ai/tests/test_model_router_security.py` | Copy `ManualClock`. Extend the existing `RecordingSafeRuntimeClient` so every recorded JSON/stream call includes `budget`. Add `AdvancingRuntimeClient`: before returning or raising each queued async result, advance its clock by the paired number of seconds. Use the existing `_remote_router()` fixture; add `_collect_router_stream()` plus provider-specific `_valid_stream_line()`/`_expected_stream_content()` helpers for the already covered OpenAI, Anthropic, and Google formats. |
| `backend/app/services/system/tests/test_embedding_security.py` | Copy `ManualClock`. Extend the existing `RecordingSafeRuntimeClient` with optional `(advance_seconds, result_or_exception)` outcomes; its `post_json()` records `budget`, advances the clock, then returns or raises. Use the existing `remote_service()` factory and `_timeout_errors()` fixed public errors. |
| `backend/app/security/tests/test_runtime_http.py` stream section | Add `AdvancingAsyncStream` by extending `RecordingAsyncStream`; each configured `(line, advance_seconds)` advances the clock immediately before returning that line and increments the inherited close counter normally. |
| `backend/app/ai/tests/test_streaming_helper.py` | Define `RecordingRouter` with recorded `ainvoke_calls`/`invoke_calls` and a configurable async result for Task 8. Define `StreamRouter(items)` with both `astream()` and `astream_capability()` async generators that yield the supplied items verbatim for Task 9. |
| `backend/app/services/analytics/tests/test_report_builder_streaming.py` | Define minimal router/callback fixtures for both report builders; yield a 100-character content chunk followed by the canonical `interrupted` status. Stub unrelated world-state dependencies with the smallest valid values used by the existing builders. |
| `backend/app/services/species/tests/test_speciation_streaming.py` | Construct `SpeciationService` with a minimal router yielding partial JSON then `interrupted`; spy on the existing fallback path and assert no partial parsed object is accepted. |

---

### Task 1: Add monotonic budgets and extract the bounded runner

**Files:**
- Create: `backend/app/security/deadline.py`
- Create: `backend/app/security/bounded_runner.py`
- Create: `backend/app/security/tests/test_deadline.py`
- Create: `backend/app/security/tests/test_bounded_runner.py`
- Modify: `backend/app/security/safe_http.py:1-160`
- Modify: `backend/app/security/tests/test_safe_http.py:517-597`
- Modify: `backend/app/security/__init__.py`

**Interfaces:**
- Produces: `DeadlineExpired`, `TimeoutBudget`, and `DeadlineBudget.from_timeout(timeout, *, started_at=None, clock=time.monotonic)`.
- Produces: `DeadlineBudget.remaining() -> float` and `DeadlineBudget.phase_timeout(limit: float | None = None) -> float`.
- Produces: `BoundedDaemonRunner.run(operation, *, timeout)`, `await BoundedDaemonRunner.arun(operation, *, timeout)`, and one process-wide `DEFAULT_BOUNDED_RUNNER` with four shared slots.
- Preserves: `SafeProbeClient` public API and exact 10/15-second contracts.

- [x] **Step 1: Write failing ordinary budget tests**

```python
# backend/app/security/tests/test_deadline.py
import math
import pytest

from app.security.deadline import DeadlineBudget, DeadlineExpired


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
```

- [x] **Step 2: Write failing sync/async runner tests**

```python
# backend/app/security/tests/test_bounded_runner.py
import asyncio
import threading
import time

import pytest

from app.security.bounded_runner import BoundedDaemonRunner


def test_runner_never_starts_more_than_four_expired_workers() -> None:
    runner = BoundedDaemonRunner(max_workers=4)
    release = threading.Event()
    for _ in range(4):
        with pytest.raises(TimeoutError):
            runner.run(lambda: release.wait(), timeout=0.01)
    with pytest.raises(TimeoutError):
        runner.run(lambda: None, timeout=0.01)
    assert runner.max_active == 4
    release.set()


@pytest.mark.asyncio
async def test_async_wait_times_out_without_blocking_event_loop() -> None:
    runner = BoundedDaemonRunner(max_workers=1)
    release = threading.Event()
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while ticks < 3:
            await asyncio.sleep(0)
            ticks += 1

    ticker_task = asyncio.create_task(ticker())
    with pytest.raises(TimeoutError):
        await runner.arun(lambda: release.wait(), timeout=0.01)
    await ticker_task
    assert ticks == 3
    release.set()
```

- [x] **Step 3: Run the new tests and verify RED**

Run from `backend`:

```powershell
& $PYTHON -m pytest app/security/tests/test_deadline.py app/security/tests/test_bounded_runner.py -q
```

Expected: collection fails because `app.security.deadline` and `app.security.bounded_runner` do not exist.

- [x] **Step 4: Implement `DeadlineBudget`**

```python
# backend/app/security/deadline.py
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
```

- [x] **Step 5: Extract and extend the runner**

Move the existing `_BoundedDaemonRunner` implementation from `safe_http.py` into `bounded_runner.py`, rename it `BoundedDaemonRunner`, preserve `max_workers <= 4`, `max_active`, daemon threads, slot retention, and exception propagation. Add an async API that starts the same bounded worker and completes an event-loop future with `loop.call_soon_threadsafe`; it must not call `asyncio.to_thread()` merely to wait for the result.

```python
async def arun(self, operation: Callable[[], T], *, timeout: float) -> T:
    loop = asyncio.get_running_loop()
    deadline = time.monotonic() + max(timeout, 0.0)
    while not self._slots.acquire(blocking=False):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        await asyncio.sleep(min(0.01, remaining))

    future: asyncio.Future[T] = loop.create_future()

    def publish(succeeded: bool, value: object) -> None:
        if future.done():
            return
        if succeeded:
            future.set_result(cast(T, value))
        else:
            future.set_exception(cast(BaseException, value))

    def worker() -> None:
        self._mark_started()
        try:
            try:
                value: object = operation()
                succeeded = True
            except BaseException as exc:
                value = exc
                succeeded = False
            try:
                loop.call_soon_threadsafe(publish, succeeded, value)
            except RuntimeError:
                # The owning event loop may already be closed after cancellation.
                pass
        finally:
            self._mark_finished()
            self._slots.release()

    self._start_worker(worker)
    try:
        return await asyncio.wait_for(
            asyncio.shield(future),
            timeout=max(deadline - time.monotonic(), 0.0),
        )
    except asyncio.CancelledError:
        future.cancel()
        raise
    except asyncio.TimeoutError:
        future.cancel()
        raise TimeoutError from None
```

Factor `_mark_started()`, `_mark_finished()`, and `_start_worker()` so sync and async APIs share the same active-count and slot-release rules. If thread creation fails, release the acquired slot before re-raising.

After the class definition, create exactly one shared instance:

```python
DEFAULT_BOUNDED_RUNNER = BoundedDaemonRunner(max_workers=4)
```

Production probe, normal JSON, and streaming DNS call sites all use this singleton unless a test injects a runner. Do not create separate four-slot defaults per client module.

- [x] **Step 6: Migrate `SafeProbeClient` without changing behavior**

Import `DEFAULT_BOUNDED_RUNNER`, define a local `_Runner` protocol for `run()` if needed by existing test fakes, bind `_DEFAULT_RUNNER = DEFAULT_BOUNDED_RUNNER`, and delete the duplicate queue/thread implementation from `safe_http.py`. Update `test_safe_http.py` imports to the shared class; do not alter probe return shapes or fixed timeouts.

- [x] **Step 7: Run focused tests and verify GREEN**

```powershell
& $PYTHON -m pytest app/security/tests/test_deadline.py app/security/tests/test_bounded_runner.py app/security/tests/test_safe_http.py -q
```

Expected: all selected tests pass; deadline tests use no wall-clock sleeps except millisecond runner bounds.

- [x] **Step 8: Commit**

```powershell
git add backend/app/security/deadline.py backend/app/security/bounded_runner.py backend/app/security/safe_http.py backend/app/security/__init__.py backend/app/security/tests/test_deadline.py backend/app/security/tests/test_bounded_runner.py backend/app/security/tests/test_safe_http.py
git commit -m "feat(security): add reusable request deadlines"
```

---

### Task 2: Clamp approved-IP transport operations to the shared deadline

**Files:**
- Modify: `backend/app/security/pinned_transport.py:11-385`
- Modify: `backend/app/security/tests/test_pinned_transport.py:270-690`

**Interfaces:**
- Consumes: `TimeoutBudget.phase_timeout(limit)` from Task 1.
- Produces: optional `budget: TimeoutBudget | None` on `PinnedSyncTransport` and `PinnedAsyncTransport`.
- Preserves: approved-IP order, original Host/SNI/certificate hostname, Unix-socket rejection, sanitized errors, and exactly-once close.

- [x] **Step 1: Write failing sync and async multi-IP budget tests**

Add a recording delegate whose first connection advances a `ManualClock` and fails. Assert the second approved IP receives only the remaining time, not the original connect timeout.

```python
def test_sync_approved_ips_share_one_connect_budget() -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(5.0, clock=clock)
    backend = AdvancingSyncBackend(
        RecordingStream(),
        clock=clock,
        advances=[4.0, 0.0],
        connect_errors=[httpcore.ConnectError("first IP failed")],
    )
    transport = PinnedSyncTransport(
        _validated("93.184.216.34", "192.0.2.2"), backend, budget=budget
    )
    response = transport.handle_request(_request())
    _close_response_and_transport(response, transport)
    assert backend.connect_timeouts == [5.0, 1.0]


@pytest.mark.asyncio
async def test_async_does_not_try_next_ip_after_budget_expires() -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(5.0, clock=clock)
    backend = AdvancingAsyncBackend(
        RecordingAsyncStream(),
        clock=clock,
        advances=[5.0],
        connect_errors=[httpcore.ConnectError("first IP failed")],
    )
    transport = PinnedAsyncTransport(
        _validated("93.184.216.34", "192.0.2.2"), backend, budget=budget
    )
    with pytest.raises(httpcore.ConnectTimeout):
        await transport.handle_async_request(_request())
    await transport.aclose()
    assert len(backend.connect_calls) == 1
```

- [x] **Step 2: Run the two tests and verify RED**

```powershell
& $PYTHON -m pytest app/security/tests/test_pinned_transport.py -q -k "share_one_connect_budget or after_budget_expires"
```

Expected: constructor rejects `budget` or both IPs receive the original timeout.

- [x] **Step 3: Thread the budget through backends and streams**

Add `budget` to `_PinnedNetworkBackend`, `_PinnedAsyncNetworkBackend`, `_SanitizedNetworkBackend`, `_SanitizedAsyncNetworkBackend`, `_SanitizedNetworkStream`, and `_SanitizedAsyncNetworkStream`. Clamp immediately before every connect, TLS, read, and write:

```python
def _bounded_timeout(
    budget: TimeoutBudget | None,
    requested: float | None,
    *,
    timeout_error: type[Exception],
) -> float | None:
    if budget is None:
        return requested
    try:
        return budget.phase_timeout(requested)
    except DeadlineExpired:
        raise timeout_error("outbound deadline expired") from None
```

Use `httpcore.ConnectTimeout` for connect/TLS, `httpcore.ReadTimeout` for reads, and `httpcore.WriteTimeout` for writes. Recalculate inside the approved-IP loop before every delegate call.

- [x] **Step 4: Pass the budget from both transport constructors**

```python
class PinnedSyncTransport(httpx.BaseTransport):
    def __init__(
        self,
        validated: ValidatedOutboundURL,
        network_backend: httpcore.NetworkBackend | None = None,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        delegate = (
            httpcore.SyncBackend()
            if network_backend is None
            else network_backend
        )
        self._validated = validated
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            retries=0,
            network_backend=_SanitizedNetworkBackend(
                _PinnedNetworkBackend(validated, delegate, budget=budget),
                budget=budget,
            ),
        )
```

Mirror the keyword-only parameter on `PinnedAsyncTransport`. Keep all existing call sites valid by defaulting to `None` in this task.

- [x] **Step 5: Run complete transport tests**

```powershell
& $PYTHON -m pytest app/security/tests/test_pinned_transport.py app/security/tests/test_safe_http.py -q
```

Expected: all pass, including existing Host/SNI, error sanitization, Unix rejection, and cleanup tests.

- [x] **Step 6: Commit**

```powershell
git add backend/app/security/pinned_transport.py backend/app/security/tests/test_pinned_transport.py
git commit -m "fix(security): clamp pinned transport to request deadlines"
```

---

### Task 3: Enforce ordinary deadlines inside `SafeRuntimeClient`

**Files:**
- Modify: `backend/app/security/runtime_http.py:40-360`
- Modify: `backend/app/security/tests/test_runtime_http.py:60-1303`
- Modify: `backend/app/security/__init__.py`

**Interfaces:**
- Consumes: `DeadlineBudget`, `BoundedDaemonRunner`, and deadline-aware pinned transports.
- Transitional input: `budget: DeadlineBudget | None = None` plus existing `read_timeout`; exactly one effective budget is built.
- Produces: sync/async JSON calls whose DNS, request, body, parse, and close are bounded by the caller's deadline.

- [x] **Step 1: Add failing end-to-end runtime tests**

Cover sync blocking DNS, async blocking DNS without event-loop starvation, body reads spanning multiple phase timeouts, cancellation, and close counts.

```python
@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_normal_budget_spans_dns_connect_and_complete_body(mode: Mode) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(6.0, clock=clock)
    policy = AdvancingPolicy(clock, dns_seconds=2.0)
    stream = _advancing_stream(mode, clock, read_advances=[2.0, 2.1])
    client, _, backend = _runtime_client(mode, stream, policy=policy)
    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, budget=budget, read_timeout=None)
    assert exc_info.value.code == "outbound_timeout"
    assert backend.connect_calls == [("93.184.216.34", 443)]
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_async_blocking_dns_timeout_does_not_block_other_task() -> None:
    release = threading.Event()
    started = threading.Event()
    ticks = 0

    def resolver(hostname: str, port: int) -> tuple[IPv4Address, ...]:
        started.set()
        release.wait()
        return (IPv4Address("93.184.216.34"),)

    async def ticker() -> None:
        nonlocal ticks
        while ticks < 3:
            await asyncio.sleep(0)
            ticks += 1

    client = SafeRuntimeClient(
        policy=OutboundURLPolicy(resolver),
        runner=BoundedDaemonRunner(max_workers=1),
    )
    budget = DeadlineBudget.from_timeout(0.02)
    ticker_task = asyncio.create_task(ticker())
    try:
        with pytest.raises(OutboundRequestError) as exc_info:
            await client.apost_json(
                "https://public.example/v1",
                request_target="/chat/completions",
                headers={"Authorization": "Bearer test-sentinel"},
                json_body={"model": "test", "messages": []},
                allow_local=False,
                budget=budget,
                max_bytes=1024,
            )
        assert exc_info.value.code == "outbound_timeout"
        await ticker_task
        assert ticks == 3
        assert started.is_set()
    finally:
        release.set()
```

- [x] **Step 2: Run the new cases and verify RED**

```powershell
& $PYTHON -m pytest app/security/tests/test_runtime_http.py -q -k "normal_budget or blocking_dns_timeout"
```

Expected: DNS runs inline or the new `budget` keyword is rejected.

- [x] **Step 3: Add budget resolution and runner injection**

```python
class SafeRuntimeClient:
    def __init__(
        self,
        policy: OutboundURLPolicy | None = None,
        *,
        sync_network_backend: httpcore.NetworkBackend | None = None,
        async_network_backend: httpcore.AsyncNetworkBackend | None = None,
        runner: BoundedDaemonRunner | None = None,
        timeouts: RuntimeTimeouts = RuntimeTimeouts(),
    ) -> None:
        self._runner = runner or DEFAULT_BOUNDED_RUNNER
        self._policy = OutboundURLPolicy() if policy is None else policy
        self._sync_network_backend = sync_network_backend
        self._async_network_backend = async_network_backend
        self._timeouts = timeouts

    @staticmethod
    def _normal_budget(
        budget: DeadlineBudget | None,
        read_timeout: float | None,
    ) -> DeadlineBudget:
        if budget is not None:
            return budget
        if read_timeout is None:
            raise _invalid_url()
        try:
            return DeadlineBudget.from_timeout(read_timeout)
        except ValueError:
            raise _invalid_url() from None
```

The `read_timeout` fallback is migration-only and is removed in Task 5 after all production callers pass budgets.

- [x] **Step 4: Bound the synchronous operation as one worker**

Move the existing sync request body to `_post_json_impl(base_url, request_target, headers, json_body, allow_local, max_bytes, budget)`. Set and reset the HTTP log-suppression context inside the worker, validate the URL there, create `PinnedSyncTransport(validated, self._sync_network_backend, budget=budget)`, and use `budget.phase_timeout()`/phase caps for HTTPX values. Call it through:

```python
try:
    return self._runner.run(
        lambda: self._post_json_impl(
            base_url,
            request_target=request_target,
            headers=headers,
            json_body=json_body,
            allow_local=allow_local,
            max_bytes=max_bytes,
            budget=effective_budget,
        ),
        timeout=effective_budget.phase_timeout(),
    )
except (DeadlineExpired, TimeoutError, httpx.TimeoutException, httpcore.TimeoutException):
    raise _timeout() from None
```

Only the low-level guarded HTTP operation belongs in the worker. Cache writes, router statistics, and success events remain on the caller thread after a result is returned.

- [x] **Step 5: Bound async DNS and the complete async request**

Run `OutboundURLPolicy.validate()` through `await self._runner.arun(lambda: self._policy.validate(base_url, allow_local=allow_local), timeout=effective_budget.phase_timeout())`, then wrap client creation, request, bounded read, parse, and cleanup in the current budget:

```python
validated = await self._runner.arun(
    lambda: self._policy.validate(base_url, allow_local=allow_local),
    timeout=effective_budget.phase_timeout(),
)
async with asyncio.timeout(effective_budget.phase_timeout()):
    transport = PinnedAsyncTransport(
        validated,
        self._async_network_backend,
        budget=effective_budget,
    )
    # existing hardened AsyncClient and bounded JSON read
```

Catch and re-raise `asyncio.CancelledError` before timeout/error mapping. Preserve existing fixed errors and log suppression.

- [x] **Step 6: Run the complete runtime security suite**

```powershell
& $PYTHON -m pytest app/security/tests/test_deadline.py app/security/tests/test_bounded_runner.py app/security/tests/test_pinned_transport.py app/security/tests/test_runtime_http.py app/security/tests/test_safe_http.py -q
```

Expected: all selected tests pass with no public-network access.

- [x] **Step 7: Commit**

```powershell
git add backend/app/security/runtime_http.py backend/app/security/__init__.py backend/app/security/tests/test_runtime_http.py
git commit -m "fix(security): enforce end-to-end runtime deadlines"
```

---

### Task 4: Share one normal budget across router queueing and retries

**Files:**
- Modify: `backend/app/ai/model_router.py:380-755,1057-1511`
- Modify: `backend/app/ai/tests/test_model_router_security.py`

**Interfaces:**
- Consumes: `DeadlineBudget` and budget-aware `post_json`/`apost_json`.
- Produces: optional keyword-only `budget: DeadlineBudget | None = None` on the five normal router entries.
- Produces: `_acquire_with_budget(budget) -> None` and one logical timeout statistic per request.
- Produces: `total_cancellations` plus per-capability `cancelled`; cancellation never increments `total_timeouts`.

- [x] **Step 1: Add failing queue and retry tests**

```python
@pytest.mark.asyncio
async def test_ainvoke_queue_wait_is_inside_total_budget() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    router = _remote_router(runtime_client, timeout=0.02)
    await router._semaphore.acquire()
    try:
        result = await router.ainvoke("generate", {"name": "elm"})
    finally:
        router._semaphore.release()
    assert result["error"] == PUBLIC_TIMEOUT
    assert runtime_client.calls == []


@pytest.mark.asyncio
async def test_ainvoke_retries_share_one_budget_and_count_one_timeout() -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(6.0, clock=clock)
    runtime_client = AdvancingRuntimeClient(
        clock,
        outcomes=[
            (4.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
            (2.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
        ],
    )
    router = _remote_router(runtime_client, max_retries=3)
    result = await router.ainvoke("generate", {"name": "elm"}, budget=budget)
    assert result["error"] == PUBLIC_TIMEOUT
    assert len(runtime_client.calls) == 2
    assert router.get_diagnostics()["total_timeouts"] == 1
```

Add a parameterized test across `invoke`, `call_capability`, `acall_capability`, and `chat` proving the exact same budget object reaches the recording runtime client.

Extend the existing semaphore/safe-call/backoff cancellation tests to assert `total_timeouts == 0`, `total_cancellations == 1`, and the capability's `cancelled == 1` after cleanup.

- [x] **Step 2: Run the new router tests and verify RED**

```powershell
& $PYTHON -m pytest app/ai/tests/test_model_router_security.py -q -k "inside_total_budget or share_one_budget or same_budget_object"
```

Expected: queue wait has no timeout, retries receive fresh read timeouts, or signatures reject `budget`.

- [x] **Step 3: Create budgets at logical entry**

Record `started_at = time.monotonic()` before `_prepare_request()`/`resolve()`. Use the prepared/configured timeout without resetting the start:

```python
def _ensure_deadline(
    supplied: DeadlineBudget | None,
    *,
    timeout: float,
    started_at: float,
) -> DeadlineBudget:
    if supplied is not None:
        return supplied
    try:
        return DeadlineBudget.from_timeout(timeout, started_at=started_at)
    except ValueError:
        raise OutboundRequestError(
            "outbound_url_invalid", 400, "外部服务地址无效"
        ) from None
```

Pass the budget to every normal runtime-client call. Keep optional keyword-only parameters so existing direct callers remain source compatible.

- [x] **Step 4: Put semaphore waiting inside the budget**

```python
async def _acquire_with_budget(
    semaphore: asyncio.Semaphore,
    budget: DeadlineBudget,
) -> None:
    try:
        await asyncio.wait_for(
            semaphore.acquire(), timeout=budget.phase_timeout()
        )
    except (DeadlineExpired, TimeoutError, asyncio.TimeoutError):
        raise OutboundRequestError(
            "outbound_timeout", 504, "外部服务请求超时"
        ) from None
```

Replace `async with self._semaphore` in `ainvoke`, `acall_capability`, and `chat` with acquire/`finally: release()`. Update queued/active counters exactly once on every queue timeout, success, error, and cancellation.

- [x] **Step 5: Make retry and backoff consume the same budget**

Pass `budget=effective_budget` on every attempt. Before retry sleep:

```python
sleep_time = min(2.0, 0.5 * (attempt + 1))
try:
    await asyncio.wait_for(
        asyncio.sleep(sleep_time),
        timeout=effective_budget.phase_timeout(),
    )
except (DeadlineExpired, TimeoutError, asyncio.TimeoutError):
    last_error = PUBLIC_TIMEOUT
    break
```

Do not start another resolver/connection after expiry. Add one idempotent `_finish_request_stats(capability, outcome, elapsed)` helper where `outcome` is `success | timeout | error | cancelled`; it updates the matching per-capability counter and the global timeout/cancellation counter at most once. Use it for every async normal exit so repeated timed-out attempts do not inflate request totals and cancellation remains separate.

- [x] **Step 6: Run router and runtime tests**

```powershell
& $PYTHON -m pytest app/ai/tests/test_model_router_security.py app/security/tests/test_runtime_http.py -q
```

Expected: all pass; the existing seven-entry routing/security cases remain unchanged except recorded calls now carry a budget.

- [x] **Step 7: Commit**

```powershell
git add backend/app/ai/model_router.py backend/app/ai/tests/test_model_router_security.py
git commit -m "fix(ai): share deadlines across queue and retries"
```

---

### Task 5: Share one budget across each Embedding remote chunk

**Files:**
- Modify: `backend/app/services/system/embedding.py:590-681`
- Modify: `backend/app/services/system/tests/test_embedding_security.py`
- Modify: `backend/app/security/runtime_http.py` (remove migration-only `read_timeout`)
- Modify: `backend/app/security/tests/test_runtime_http.py`
- Modify: router/Embedding recording clients in their security tests

**Interfaces:**
- Consumes: `DeadlineBudget` and `SafeRuntimeClient.post_json(base_url: str, *, request_target: str, headers: Mapping[str, str], json_body: Mapping[str, Any], allow_local: bool, budget: DeadlineBudget, max_bytes: int)`.
- Produces: optional private `budget: DeadlineBudget | None = None` on `_request_embedding_chunk_result()` for deterministic tests.
- Finalizes: `post_json`/`apost_json` require `budget`; legacy `read_timeout` is removed.

- [x] **Step 1: Write failing retry-budget tests**

```python
def test_embedding_chunk_retries_share_one_total_budget(monkeypatch) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(6.0, clock=clock)
    client = AdvancingSafeRuntimeClient(
        clock,
        outcomes=[
            (4.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
            (2.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
        ],
    )
    service = remote_service(client)
    monkeypatch.setattr(time, "sleep", lambda seconds: setattr(clock, "now", clock.now + seconds))
    result = service._request_embedding_chunk_result(
        ["oak"], require_real=False, budget=budget
    )
    assert result.items[0].source == "remote_fallback_fake"
    assert result.items[0].cacheable is False
    assert len(client.calls) == 2


def test_embedding_expired_budget_never_starts_another_retry() -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(3.0, clock=clock)
    client = AdvancingSafeRuntimeClient(
        clock,
        outcomes=[
            (3.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
        ],
    )
    service = remote_service(client)
    with pytest.raises(RuntimeError, match="外部服务请求超时"):
        service._request_embedding_chunk_result(
            ["oak"], require_real=True, budget=budget
        )
    assert len(client.calls) == 1
```

- [x] **Step 2: Run the new Embedding cases and verify RED**

```powershell
& $PYTHON -m pytest app/services/system/tests/test_embedding_security.py -q -k "share_one_total_budget or never_starts_another_retry"
```

Expected: the private method rejects `budget` and each attempt passes a fresh read timeout.

- [x] **Step 3: Implement one chunk budget**

Capture `started_at = time.monotonic()` as the first executable line of `_request_embedding_chunk_result()`. Take the frozen runtime-config snapshot, then create `DeadlineBudget.from_timeout(config.timeout, started_at=started_at)` so payload preparation before the first attempt is included.

```python
effective_budget = budget or DeadlineBudget.from_timeout(
    config.timeout, started_at=started_at
)
for attempt in range(max_retries):
    try:
        data = self._runtime_client.post_json(
            config.api_base_url,
            request_target="/embeddings",
            headers=headers,
            json_body=body,
            allow_local=config.allow_local_ai_endpoints,
            budget=effective_budget,
            max_bytes=EMBEDDING_JSON_MAX_BYTES,
        )
        batch_vectors = self._parse_embedding_response(data, len(batch_texts))
        with self._stats_lock:
            self._stats["api_calls"] += 1
        return _EmbeddingGenerationResult(tuple(
            _GeneratedEmbedding(
                vector=vector,
                cacheable=True,
                source=_CACHE_SOURCE_REMOTE,
            )
            for vector in batch_vectors
        ))
    except OutboundRequestError as exc:
        if exc.code not in RETRYABLE_OUTBOUND_CODES:
            logger.warning("[Embedding] blocked error_code=%s", exc.code)
            raise RuntimeError(exc.public_message) from None
        exhausted = attempt == max_retries - 1
        sleep_time = 2 ** attempt
        remaining = effective_budget.remaining()
        if remaining <= 0:
            exc = OutboundRequestError(
                "outbound_timeout", 504, "外部服务请求超时"
            )
            exhausted = True
        if exhausted:
            if require_real or not config.allow_fake_embeddings:
                raise RuntimeError(exc.public_message) from None
            vectors = [self._fake_embed(text) for text in batch_texts]
            with self._stats_lock:
                self._stats["fake_embeds"] += len(batch_texts)
            return _EmbeddingGenerationResult(tuple(
                _GeneratedEmbedding(
                    vector=vector,
                    cacheable=False,
                    source=_CACHE_SOURCE_REMOTE_FALLBACK_FAKE,
                )
                for vector in vectors
            ))
        else:
            time.sleep(min(sleep_time, remaining))
```

After sleeping, call `effective_budget.phase_timeout()` before the next attempt. If it raises `DeadlineExpired`, route the fixed timeout through the same `require_real`/allowed-fake terminal branch shown above; never let it start another call or escape as a different public error. Preserve the frozen runtime config and fake-vector rules from Phase 2C.

- [x] **Step 4: Remove the transitional runtime API**

Delete `read_timeout` from `post_json`/`apost_json`, require `budget`, and update all runtime-client fakes/recorders to record the same budget object. Run `rg -n "read_timeout=" backend/app` and ensure only unrelated diagnostic/probe configuration remains.

- [x] **Step 5: Run Embedding, router, and runtime tests**

```powershell
& $PYTHON -m pytest app/services/system/tests/test_embedding_security.py app/ai/tests/test_model_router_security.py app/security/tests/test_runtime_http.py -q
```

Expected: all pass; remote fallback fake vectors remain non-cacheable and safety/response errors never fall back.

- [x] **Step 6: Commit**

```powershell
git add backend/app/services/system/embedding.py backend/app/services/system/tests/test_embedding_security.py backend/app/security/runtime_http.py backend/app/security/tests/test_runtime_http.py backend/app/ai/tests/test_model_router_security.py
git commit -m "fix(embedding): share timeout across chunk retries"
```

---

### Task 6: Add real-content idle windows and a 600-second stream hard deadline

**Files:**
- Modify: `backend/app/security/deadline.py`
- Modify: `backend/app/security/tests/test_deadline.py`
- Modify: `backend/app/security/runtime_http.py:350-510`
- Modify: `backend/app/security/tests/test_runtime_http.py:1304-1958`

**Interfaces:**
- Produces: `StreamBudget.from_timeouts(idle_timeout, *, hard_timeout=600.0, started_at=None, clock=time.monotonic)`.
- Produces: `StreamBudget.remaining()`, `phase_timeout(limit=None)`, `mark_content()`, and `content_started`.
- Transitional stream input: optional `budget: StreamBudget`; old idle/total arguments remain only until Task 7 migrates the router.

- [x] **Step 1: Write failing `StreamBudget` tests**

```python
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
    clock.now = 170.0  # local consumer work; under the 600-second hard limit
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
```

- [x] **Step 2: Run budget tests and verify RED**

```powershell
& $PYTHON -m pytest app/security/tests/test_deadline.py -q -k "stream_ or real_content"
```

Expected: `StreamBudget` is missing.

- [x] **Step 3: Implement `StreamBudget`**

```python
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
```

- [x] **Step 4: Write failing guarded-stream tests**

Add tests showing blocking DNS and response headers consume the initial idle window, empty/SSE-control lines do not refresh it unless the caller calls `mark_content()`, local consumer delay does not start a new idle window until reading resumes, and hard deadline closes once.

```python
@pytest.mark.asyncio
async def test_stream_protocol_lines_cannot_refresh_idle_budget() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(3.0, clock=clock)
    stream = AdvancingAsyncStream(
        clock,
        lines=[(b": heartbeat\n", 1.0), (b"\n", 1.0), (b": again\n", 1.1)],
    )
    client, _, _ = _runtime_client("async", stream)
    with pytest.raises(OutboundRequestError) as exc_info:
        async for _ in client.astream_lines(
            "https://public.example/v1",
            request_target="/chat/completions",
            headers={"Authorization": "Bearer test-sentinel"},
            json_body={"model": "test", "messages": [], "stream": True},
            allow_local=False,
            max_bytes=1024,
            max_event_bytes=256,
            budget=budget,
        ):
            pass
    assert exc_info.value.code == "outbound_timeout"
    assert stream.close_count == 1
```

- [x] **Step 5: Replace the stream's independent deadlines with `StreamBudget`**

Use the shared bounded runner for DNS; pass the stream budget into `PinnedAsyncTransport`; call `budget.phase_timeout()` before response headers and every raw `__anext__()`. `SafeRuntimeClient` never calls `mark_content()` because it cannot distinguish provider content from protocol lines. The router owns that action in Task 7.

Keep `asyncio.CancelledError` propagation and generator cleanup. Map `DeadlineExpired`, built-in `TimeoutError`, HTTPX/httpcore timeouts to fixed `outbound_timeout`.

- [x] **Step 6: Run deadline and runtime-stream tests**

```powershell
& $PYTHON -m pytest app/security/tests/test_deadline.py app/security/tests/test_runtime_http.py -q
```

Expected: all pass, including existing byte/event limits, log-context restoration, cross-task continuation, early close, cancellation, and error redaction.

- [x] **Step 7: Commit**

```powershell
git add backend/app/security/deadline.py backend/app/security/tests/test_deadline.py backend/app/security/runtime_http.py backend/app/security/tests/test_runtime_http.py
git commit -m "fix(security): enforce stream idle and hard budgets"
```

---

### Task 7: Publish explicit stream interruption states from both router streams

**Files:**
- Modify: `backend/app/ai/model_router.py:755-1041,1513-1915`
- Modify: `backend/app/ai/tests/test_model_router_security.py`
- Modify: `backend/app/security/runtime_http.py` (remove transitional stream arguments)
- Modify: recording stream client in router tests

**Interfaces:**
- Consumes: `StreamBudget` and `SafeRuntimeClient.astream_lines(base_url: str, *, request_target: str, headers: Mapping[str, str], json_body: Mapping[str, Any], allow_local: bool, budget: StreamBudget, max_bytes: int, max_event_bytes: int)`.
- Produces: optional keyword-only `budget: StreamBudget | None = None` on `astream()` and `astream_capability()`.
- Produces: terminal status `{type: "status", state: "interrupted", reason: "outbound_timeout", partial: True}` after partial timeout.
- Produces: one logical request statistic: completed is success, any outbound deadline is timeout, other terminal error is error, and cancellation/early close is cancelled.
- Preserves: cancellation propagation, provider parsing, no stream retry, redacted error events, and cleanup.

- [x] **Step 1: Write failing tests for both stream entry points**

Parameterize over `astream` and `astream_capability`:

```python
@pytest.mark.parametrize("entry", ["template", "capability"])
def test_partial_timeout_emits_interrupted_without_completed(entry: str) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = [_valid_stream_line(entry)]
    runtime_client.stream_error = OutboundRequestError(
        "outbound_timeout", 504, PUBLIC_TIMEOUT
    )
    router = _remote_router(runtime_client)
    events = asyncio.run(_collect_router_stream(router, entry))
    assert any(event == _expected_stream_content(entry) for event in events)
    terminals = [e for e in events if isinstance(e, dict) and e.get("state") in {"completed", "interrupted"}]
    assert terminals == [{
        "type": "status",
        "state": "interrupted",
        "capability": "generate",
        "reason": "outbound_timeout",
        "partial": True,
        "timestamp": terminals[0]["timestamp"],
    }]
    diagnostics = router.get_diagnostics()
    assert diagnostics["total_timeouts"] == 1
    assert diagnostics["request_stats"]["generate"]["success"] == 0


def test_timeout_before_content_emits_one_error() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_error = OutboundRequestError(
        "outbound_timeout", 504, PUBLIC_TIMEOUT
    )
    router = _remote_router(runtime_client)
    events = asyncio.run(_collect_router_stream(router, "template"))
    errors = [
        event for event in events
        if isinstance(event, dict) and event.get("type") == "error"
    ]
    assert [(event["code"], event["message"]) for event in errors] == [
        ("outbound_timeout", PUBLIC_TIMEOUT)
    ]
    assert not any(
        isinstance(event, dict)
        and event.get("state") in {"completed", "interrupted"}
        for event in events
    )
```

- [x] **Step 2: Run new stream-router tests and verify RED**

```powershell
& $PYTHON -m pytest app/ai/tests/test_model_router_security.py -q -k "partial_timeout or timeout_before_content"
```

Expected: current router emits a generic error after partial output and hard-codes 120/600 in its call.

- [x] **Step 3: Create the stream budget before queueing**

Record `started_at` before request preparation. Resolve idle timeout from capability override or global router timeout and create `StreamBudget.from_timeouts(idle, hard_timeout=600.0, started_at=started_at)` unless supplied. Acquire/release the router semaphore with `budget.phase_timeout()` just like Task 4.

- [x] **Step 4: Refresh only on parsed, non-empty model content**

Immediately before yielding each real content string in every OpenAI, Anthropic, and Google parsing branch:

```python
if content:
    effective_budget.mark_content()
    if first_chunk:
        yield self._stream_status_event(capability, "receiving")
        first_chunk = False
    yield content
```

Do not call `mark_content()` for response headers, local status events, SSE comments, empty data, malformed fragments, or upstream error objects.

- [x] **Step 5: Emit mutually exclusive terminal states**

```python
except OutboundRequestError as exc:
    if exc.code == "outbound_timeout" and effective_budget.content_started:
        yield self._stream_status_event(
            capability,
            "interrupted",
            reason=exc.code,
            partial=True,
        )
    else:
        yield self._stream_error_event(
            capability, exc.public_message, code=exc.code
        )
    return
```

Only the normal end-of-stream path emits `completed`. Re-raise `asyncio.CancelledError`; the owner of cancellation publishes `cancelled` outside the generator.

At logical stream entry, initialize the same request-stat record used by normal async calls. Reuse Task 4's idempotent `_finish_request_stats()` on every terminal path: `completed -> success`, timeout before content or `interrupted -> timeout`, protocol/upstream error -> error, and `CancelledError`/`GeneratorExit` -> cancelled. Finalize the statistic immediately before yielding a terminal event so a consumer that closes after receiving it cannot relabel that outcome. Extend the existing stream cancellation and early-`aclose()` tests to assert cancellation increments once and timeout remains zero.

- [x] **Step 6: Remove transitional stream timeout arguments**

Require `budget` on `SafeRuntimeClient.astream_lines`, remove `idle_timeout`/`total_timeout`, and update router recording fakes to assert identity with the supplied `StreamBudget`.

- [x] **Step 7: Run router and guarded-stream suites**

```powershell
& $PYTHON -m pytest app/ai/tests/test_model_router_security.py app/security/tests/test_runtime_http.py -q
```

Expected: all pass; no stream retries and cancellation/close tests remain green.

- [x] **Step 8: Commit**

```powershell
git add backend/app/ai/model_router.py backend/app/ai/tests/test_model_router_security.py backend/app/security/runtime_http.py backend/app/security/tests/test_runtime_http.py
git commit -m "fix(ai): publish explicit stream interruption states"
```

---

### Task 8: Remove competing ordinary heartbeat timeouts

**Files:**
- Create: `backend/app/ai/tests/test_streaming_helper.py`
- Modify: `backend/app/ai/streaming_helper.py:261-470`
- Modify: `backend/app/ai/model_router.py:2109-2205`
- Modify: `backend/app/services/analytics/critical_analyzer.py`
- Modify: `backend/app/services/analytics/focus_processor.py`
- Modify: `backend/app/services/species/hybridization.py:410-450,1250-1285`
- Modify: `backend/app/services/species/speciation.py:1378-1405,2180-2230,6635-6660`

**Interfaces:**
- Consumes: normal router methods that already enforce their configured budget.
- Produces: one `invoke_with_heartbeat()` definition using `router.ainvoke()` and one `acall_with_heartbeat()` using `router.acall_capability()`.
- Preserves: heartbeats and event callback shapes; removes wrapper `timeout` and `staggered_gather.task_timeout`.

- [x] **Step 1: Write failing helper tests**

```python
@pytest.mark.asyncio
async def test_invoke_heartbeat_does_not_wrap_router_in_another_timeout() -> None:
    router = RecordingRouter()
    events: list[str] = []
    result = await invoke_with_heartbeat(
        router,
        "generate",
        {"name": "elm"},
        heartbeat_interval=0.001,
        event_callback=lambda event, *_: events.append(event),
    )
    assert result == {"content": {"ok": True}}
    assert router.ainvoke_calls == [("generate", {"name": "elm"})]
    assert router.invoke_calls == []
    assert events[0] == "ai_request_start"
    assert events[-1] == "ai_request_complete"


def test_streaming_helper_defines_invoke_wrapper_once() -> None:
    source = Path(streaming_helper.__file__).read_text(encoding="utf-8")
    assert source.count("async def invoke_with_heartbeat(") == 1
```

Also add a cancellation test proving the heartbeat task is closed and `CancelledError` propagates.

- [x] **Step 2: Run helper tests and verify RED**

```powershell
& $PYTHON -m pytest app/ai/tests/test_streaming_helper.py -q
```

Expected: the active duplicate wrapper uses `asyncio.to_thread(router.invoke)` and the source contains two definitions.

- [x] **Step 3: Keep heartbeats, remove request ownership**

Delete the duplicate wrapper. `invoke_with_heartbeat` calls `await router.ainvoke(capability, payload)` directly; `acall_with_heartbeat` calls `await router.acall_capability(capability, messages, response_format)` directly. Remove their `timeout` parameters and outer `asyncio.wait_for`; preserve start/heartbeat/complete/error events and cleanup. Catch `asyncio.CancelledError` separately, emit `ai_request_cancelled`, then re-raise.

- [x] **Step 4: Remove the batch utility's competing timer**

Delete `task_timeout` from `staggered_gather()` and replace `await asyncio.wait_for(coro, timeout=task_timeout)` with `await coro`. Keep concurrency, stagger delay, progress events, exception capture, and heartbeat behavior. Remove the `ai_parallel_task_timeout` branch; child logical requests now report their own bounded result.

- [x] **Step 5: Migrate all ordinary wrapper call sites**

Remove `timeout=30/45/60/90` arguments from critical, focus, hybridization, speciation, and endosymbiosis calls. Do not alter their capability names, payloads, callbacks, fallbacks, or batch concurrency values.

Run:

```powershell
rg -n "invoke_with_heartbeat|acall_with_heartbeat|task_timeout" backend/app
```

Expected: no call passes `timeout=` or `task_timeout=`; each helper has one definition.

- [x] **Step 6: Run helper, router, and affected service tests**

```powershell
& $PYTHON -m pytest app/ai/tests/test_streaming_helper.py app/ai/tests/test_model_router_security.py app/services/analytics app/services/species -q
```

Expected: all selected tests pass. If this broad selection exposes an unrelated GPU-only test, record the existing skip rather than weakening the new tests.

- [x] **Step 7: Commit**

```powershell
git add backend/app/ai/streaming_helper.py backend/app/ai/model_router.py backend/app/ai/tests/test_streaming_helper.py backend/app/services/analytics/critical_analyzer.py backend/app/services/analytics/focus_processor.py backend/app/services/species/hybridization.py backend/app/services/species/speciation.py
git commit -m "refactor(ai): remove duplicate heartbeat timeouts"
```

---

### Task 9: Make stream helpers and business consumers reject partial success

**Files:**
- Modify: `backend/app/ai/streaming_helper.py:1-260`
- Modify: `backend/app/ai/tests/test_streaming_helper.py`
- Modify: `backend/app/services/analytics/report_builder.py:50-130`
- Modify: `backend/app/services/analytics/report_builder_v2.py:714-805`
- Modify: `backend/app/services/species/speciation.py:1985-2030`
- Create: `backend/app/services/analytics/tests/__init__.py`
- Create: `backend/app/services/analytics/tests/test_report_builder_streaming.py`
- Create: `backend/app/services/species/tests/test_speciation_streaming.py`

**Interfaces:**
- Produces: immutable `StreamOutcome(content: str, completed: bool, reason: str | None)`.
- Produces: `stream_call_with_heartbeat(router, capability, messages, response_format=None, task_name="AI处理", heartbeat_interval=1.5, event_callback=None, chunk_callback=None) -> StreamOutcome`.
- Produces: `stream_invoke_with_heartbeat(router, capability, payload, task_name="AI处理", heartbeat_interval=2.0, event_callback=None, chunk_callback=None) -> StreamOutcome`.
- Preserves: already-delivered chunks and heartbeat events; complete-only JSON parsing/final persistence.

- [x] **Step 1: Write failing helper outcome tests**

```python
@pytest.mark.asyncio
async def test_partial_stream_returns_incomplete_outcome_and_keeps_chunks() -> None:
    router = StreamRouter([
        {"type": "status", "state": "receiving"},
        '{"species":',
        {"type": "status", "state": "interrupted", "reason": "outbound_timeout", "partial": True},
    ])
    shown: list[str] = []
    events: list[str] = []
    outcome = await stream_invoke_with_heartbeat(
        router,
        "speciation",
        {},
        chunk_callback=lambda chunk: shown.append(chunk),
        event_callback=lambda event, *_: events.append(event),
    )
    assert outcome == StreamOutcome(
        content='{"species":', completed=False, reason="outbound_timeout"
    )
    assert shown == ['{"species":']
    assert "ai_stream_interrupted" in events
    assert "ai_stream_complete" not in events


@pytest.mark.asyncio
async def test_complete_stream_returns_complete_outcome() -> None:
    router = StreamRouter([
        {"type": "status", "state": "receiving"},
        '{"ok":true}',
        {"type": "status", "state": "completed"},
    ])
    outcome = await stream_invoke_with_heartbeat(
        router,
        "generate",
        {},
    )
    assert outcome == StreamOutcome(
        content='{"ok":true}', completed=True, reason=None
    )
```

- [x] **Step 2: Run helper outcome tests and verify RED**

```powershell
& $PYTHON -m pytest app/ai/tests/test_streaming_helper.py -q -k "outcome or partial_stream"
```

Expected: helpers return strings/dicts and currently treat partial content as success.

- [x] **Step 3: Implement `StreamOutcome` and one collector**

```python
@dataclass(frozen=True)
class StreamOutcome:
    content: str
    completed: bool
    reason: str | None = None


async def _collect_stream(
    iterator: AsyncIterator[Any],
    *,
    task_name: str,
    emit_event: Callable[[str, str], None],
    chunk_callback: Callable[[str], Awaitable[None] | None] | None,
) -> StreamOutcome:
    chunks: list[str] = []
    terminal: str | None = None
    reason: str | None = None
    async for item in iterator:
        if isinstance(item, str):
            if item:
                chunks.append(item)
                await _maybe_call_chunk_callback(chunk_callback, item)
            continue
        state = item.get("state")
        if state == "completed":
            terminal = "completed"
        elif state == "interrupted":
            terminal = "interrupted"
            reason = item.get("reason") or "outbound_timeout"
        elif item.get("type") == "error":
            terminal = "error"
            reason = item.get("code") or "stream_error"
    completed = terminal == "completed"
    return StreamOutcome("".join(chunks), completed, None if completed else reason)
```

The public helpers only create the correct router iterator, heartbeat/event callbacks, and delegate to `_collect_stream`. They do not own idle or total timers and do not parse JSON.

- [x] **Step 4: Migrate the batch speciation caller**

Remove `idle_timeout=90`. If `batch_result` is a `StreamOutcome` and `completed` is true, parse `batch_result.content` as JSON and require a dict. Otherwise set `{"_timeout": True, "_use_fallback": True}` for timeout interruption or the existing error fallback. Never include the partial content or raw error in the saved fallback object.

- [x] **Step 5: Migrate both report builders**

Replace direct router loops and their 20/30/60-second timers with the appropriate helper and `chunk_callback=stream_callback`. Use AI narrative only when `outcome.completed` and the complete stripped content passes the existing minimum-length rule. When incomplete, keep already sent callback text visible but build and return the existing complete structured fallback report.

For `report_builder_v2.py`, remove the incorrect `item.get("status")` handling; the helper is the single consumer of router `state` events.

- [x] **Step 6: Add focused business regression tests**

Test each report builder with a helper/router that yields a 100-character partial narrative then `interrupted`. Assert the chunk callback received it, the returned V1 report contains `**环境压力**`, the returned V2 report contains `## 🕐 第`, and neither returned report contains the partial narrative. Test speciation with partial JSON and assert the result is exactly `{"_timeout": True, "_use_fallback": True}` before any allowed `_endo_overrides` merge; monkeypatch `json.loads` for that partial string to fail the test if it is called.

- [x] **Step 7: Run helper and affected business tests**

```powershell
& $PYTHON -m pytest app/ai/tests/test_streaming_helper.py app/services/analytics/tests/test_report_builder_streaming.py app/services/species/tests/test_speciation_streaming.py -q
```

Expected: all selected tests pass; partial content is display-only.

- [x] **Step 8: Commit**

```powershell
git add backend/app/ai/streaming_helper.py backend/app/ai/tests/test_streaming_helper.py backend/app/services/analytics/report_builder.py backend/app/services/analytics/report_builder_v2.py backend/app/services/species/speciation.py backend/app/services/analytics/tests/__init__.py backend/app/services/analytics/tests/test_report_builder_streaming.py backend/app/services/species/tests/test_speciation_streaming.py
git commit -m "fix(ai): reject incomplete streamed business results"
```

---

### Task 10: Show stream interruption in the UI and document timeout semantics

**Files:**
- Create: `frontend/src/components/TurnProgressOverlay.test.tsx`
- Modify: `frontend/src/components/TurnProgressOverlay.tsx:350-470`
- Modify: `frontend/src/components/SettingsDrawer/sections/PerformanceSection.tsx:380-400`
- Modify: `docs/api-guides/modules/config-ui/api-connectivity.md:135-155`
- Modify: `docs/api-guides/modules/config-ui/ui-config.md`

**Interfaces:**
- Consumes: backend event `ai_stream_interrupted` with a redacted message/task.
- Produces: warning connection state and exact user text `AI 生成中断，已使用备用结果`.
- Preserves: already displayed stream text and does not increment AI successful completion.

- [x] **Step 1: Write the failing overlay test**

Mock `connectToEventStream` and capture its callback:

```tsx
it("shows interrupted stream as fallback warning without successful completion", async () => {
  render(<TurnProgressOverlay />);
  act(() => {
    emitEvent({
      type: "ai_stream_interrupted",
      task: "回合报告",
      message: "AI 生成中断，已使用备用结果",
      category: "AI",
    });
  });
  expect(await screen.findByText(/AI 生成中断，已使用备用结果/)).toBeInTheDocument();
  expect(screen.queryByText(/✅ 完成: 回合报告/)).not.toBeInTheDocument();
});
```

The test mock returns an object with `close: vi.fn()` cast as `EventSource`, and resets the captured callback after each test.

- [x] **Step 2: Run the UI test and verify RED**

```powershell
npm run test:run -- src/components/TurnProgressOverlay.test.tsx
```

Expected: no interruption handler or warning text exists.

- [x] **Step 3: Implement the interruption branch**

Place it beside existing stream completion/error handling:

```tsx
if (event.type === "ai_stream_interrupted") {
  setLastAIActivity(Date.now());
  setConnectionStatus("warning");
  setAIProgress(prev => prev ? {
    ...prev,
    current_task: event.message || "AI 生成中断，已使用备用结果",
    last_activity: Date.now(),
  } : {
    total: 1,
    completed: 0,
    current_task: event.message || "AI 生成中断，已使用备用结果",
    last_activity: Date.now(),
  });
  return;
}
```

Do not clear `streamingText`; do not increment `completed`; do not schedule a return to `receiving`.

- [x] **Step 4: Clarify existing setting copy and docs**

Performance copy must say: ordinary calls use an end-to-end total timeout; streamed calls use it as the maximum wait for new AI content and always stop after 10 minutes. Update connectivity docs with queue/DNS/retry inclusion, 600-second stream hard limit, partial-display/complete-fallback behavior, and cancellation distinction. Do not add a new setting or expose internal URLs/errors.

- [x] **Step 5: Run focused and full frontend gates**

```powershell
npm run test:run -- src/components/TurnProgressOverlay.test.tsx src/components/SettingsDrawer/sections/PerformanceSection.test.tsx
npm run test:run
npm run lint
npx tsc --noEmit
npm run build
```

Expected: Vitest passes, ESLint stays within `--max-warnings=162`, TypeScript exits 0, and the production build succeeds.

- [x] **Step 6: Commit**

```powershell
git add frontend/src/components/TurnProgressOverlay.tsx frontend/src/components/TurnProgressOverlay.test.tsx frontend/src/components/SettingsDrawer/sections/PerformanceSection.tsx docs/api-guides/modules/config-ui/api-connectivity.md docs/api-guides/modules/config-ui/ui-config.md
git commit -m "feat(ui): explain interrupted AI stream fallback"
```

---

### Task 11: Complete Phase 3B verification and publication

**Files:**
- Modify: `docs/superpowers/plans/2026-07-19-phase-3b-end-to-end-time-budget.md` only to mark executed checkboxes after evidence exists.

**Interfaces:**
- Produces: reviewed Phase 3B commits pushed to the existing fork branch and reflected in PR #15 without changing Draft status.

- [x] **Step 1: Run the complete focused Phase 3B backend gate**

```powershell
& $PYTHON -m pytest app/security/tests/test_deadline.py app/security/tests/test_bounded_runner.py app/security/tests/test_safe_http.py app/security/tests/test_pinned_transport.py app/security/tests/test_runtime_http.py app/ai/tests/test_model_router_security.py app/ai/tests/test_streaming_helper.py app/services/system/tests/test_embedding_security.py app/services/analytics/tests/test_report_builder_streaming.py app/services/species/tests/test_speciation_streaming.py -q
```

Expected: all pass; no real network; no secret sentinel in output.

- [x] **Step 2: Run the complete backend suite**

```powershell
& $PYTHON -m pytest -q
```

Expected: zero failures and no increase from the existing skip baseline.

- [x] **Step 3: Re-run complete frontend gates**

```powershell
npm run test:run
npm run lint
npx tsc --noEmit
npm run build
```

Expected: zero test/build/type failures and no increase over 162 allowed lint warnings.

- [x] **Step 4: Audit timeout ownership and security invariants**

```powershell
rg -n "read_timeout=|idle_timeout=|total_timeout=|asyncio\.wait_for|asyncio\.timeout|task_timeout|chunk_timeout" backend/app
rg -n "api_key|Authorization|request_target|base_url" backend/app/security backend/app/ai backend/app/services/system/embedding.py
git diff --check
git status --short
```

Review every hit. Confirm remaining waits are the new deadline enforcement or unrelated business orchestration, no competing AI timeout remains, stream heartbeats cannot refresh idle windows, and logs/events never expose credentials, full Google query targets, bodies, or upstream exception text.

- [x] **Step 5: Review exact Phase 3B diff**

```powershell
git diff c48983a..HEAD --stat
git diff c48983a..HEAD
```

Expected: only Phase 3B time-budget, stream outcome, tests, UI copy, and docs changes. No database, save, gameplay, dependency, provider-selection, retry-count, or PR-state change.

**Final verification evidence (2026-07-19, HEAD `7010889`):**

- Phase 3B focused backend gate: `575 passed`, `1` pre-existing warning.
- Complete backend suite: `1278 passed`, `2 skipped`, `45 warnings`; skip and warning baselines did not increase.
- Complete frontend gate: `85 passed`; ESLint `0 errors / 162 warnings`; TypeScript and production build exited `0`. The final backend-only fix changed no frontend files.
- Direct runtime/router/Embedding compatibility gate: `469 passed`; exact final-boundary regressions: `17 passed`.
- Timeout/security audit: no competing AI wrapper remained; the ten internal-budget stages were verified; dynamic raw-exception leak checks were all false; credential, Google query-target, request-body, and upstream-exception sinks were not found.
- Exact diff review: no database, save format, gameplay formula, dependency, provider-selection, retry-count, backoff-formula, or PR-state change.
- Final independent review: `0 Critical`, `0 Important`; publication approved with non-blocking Minor notes recorded in the SDD ledger/report.

- [x] **Step 6: Mark executed plan checkboxes and commit verification evidence**

Only after Steps 1-5 pass, change completed `- [ ]` markers to `- [x]`, record exact pass/skip/warning counts in the final verification task, then:

```powershell
git add docs/superpowers/plans/2026-07-19-phase-3b-end-to-end-time-budget.md
git commit -m "docs: record Phase 3B verification"
```

- [x] **Step 7: Push and verify PR #15**

Push `phase-2c-outbound-url-security` to the existing `fork` remote. Verify PR #15 points at the pushed head, remains Draft, and its description identifies the cumulative Phase 1 through Phase 3B scope. Do not merge or mark ready for review without a separate user decision.
