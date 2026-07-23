from __future__ import annotations

import logging
import ssl
import threading
import time
import tracemalloc
import zlib
from collections.abc import Callable
from ipaddress import ip_address
from typing import Any

import httpcore
import pytest

from app.security.bounded_runner import BoundedDaemonRunner
from app.security.outbound_url import (
    OutboundRequestError,
    OutboundURLPolicy,
    ValidatedOutboundURL,
)
from app.security.pinned_transport import _PinnedNetworkBackend
from app.security.safe_http import (
    CONNECTION_TEST_TIMEOUTS,
    MODEL_LIST_MAX_BYTES,
    MODEL_LIST_TIMEOUTS,
    ProbeTimeouts,
    SafeProbeClient,
)


class FakeResolver:
    def __init__(
        self,
        answers: dict[str, list[str]],
        *,
        before_answer: Callable[[], None] | None = None,
    ) -> None:
        self.answers = answers
        self.before_answer = before_answer
        self.calls: list[tuple[str, int]] = []

    def __call__(self, hostname: str, port: int):
        self.calls.append((hostname, port))
        if self.before_answer is not None:
            self.before_answer()
        answer = self.answers.get(hostname)
        if answer is None:
            raise OSError("resolver-secret-must-not-leak")
        return tuple(ip_address(value) for value in answer)


class CannedHTTPStream(httpcore.NetworkStream):
    def __init__(
        self,
        headers: bytes,
        body_chunks: list[bytes] | None = None,
        *,
        read_delay: float = 0.0,
        read_error: Exception | None = None,
        write_error: Exception | None = None,
    ) -> None:
        self._chunks: list[tuple[bool, bytes]] = [(False, headers)]
        self._chunks.extend((True, chunk) for chunk in (body_chunks or []))
        self.read_delay = read_delay
        self.read_error = read_error
        self.write_error = write_error
        self.request_bytes = bytearray()
        self.tls_server_names: list[str | None] = []
        self.ssl_contexts: list[ssl.SSLContext] = []
        self.body_bytes_read = 0
        self.close_count = 0

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if self.read_error is not None:
            raise self.read_error
        if not self._chunks:
            return b""
        is_body, chunk = self._chunks[0]
        if is_body and self.read_delay:
            time.sleep(self.read_delay)
        result = chunk[:max_bytes]
        remainder = chunk[max_bytes:]
        if remainder:
            self._chunks[0] = (is_body, remainder)
        else:
            self._chunks.pop(0)
        if is_body:
            self.body_bytes_read += len(result)
        return result

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.request_bytes.extend(buffer)
        if self.write_error is not None:
            raise self.write_error

    def close(self) -> None:
        self.close_count += 1

    def start_tls(
        self,
        ssl_context: Any,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        self.ssl_contexts.append(ssl_context)
        self.tls_server_names.append(server_hostname)
        return self


class RecordingBackend(httpcore.NetworkBackend):
    def __init__(
        self,
        stream: CannedHTTPStream,
        *,
        connect_errors: list[Exception] | None = None,
    ) -> None:
        self.stream = stream
        self.connect_errors = list(connect_errors or [])
        self.connect_calls: list[tuple[str, int, float | None]] = []

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        self.connect_calls.append((host, port, timeout))
        if self.connect_errors:
            raise self.connect_errors.pop(0)
        return self.stream

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        raise AssertionError("unix sockets are never allowed")

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _response_headers(
    status: int = 200,
    *,
    content_length: int | None = 0,
    extra: bytes = b"",
) -> bytes:
    reason = b"OK" if status == 200 else b"Found"
    result = b"HTTP/1.1 " + str(status).encode() + b" " + reason + b"\r\n"
    if content_length is not None:
        result += b"Content-Length: " + str(content_length).encode() + b"\r\n"
    return result + extra + b"\r\n"


def _public_policy() -> OutboundURLPolicy:
    return OutboundURLPolicy(
        resolver=FakeResolver({"public.example": ["93.184.216.34"]})
    )


def _local_policy() -> OutboundURLPolicy:
    return OutboundURLPolicy(resolver=FakeResolver({"localhost": ["127.0.0.1"]}))


def test_timeout_contract_constants_are_locked() -> None:
    assert CONNECTION_TEST_TIMEOUTS == ProbeTimeouts(5.0, 5.0, 5.0, 5.0, 10.0)
    assert MODEL_LIST_TIMEOUTS == ProbeTimeouts(5.0, 10.0, 5.0, 5.0, 15.0)
    assert MODEL_LIST_MAX_BYTES == 1_048_576


def test_pinned_backend_connects_to_approved_ip_not_original_hostname() -> None:
    stream = CannedHTTPStream(_response_headers())
    delegate = RecordingBackend(stream)
    validated = ValidatedOutboundURL(
        url="https://public.example/v1",
        scheme="https",
        hostname="public.example",
        port=443,
        resolved_ips=(ip_address("93.184.216.34"),),
        is_local=False,
    )

    backend = _PinnedNetworkBackend(validated, delegate)
    assert backend.connect_tcp("public.example", 443) is stream

    assert delegate.connect_calls == [("93.184.216.34", 443, None)]
    assert all(call[0] != "public.example" for call in delegate.connect_calls)


def test_pinned_backend_retries_only_the_next_approved_ip() -> None:
    stream = CannedHTTPStream(_response_headers())
    delegate = RecordingBackend(
        stream, connect_errors=[httpcore.ConnectError("first approved IP failed")]
    )
    validated = ValidatedOutboundURL(
        url="https://public.example/v1",
        scheme="https",
        hostname="public.example",
        port=443,
        resolved_ips=(ip_address("93.184.216.34"), ip_address("8.8.8.8")),
        is_local=False,
    )

    result = _PinnedNetworkBackend(validated, delegate).connect_tcp(
        "public.example", 443
    )

    assert result is stream
    assert [call[0] for call in delegate.connect_calls] == [
        "93.184.216.34",
        "8.8.8.8",
    ]


def test_pinned_backend_rejects_unexpected_origin_and_unix_socket() -> None:
    stream = CannedHTTPStream(_response_headers())
    delegate = RecordingBackend(stream)
    validated = ValidatedOutboundURL(
        url="https://public.example/v1",
        scheme="https",
        hostname="public.example",
        port=443,
        resolved_ips=(ip_address("93.184.216.34"),),
        is_local=False,
    )
    backend = _PinnedNetworkBackend(validated, delegate)

    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("attacker.example", 443)
    with pytest.raises(httpcore.ConnectError):
        backend.connect_tcp("public.example", 444)
    with pytest.raises(httpcore.ConnectError):
        backend.connect_unix_socket("/tmp/secret.sock")
    assert delegate.connect_calls == []


def test_transport_preserves_original_host_header_and_tls_server_name() -> None:
    stream = CannedHTTPStream(_response_headers())
    backend = RecordingBackend(stream)
    resolver = FakeResolver({"public.example": ["93.184.216.34"]})
    client = SafeProbeClient(
        policy=OutboundURLPolicy(resolver=resolver), network_backend=backend
    )

    assert client.probe_status(
        "https://public.example/v1",
        endpoint="models",
        headers={"hOsT": "attacker.invalid"},
        allow_local=False,
    ) == 200

    assert b"Host: public.example\r\n" in stream.request_bytes
    assert b"attacker.invalid" not in stream.request_bytes
    assert b"GET /v1/models HTTP/1.1\r\n" in stream.request_bytes
    assert stream.tls_server_names == ["public.example"]
    assert stream.ssl_contexts[0].check_hostname is True
    assert stream.ssl_contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert backend.connect_calls[0][0:2] == ("93.184.216.34", 443)
    assert resolver.calls == [("public.example", 443)]


def test_transport_preserves_nondefault_port_in_host_header() -> None:
    stream = CannedHTTPStream(_response_headers())
    backend = RecordingBackend(stream)
    client = SafeProbeClient(policy=_local_policy(), network_backend=backend)

    assert client.probe_status(
        "http://localhost:11434/v1/",
        endpoint="messages",
        headers={},
        allow_local=True,
    ) == 200

    assert b"Host: localhost:11434\r\n" in stream.request_bytes
    assert b"GET /v1/messages HTTP/1.1\r\n" in stream.request_bytes
    assert backend.connect_calls[0][0:2] == ("127.0.0.1", 11434)


def test_probe_disables_environment_proxy_and_redirect_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-sentinel.invalid")
    stream = CannedHTTPStream(
        _response_headers(
            302,
            extra=b"Location: https://redirect-secret.invalid/steal\r\n",
        )
    )
    backend = RecordingBackend(stream)
    client = SafeProbeClient(policy=_public_policy(), network_backend=backend)

    status = client.probe_status(
        "https://public.example/v1",
        endpoint="models",
        headers={},
        allow_local=False,
    )

    assert status == 302
    assert [call[0] for call in backend.connect_calls] == ["93.184.216.34"]
    assert "proxy-sentinel.invalid" not in repr(backend.connect_calls)
    assert "redirect-secret.invalid" not in repr(backend.connect_calls)


def test_probe_json_response_is_public_and_immutable() -> None:
    import app.security as security

    result_type = security.ProbeJSONResponse
    result = result_type(status_code=200, data={"ok": True})

    assert result.status_code == 200
    assert result.data == {"ok": True}
    with pytest.raises(AttributeError):
        result.status_code = 201


def test_fetch_json_response_non_200_skips_body_and_closes_one_request() -> None:
    stream = CannedHTTPStream(
        _response_headers(status=401, content_length=2_000_000),
        [b"upstream-body-secret-must-not-be-read"],
    )
    backend = RecordingBackend(stream)
    client = SafeProbeClient(policy=_public_policy(), network_backend=backend)

    result = client.fetch_json_response(
        "https://public.example/v1",
        endpoint="models",
        headers={"Authorization": "Bearer header-secret"},
        allow_local=False,
    )

    assert result.status_code == 401
    assert result.data is None
    assert stream.body_bytes_read == 0
    assert stream.close_count == 1
    assert stream.request_bytes.count(b"GET /v1/models HTTP/1.1\r\n") == 1
    assert len(backend.connect_calls) == 1


def test_fetch_json_response_200_uses_existing_bounded_json_contract() -> None:
    body = b'{"data":[{"id":"model-1"}]}'
    stream = CannedHTTPStream(
        _response_headers(content_length=len(body)),
        [body],
    )
    backend = RecordingBackend(stream)
    client = SafeProbeClient(policy=_public_policy(), network_backend=backend)

    result = client.fetch_json_response(
        "https://public.example/v1",
        endpoint="models",
        headers={},
        allow_local=False,
    )

    assert result.status_code == 200
    assert result.data == {"data": [{"id": "model-1"}]}
    assert stream.body_bytes_read == len(body)
    assert stream.close_count == 1
    assert stream.request_bytes.count(b"GET /v1/models HTTP/1.1\r\n") == 1
    assert len(backend.connect_calls) == 1


def test_fetch_json_keeps_dict_contract_and_maps_non_200_to_bad_response() -> None:
    stream = CannedHTTPStream(
        _response_headers(status=503, content_length=2_000_000),
        [b"upstream-body-secret-must-not-be-read"],
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )

    assert exc_info.value.code == "outbound_bad_response"
    assert stream.body_bytes_read == 0
    assert stream.close_count == 1


def test_fetch_json_rejects_content_length_over_exact_one_mib() -> None:
    stream = CannedHTTPStream(
        _response_headers(content_length=MODEL_LIST_MAX_BYTES + 1),
        [b"body-secret-must-not-be-read"],
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )

    assert exc_info.value.code == "outbound_response_too_large"
    assert stream.body_bytes_read == 0
    assert stream.close_count == 1


def test_fetch_json_cannot_raise_the_fixed_one_mib_limit() -> None:
    oversized_body = b"x" * (MODEL_LIST_MAX_BYTES + 1)
    stream = CannedHTTPStream(
        _response_headers(content_length=len(oversized_body)), [oversized_body]
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
            max_bytes=MODEL_LIST_MAX_BYTES * 2,
        )

    assert exc_info.value.code == "outbound_response_too_large"
    assert stream.body_bytes_read == 0
    assert stream.close_count == 1


def test_fetch_json_stops_after_one_mib_plus_one_without_content_length() -> None:
    body_chunks = [b"x" * 65_536 for _ in range(16)] + [b"!"]
    stream = CannedHTTPStream(
        _response_headers(content_length=None, extra=b"Connection: close\r\n"),
        body_chunks,
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )

    assert exc_info.value.code == "outbound_response_too_large"
    assert stream.body_bytes_read <= MODEL_LIST_MAX_BYTES + 1
    assert stream.body_bytes_read == MODEL_LIST_MAX_BYTES + 1
    assert stream.close_count == 1


def test_fetch_json_accepts_exact_limit_and_requires_an_object() -> None:
    padding = MODEL_LIST_MAX_BYTES - len(b'{"value":""}')
    exact_body = b'{"value":"' + (b"x" * padding) + b'"}'
    assert len(exact_body) == MODEL_LIST_MAX_BYTES
    exact_stream = CannedHTTPStream(
        _response_headers(content_length=len(exact_body)), [exact_body]
    )
    exact_client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(exact_stream)
    )

    result = exact_client.fetch_json(
        "https://public.example/v1",
        endpoint="models",
        headers={},
        allow_local=False,
    )

    assert result == {"value": "x" * padding}
    list_body = b"[]"
    list_stream = CannedHTTPStream(
        _response_headers(content_length=len(list_body)), [list_body]
    )
    list_client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(list_stream)
    )
    with pytest.raises(OutboundRequestError) as exc_info:
        list_client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )
    assert exc_info.value.code == "outbound_bad_response"


def test_probe_status_closes_without_consuming_response_body() -> None:
    stream = CannedHTTPStream(
        _response_headers(content_length=2 * 1024 * 1024),
        [b"sentinel" * (2 * 1024 * 1024 // len(b"sentinel"))],
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    status = client.probe_status(
        "https://public.example/v1",
        endpoint="models",
        headers={},
        allow_local=False,
    )

    assert status == 200
    assert stream.body_bytes_read == 0
    assert stream.close_count == 1


def test_total_deadline_includes_dns_and_body_read() -> None:
    tiny = ProbeTimeouts(1.0, 1.0, 1.0, 1.0, 0.03)
    dns_runner = BoundedDaemonRunner(max_workers=4)
    dns_policy = OutboundURLPolicy(
        resolver=FakeResolver(
            {"public.example": ["93.184.216.34"]},
            before_answer=lambda: time.sleep(0.2),
        )
    )
    dns_client = SafeProbeClient(
        policy=dns_policy,
        network_backend=RecordingBackend(CannedHTTPStream(_response_headers())),
        runner=dns_runner,
        connection_timeouts=tiny,
    )
    started = time.monotonic()
    with pytest.raises(OutboundRequestError) as dns_error:
        dns_client.probe_status(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )
    dns_elapsed = time.monotonic() - started

    body_runner = BoundedDaemonRunner(max_workers=4)
    body = b'{"ok":true}'
    body_stream = CannedHTTPStream(
        _response_headers(content_length=len(body)),
        [body],
        read_delay=0.2,
    )
    body_client = SafeProbeClient(
        policy=_public_policy(),
        network_backend=RecordingBackend(body_stream),
        runner=body_runner,
        model_list_timeouts=tiny,
    )
    started = time.monotonic()
    with pytest.raises(OutboundRequestError) as body_error:
        body_client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )
    body_elapsed = time.monotonic() - started

    assert dns_error.value.code == "outbound_timeout"
    assert body_error.value.code == "outbound_timeout"
    assert dns_elapsed < 1.0
    assert body_elapsed < 1.0
    assert dns_runner.max_active <= 4
    assert body_runner.max_active <= 4


def test_bounded_runner_never_starts_more_than_four_blocked_workers() -> None:
    runner = BoundedDaemonRunner(max_workers=4)
    release = threading.Event()
    barrier = threading.Barrier(7)
    errors: list[str] = []

    def caller() -> None:
        barrier.wait()
        try:
            runner.run(lambda: release.wait(0.5), timeout=0.03)
        except TimeoutError:
            errors.append("timeout")

    callers = [threading.Thread(target=caller) for _ in range(6)]
    for caller_thread in callers:
        caller_thread.start()
    barrier.wait()
    for caller_thread in callers:
        caller_thread.join(timeout=0.5)
    release.set()

    assert errors == ["timeout"] * 6
    assert runner.max_active == 4


def test_errors_and_logs_never_contain_headers_query_or_response_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    header_secret = "authorization-secret-sentinel"
    query_secret = "query-secret-sentinel"
    body_secret = "body-secret-sentinel"
    errors: list[OutboundRequestError] = []

    query_client = SafeProbeClient(
        policy=_public_policy(),
        network_backend=RecordingBackend(CannedHTTPStream(_response_headers())),
    )
    with pytest.raises(OutboundRequestError) as query_error:
        query_client.probe_status(
            f"https://public.example/v1?token={query_secret}",
            endpoint="models",
            headers={"Authorization": f"Bearer {header_secret}"},
            allow_local=False,
        )
    errors.append(query_error.value)

    read_stream = CannedHTTPStream(
        _response_headers(), read_error=OSError(header_secret)
    )
    read_client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(read_stream)
    )
    with pytest.raises(OutboundRequestError) as read_error:
        read_client.probe_status(
            "https://public.example/v1",
            endpoint="models",
            headers={"Authorization": f"Bearer {header_secret}"},
            allow_local=False,
        )
    errors.append(read_error.value)

    body = body_secret.encode()
    body_stream = CannedHTTPStream(
        _response_headers(content_length=len(body)), [body]
    )
    body_client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(body_stream)
    )
    with pytest.raises(OutboundRequestError) as body_error:
        body_client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={"Authorization": f"Bearer {header_secret}"},
            allow_local=False,
        )
    errors.append(body_error.value)

    combined = "\n".join(str(error) for error in errors) + caplog.text
    assert header_secret not in combined
    assert query_secret not in combined
    assert body_secret not in combined
    assert [error.code for error in errors] == [
        "outbound_url_invalid",
        "outbound_connect_failed",
        "outbound_bad_response",
    ]


def test_malformed_http_body_never_reaches_errors_or_debug_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    body_secret = "malformed-chunk-body-secret"
    stream = CannedHTTPStream(
        _response_headers(
            content_length=None, extra=b"Transfer-Encoding: chunked\r\n"
        ),
        [f"not-hex-{body_secret}\r\n".encode()],
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )

    assert exc_info.value.code == "outbound_bad_response"
    assert body_secret not in str(exc_info.value)
    assert body_secret not in caplog.text


def test_malformed_http_header_never_reaches_errors_or_debug_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    header_secret = "malformed-header-secret"
    stream = CannedHTTPStream(
        b"HTTP/1.1 200 OK\r\nBad Header "
        + header_secret.encode()
        + b"\r\n\r\n"
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )

    assert exc_info.value.code == "outbound_bad_response"
    assert header_secret not in str(exc_info.value)
    assert header_secret not in caplog.text


def test_invalid_content_encoding_maps_to_fixed_bad_response() -> None:
    body = b"not-a-valid-gzip-stream"
    stream = CannedHTTPStream(
        _response_headers(
            content_length=len(body), extra=b"Content-Encoding: gzip\r\n"
        ),
        [body],
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.fetch_json(
            "https://public.example/v1",
            endpoint="models",
            headers={},
            allow_local=False,
        )

    assert exc_info.value.code == "outbound_bad_response"


def test_valid_compression_bomb_is_rejected_before_body_read_or_large_decode() -> None:
    compressor = zlib.compressobj(wbits=31)
    one_mib = b"x" * MODEL_LIST_MAX_BYTES
    encoded_body = b"".join(compressor.compress(one_mib) for _ in range(16))
    encoded_body += compressor.flush()
    assert len(encoded_body) < 20_000

    stream = CannedHTTPStream(
        _response_headers(
            content_length=len(encoded_body), extra=b"Content-Encoding: gzip\r\n"
        ),
        [encoded_body],
    )
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    tracemalloc.start()
    try:
        with pytest.raises(OutboundRequestError) as exc_info:
            client.fetch_json(
                "https://public.example/v1",
                endpoint="models",
                headers={"Accept-Encoding": "gzip"},
                allow_local=False,
            )
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert exc_info.value.code == "outbound_bad_response"
    assert stream.body_bytes_read == 0
    assert stream.close_count == 1
    assert b"Accept-Encoding: identity\r\n" in stream.request_bytes
    assert b"Accept-Encoding: gzip\r\n" not in stream.request_bytes
    assert peak_bytes < 8 * MODEL_LIST_MAX_BYTES


def test_endpoint_is_restricted_to_controlled_tail() -> None:
    stream = CannedHTTPStream(_response_headers())
    client = SafeProbeClient(
        policy=_public_policy(), network_backend=RecordingBackend(stream)
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        client.probe_status(
            "https://public.example/v1",
            endpoint="https://attacker.invalid/steal",  # type: ignore[arg-type]
            headers={},
            allow_local=False,
        )

    assert exc_info.value.code == "outbound_url_invalid"
    assert stream.request_bytes == b""
