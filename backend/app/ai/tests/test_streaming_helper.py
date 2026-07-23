from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any

import pytest

from app.ai import streaming_helper
from app.ai.model_router import staggered_gather
from app.ai.streaming_helper import (
    acall_with_heartbeat,
    invoke_with_heartbeat,
    stream_call_with_heartbeat,
    stream_invoke_with_heartbeat,
)


class StreamRouter:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    async def astream(self, capability: str, payload: dict[str, Any]):
        for item in self.items:
            yield item

    async def astream_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ):
        for item in self.items:
            yield item


@pytest.mark.asyncio
async def test_partial_stream_returns_incomplete_outcome_and_keeps_chunks() -> None:
    router = StreamRouter(
        [
            {"type": "status", "state": "receiving"},
            '{"species":',
            {
                "type": "status",
                "state": "interrupted",
                "reason": "outbound_timeout",
                "partial": True,
            },
        ]
    )
    shown: list[str] = []
    events: list[str] = []

    outcome = await stream_invoke_with_heartbeat(
        router,
        "speciation",
        {},
        chunk_callback=lambda chunk: shown.append(chunk),
        event_callback=lambda event, *_: events.append(event),
    )

    assert outcome == streaming_helper.StreamOutcome(
        content='{"species":', completed=False, reason="outbound_timeout"
    )
    assert shown == ['{"species":']
    assert "ai_stream_interrupted" in events
    assert "ai_stream_complete" not in events


@pytest.mark.asyncio
async def test_complete_stream_returns_complete_outcome() -> None:
    router = StreamRouter(
        [
            {"type": "status", "state": "receiving"},
            '{"ok":true}',
            {"type": "status", "state": "completed"},
        ]
    )

    outcome = await stream_invoke_with_heartbeat(router, "generate", {})

    assert outcome == streaming_helper.StreamOutcome(
        content='{"ok":true}', completed=True, reason=None
    )


@pytest.mark.asyncio
async def test_capability_stream_returns_complete_outcome_and_keeps_chunks() -> None:
    router = StreamRouter(
        [
            {"type": "status", "state": "connected"},
            "complete narrative",
            {"type": "status", "state": "completed"},
        ]
    )
    shown: list[str] = []

    outcome = await stream_call_with_heartbeat(
        router,
        "turn_report",
        [{"role": "user", "content": "Write a report"}],
        chunk_callback=lambda chunk: shown.append(chunk),
    )

    assert outcome == streaming_helper.StreamOutcome(
        content="complete narrative", completed=True, reason=None
    )
    assert shown == ["complete narrative"]


@pytest.mark.asyncio
async def test_stream_collector_closes_router_iterator_after_terminal_event() -> None:
    class ClosingRouter(StreamRouter):
        def __init__(self) -> None:
            super().__init__([])
            self.closed = False

        async def astream(self, capability: str, payload: dict[str, Any]):
            try:
                yield "done"
                yield {"type": "status", "state": "completed"}
                yield "must not be collected"
            finally:
                self.closed = True

    router = ClosingRouter()

    outcome = await stream_invoke_with_heartbeat(router, "generate", {})

    assert outcome.content == "done"
    assert router.closed is True


@pytest.mark.asyncio
async def test_stream_chunk_callback_awaits_any_awaitable() -> None:
    router = StreamRouter(
        ["chunk", {"type": "status", "state": "completed"}]
    )
    callback_future: asyncio.Future[None] | None = None

    def callback(chunk: str) -> asyncio.Future[None]:
        nonlocal callback_future
        callback_future = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(callback_future.set_result, None)
        return callback_future

    await stream_invoke_with_heartbeat(
        router,
        "generate",
        {},
        chunk_callback=callback,
    )

    assert callback_future is not None
    assert callback_future.done()


@pytest.mark.asyncio
async def test_stream_close_error_does_not_replace_terminal_outcome() -> None:
    class CloseErrorIterator:
        def __init__(self) -> None:
            self.items = iter(
                ["done", {"type": "status", "state": "completed"}]
            )

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.items)
            except StopIteration:
                raise StopAsyncIteration from None

        async def aclose(self) -> None:
            raise RuntimeError("secondary close failure")

    class CloseErrorRouter(StreamRouter):
        def astream(self, capability: str, payload: dict[str, Any]):
            return CloseErrorIterator()

    outcome = await stream_invoke_with_heartbeat(
        CloseErrorRouter([]),
        "generate",
        {},
    )

    assert outcome == streaming_helper.StreamOutcome(
        content="done", completed=True, reason=None
    )


class RecordingRouter:
    def __init__(self) -> None:
        self.ainvoke_calls: list[tuple[str, dict[str, Any]]] = []
        self.ainvoke_tasks: list[asyncio.Task[Any] | None] = []
        self.invoke_calls: list[tuple[str, dict[str, Any]]] = []
        self.acall_calls: list[
            tuple[str, list[dict[str, str]], dict[str, Any] | None]
        ] = []
        self.acall_tasks: list[asyncio.Task[Any] | None] = []

    async def ainvoke(self, capability: str, payload: dict[str, Any]) -> dict:
        self.ainvoke_calls.append((capability, payload))
        self.ainvoke_tasks.append(asyncio.current_task())
        return {"content": {"ok": True}}

    def invoke(self, capability: str, payload: dict[str, Any]) -> dict:
        self.invoke_calls.append((capability, payload))
        return {"content": {"wrong_route": True}}

    async def acall_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None,
    ) -> str:
        self.acall_calls.append((capability, messages, response_format))
        self.acall_tasks.append(asyncio.current_task())
        return "ok"


class BlockingRouter(RecordingRouter):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def acall_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None,
    ) -> str:
        self.acall_calls.append((capability, messages, response_format))
        self.acall_tasks.append(asyncio.current_task())
        self.started.set()
        await self.release.wait()
        return "ok"


@pytest.mark.asyncio
async def test_invoke_heartbeat_does_not_wrap_router_in_another_timeout() -> None:
    router = RecordingRouter()
    events: list[str] = []
    caller_task = asyncio.current_task()

    result = await invoke_with_heartbeat(
        router,
        "generate",
        {"name": "elm"},
        heartbeat_interval=0.001,
        event_callback=lambda event, *_: events.append(event),
    )

    assert result == {"content": {"ok": True}}
    assert router.ainvoke_calls == [("generate", {"name": "elm"})]
    assert router.ainvoke_tasks == [caller_task]
    assert router.invoke_calls == []
    assert events[0] == "ai_request_start"
    assert events[-1] == "ai_request_complete"


@pytest.mark.asyncio
async def test_acall_heartbeat_awaits_router_directly() -> None:
    router = RecordingRouter()
    messages = [{"role": "user", "content": "Name a tree"}]
    response_format = {"type": "json_object"}
    caller_task = asyncio.current_task()

    result = await acall_with_heartbeat(
        router,
        "generate",
        messages,
        response_format,
        heartbeat_interval=0.001,
    )

    assert result == "ok"
    assert router.acall_calls == [("generate", messages, response_format)]
    assert router.acall_tasks == [caller_task]


def test_ordinary_heartbeat_helpers_do_not_accept_wrapper_timeouts() -> None:
    assert "timeout" not in inspect.signature(invoke_with_heartbeat).parameters
    assert "timeout" not in inspect.signature(acall_with_heartbeat).parameters


def test_streaming_helper_defines_invoke_wrapper_once() -> None:
    source = Path(streaming_helper.__file__).read_text(encoding="utf-8")
    assert source.count("async def invoke_with_heartbeat(") == 1


@pytest.mark.asyncio
async def test_acall_heartbeat_cancellation_closes_heartbeat_and_propagates() -> None:
    router = BlockingRouter()
    events: list[str] = []
    request_task = asyncio.create_task(
        acall_with_heartbeat(
            router,
            "generate",
            [{"role": "user", "content": "Name a tree"}],
            heartbeat_interval=0.001,
            event_callback=lambda event, *_: events.append(event),
        )
    )
    await router.started.wait()

    request_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request_task
    await asyncio.sleep(0)

    assert events[0] == "ai_request_start"
    assert events[-1] == "ai_request_cancelled"
    assert "ai_request_complete" not in events
    assert "ai_request_error" not in events
    assert not any(
        "send_heartbeats" in task.get_coro().__qualname__
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task()
    )


@pytest.mark.asyncio
async def test_staggered_gather_leaves_child_timeout_as_child_error() -> None:
    child_timeout = TimeoutError("child owns its deadline")
    events: list[str] = []

    async def timed_out_child() -> None:
        raise child_timeout

    results = await staggered_gather(
        [timed_out_child()],
        interval=0,
        max_concurrent=1,
        task_name="child",
        event_callback=lambda event, *_: events.append(event),
    )

    assert results == [child_timeout]
    assert "ai_parallel_task_error" in events
    assert "ai_parallel_task_timeout" not in events
    assert "task_timeout" not in inspect.signature(staggered_gather).parameters


_SECRET_SENTINEL = "DO_NOT_EXPOSE_HELPER_EXCEPTION_SENTINEL"


class RaisingRouter:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def ainvoke(self, capability: str, payload: dict[str, Any]) -> dict:
        raise self.error

    async def acall_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None,
    ) -> str:
        raise self.error

    async def astream(self, capability: str, payload: dict[str, Any]):
        raise self.error
        yield  # pragma: no cover - keeps this an async generator

    async def astream_capability(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ):
        raise self.error
        yield  # pragma: no cover - keeps this an async generator


@pytest.mark.parametrize("helper_name", ["invoke", "acall"])
@pytest.mark.asyncio
async def test_ordinary_helper_redacts_exception_from_logs_and_events(
    helper_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = RuntimeError(_SECRET_SENTINEL)
    router = RaisingRouter(error)
    events: list[tuple[str, str, str]] = []
    caplog.set_level(logging.DEBUG, logger="app.ai.streaming_helper")

    with pytest.raises(RuntimeError) as raised:
        if helper_name == "invoke":
            await invoke_with_heartbeat(
                router,
                "generate",
                {},
                event_callback=lambda *event: events.append(event),
            )
        else:
            await acall_with_heartbeat(
                router,
                "generate",
                [],
                event_callback=lambda *event: events.append(event),
            )

    assert raised.value is error
    assert [event for event in events if event[0] == "ai_request_error"]
    assert _SECRET_SENTINEL not in caplog.text
    assert all(_SECRET_SENTINEL not in message for _, message, _ in events)


@pytest.mark.parametrize("helper_name", ["stream_invoke", "stream_call"])
@pytest.mark.asyncio
async def test_stream_helper_redacts_exception_and_preserves_rethrow(
    helper_name: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    error = RuntimeError(_SECRET_SENTINEL)
    router = RaisingRouter(error)
    events: list[tuple[str, str, str]] = []
    caplog.set_level(logging.DEBUG, logger="app.ai.streaming_helper")

    with pytest.raises(RuntimeError) as raised:
        if helper_name == "stream_invoke":
            await stream_invoke_with_heartbeat(
                router,
                "generate",
                {},
                event_callback=lambda *event: events.append(event),
            )
        else:
            await stream_call_with_heartbeat(
                router,
                "generate",
                [],
                event_callback=lambda *event: events.append(event),
            )

    assert raised.value is error
    assert [event for event in events if event[0] == "ai_stream_error"]
    assert _SECRET_SENTINEL not in caplog.text
    assert all(_SECRET_SENTINEL not in message for _, message, _ in events)


@pytest.mark.asyncio
async def test_event_callback_failure_is_redacted_and_stream_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    router = StreamRouter(
        [
            {"type": "status", "state": "connected"},
            "done",
            {"type": "status", "state": "completed"},
        ]
    )
    caplog.set_level(logging.DEBUG, logger="app.ai.streaming_helper")

    def failing_callback(*_args: Any) -> None:
        raise RuntimeError(_SECRET_SENTINEL)

    outcome = await stream_call_with_heartbeat(
        router,
        "generate",
        [],
        event_callback=failing_callback,
    )

    assert outcome.completed is True
    assert outcome.content == "done"
    assert _SECRET_SENTINEL not in caplog.text
