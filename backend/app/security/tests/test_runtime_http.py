from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from ipaddress import ip_address
from typing import Any, Literal, cast
from urllib.parse import quote, urlencode

import httpcore
import httpx
import pytest

import app.security as security
import app.security.runtime_http as runtime_http
from app.security.bounded_runner import BoundedDaemonRunner
from app.security.deadline import DeadlineBudget, StreamBudget
from app.security.outbound_url import (
    OutboundRequestError,
    OutboundURLPolicy,
    ValidatedOutboundURL,
)
from app.security.runtime_http import (
    AI_JSON_MAX_BYTES,
    EMBEDDING_JSON_MAX_BYTES,
    RETRYABLE_OUTBOUND_CODES,
    STREAM_EVENT_MAX_BYTES,
    STREAM_MAX_BYTES,
    RuntimeTimeouts,
    SafeRuntimeClient,
)


Mode = Literal["sync", "async"]

INVALID_TARGETS = [
    "",
    "relative",
    "//evil.example/path",
    "https://evil.example/path",
    "/ok#fragment",
    "/bad\\path",
    "/bad path",
    "/bad\npath",
    "/forward/https://evil.example",
    "/forward?next=https://evil.example",
]
VALIDATED_BASE = "https://public.example/v1"
VALID_TARGET = "/chat/completions"
EXPECTED_FINAL_URL = "https://public.example/v1/chat/completions"


def _validated() -> ValidatedOutboundURL:
    return ValidatedOutboundURL(
        url=VALIDATED_BASE,
        scheme="https",
        hostname="public.example",
        port=443,
        resolved_ips=(ip_address("93.184.216.34"),),
        is_local=False,
    )


class RecordingPolicy:
    def __init__(
        self,
        *,
        result: ValidatedOutboundURL | None = None,
        error: OutboundRequestError | None = None,
    ) -> None:
        self.result = _validated() if result is None else result
        self.error = error
        self.calls: list[tuple[object, bool]] = []

    def validate(
        self,
        url: str,
        *,
        allow_local: bool,
    ) -> ValidatedOutboundURL:
        self.calls.append((url, allow_local))
        if self.error is not None:
            raise self.error
        return self.result


class ManualClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class AdvancingPolicy(RecordingPolicy):
    def __init__(self, clock: ManualClock, *, dns_seconds: float) -> None:
        super().__init__()
        self._clock = clock
        self._dns_seconds = dns_seconds

    def validate(
        self,
        url: str,
        *,
        allow_local: bool,
    ) -> ValidatedOutboundURL:
        self._clock.advance(self._dns_seconds)
        return super().validate(url, allow_local=allow_local)


_AUTO_CONTENT_LENGTH = object()


def _response_head(
    *,
    status: int = 200,
    body: bytes = b'{"ok":true}',
    headers: Mapping[str, str] | None = None,
    content_length: object = _AUTO_CONTENT_LENGTH,
) -> bytes:
    reasons = {
        200: "OK",
        201: "Created",
        204: "No Content",
        302: "Found",
        400: "Bad Request",
        500: "Internal Server Error",
    }
    lines = [f"HTTP/1.1 {status} {reasons.get(status, 'Status')}"]
    for key, value in (headers or {}).items():
        lines.append(f"{key}: {value}")
    if content_length is _AUTO_CONTENT_LENGTH:
        lines.append(f"Content-Length: {len(body)}")
    elif content_length is not None:
        lines.append(f"Content-Length: {content_length}")
    lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


class RecordingSyncStream(httpcore.NetworkStream):
    def __init__(
        self,
        *,
        body: bytes = b'{"ok":true}',
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        content_length: object = _AUTO_CONTENT_LENGTH,
        raw_head: bytes | None = None,
        body_chunk_size: int | None = None,
        read_error: Exception | None = None,
        write_error: Exception | None = None,
        tls_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self._head = bytearray(
            raw_head
            if raw_head is not None
            else _response_head(
                status=status,
                body=body,
                headers=headers,
                content_length=content_length,
            )
        )
        self._body = bytearray(body)
        self._body_chunk_size = body_chunk_size
        self.read_error = read_error
        self.write_error = write_error
        self.tls_error = tls_error
        self.close_error = close_error
        self.request_bytes = bytearray()
        self.body_bytes_returned = 0
        self.close_count = 0

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self._head:
            chunk = bytes(self._head[:max_bytes])
            del self._head[:max_bytes]
            return chunk
        if self.read_error is not None:
            raise self.read_error
        if not self._body:
            return b""
        size = min(max_bytes, len(self._body))
        if self._body_chunk_size is not None:
            size = min(size, self._body_chunk_size)
        chunk = bytes(self._body[:size])
        del self._body[:size]
        self.body_bytes_returned += len(chunk)
        return chunk

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.request_bytes.extend(buffer)
        if self.write_error is not None:
            raise self.write_error

    def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error

    def start_tls(
        self,
        ssl_context: Any,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        if self.tls_error is not None:
            raise self.tls_error
        return self


class AdvancingSyncStream(RecordingSyncStream):
    def __init__(
        self,
        clock: ManualClock,
        *,
        read_advances: list[float],
    ) -> None:
        super().__init__(body_chunk_size=6)
        self._clock = clock
        self._read_advances = iter(read_advances)

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if not self._head and self._body:
            self._clock.advance(next(self._read_advances))
        return super().read(max_bytes, timeout=timeout)


class RecordingAsyncStream(httpcore.AsyncNetworkStream):
    def __init__(
        self,
        *,
        body: bytes = b'{"ok":true}',
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        content_length: object = _AUTO_CONTENT_LENGTH,
        raw_head: bytes | None = None,
        body_chunk_size: int | None = None,
        read_error: Exception | None = None,
        write_error: Exception | None = None,
        tls_error: Exception | None = None,
        close_error: Exception | None = None,
        block_body: bool = False,
        body_read_delay: float = 0.0,
    ) -> None:
        self._head = bytearray(
            raw_head
            if raw_head is not None
            else _response_head(
                status=status,
                body=body,
                headers=headers,
                content_length=content_length,
            )
        )
        self._body = bytearray(body)
        self._body_chunk_size = body_chunk_size
        self.read_error = read_error
        self.write_error = write_error
        self.tls_error = tls_error
        self.close_error = close_error
        self.block_body = block_body
        self.body_read_delay = body_read_delay
        self.request_bytes = bytearray()
        self.body_bytes_returned = 0
        self.close_count = 0
        self.body_read_started = asyncio.Event()
        self._never_ready = asyncio.Event()

    async def read(
        self,
        max_bytes: int,
        timeout: float | None = None,
    ) -> bytes:
        if self._head:
            chunk = bytes(self._head[:max_bytes])
            del self._head[:max_bytes]
            return chunk
        self.body_read_started.set()
        if self.body_read_delay:
            await asyncio.sleep(self.body_read_delay)
        if self.block_body:
            await self._never_ready.wait()
        if self.read_error is not None:
            raise self.read_error
        if not self._body:
            return b""
        size = min(max_bytes, len(self._body))
        if self._body_chunk_size is not None:
            size = min(size, self._body_chunk_size)
        chunk = bytes(self._body[:size])
        del self._body[:size]
        self.body_bytes_returned += len(chunk)
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.request_bytes.extend(buffer)
        if self.write_error is not None:
            raise self.write_error

    async def aclose(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error

    async def start_tls(
        self,
        ssl_context: Any,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if self.tls_error is not None:
            raise self.tls_error
        return self


class AdvancingAsyncStream(RecordingAsyncStream):
    def __init__(
        self,
        clock: ManualClock,
        *,
        read_advances: list[float],
    ) -> None:
        super().__init__(body_chunk_size=6)
        self._clock = clock
        self._read_advances = iter(read_advances)

    async def read(
        self,
        max_bytes: int,
        timeout: float | None = None,
    ) -> bytes:
        if not self._head and self._body:
            self._clock.advance(next(self._read_advances))
        return await super().read(max_bytes, timeout=timeout)


class HeadAdvancingAsyncStream(RecordingAsyncStream):
    def __init__(self, clock: ManualClock, *, seconds: float) -> None:
        super().__init__(body=b"content\n", content_length=None)
        self._clock = clock
        self._seconds = seconds
        self._advanced = False

    async def read(
        self,
        max_bytes: int,
        timeout: float | None = None,
    ) -> bytes:
        if self._head and not self._advanced:
            self._clock.advance(self._seconds)
            self._advanced = True
        return await super().read(max_bytes, timeout=timeout)


class ScriptedAdvancingAsyncStream(RecordingAsyncStream):
    def __init__(
        self,
        clock: ManualClock,
        *,
        chunks: list[tuple[bytes, float]],
    ) -> None:
        super().__init__(body=b"", content_length=None)
        self._clock = clock
        self._chunks = chunks
        self._chunk_index = 0

    async def read(
        self,
        max_bytes: int,
        timeout: float | None = None,
    ) -> bytes:
        if self._head:
            return await super().read(max_bytes, timeout=timeout)
        self.body_read_started.set()
        if self._chunk_index >= len(self._chunks):
            return b""
        chunk, seconds = self._chunks[self._chunk_index]
        self._chunk_index += 1
        self._clock.advance(seconds)
        self.body_bytes_returned += len(chunk)
        return chunk


class RecordingSyncBackend(httpcore.NetworkBackend):
    def __init__(
        self,
        streams: RecordingSyncStream | list[RecordingSyncStream],
        *,
        connect_error: Exception | None = None,
    ) -> None:
        self.streams = list(streams) if isinstance(streams, list) else [streams]
        self.connect_error = connect_error
        self.connect_calls: list[tuple[str, int]] = []

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        self.connect_calls.append((host, port))
        if self.connect_error is not None:
            raise self.connect_error
        return self.streams[len(self.connect_calls) - 1]

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        raise AssertionError("Unix sockets must not be used")

    def sleep(self, seconds: float) -> None:
        return None


class RecordingAsyncBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        streams: RecordingAsyncStream | list[RecordingAsyncStream],
        *,
        connect_error: Exception | None = None,
    ) -> None:
        self.streams = list(streams) if isinstance(streams, list) else [streams]
        self.connect_error = connect_error
        self.connect_calls: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connect_calls.append((host, port))
        if self.connect_error is not None:
            raise self.connect_error
        return self.streams[len(self.connect_calls) - 1]

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError("Unix sockets must not be used")

    async def sleep(self, seconds: float) -> None:
        return None


def _runtime_client(
    mode: Mode,
    stream: RecordingSyncStream | RecordingAsyncStream,
    *,
    policy: Any | None = None,
    connect_error: Exception | None = None,
    timeouts: RuntimeTimeouts = RuntimeTimeouts(),
) -> tuple[SafeRuntimeClient, RecordingPolicy | Any, Any]:
    active_policy = RecordingPolicy() if policy is None else policy
    if mode == "sync":
        backend = RecordingSyncBackend(
            cast(RecordingSyncStream, stream),
            connect_error=connect_error,
        )
        client = SafeRuntimeClient(
            active_policy,
            sync_network_backend=backend,
            timeouts=timeouts,
        )
    else:
        backend = RecordingAsyncBackend(
            cast(RecordingAsyncStream, stream),
            connect_error=connect_error,
        )
        client = SafeRuntimeClient(
            active_policy,
            async_network_backend=backend,
            timeouts=timeouts,
        )
    return client, active_policy, backend


def _stream_for(mode: Mode, **kwargs: Any) -> Any:
    if mode == "sync":
        return RecordingSyncStream(**kwargs)
    return RecordingAsyncStream(**kwargs)


async def _invoke(
    mode: Mode,
    client: SafeRuntimeClient,
    *,
    base_url: str = VALIDATED_BASE,
    request_target: Any = VALID_TARGET,
    headers: Mapping[str, str] | None = None,
    json_body: Mapping[str, Any] | None = None,
    allow_local: bool = False,
    budget: DeadlineBudget | None = None,
    max_bytes: int = AI_JSON_MAX_BYTES,
) -> dict[str, Any]:
    effective_budget = budget or DeadlineBudget.from_timeout(7.5)
    kwargs = {
        "request_target": request_target,
        "headers": {} if headers is None else headers,
        "json_body": {"request": True} if json_body is None else json_body,
        "allow_local": allow_local,
        "budget": effective_budget,
        "max_bytes": max_bytes,
    }
    if mode == "sync":
        return client.post_json(base_url, **kwargs)
    return await client.apost_json(base_url, **kwargs)


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_normal_budget_spans_dns_connect_and_complete_body(
    mode: Mode,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(6.0, clock=clock)
    policy = AdvancingPolicy(clock, dns_seconds=2.0)
    stream: RecordingSyncStream | RecordingAsyncStream
    if mode == "sync":
        stream = AdvancingSyncStream(clock, read_advances=[2.0, 2.1])
    else:
        stream = AdvancingAsyncStream(clock, read_advances=[2.0, 2.1])
    client, _, backend = _runtime_client(mode, stream, policy=policy)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(
            mode,
            client,
            budget=budget,
        )

    assert exc_info.value.code == "outbound_timeout"
    assert backend.connect_calls == [("93.184.216.34", 443)]
    assert stream.close_count == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_normal_budget_spans_json_parse(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(3.0, clock=clock)
    policy = AdvancingPolicy(clock, dns_seconds=1.0)
    stream: RecordingSyncStream | RecordingAsyncStream
    if mode == "sync":
        stream = AdvancingSyncStream(clock, read_advances=[0.5, 0.5])
    else:
        stream = AdvancingAsyncStream(clock, read_advances=[0.5, 0.5])
    client, _, _ = _runtime_client(mode, stream, policy=policy)
    real_parse = runtime_http._parse_json_object

    def advancing_parse(content: bytearray) -> dict[str, Any]:
        clock.advance(1.1)
        return real_parse(content)

    monkeypatch.setattr(runtime_http, "_parse_json_object", advancing_parse)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, budget=budget)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.close_count == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_normal_budget_spans_cleanup(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(3.0, clock=clock)
    policy = AdvancingPolicy(clock, dns_seconds=1.0)
    stream = _stream_for(mode)
    if mode == "sync":
        real_transport = runtime_http.PinnedSyncTransport

        class CleanupAdvancingTransport(real_transport):
            def close(self) -> None:
                super().close()
                clock.advance(2.1)

        monkeypatch.setattr(
            runtime_http,
            "PinnedSyncTransport",
            CleanupAdvancingTransport,
        )
    else:
        real_async_transport = runtime_http.PinnedAsyncTransport

        class CleanupAdvancingAsyncTransport(real_async_transport):
            async def aclose(self) -> None:
                await super().aclose()
                clock.advance(2.1)

        monkeypatch.setattr(
            runtime_http,
            "PinnedAsyncTransport",
            CleanupAdvancingAsyncTransport,
        )
    client, _, _ = _runtime_client(mode, stream, policy=policy)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, budget=budget)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.close_count == 1


def test_sync_blocking_dns_timeout_is_bounded_by_normal_budget() -> None:
    release = threading.Event()
    started = threading.Event()

    def resolver(hostname: str, port: int) -> tuple[Any, ...]:
        started.set()
        release.wait()
        return (ip_address("93.184.216.34"),)

    client = SafeRuntimeClient(
        policy=OutboundURLPolicy(resolver),
        runner=BoundedDaemonRunner(max_workers=1),
    )
    try:
        with pytest.raises(OutboundRequestError) as exc_info:
            client.post_json(
                VALIDATED_BASE,
                request_target=VALID_TARGET,
                headers={"Authorization": "Bearer test-sentinel"},
                json_body={"model": "test", "messages": []},
                allow_local=False,
                budget=DeadlineBudget.from_timeout(0.02),
                max_bytes=1024,
            )
        assert exc_info.value.code == "outbound_timeout"
        assert started.is_set()
    finally:
        release.set()


@pytest.mark.asyncio
async def test_async_blocking_dns_timeout_does_not_block_other_task() -> None:
    release = threading.Event()
    started = threading.Event()
    ticks = 0

    def resolver(hostname: str, port: int) -> tuple[Any, ...]:
        started.set()
        release.wait()
        return (ip_address("93.184.216.34"),)

    async def ticker() -> None:
        nonlocal ticks
        while ticks < 3:
            await asyncio.sleep(0)
            ticks += 1

    client = SafeRuntimeClient(
        policy=OutboundURLPolicy(resolver),
        runner=BoundedDaemonRunner(max_workers=1),
    )
    ticker_task = asyncio.create_task(ticker())
    try:
        with pytest.raises(OutboundRequestError) as exc_info:
            await client.apost_json(
                VALIDATED_BASE,
                request_target=VALID_TARGET,
                headers={"Authorization": "Bearer test-sentinel"},
                json_body={"model": "test", "messages": []},
                allow_local=False,
                budget=DeadlineBudget.from_timeout(0.02),
                max_bytes=1024,
            )
        assert exc_info.value.code == "outbound_timeout"
        await ticker_task
        assert ticks == 3
        assert started.is_set()
    finally:
        release.set()


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_expired_caller_budget_stops_before_network(
    mode: Mode,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(1.0, clock=clock)
    clock.advance(1.0)
    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, budget=budget)

    assert exc_info.value.code == "outbound_timeout"
    assert policy.calls == []
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_timeout_primary_survives_failing_cleanup(
    mode: Mode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleanup_sentinel = f"{mode}-timeout-cleanup-secret"
    cleanup_error = OSError(cleanup_sentinel)
    stream = _stream_for(
        mode,
        read_error=httpcore.ReadTimeout("primary-timeout"),
        close_error=cleanup_error,
    )
    client, _, _ = _runtime_client(mode, stream)
    for logger_name in ("httpx", "httpcore.connection", "httpcore.http11"):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.close_count == 1
    assert cleanup_sentinel not in repr(exc_info.value)
    assert cleanup_sentinel not in caplog.text
    _assert_no_displaced_cleanup_traceback_artifacts(
        exc_info.value,
        stream=stream,
        cleanup_error=cleanup_error,
    )


@pytest.mark.asyncio
async def test_caller_cancellation_survives_failing_cleanup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cancel_sentinel = "caller-cancel-primary"
    cleanup_sentinel = "cancel-cleanup-secret"
    cleanup_error = OSError(cleanup_sentinel)
    stream = RecordingAsyncStream(
        block_body=True,
        close_error=cleanup_error,
    )
    client, _, _ = _runtime_client("async", stream)
    for logger_name in ("httpx", "httpcore.connection", "httpcore.http11"):
        caplog.set_level(logging.DEBUG, logger=logger_name)
    task = asyncio.create_task(_invoke("async", client))

    await asyncio.wait_for(stream.body_read_started.wait(), timeout=1.0)
    task.cancel(cancel_sentinel)
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    assert exc_info.value.args == (cancel_sentinel,)
    assert stream.close_count == 1
    assert cleanup_sentinel not in repr(exc_info.value)
    assert cleanup_sentinel not in caplog.text
    _assert_no_displaced_cleanup_traceback_artifacts(
        exc_info.value,
        stream=stream,
        cleanup_error=cleanup_error,
    )


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_cleanup_failure_without_primary_keeps_fixed_error(
    mode: Mode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleanup_sentinel = f"{mode}-standalone-cleanup-secret"
    stream = _stream_for(mode, close_error=OSError(cleanup_sentinel))
    client, _, _ = _runtime_client(mode, stream)
    for logger_name in ("httpx", "httpcore.connection", "httpcore.http11"):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    assert exc_info.value.code == "outbound_connect_failed"
    assert stream.close_count == 1
    assert cleanup_sentinel not in repr(exc_info.value)
    assert cleanup_sentinel not in caplog.text


class StaleFatalCleanupContext(BaseException):
    pass


def _assert_no_displaced_cleanup_traceback_artifacts(
    error: BaseException,
    *,
    stream: RecordingSyncStream | RecordingAsyncStream,
    cleanup_error: BaseException,
) -> None:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        traceback = current.__traceback__
        while traceback is not None:
            if traceback.tb_frame.f_code.co_name.startswith("test_"):
                traceback = traceback.tb_next
                continue
            frame_locals = traceback.tb_frame.f_locals
            assert "escaped_error" not in frame_locals
            assert cleanup_error not in frame_locals.values()
            assert stream not in frame_locals.values()
            retained_responses = [
                name
                for name, value in frame_locals.items()
                if isinstance(value, httpx.Response)
            ]
            assert not retained_responses, (
                type(current).__name__,
                traceback.tb_frame.f_code.co_name,
                retained_responses,
            )
            assert not any(
                type(value).__name__ == "_ReadInvocationMarker"
                for value in frame_locals.values()
            )
            traceback = traceback.tb_next
        if current.__context__ is not None:
            pending.append(current.__context__)
        if current.__cause__ is not None:
            pending.append(current.__cause__)


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_ordinary_read_error_preserves_traceback_and_cause(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cause = RuntimeError("ordinary-read-cause")
    original = OutboundRequestError(
        "outbound_bad_response",
        502,
        "fixed ordinary read failure",
    )

    def fail_parse(content: bytearray) -> dict[str, Any]:
        raise original from cause

    monkeypatch.setattr(runtime_http, "_parse_json_object", fail_parse)
    stream = _stream_for(mode)
    client, _, _ = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    frame_names: list[str] = []
    traceback = exc_info.value.__traceback__
    while traceback is not None:
        frame_names.append(traceback.tb_frame.f_code.co_name)
        traceback = traceback.tb_next
    assert exc_info.value is original
    assert exc_info.value.__cause__ is cause
    assert "fail_parse" in frame_names
    assert (
        "_read_sync_json_impl" if mode == "sync" else "_read_async_json_impl"
    ) in frame_names


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "stale_error",
    [
        asyncio.CancelledError("stale-cancel-context"),
        StaleFatalCleanupContext("stale-fatal-context"),
    ],
    ids=["cancelled", "fatal"],
)
@pytest.mark.asyncio
async def test_reused_cleanup_error_ignores_unrelated_stale_context(
    mode: Mode,
    stale_error: BaseException,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleanup_sentinel = f"{mode}-reused-cleanup-secret"
    cleanup_error = OSError(cleanup_sentinel)
    try:
        raise stale_error
    except BaseException:
        try:
            raise cleanup_error
        except OSError:
            pass
    assert cleanup_error.__context__ is stale_error

    stream = _stream_for(mode, close_error=cleanup_error)
    client, _, _ = _runtime_client(mode, stream)
    for logger_name in ("httpx", "httpcore.connection", "httpcore.http11"):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    context_chain: list[BaseException] = []
    current: BaseException | None = exc_info.value
    while current is not None and current not in context_chain:
        context_chain.append(current)
        current = current.__context__
    assert exc_info.value.code == "outbound_connect_failed"
    assert stream.close_count == 1
    assert stale_error not in context_chain
    assert cleanup_error not in context_chain
    assert cleanup_sentinel not in repr(context_chain)
    assert cleanup_sentinel not in caplog.text


def _request_bytes(stream: Any) -> bytes:
    return bytes(stream.request_bytes)


def _record_parser_buffer_lengths(
    monkeypatch: pytest.MonkeyPatch,
) -> list[int]:
    lengths: list[int] = []

    class RecordingParserBuffer(bytearray):
        def extend(self, data: Any) -> None:
            super().extend(data)
            lengths.append(len(self))

    monkeypatch.setattr(
        runtime_http,
        "bytearray",
        RecordingParserBuffer,
        raising=False,
    )
    return lengths


def test_public_runtime_contract_is_exported() -> None:
    assert AI_JSON_MAX_BYTES == 8 * 1024 * 1024
    assert EMBEDDING_JSON_MAX_BYTES == 16 * 1024 * 1024
    assert STREAM_MAX_BYTES == 16 * 1024 * 1024
    assert STREAM_EVENT_MAX_BYTES == 1 * 1024 * 1024
    assert RETRYABLE_OUTBOUND_CODES == frozenset(
        {"outbound_connect_failed", "outbound_timeout"}
    )
    assert RuntimeTimeouts() == RuntimeTimeouts(
        connect=10.0,
        read=60.0,
        write=30.0,
        pool=10.0,
        stream_idle=120.0,
        stream_total=600.0,
    )
    with pytest.raises(FrozenInstanceError):
        RuntimeTimeouts().connect = 99.0  # type: ignore[misc]

    for name in (
        "AI_JSON_MAX_BYTES",
        "EMBEDDING_JSON_MAX_BYTES",
        "STREAM_MAX_BYTES",
        "STREAM_EVENT_MAX_BYTES",
        "RETRYABLE_OUTBOUND_CODES",
        "RuntimeTimeouts",
        "SafeRuntimeClient",
    ):
        assert getattr(security, name) is getattr(runtime_http, name)


def test_normal_json_api_requires_caller_budget() -> None:
    for method in (SafeRuntimeClient.post_json, SafeRuntimeClient.apost_json):
        parameters = inspect.signature(method).parameters
        assert "read_timeout" not in parameters
        assert parameters["budget"].default is inspect.Parameter.empty


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("request_target", INVALID_TARGETS)
@pytest.mark.asyncio
async def test_request_target_rejects_origin_escape_and_ambiguous_forms(
    mode: Mode,
    request_target: str,
) -> None:
    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, request_target=request_target)

    assert exc_info.value.code == "outbound_url_invalid"
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("request_target", [None, b"/bytes", 7])
@pytest.mark.asyncio
async def test_request_target_rejects_non_strings(
    mode: Mode,
    request_target: Any,
) -> None:
    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, request_target=request_target)

    assert exc_info.value.code == "outbound_url_invalid"
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_request_target_rejects_unpaired_unicode_surrogate(
    mode: Mode,
) -> None:
    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, request_target="/\ud800")

    assert exc_info.value.code == "outbound_url_invalid"
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("suffix", ["?key=query-secret", "#fragment-secret"])
@pytest.mark.asyncio
async def test_base_url_query_and_fragment_still_use_real_policy(
    mode: Mode,
    suffix: str,
) -> None:
    resolver_calls: list[tuple[str, int]] = []

    def resolver(hostname: str, port: int) -> tuple[Any, ...]:
        resolver_calls.append((hostname, port))
        return (ip_address("93.184.216.34"),)

    policy = OutboundURLPolicy(resolver)
    stream = _stream_for(mode)
    client, _, backend = _runtime_client(mode, stream, policy=policy)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, base_url=VALIDATED_BASE + suffix)

    assert exc_info.value.code == "outbound_url_invalid"
    assert resolver_calls == []
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_request_target_preserves_validated_base_path_without_urljoin(
    mode: Mode,
) -> None:
    stream = _stream_for(mode)
    client, policy, _ = _runtime_client(mode, stream)

    assert await _invoke(mode, client, allow_local=True) == {"ok": True}

    target = EXPECTED_FINAL_URL.removeprefix("https://public.example")
    request_line = f"POST {target} HTTP/1.1"
    assert request_line.encode() in _request_bytes(stream)
    assert policy.calls == [(VALIDATED_BASE, True)]


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_encoded_google_target_keeps_approved_origin_and_hides_query_log(
    mode: Mode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    query_sentinel = "google-query-secret-sentinel"
    model_segment = quote("gemini/2?preview", safe="")
    target = (
        f"/models/{model_segment}:generateContent?"
        + urlencode({"key": query_sentinel})
    )
    stream = _stream_for(mode)
    client, _, backend = _runtime_client(mode, stream)
    for logger_name in ("httpx", "httpcore.connection", "httpcore.http11"):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    assert await _invoke(mode, client, request_target=target) == {"ok": True}

    request = _request_bytes(stream)
    assert (
        b"POST /v1/models/gemini%2F2%3Fpreview:generateContent?key="
        + query_sentinel.encode()
        + b" HTTP/1.1"
    ) in request
    assert b"host: public.example\r\n" in request.lower()
    assert backend.connect_calls == [("93.184.216.34", 443)]
    assert query_sentinel not in caplog.text


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b'{"answer":42}', {"answer": 42}),
        (b"[]", None),
        (b"null", None),
        (b'"value"', None),
        (b"{", None),
        (b"\xff", None),
    ],
    ids=["object", "array", "null", "string", "malformed", "non-utf8"],
)
@pytest.mark.asyncio
async def test_json_response_must_be_a_valid_object(
    mode: Mode,
    body: bytes,
    expected: dict[str, Any] | None,
) -> None:
    stream = _stream_for(mode, body=body)
    client, _, _ = _runtime_client(mode, stream)

    if expected is not None:
        assert await _invoke(mode, client) == expected
    else:
        with pytest.raises(OutboundRequestError) as exc_info:
            await _invoke(mode, client)
        assert exc_info.value.code == "outbound_bad_response"
    assert stream.close_count == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "body",
    [
        b'{"number":' + (b"9" * 5_000) + b"}",
        b'{"nested":' + (b"[" * 20_000) + b"0" + (b"]" * 20_000) + b"}",
    ],
    ids=["integer-digit-limit", "recursion-limit"],
)
@pytest.mark.asyncio
async def test_json_parser_limits_map_to_fixed_bad_response(
    mode: Mode,
    body: bytes,
) -> None:
    stream = _stream_for(mode, body=body)
    client, _, _ = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    assert exc_info.value.code == "outbound_bad_response"
    assert str(exc_info.value) == "外部服务响应无效"
    assert stream.close_count == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "case",
    ["header-unicode", "body-unicode", "unserializable", "nan", "recursive"],
)
@pytest.mark.asyncio
async def test_request_construction_errors_are_fixed_and_redacted(
    mode: Mode,
    case: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    header_sentinel = "header-construction-secret-sentinel"
    body_sentinel = "body-construction-secret-sentinel"
    repr_sentinel = "repr-construction-secret-sentinel"
    value_sentinel = f"value-{case}-secret-sentinel"
    headers: Mapping[str, str] = {}
    json_body: Mapping[str, Any] = {"ok": True}

    if case == "header-unicode":
        headers = {"X-Secret": header_sentinel + "\ud800"}
        active_sentinel = header_sentinel
    elif case == "body-unicode":
        json_body = {"prompt": body_sentinel + "\ud800"}
        active_sentinel = body_sentinel
    elif case == "unserializable":
        secret_type = type(
            repr_sentinel,
            (),
            {"__repr__": lambda self: repr_sentinel},
        )
        json_body = {"value": secret_type()}
        active_sentinel = repr_sentinel
    elif case == "nan":
        json_body = {value_sentinel: float("nan")}
        active_sentinel = value_sentinel
    else:
        nested: Any = 0
        for _ in range(20_000):
            nested = [nested]
        json_body = {value_sentinel: nested}
        active_sentinel = value_sentinel

    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)
    for logger_name in (
        "httpx",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
    ):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(
            mode,
            client,
            headers=headers,
            json_body=json_body,
        )

    assert exc_info.value.code == "outbound_bad_response"
    assert str(exc_info.value) == "外部服务响应无效"
    assert active_sentinel not in repr(exc_info.value)
    assert active_sentinel not in caplog.text
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("status", [302, 400, 500])
@pytest.mark.asyncio
async def test_non_2xx_reads_zero_body_bytes_and_never_follows_redirects(
    mode: Mode,
    status: int,
) -> None:
    body = b"upstream-body-secret"
    stream = _stream_for(
        mode,
        status=status,
        body=body,
        headers={
            "Location": "https://evil.example/redirect-secret",
            "Content-Encoding": "gzip",
        },
        content_length=len(body) + 1_000,
    )
    client, _, backend = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, max_bytes=8)

    assert exc_info.value.code == "outbound_bad_response"
    assert stream.body_bytes_returned == 0
    assert backend.connect_calls == [("93.184.216.34", 443)]
    assert b"evil.example" not in _request_bytes(stream)


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    ("encoding", "expected_code"),
    [
        ("gzip", "outbound_bad_response"),
        ("br", "outbound_bad_response"),
        ("", "outbound_bad_response"),
        ("identity", None),
        (None, None),
    ],
    ids=["gzip", "br", "empty", "identity", "missing"],
)
@pytest.mark.asyncio
async def test_content_encoding_is_checked_before_body_read(
    mode: Mode,
    encoding: str | None,
    expected_code: str | None,
) -> None:
    body = b'{"ok":true}'
    headers = {} if encoding is None else {"Content-Encoding": encoding}
    stream = _stream_for(mode, body=body, headers=headers)
    client, _, _ = _runtime_client(mode, stream)

    if expected_code is None:
        assert await _invoke(mode, client) == {"ok": True}
        assert stream.body_bytes_returned == len(body)
    else:
        with pytest.raises(OutboundRequestError) as exc_info:
            await _invoke(mode, client)
        assert exc_info.value.code == expected_code
        assert stream.body_bytes_returned == 0


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_content_length_equal_to_limit_is_allowed(mode: Mode) -> None:
    body = b'{"value":"ok"}'
    stream = _stream_for(mode, body=body, content_length=len(body))
    client, _, _ = _runtime_client(mode, stream)

    assert await _invoke(mode, client, max_bytes=len(body)) == {"value": "ok"}
    assert stream.body_bytes_returned == len(body)


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    ("declared_length", "expected_code"),
    [
        (9, "outbound_response_too_large"),
        (-1, "outbound_bad_response"),
        ("not-an-integer", "outbound_bad_response"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_oversized_content_length_reads_zero_body_bytes(
    mode: Mode,
    declared_length: object,
    expected_code: str,
) -> None:
    stream = _stream_for(
        mode,
        body=b'{"ok":true}',
        content_length=declared_length,
    )
    client, _, _ = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, max_bytes=8)

    assert exc_info.value.code == expected_code
    assert stream.body_bytes_returned == 0


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_missing_content_length_incremental_body_exceeds_parser_limit(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = 17
    parser_buffer_lengths = _record_parser_buffer_lengths(monkeypatch)
    stream = _stream_for(
        mode,
        body=b"x" * (limit + 100),
        content_length=None,
        body_chunk_size=1,
    )
    client, _, _ = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, max_bytes=limit)

    assert exc_info.value.code == "outbound_response_too_large"
    assert parser_buffer_lengths
    assert max(parser_buffer_lengths) == limit + 1
    assert stream.body_bytes_returned >= limit + 1
    assert stream.close_count == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_coalesced_socket_read_still_enforces_parser_limit(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = 17
    body = b"x" * (limit + 100)
    parser_buffer_lengths = _record_parser_buffer_lengths(monkeypatch)
    stream = _stream_for(
        mode,
        body=body,
        content_length=None,
    )
    client, _, _ = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, max_bytes=limit)

    assert exc_info.value.code == "outbound_response_too_large"
    assert parser_buffer_lengths
    assert max(parser_buffer_lengths) == limit + 1
    # This counter observes the fake TCP stream. HTTPcore may read ahead into
    # its protocol buffer; only bytes handed to the runtime parser are bounded.
    assert stream.body_bytes_returned > limit + 1
    assert stream.close_count == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_negative_max_bytes_is_rejected_before_network(mode: Mode) -> None:
    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, max_bytes=-1)

    assert exc_info.value.code == "outbound_url_invalid"
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "max_bytes",
    [True, 1.5, float("inf"), float("nan"), "8"],
    ids=["bool", "float", "infinity", "nan", "string"],
)
@pytest.mark.asyncio
async def test_invalid_max_bytes_type_is_rejected_before_network(
    mode: Mode,
    max_bytes: Any,
) -> None:
    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client, max_bytes=max_bytes)

    assert exc_info.value.code == "outbound_url_invalid"
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []


def _error_stream(mode: Mode, stage: str, error: Exception) -> Any:
    kwargs: dict[str, Any] = {}
    if stage == "read":
        kwargs["read_error"] = error
    elif stage == "write":
        kwargs["write_error"] = error
    elif stage == "tls":
        kwargs["tls_error"] = error
    elif stage == "protocol":
        kwargs["raw_head"] = b"not-an-http-response\r\n\r\n"
        kwargs["body"] = b""
        kwargs["content_length"] = None
    return _stream_for(mode, **kwargs)


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    ("stage", "error", "expected_code"),
    [
        ("connect", OSError("connect-backend-secret"), "outbound_connect_failed"),
        ("read", OSError("read-backend-secret"), "outbound_connect_failed"),
        ("tls", OSError("tls-backend-secret"), "outbound_connect_failed"),
        ("read", httpcore.ReadTimeout("read-timeout-secret"), "outbound_timeout"),
        ("write", httpcore.WriteTimeout("write-timeout-secret"), "outbound_timeout"),
        ("tls", httpcore.ConnectTimeout("tls-timeout-secret"), "outbound_timeout"),
        ("protocol", RuntimeError("unused"), "outbound_bad_response"),
    ],
    ids=[
        "connect",
        "read",
        "tls",
        "read-timeout",
        "write-timeout",
        "tls-timeout",
        "protocol",
    ],
)
@pytest.mark.asyncio
async def test_transport_errors_map_to_fixed_public_errors(
    mode: Mode,
    stage: str,
    error: Exception,
    expected_code: str,
) -> None:
    stream = _error_stream(mode, stage, error)
    connect_error = error if stage == "connect" else None
    client, policy, backend = _runtime_client(
        mode,
        stream,
        connect_error=connect_error,
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    assert exc_info.value.code == expected_code
    assert str(exc_info.value) in {
        "外部服务连接失败",
        "外部服务请求超时",
        "外部服务响应无效",
    }
    assert "secret" not in repr(exc_info.value)
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert len(backend.connect_calls) == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_client_cleans_headers_and_disables_env_and_redirects(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _stream_for(mode)
    timeouts = RuntimeTimeouts(
        connect=1.25,
        read=2.5,
        write=3.75,
        pool=4.5,
        stream_idle=5.0,
        stream_total=6.0,
    )
    client, _, _ = _runtime_client(mode, stream, timeouts=timeouts)
    constructor_kwargs: list[dict[str, Any]] = []

    if mode == "sync":
        real_client = httpx.Client

        def client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
            constructor_kwargs.append(kwargs.copy())
            return real_client(*args, **kwargs)

        monkeypatch.setattr(runtime_http.httpx, "Client", client_factory)
    else:
        real_async_client = httpx.AsyncClient

        def async_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
            constructor_kwargs.append(kwargs.copy())
            return real_async_client(*args, **kwargs)

        monkeypatch.setattr(
            runtime_http.httpx,
            "AsyncClient",
            async_client_factory,
        )

    result = await _invoke(
        mode,
        client,
        headers={
            "hOsT": "evil-host-secret",
            "aCcEpT-eNcOdInG": "gzip",
            "Authorization": "Bearer caller-header-secret",
        },
        budget=DeadlineBudget.from_timeout(9.25),
    )

    assert result == {"ok": True}
    request = _request_bytes(stream).lower()
    assert b"host: public.example\r\n" in request
    assert b"evil-host-secret" not in request
    assert request.count(b"accept-encoding: identity\r\n") == 1
    assert b"accept-encoding: gzip" not in request
    assert len(constructor_kwargs) == 1
    assert constructor_kwargs[0]["trust_env"] is False
    assert constructor_kwargs[0]["follow_redirects"] is False
    timeout = constructor_kwargs[0]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (
        1.25,
        2.5,
        3.75,
        4.5,
    )


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_client_constructor_failure_closes_new_pinned_transport(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_sentinel = "client-constructor-secret"
    stream = _stream_for(mode)
    client, policy, backend = _runtime_client(mode, stream)
    created_transports: list[Any] = []

    if mode == "sync":
        real_transport = runtime_http.PinnedSyncTransport

        class TrackingSyncTransport(real_transport):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.close_count = 0
                created_transports.append(self)

            def close(self) -> None:
                self.close_count += 1
                super().close()

        def failing_client(*args: Any, **kwargs: Any) -> None:
            raise OSError(constructor_sentinel)

        monkeypatch.setattr(
            runtime_http,
            "PinnedSyncTransport",
            TrackingSyncTransport,
        )
        monkeypatch.setattr(runtime_http.httpx, "Client", failing_client)
    else:
        real_async_transport = runtime_http.PinnedAsyncTransport

        class TrackingAsyncTransport(real_async_transport):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                self.close_count = 0
                created_transports.append(self)

            async def aclose(self) -> None:
                self.close_count += 1
                await super().aclose()

        def failing_async_client(*args: Any, **kwargs: Any) -> None:
            raise OSError(constructor_sentinel)

        monkeypatch.setattr(
            runtime_http,
            "PinnedAsyncTransport",
            TrackingAsyncTransport,
        )
        monkeypatch.setattr(
            runtime_http.httpx,
            "AsyncClient",
            failing_async_client,
        )

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    assert exc_info.value.code == "outbound_connect_failed"
    assert constructor_sentinel not in repr(exc_info.value)
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []
    assert len(created_transports) == 1
    assert created_transports[0].close_count == 1


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_errors_and_logs_redact_all_independent_sentinels(
    mode: Mode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinels = {
        "header": "header-secret-sentinel",
        "query": "query-secret-sentinel",
        "body": "body-secret-sentinel",
        "backend": "backend-secret-sentinel",
    }
    stream = _stream_for(
        mode,
        read_error=OSError(sentinels["backend"]),
        body=b'{"unread":true}',
    )
    client, _, _ = _runtime_client(mode, stream)
    for logger_name in (
        "httpx",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
    ):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(
            mode,
            client,
            request_target=VALID_TARGET + "?" + urlencode({"key": sentinels["query"]}),
            headers={"Authorization": "Bearer " + sentinels["header"]},
            json_body={"prompt": sentinels["body"]},
        )

    wire_request = _request_bytes(stream).decode("utf-8")
    assert sentinels["header"] in wire_request
    assert sentinels["query"] in wire_request
    assert sentinels["body"] in wire_request
    for sentinel in sentinels.values():
        assert sentinel not in repr(exc_info.value)
        assert sentinel not in caplog.text

    outside_sentinel = f"outside-{mode}-log-is-visible"
    logging.getLogger("httpx").info(outside_sentinel)
    assert outside_sentinel in caplog.text


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_existing_outbound_error_passes_through_unchanged(mode: Mode) -> None:
    original = OutboundRequestError(
        "private_network_blocked",
        400,
        "该网络地址不允许访问",
    )
    policy = RecordingPolicy(error=original)
    stream = _stream_for(mode)
    client, _, backend = _runtime_client(mode, stream, policy=policy)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _invoke(mode, client)

    assert exc_info.value is original
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_real_policy_resolves_exactly_once_per_invocation(mode: Mode) -> None:
    resolver_calls: list[tuple[str, int]] = []

    def resolver(hostname: str, port: int) -> tuple[Any, ...]:
        resolver_calls.append((hostname, port))
        return (ip_address("93.184.216.34"),)

    stream = _stream_for(mode)
    policy = OutboundURLPolicy(resolver)
    client, _, backend = _runtime_client(mode, stream, policy=policy)

    assert await _invoke(mode, client) == {"ok": True}
    assert resolver_calls == [("public.example", 443)]
    assert backend.connect_calls == [("93.184.216.34", 443)]


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.asyncio
async def test_each_invocation_validates_once_and_builds_a_new_client(
    mode: Mode,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = RecordingPolicy()
    constructor_count = 0
    if mode == "sync":
        streams: list[Any] = [RecordingSyncStream(), RecordingSyncStream()]
        backend: Any = RecordingSyncBackend(streams)
        client = SafeRuntimeClient(policy, sync_network_backend=backend)
        real_client = httpx.Client

        def client_factory(*args: Any, **kwargs: Any) -> httpx.Client:
            nonlocal constructor_count
            constructor_count += 1
            return real_client(*args, **kwargs)

        monkeypatch.setattr(runtime_http.httpx, "Client", client_factory)
    else:
        streams = [RecordingAsyncStream(), RecordingAsyncStream()]
        backend = RecordingAsyncBackend(streams)
        client = SafeRuntimeClient(policy, async_network_backend=backend)
        real_async_client = httpx.AsyncClient

        def async_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
            nonlocal constructor_count
            constructor_count += 1
            return real_async_client(*args, **kwargs)

        monkeypatch.setattr(
            runtime_http.httpx,
            "AsyncClient",
            async_client_factory,
        )

    assert await _invoke(mode, client) == {"ok": True}
    assert await _invoke(mode, client) == {"ok": True}

    assert policy.calls == [(VALIDATED_BASE, False), (VALIDATED_BASE, False)]
    assert constructor_count == 2
    assert len(backend.connect_calls) == 2
    assert all(stream.close_count == 1 for stream in streams)


@pytest.mark.asyncio
async def test_async_cancellation_propagates_closes_and_keeps_other_task_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    query_sentinel = "cancelled-runtime-query-secret"
    outside_sentinel = "concurrent-unrelated-httpx-log"
    stream = RecordingAsyncStream(
        body=b'{"ok":true}',
        block_body=True,
    )
    client, _, _ = _runtime_client("async", stream)
    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="httpcore.http11")
    task = asyncio.create_task(
        _invoke(
            "async",
            client,
            request_target=VALID_TARGET + "?" + urlencode({"key": query_sentinel}),
        )
    )

    await stream.body_read_started.wait()
    logging.getLogger("httpx").info(outside_sentinel)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stream.close_count == 1
    assert outside_sentinel in caplog.text
    assert query_sentinel not in caplog.text


def _open_runtime_line_stream(
    client: SafeRuntimeClient,
    *,
    base_url: str = VALIDATED_BASE,
    request_target: Any = VALID_TARGET,
    headers: Mapping[str, str] | None = None,
    json_body: Mapping[str, Any] | None = None,
    allow_local: bool = False,
    max_bytes: Any = STREAM_MAX_BYTES,
    max_event_bytes: Any = STREAM_EVENT_MAX_BYTES,
    budget: StreamBudget | None = None,
) -> Any:
    effective_budget = budget or StreamBudget.from_timeouts(
        120.0, hard_timeout=600.0
    )
    kwargs: dict[str, Any] = {
        "request_target": request_target,
        "headers": {} if headers is None else headers,
        "json_body": {"request": True} if json_body is None else json_body,
        "allow_local": allow_local,
        "budget": effective_budget,
        "max_bytes": max_bytes,
        "max_event_bytes": max_event_bytes,
    }
    return client.astream_lines(
        base_url,
        **kwargs,
    )


async def _collect_runtime_lines(
    client: SafeRuntimeClient,
    **kwargs: Any,
) -> list[str]:
    return [line async for line in _open_runtime_line_stream(client, **kwargs)]


@pytest.mark.asyncio
async def test_stream_blocking_dns_consumes_initial_idle_budget() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(3.0, clock=clock)
    policy = AdvancingPolicy(clock, dns_seconds=3.1)
    stream = RecordingAsyncStream(body=b"unread\n", content_length=None)
    client, _, backend = _runtime_client("async", stream, policy=policy)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(client, budget=budget)

    assert exc_info.value.code == "outbound_timeout"
    assert backend.connect_calls == []
    assert stream.close_count == 0


@pytest.mark.asyncio
async def test_stream_response_headers_consume_initial_idle_budget() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(3.0, clock=clock)
    stream = HeadAdvancingAsyncStream(clock, seconds=3.1)
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(client, budget=budget)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.body_bytes_returned == 0
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_protocol_lines_cannot_refresh_idle_budget() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(3.0, clock=clock)
    stream = ScriptedAdvancingAsyncStream(
        clock,
        chunks=[
            (b": heartbeat\n", 1.0),
            (b"\n", 1.0),
            (b": again\n", 1.1),
        ],
    )
    client, _, _ = _runtime_client("async", stream)
    received: list[str] = []

    with pytest.raises(OutboundRequestError) as exc_info:
        async for line in _open_runtime_line_stream(client, budget=budget):
            received.append(line)

    assert received == [": heartbeat", ""]
    assert exc_info.value.code == "outbound_timeout"
    assert budget.content_started is False
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_content_idle_window_starts_when_consumer_resumes() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(3.0, hard_timeout=10.0, clock=clock)
    stream = ScriptedAdvancingAsyncStream(
        clock,
        chunks=[(b"first\n", 1.0), (b"second\n", 2.9)],
    )
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client, budget=budget)

    assert await anext(iterator) == "first"
    budget.mark_content()
    clock.advance(5.0)
    assert await anext(iterator) == "second"
    await iterator.aclose()

    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_hard_deadline_closes_once_despite_content() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(2.0, hard_timeout=3.0, clock=clock)
    stream = ScriptedAdvancingAsyncStream(
        clock,
        chunks=[(b"a\n", 1.0), (b"b\n", 1.0), (b"c\n", 1.1)],
    )
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client, budget=budget)

    assert await anext(iterator) == "a"
    budget.mark_content()
    assert await anext(iterator) == "b"
    budget.mark_content()
    with pytest.raises(OutboundRequestError) as exc_info:
        await anext(iterator)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_yields_utf8_lines_and_trims_terminal_carriage_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = "浣犲ソ\r\n\nfinal".encode("utf-8")
    event_limit = len("浣犲ソ\r".encode("utf-8"))
    parser_buffer_lengths = _record_parser_buffer_lengths(monkeypatch)
    stream = RecordingAsyncStream(body=body, body_chunk_size=1)
    client, policy, backend = _runtime_client("async", stream)

    result = await _collect_runtime_lines(
        client,
        max_bytes=len(body),
        max_event_bytes=event_limit,
    )

    assert result == ["浣犲ソ", "", "final"]
    assert parser_buffer_lengths
    assert max(parser_buffer_lengths) <= event_limit
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == [("93.184.216.34", 443)]
    assert stream.close_count == 1


@pytest.mark.parametrize(
    "body_chunk_size",
    [1, None],
    ids=["incremental", "coalesced-default"],
)
@pytest.mark.parametrize(
    ("body", "max_bytes", "max_event_bytes", "max_accumulator"),
    [
        (b"abcd\n", 5, 3, 4),
        (b"abcd\r\n", 6, 4, 5),
        (b"abcde", 5, 4, 5),
        (b"abcd\n", 4, 4, 4),
    ],
    ids=[
        "complete-event-plus-one",
        "limit-before-carriage-return-trim",
        "final-partial-plus-one",
        "total-plus-one",
    ],
)
@pytest.mark.asyncio
async def test_stream_rejects_event_limit_plus_one_and_total_limit_plus_one(
    body_chunk_size: int | None,
    body: bytes,
    max_bytes: int,
    max_event_bytes: int,
    max_accumulator: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser_buffer_lengths = _record_parser_buffer_lengths(monkeypatch)
    stream = RecordingAsyncStream(
        body=body,
        content_length=None,
        body_chunk_size=body_chunk_size,
    )
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(
            client,
            max_bytes=max_bytes,
            max_event_bytes=max_event_bytes,
        )

    assert exc_info.value.code == "outbound_response_too_large"
    assert max(parser_buffer_lengths, default=0) <= max_accumulator
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_coalesced_chunk_copies_only_to_event_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_limit = 4
    max_slice = event_limit + 1
    real_aiter_raw = httpx.Response.aiter_raw

    class SliceGuard(bytes):
        def __getitem__(self, key: Any) -> Any:
            if isinstance(key, slice):
                start, stop, step = key.indices(len(self))
                if step == 1 and stop - start > max_slice:
                    raise AssertionError("stream copied past the event sentinel")
            return super().__getitem__(key)

    async def guarded_aiter_raw(
        response: httpx.Response,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        async for chunk in real_aiter_raw(response, *args, **kwargs):
            yield SliceGuard(chunk)

    monkeypatch.setattr(httpx.Response, "aiter_raw", guarded_aiter_raw)
    body = b"x" * 100
    stream = RecordingAsyncStream(body=body, content_length=None)
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(
            client,
            max_bytes=len(body),
            max_event_bytes=event_limit,
        )

    assert exc_info.value.code == "outbound_response_too_large"
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_accepts_equal_byte_limits_and_checks_final_partial_utf8(
) -> None:
    allowed = RecordingAsyncStream(body=b"abcd\n", content_length=None)
    allowed_client, _, _ = _runtime_client("async", allowed)

    assert await _collect_runtime_lines(
        allowed_client,
        max_bytes=5,
        max_event_bytes=4,
    ) == ["abcd"]
    assert allowed.close_count == 1

    invalid = RecordingAsyncStream(body=b"ok\n\xff", content_length=None)
    invalid_client, _, _ = _runtime_client("async", invalid)
    iterator = _open_runtime_line_stream(
        invalid_client,
        max_bytes=4,
        max_event_bytes=2,
    )

    assert await anext(iterator) == "ok"
    with pytest.raises(OutboundRequestError) as exc_info:
        await anext(iterator)
    assert exc_info.value.code == "outbound_bad_response"
    assert invalid.close_count == 1


@pytest.mark.parametrize(
    ("status", "headers", "content_length", "expected_code"),
    [
        (500, {}, 1, "outbound_bad_response"),
        (200, {"Content-Encoding": "gzip"}, 1, "outbound_bad_response"),
        (200, {}, 9, "outbound_response_too_large"),
    ],
    ids=["non-2xx", "encoded", "oversized-content-length"],
)
@pytest.mark.asyncio
async def test_stream_rejects_response_headers_before_application_iteration(
    status: int,
    headers: Mapping[str, str],
    content_length: object,
    expected_code: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser_buffer_lengths = _record_parser_buffer_lengths(monkeypatch)
    stream = RecordingAsyncStream(
        body=b"x",
        status=status,
        headers=headers,
        content_length=content_length,
    )
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(
            client,
            max_bytes=8,
            max_event_bytes=8,
        )

    assert exc_info.value.code == expected_code
    assert parser_buffer_lengths == []
    assert stream.body_bytes_returned == 0
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_idle_timeout_uses_caller_budget_and_closes_once() -> None:
    class BlockAfterFirstBodyStream(RecordingAsyncStream):
        def __init__(self) -> None:
            super().__init__(
                body=b"ready\n",
                content_length=None,
                body_chunk_size=6,
            )
            self.blocked_read_started = asyncio.Event()
            self._blocked_forever = asyncio.Event()

        async def read(
            self,
            max_bytes: int,
            timeout: float | None = None,
        ) -> bytes:
            if not self._head and self.body_bytes_returned:
                self.blocked_read_started.set()
                await self._blocked_forever.wait()
            return await super().read(max_bytes, timeout=timeout)

    stream = BlockAfterFirstBodyStream()
    client, _, _ = _runtime_client(
        "async",
        stream,
        timeouts=RuntimeTimeouts(stream_idle=0.5, stream_total=2.0),
    )
    iterator = _open_runtime_line_stream(
        client,
        budget=StreamBudget.from_timeouts(0.5, hard_timeout=2.0),
    )

    assert await anext(iterator) == "ready"
    with pytest.raises(OutboundRequestError) as exc_info:
        await anext(iterator)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.blocked_read_started.is_set()
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_total_deadline_is_distinct_and_spans_yields() -> None:
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(10.0, hard_timeout=3.0, clock=clock)
    stream = ScriptedAdvancingAsyncStream(
        clock,
        chunks=[(b"a\n", 1.0), (b"a\n", 1.0), (b"a\n", 1.1)],
    )
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client, budget=budget)

    assert await anext(iterator) == "a"
    budget.mark_content()
    assert await anext(iterator) == "a"
    budget.mark_content()
    with pytest.raises(OutboundRequestError) as exc_info:
        await anext(iterator)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_total_deadline_spans_lines_from_one_coalesced_chunk(
) -> None:
    stream = RecordingAsyncStream(body=b"first\nsecond\n")
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(
        client,
        budget=StreamBudget.from_timeouts(1.0, hard_timeout=0.5),
    )

    assert await anext(iterator) == "first"
    await asyncio.sleep(0.55)
    with pytest.raises(OutboundRequestError) as exc_info:
        await anext(iterator)

    assert exc_info.value.code == "outbound_timeout"
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_uses_fresh_hardened_clients_and_closes_success_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    streams = [
        RecordingAsyncStream(body=b"one\n"),
        RecordingAsyncStream(body=b"two\n"),
    ]
    backend = RecordingAsyncBackend(streams)
    policy = RecordingPolicy()
    timeouts = RuntimeTimeouts(
        connect=1.25,
        read=2.5,
        write=3.75,
        pool=4.5,
        stream_idle=5.0,
        stream_total=6.0,
    )
    client = SafeRuntimeClient(
        policy,
        async_network_backend=backend,
        timeouts=timeouts,
    )
    constructor_kwargs: list[dict[str, Any]] = []
    real_async_client = httpx.AsyncClient

    def async_client_factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        constructor_kwargs.append(kwargs.copy())
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(runtime_http.httpx, "AsyncClient", async_client_factory)
    headers = {
        "hOsT": "evil-host-secret",
        "aCcEpT-eNcOdInG": "gzip",
        "Authorization": "Bearer caller-secret",
    }

    assert await _collect_runtime_lines(client, headers=headers) == ["one"]
    assert await _collect_runtime_lines(client, headers=headers) == ["two"]

    assert policy.calls == [
        (VALIDATED_BASE, False),
        (VALIDATED_BASE, False),
    ]
    assert backend.connect_calls == [
        ("93.184.216.34", 443),
        ("93.184.216.34", 443),
    ]
    assert len(constructor_kwargs) == 2
    for kwargs in constructor_kwargs:
        assert kwargs["trust_env"] is False
        assert kwargs["follow_redirects"] is False
        timeout = kwargs["timeout"]
        assert isinstance(timeout, httpx.Timeout)
        assert (timeout.connect, timeout.read, timeout.write, timeout.pool) == (
            1.25,
            None,
            3.75,
            4.5,
        )
    for stream in streams:
        request = _request_bytes(stream).lower()
        assert b"host: public.example\r\n" in request
        assert b"evil-host-secret" not in request
        assert request.count(b"accept-encoding: identity\r\n") == 1
        assert b"accept-encoding: gzip" not in request
        assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_early_aclose_closes_response_client_and_transport_once(
) -> None:
    stream = RecordingAsyncStream(body=b"first\nsecond\n")
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client)

    assert await anext(iterator) == "first"
    await iterator.aclose()

    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_logging_context_is_restored_while_yield_is_paused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    internal_sentinel = "stream-internal-log-must-stay-hidden"
    caller_sentinel = "stream-caller-log-must-stay-visible"

    class InternallyLoggingStream(RecordingAsyncStream):
        async def read(
            self,
            max_bytes: int,
            timeout: float | None = None,
        ) -> bytes:
            if not self._head and self.body_bytes_returned:
                logging.getLogger("httpx").info(internal_sentinel)
            return await super().read(max_bytes, timeout=timeout)

    caplog.set_level(logging.INFO, logger="httpx")
    stream = InternallyLoggingStream(
        body=b"first\nsecond\n",
        body_chunk_size=6,
    )
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client)

    first = await anext(iterator)
    paused_after_first = runtime_http._SUPPRESS_RUNTIME_HTTP_LOGS.get()
    logging.getLogger("httpx").info(caller_sentinel)
    second = await asyncio.create_task(anext(iterator))
    paused_after_second = runtime_http._SUPPRESS_RUNTIME_HTTP_LOGS.get()
    await iterator.aclose()

    assert [first, second] == ["first", "second"]
    assert paused_after_first is False
    assert paused_after_second is False
    assert runtime_http._SUPPRESS_RUNTIME_HTTP_LOGS.get() is False
    assert caller_sentinel in caplog.text
    assert internal_sentinel not in caplog.text
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_can_continue_in_a_different_task_without_context_leak(
) -> None:
    stream = RecordingAsyncStream(
        body=b"first\nsecond\n",
        body_chunk_size=6,
    )
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client)

    first = await asyncio.create_task(anext(iterator))

    async def collect_remaining() -> tuple[list[str], bool]:
        lines = [line async for line in iterator]
        return lines, runtime_http._SUPPRESS_RUNTIME_HTTP_LOGS.get()

    remaining, worker_context = await asyncio.create_task(collect_remaining())

    assert first == "first"
    assert remaining == ["second"]
    assert worker_context is False
    assert runtime_http._SUPPRESS_RUNTIME_HTTP_LOGS.get() is False
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_can_aclose_in_a_different_task_without_context_leak(
) -> None:
    stream = RecordingAsyncStream(body=b"first\nsecond\n")
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client)

    assert await asyncio.create_task(anext(iterator)) == "first"

    async def close_and_read_context() -> bool:
        await iterator.aclose()
        return runtime_http._SUPPRESS_RUNTIME_HTTP_LOGS.get()

    worker_context = await asyncio.create_task(close_and_read_context())

    assert worker_context is False
    assert runtime_http._SUPPRESS_RUNTIME_HTTP_LOGS.get() is False
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_cancel_propagates_and_closes_once() -> None:
    stream = RecordingAsyncStream(body=b"never", block_body=True)
    client, _, _ = _runtime_client("async", stream)
    iterator = _open_runtime_line_stream(client)
    task = asyncio.create_task(anext(iterator))

    await asyncio.wait_for(stream.body_read_started.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_outer_cancellation_survives_failing_cleanup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cancel_sentinel = "stream-outer-cancel-primary"
    cleanup_sentinel = "stream-cancel-cleanup-secret"
    stream = RecordingAsyncStream(
        body=b"never",
        block_body=True,
        close_error=OSError(cleanup_sentinel),
    )
    client, _, _ = _runtime_client("async", stream)
    task = asyncio.create_task(_collect_runtime_lines(client))

    await asyncio.wait_for(stream.body_read_started.wait(), timeout=1.0)
    task.cancel(cancel_sentinel)
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    assert exc_info.value.args == (cancel_sentinel,)
    assert stream.close_count == 1
    assert cleanup_sentinel not in repr(exc_info.value)
    assert cleanup_sentinel not in caplog.text


@pytest.mark.asyncio
async def test_stream_outer_cancellation_survives_cleanup_cancellation() -> None:
    stream = RecordingAsyncStream(
        body=b"never",
        block_body=True,
        close_error=cast(Any, asyncio.CancelledError("inner-cleanup-cancel")),
    )
    client, _, _ = _runtime_client("async", stream)
    task = asyncio.create_task(_collect_runtime_lines(client))

    await asyncio.wait_for(stream.body_read_started.wait(), timeout=1.0)
    task.cancel("outer-cancel")
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await task

    assert exc_info.value.args == ("outer-cancel",)
    assert stream.close_count == 1


@pytest.mark.parametrize(
    ("failure_kind", "expected_code"),
    [
        ("timeout", "outbound_timeout"),
        ("read", "outbound_connect_failed"),
        ("protocol", "outbound_bad_response"),
    ],
    ids=["timeout", "read", "protocol"],
)
@pytest.mark.asyncio
async def test_stream_primary_error_survives_failing_cleanup(
    failure_kind: str,
    expected_code: str,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cleanup_sentinel = f"stream-{expected_code}-cleanup-secret"
    if failure_kind == "protocol":
        stream = RecordingAsyncStream(
            close_error=OSError(cleanup_sentinel),
        )

        def raise_protocol_error(
            response: httpx.Response, max_bytes: int
        ) -> None:
            del response, max_bytes
            raise httpcore.ProtocolError("primary-protocol-error")

        monkeypatch.setattr(
            runtime_http, "_check_response_headers", raise_protocol_error
        )
    else:
        primary_error: BaseException = (
            httpcore.ReadTimeout("primary-timeout")
            if failure_kind == "timeout"
            else httpcore.ReadError("primary-read-error")
        )
        stream = RecordingAsyncStream(
            read_error=cast(Any, primary_error),
            close_error=OSError(cleanup_sentinel),
        )
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(client)

    assert exc_info.value.code == expected_code
    assert stream.close_count == 1
    assert cleanup_sentinel not in repr(exc_info.value)
    assert cleanup_sentinel not in caplog.text


@pytest.mark.asyncio
async def test_stream_cleanup_failure_without_primary_keeps_fixed_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    cleanup_sentinel = "stream-standalone-cleanup-secret"
    stream = RecordingAsyncStream(
        body=b"complete\n",
        close_error=OSError(cleanup_sentinel),
    )
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(client)

    assert exc_info.value.code == "outbound_connect_failed"
    assert stream.close_count == 1
    assert cleanup_sentinel not in repr(exc_info.value)
    assert cleanup_sentinel not in caplog.text


@pytest.mark.asyncio
async def test_stream_base_exception_propagates_unchanged_and_closes_once(
) -> None:
    class FatalStreamSignal(BaseException):
        pass

    signal = FatalStreamSignal("fatal-stream-sentinel")
    stream = RecordingAsyncStream(read_error=cast(Any, signal))
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(FatalStreamSignal) as exc_info:
        await _collect_runtime_lines(client)

    assert exc_info.value is signal
    assert stream.close_count == 1


@pytest.mark.parametrize(
    ("limit_name", "invalid_limit"),
    [
        ("max_bytes", -1),
        ("max_bytes", True),
        ("max_bytes", 1.5),
        ("max_bytes", "8"),
        ("max_event_bytes", -1),
        ("max_event_bytes", True),
        ("max_event_bytes", 1.5),
        ("max_event_bytes", "8"),
    ],
)
@pytest.mark.asyncio
async def test_stream_invalid_limit_types_are_rejected_before_network(
    limit_name: str,
    invalid_limit: Any,
) -> None:
    stream = RecordingAsyncStream()
    client, policy, backend = _runtime_client("async", stream)
    kwargs: dict[str, Any] = {"max_bytes": 8, "max_event_bytes": 8}
    kwargs[limit_name] = invalid_limit

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(client, **kwargs)

    assert exc_info.value.code == "outbound_url_invalid"
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []
    assert stream.close_count == 0


@pytest.mark.parametrize(
    ("idle_timeout", "total_timeout"),
    [(1.0, 3.0), (3.0, 1.0)],
    ids=["idle", "total"],
)
@pytest.mark.asyncio
async def test_stream_timeouts_cover_response_headers(
    idle_timeout: float,
    total_timeout: float,
) -> None:
    stream = RecordingAsyncStream(raw_head=b"", block_body=True)
    client, _, _ = _runtime_client("async", stream)

    with pytest.raises(OutboundRequestError) as exc_info:
        await asyncio.wait_for(
            _collect_runtime_lines(
                client,
                budget=StreamBudget.from_timeouts(
                    idle_timeout, hard_timeout=total_timeout
                ),
            ),
            timeout=2.5,
        )

    assert exc_info.value.code == "outbound_timeout"
    assert stream.body_read_started.is_set()
    assert stream.close_count == 1


@pytest.mark.asyncio
async def test_stream_request_serialization_error_is_fixed_and_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repr_sentinel = "stream-serialization-secret-sentinel"
    secret_type = type(
        repr_sentinel,
        (),
        {"__repr__": lambda self: repr_sentinel},
    )
    stream = RecordingAsyncStream()
    client, policy, backend = _runtime_client("async", stream)
    for logger_name in (
        "httpx",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
    ):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(
            client,
            json_body={"value": secret_type()},
        )

    assert exc_info.value.code == "outbound_bad_response"
    assert repr_sentinel not in repr(exc_info.value)
    assert repr_sentinel not in caplog.text
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []
    assert stream.close_count == 0


@pytest.mark.asyncio
async def test_stream_constructor_failure_closes_new_transport_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructor_sentinel = "stream-client-constructor-secret"
    stream = RecordingAsyncStream()
    client, policy, backend = _runtime_client("async", stream)
    created_transports: list[Any] = []
    real_transport = runtime_http.PinnedAsyncTransport

    class TrackingAsyncTransport(real_transport):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.close_count = 0
            created_transports.append(self)

        async def aclose(self) -> None:
            self.close_count += 1
            await super().aclose()

    def failing_async_client(*args: Any, **kwargs: Any) -> None:
        raise OSError(constructor_sentinel)

    monkeypatch.setattr(
        runtime_http,
        "PinnedAsyncTransport",
        TrackingAsyncTransport,
    )
    monkeypatch.setattr(runtime_http.httpx, "AsyncClient", failing_async_client)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(client)

    assert exc_info.value.code == "outbound_connect_failed"
    assert constructor_sentinel not in repr(exc_info.value)
    assert policy.calls == [(VALIDATED_BASE, False)]
    assert backend.connect_calls == []
    assert len(created_transports) == 1
    assert created_transports[0].close_count == 1


@pytest.mark.asyncio
async def test_stream_error_and_logs_redact_all_sentinels(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinels = {
        "header": "stream-header-secret-sentinel",
        "query": "stream-query-secret-sentinel",
        "body": "stream-body-secret-sentinel",
        "backend": "stream-backend-secret-sentinel",
    }
    stream = RecordingAsyncStream(
        body=b"unread",
        read_error=OSError(sentinels["backend"]),
    )
    client, _, _ = _runtime_client("async", stream)
    for logger_name in (
        "httpx",
        "httpcore.connection",
        "httpcore.http11",
        "httpcore.http2",
        "httpcore.proxy",
        "httpcore.socks",
    ):
        caplog.set_level(logging.DEBUG, logger=logger_name)

    with pytest.raises(OutboundRequestError) as exc_info:
        await _collect_runtime_lines(
            client,
            request_target=(
                VALID_TARGET + "?" + urlencode({"key": sentinels["query"]})
            ),
            headers={"Authorization": "Bearer " + sentinels["header"]},
            json_body={"prompt": sentinels["body"]},
        )

    wire_request = _request_bytes(stream).decode("utf-8")
    assert sentinels["header"] in wire_request
    assert sentinels["query"] in wire_request
    assert sentinels["body"] in wire_request
    for sentinel in sentinels.values():
        assert sentinel not in repr(exc_info.value)
        assert sentinel not in caplog.text
    assert exc_info.value.code == "outbound_connect_failed"
    assert stream.close_count == 1

    outside_sentinel = "outside-stream-log-is-visible"
    logging.getLogger("httpx").info(outside_sentinel)
    assert outside_sentinel in caplog.text
