from __future__ import annotations

import asyncio
import json
import logging
import math
import unicodedata
from collections.abc import AsyncIterator, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit

import httpcore
import httpx

from .bounded_runner import BoundedDaemonRunner, DEFAULT_BOUNDED_RUNNER
from .deadline import DeadlineBudget, DeadlineExpired, StreamBudget
from .outbound_url import (
    OutboundRequestError,
    OutboundURLPolicy,
    ValidatedOutboundURL,
)
from .pinned_transport import PinnedAsyncTransport, PinnedSyncTransport


AI_JSON_MAX_BYTES = 8 * 1024 * 1024
EMBEDDING_JSON_MAX_BYTES = 16 * 1024 * 1024
STREAM_MAX_BYTES = 16 * 1024 * 1024
STREAM_EVENT_MAX_BYTES = 1 * 1024 * 1024

RETRYABLE_OUTBOUND_CODES = frozenset(
    {"outbound_connect_failed", "outbound_timeout"}
)


_SUPPRESS_RUNTIME_HTTP_LOGS: ContextVar[bool] = ContextVar(
    "suppress_runtime_http_logs",
    default=False,
)


class _RuntimeHTTPLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _SUPPRESS_RUNTIME_HTTP_LOGS.get()


_RUNTIME_HTTP_LOG_FILTER = _RuntimeHTTPLogFilter()
for _logger_name in (
    "httpx",
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
):
    logging.getLogger(_logger_name).addFilter(_RUNTIME_HTTP_LOG_FILTER)


@dataclass(frozen=True)
class RuntimeTimeouts:
    connect: float = 10.0
    read: float = 60.0
    write: float = 30.0
    pool: float = 10.0
    stream_idle: float = 120.0
    stream_total: float = 600.0


def _invalid_url() -> OutboundRequestError:
    return OutboundRequestError("outbound_url_invalid", 400, "外部服务地址无效")


def _connect_failed() -> OutboundRequestError:
    return OutboundRequestError("outbound_connect_failed", 502, "外部服务连接失败")


def _response_too_large() -> OutboundRequestError:
    return OutboundRequestError(
        "outbound_response_too_large",
        502,
        "外部服务响应过大",
    )


def _bad_response() -> OutboundRequestError:
    return OutboundRequestError("outbound_bad_response", 502, "外部服务响应无效")


def _timeout() -> OutboundRequestError:
    return OutboundRequestError("outbound_timeout", 504, "外部服务请求超时")


def _validated_request_url(
    validated: ValidatedOutboundURL,
    request_target: str,
) -> str:
    if not isinstance(request_target, str) or not request_target:
        raise _invalid_url()
    if any(
        char.isspace() or unicodedata.category(char) == "Cc"
        for char in request_target
    ):
        raise _invalid_url()
    if "\\" in request_target:
        raise _invalid_url()
    if "#" in request_target:
        raise _invalid_url()
    if not request_target.startswith("/") or request_target.startswith("//"):
        raise _invalid_url()
    try:
        parsed = urlsplit(request_target)
    except (TypeError, ValueError):
        raise _invalid_url() from None
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise _invalid_url()
    if "://" in request_target:
        raise _invalid_url()
    try:
        request_target.encode("utf-8")
    except UnicodeEncodeError:
        raise _invalid_url() from None
    return validated.url.rstrip("/") + request_target


def _request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    request_headers = {
        key: value
        for key, value in headers.items()
        if key.lower() not in ("host", "accept-encoding")
    }
    request_headers["Accept-Encoding"] = "identity"
    return request_headers


def _reject_non_identity_encoding(headers: httpx.Headers) -> None:
    content_encoding = headers.get("Content-Encoding")
    if content_encoding is None:
        return
    encodings = [
        value.strip().lower()
        for value in content_encoding.split(",")
        if value.strip()
    ]
    if not encodings or any(value != "identity" for value in encodings):
        raise _bad_response()


def _reject_oversized_content_length(
    headers: httpx.Headers,
    max_bytes: int,
) -> None:
    content_length = headers.get("Content-Length")
    if content_length is None:
        return
    try:
        declared_length = int(content_length)
    except ValueError:
        raise _bad_response() from None
    if declared_length < 0:
        raise _bad_response()
    if declared_length > max_bytes:
        raise _response_too_large()


def _check_response_headers(response: httpx.Response, max_bytes: int) -> None:
    if not 200 <= response.status_code < 300:
        raise _bad_response()
    _reject_non_identity_encoding(response.headers)
    _reject_oversized_content_length(response.headers, max_bytes)


def _validated_stream_timeout(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _invalid_url()
    try:
        normalized = float(value)
    except (OverflowError, ValueError):
        raise _invalid_url() from None
    if normalized <= 0 or not math.isfinite(normalized):
        raise _invalid_url()
    return normalized


def _parse_json_object(content: bytearray) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        raise _bad_response() from None
    if not isinstance(parsed, dict):
        raise _bad_response()
    return cast(dict[str, Any], parsed)


class _ReadInvocationMarker:
    def __init__(self, response: httpx.Response) -> None:
        identities: set[int] = set()
        current: object | None = response.stream
        while current is not None and id(current) not in identities:
            identities.add(id(current))
            current = getattr(current, "_stream", None)
        self.stream_identities = frozenset(identities)


_CLEANUP_DISPLACED = object()
_CLEANUP_DISPLACED_ATTRIBUTE = "_clade_cleanup_displaced"


def _traceback_references_read_stream(
    error: BaseException,
    marker: _ReadInvocationMarker,
) -> bool:
    traceback = error.__traceback__
    while traceback is not None:
        if any(
            id(value) in marker.stream_identities
            for value in traceback.tb_frame.f_locals.values()
        ):
            return True
        traceback = traceback.tb_next
    return False


def _cleanup_displaced_primary(
    cleanup_error: httpcore.NetworkError,
    marker: _ReadInvocationMarker,
) -> BaseException | None:
    if type(cleanup_error) is not httpcore.NetworkError:
        return None
    delegate_cleanup_error = cleanup_error.__context__
    if delegate_cleanup_error is None:
        return None
    candidate = delegate_cleanup_error.__context__
    if candidate is None:
        return None
    return (
        candidate
        if _traceback_references_read_stream(candidate, marker)
        else None
    )


def _is_sanitized_close_error(error: BaseException) -> bool:
    if type(error) is not httpcore.NetworkError:
        return False
    traceback = error.__traceback__
    while traceback is not None:
        frame = traceback.tb_frame
        if (
            frame.f_globals.get("__name__") == "app.security.pinned_transport"
            and frame.f_code.co_name in {"close", "aclose"}
            and type(frame.f_locals.get("self")).__name__
            in {"_SanitizedNetworkStream", "_SanitizedAsyncNetworkStream"}
        ):
            return True
        traceback = traceback.tb_next
    return False


def _displaced_read_error(
    captured_error: BaseException,
    marker: _ReadInvocationMarker,
) -> BaseException | None:
    primary_error = (
        _cleanup_displaced_primary(captured_error, marker)
        if isinstance(captured_error, httpcore.NetworkError)
        else None
    )
    if primary_error is None and isinstance(
        captured_error, asyncio.CancelledError
    ):
        candidate = captured_error.__context__
        if candidate is not None and _traceback_references_read_stream(
            candidate, marker
        ):
            primary_error = candidate
    if primary_error is None and not _is_sanitized_close_error(captured_error):
        return None
    escaped_error = captured_error if primary_error is None else primary_error
    escaped_error.__traceback__ = None
    escaped_error.__context__ = None
    escaped_error.__cause__ = None
    setattr(
        escaped_error,
        _CLEANUP_DISPLACED_ATTRIBUTE,
        _CLEANUP_DISPLACED,
    )
    return escaped_error


def _clear_displaced_cleanup_artifacts(error: BaseException) -> None:
    chain: list[BaseException] = []
    pending = [error]
    seen: set[int] = set()
    displaced = False
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        chain.append(current)
        displaced = displaced or (
            getattr(current, _CLEANUP_DISPLACED_ATTRIBUTE, None)
            is _CLEANUP_DISPLACED
        )
        if current.__context__ is not None:
            pending.append(current.__context__)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
    if not displaced:
        return
    for current in chain:
        current.__traceback__ = None
        current.__context__ = None
        current.__cause__ = None
        if hasattr(current, _CLEANUP_DISPLACED_ATTRIBUTE):
            delattr(current, _CLEANUP_DISPLACED_ATTRIBUTE)


def _read_sync_json_impl(
    response: httpx.Response,
    max_bytes: int,
    budget: DeadlineBudget,
) -> dict[str, Any]:
    budget.phase_timeout()
    _check_response_headers(response, max_bytes)
    content = bytearray()
    for chunk in response.iter_raw(chunk_size=max_bytes + 1):
        remaining = max_bytes + 1 - len(content)
        content.extend(chunk[:remaining])
        if len(content) > max_bytes or len(chunk) > remaining:
            raise _response_too_large()
        budget.phase_timeout()
    budget.phase_timeout()
    try:
        return _parse_json_object(content)
    finally:
        budget.phase_timeout()


def _read_sync_json(
    response: httpx.Response,
    max_bytes: int,
    budget: DeadlineBudget,
) -> dict[str, Any]:
    marker = _ReadInvocationMarker(response)
    try:
        return _read_sync_json_impl(response, max_bytes, budget)
    except BaseException as exc:
        displaced_error = _displaced_read_error(exc, marker)
        if displaced_error is None:
            del marker
            raise
    del marker
    raise displaced_error from None


async def _read_async_json_impl(
    response: httpx.Response,
    max_bytes: int,
    budget: DeadlineBudget,
) -> dict[str, Any]:
    budget.phase_timeout()
    _check_response_headers(response, max_bytes)
    content = bytearray()
    async for chunk in response.aiter_raw(chunk_size=max_bytes + 1):
        remaining = max_bytes + 1 - len(content)
        content.extend(chunk[:remaining])
        if len(content) > max_bytes or len(chunk) > remaining:
            raise _response_too_large()
        budget.phase_timeout()
    budget.phase_timeout()
    try:
        return _parse_json_object(content)
    finally:
        budget.phase_timeout()


async def _read_async_json(
    response: httpx.Response,
    max_bytes: int,
    budget: DeadlineBudget,
) -> dict[str, Any]:
    marker = _ReadInvocationMarker(response)
    try:
        return await _read_async_json_impl(response, max_bytes, budget)
    except BaseException as exc:
        displaced_error = _displaced_read_error(exc, marker)
        if displaced_error is None:
            del marker
            raise
    del marker
    raise displaced_error from None


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

    def _httpx_timeout(self, budget: DeadlineBudget) -> httpx.Timeout:
        return httpx.Timeout(
            connect=budget.phase_timeout(self._timeouts.connect),
            read=budget.phase_timeout(self._timeouts.read),
            write=budget.phase_timeout(self._timeouts.write),
            pool=budget.phase_timeout(self._timeouts.pool),
        )

    def post_json(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any],
        allow_local: bool,
        budget: DeadlineBudget,
        max_bytes: int = AI_JSON_MAX_BYTES,
    ) -> dict[str, Any]:
        effective_budget = budget
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
        except OutboundRequestError as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise
        except (
            DeadlineExpired,
            TimeoutError,
            httpx.TimeoutException,
            httpcore.TimeoutException,
        ) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _timeout() from None
        except (
            httpx.DecodingError,
            httpx.ProtocolError,
            httpcore.ProtocolError,
        ) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _bad_response() from None
        except (httpx.RequestError, httpcore.NetworkError, OSError) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _connect_failed() from None
        except Exception as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _bad_response() from None
        except BaseException as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise

    def _post_json_impl(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any],
        allow_local: bool,
        max_bytes: int,
        budget: DeadlineBudget,
    ) -> dict[str, Any]:
        token = _SUPPRESS_RUNTIME_HTTP_LOGS.set(True)
        try:
            validated = self._policy.validate(base_url, allow_local=allow_local)
            request_url = _validated_request_url(validated, request_target)
            if (
                not isinstance(max_bytes, int)
                or isinstance(max_bytes, bool)
                or max_bytes < 0
            ):
                raise _invalid_url()
            transport = PinnedSyncTransport(
                validated,
                self._sync_network_backend,
                budget=budget,
            )
            client: httpx.Client | None = None
            primary_error: BaseException | None = None
            response_cleanup_failed = False
            try:
                client = httpx.Client(
                    transport=transport,
                    timeout=self._httpx_timeout(budget),
                    trust_env=False,
                    follow_redirects=False,
                )
                response_context = client.stream(
                    "POST",
                    request_url,
                    headers=_request_headers(headers),
                    json=json_body,
                )
                response: httpx.Response | None = None
                try:
                    response = response_context.__enter__()
                    result = _read_sync_json(response, max_bytes, budget)
                except BaseException as exc:
                    if response is None:
                        raise
                    if response.is_closed:
                        response_cleanup_failed = True
                    else:
                        try:
                            response_context.__exit__(
                                type(exc),
                                exc,
                                exc.__traceback__,
                            )
                        except BaseException:
                            response_cleanup_failed = True
                    raise
                else:
                    try:
                        response_context.__exit__(None, None, None)
                    except BaseException:
                        response_cleanup_failed = True
                        raise
                    return result
            except BaseException as exc:
                primary_error = exc
                raise
            finally:
                if not response_cleanup_failed:
                    try:
                        if client is None:
                            transport.close()
                        else:
                            client.close()
                    except BaseException:
                        if primary_error is None:
                            raise
                if primary_error is None:
                    budget.phase_timeout()
        finally:
            _SUPPRESS_RUNTIME_HTTP_LOGS.reset(token)

    async def apost_json(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any],
        allow_local: bool,
        budget: DeadlineBudget,
        max_bytes: int = AI_JSON_MAX_BYTES,
    ) -> dict[str, Any]:
        effective_budget = budget
        token = _SUPPRESS_RUNTIME_HTTP_LOGS.set(True)
        try:
            validated = await self._runner.arun(
                lambda: self._policy.validate(
                    base_url,
                    allow_local=allow_local,
                ),
                timeout=effective_budget.phase_timeout(),
            )
            request_url = _validated_request_url(validated, request_target)
            if (
                not isinstance(max_bytes, int)
                or isinstance(max_bytes, bool)
                or max_bytes < 0
            ):
                raise _invalid_url()
            async with asyncio.timeout(effective_budget.phase_timeout()):
                transport = PinnedAsyncTransport(
                    validated,
                    self._async_network_backend,
                    budget=effective_budget,
                )
                client: httpx.AsyncClient | None = None
                primary_error: BaseException | None = None
                response_cleanup_failed = False
                try:
                    client = httpx.AsyncClient(
                        transport=transport,
                        timeout=self._httpx_timeout(effective_budget),
                        trust_env=False,
                        follow_redirects=False,
                    )
                    response_context = client.stream(
                        "POST",
                        request_url,
                        headers=_request_headers(headers),
                        json=json_body,
                    )
                    response: httpx.Response | None = None
                    try:
                        response = await response_context.__aenter__()
                        result = await _read_async_json(
                            response,
                            max_bytes,
                            effective_budget,
                        )
                    except BaseException as exc:
                        if response is None:
                            raise
                        if response.is_closed:
                            response_cleanup_failed = True
                        else:
                            try:
                                await response_context.__aexit__(
                                    type(exc),
                                    exc,
                                    exc.__traceback__,
                                )
                            except BaseException:
                                response_cleanup_failed = True
                        raise
                    else:
                        try:
                            await response_context.__aexit__(None, None, None)
                        except BaseException:
                            response_cleanup_failed = True
                            raise
                        return result
                except BaseException as exc:
                    primary_error = exc
                    raise
                finally:
                    if not response_cleanup_failed:
                        try:
                            if client is None:
                                await transport.aclose()
                            else:
                                await client.aclose()
                        except BaseException:
                            if primary_error is None:
                                raise
                    if primary_error is None:
                        effective_budget.phase_timeout()
                    if (
                        getattr(
                            primary_error,
                            _CLEANUP_DISPLACED_ATTRIBUTE,
                            None,
                        )
                        is _CLEANUP_DISPLACED
                    ):
                        transport = None
                        client = None
                        response_context = None
                        response = None
                        result = None
                        primary_error = None
        except OutboundRequestError as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise
        except asyncio.CancelledError as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise
        except (
            DeadlineExpired,
            TimeoutError,
            httpx.TimeoutException,
            httpcore.TimeoutException,
        ) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _timeout() from None
        except (
            httpx.DecodingError,
            httpx.ProtocolError,
            httpcore.ProtocolError,
        ) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _bad_response() from None
        except (httpx.RequestError, httpcore.NetworkError, OSError) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _connect_failed() from None
        except Exception as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _bad_response() from None
        except BaseException as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise
        finally:
            _SUPPRESS_RUNTIME_HTTP_LOGS.reset(token)

    async def astream_lines(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any],
        allow_local: bool,
        budget: StreamBudget,
        max_bytes: int = STREAM_MAX_BYTES,
        max_event_bytes: int = STREAM_EVENT_MAX_BYTES,
    ) -> AsyncIterator[str]:
        effective_budget = budget
        token = _SUPPRESS_RUNTIME_HTTP_LOGS.set(True)
        try:
            validated = await self._runner.arun(
                lambda: self._policy.validate(
                    base_url,
                    allow_local=allow_local,
                ),
                timeout=effective_budget.phase_timeout(),
            )
            effective_budget.phase_timeout()
            request_url = _validated_request_url(validated, request_target)
            if (
                not isinstance(max_bytes, int)
                or isinstance(max_bytes, bool)
                or max_bytes < 0
                or not isinstance(max_event_bytes, int)
                or isinstance(max_event_bytes, bool)
                or max_event_bytes < 0
            ):
                raise _invalid_url()
            effective_budget.phase_timeout()
            transport = PinnedAsyncTransport(
                validated,
                self._async_network_backend,
                budget=effective_budget,
            )
            client: httpx.AsyncClient | None = None
            primary_error: BaseException | None = None
            response_cleanup_failed = False
            try:
                client = httpx.AsyncClient(
                    transport=transport,
                    timeout=httpx.Timeout(
                        connect=effective_budget.phase_timeout(
                            self._timeouts.connect
                        ),
                        read=None,
                        write=effective_budget.phase_timeout(
                            self._timeouts.write
                        ),
                        pool=effective_budget.phase_timeout(self._timeouts.pool),
                    ),
                    trust_env=False,
                    follow_redirects=False,
                )
                response_context = client.stream(
                    "POST",
                    request_url,
                    headers=_request_headers(headers),
                    json=json_body,
                )
                response: httpx.Response | None = None
                try:
                    try:
                        async with asyncio.timeout(
                            effective_budget.phase_timeout()
                        ):
                            response = await response_context.__aenter__()
                        effective_budget.phase_timeout()
                        _check_response_headers(response, max_bytes)
                        iterator = response.aiter_raw().__aiter__()
                        marker = _ReadInvocationMarker(response)
                        try:
                            line_buffer = bytearray()
                            total_bytes = 0

                            while True:
                                try:
                                    async with asyncio.timeout(
                                        effective_budget.phase_timeout()
                                    ):
                                        chunk = await iterator.__anext__()
                                except StopAsyncIteration:
                                    break
                                effective_budget.phase_timeout()

                                total_bytes += len(chunk)
                                if total_bytes > max_bytes:
                                    raise _response_too_large()

                                offset = 0
                                while offset < len(chunk):
                                    newline = chunk.find(b"\n", offset)
                                    segment_end = (
                                        len(chunk) if newline < 0 else newline
                                    )
                                    segment_length = segment_end - offset
                                    accumulator_room = (
                                        max_event_bytes + 1 - len(line_buffer)
                                    )
                                    copy_length = min(
                                        segment_length, accumulator_room
                                    )
                                    if copy_length:
                                        line_buffer.extend(
                                            chunk[offset : offset + copy_length]
                                        )
                                    if (
                                        segment_length > accumulator_room
                                        or len(line_buffer) > max_event_bytes
                                    ):
                                        raise _response_too_large()
                                    if newline < 0:
                                        break

                                    raw_line = bytes(line_buffer)
                                    line_buffer.clear()
                                    if raw_line.endswith(b"\r"):
                                        raw_line = raw_line[:-1]
                                    effective_budget.phase_timeout()
                                    line = raw_line.decode(
                                        "utf-8", errors="strict"
                                    )
                                    _SUPPRESS_RUNTIME_HTTP_LOGS.reset(token)
                                    token = None
                                    try:
                                        yield line
                                    finally:
                                        token = _SUPPRESS_RUNTIME_HTTP_LOGS.set(
                                            True
                                        )
                                    offset = newline + 1

                            if line_buffer:
                                if len(line_buffer) > max_event_bytes:
                                    raise _response_too_large()
                                raw_line = bytes(line_buffer)
                                if raw_line.endswith(b"\r"):
                                    raw_line = raw_line[:-1]
                                effective_budget.phase_timeout()
                                line = raw_line.decode(
                                    "utf-8", errors="strict"
                                )
                                _SUPPRESS_RUNTIME_HTTP_LOGS.reset(token)
                                token = None
                                try:
                                    yield line
                                finally:
                                    token = _SUPPRESS_RUNTIME_HTTP_LOGS.set(
                                        True
                                    )
                        except BaseException as exc:
                            displaced_error = _displaced_read_error(exc, marker)
                            if displaced_error is None:
                                del marker
                                raise
                            del marker
                            raise displaced_error from None
                        else:
                            del marker
                    except BaseException as exc:
                        if response is None:
                            raise
                        if response.is_closed:
                            response_cleanup_failed = True
                        else:
                            try:
                                await response_context.__aexit__(
                                    type(exc), exc, exc.__traceback__
                                )
                            except BaseException:
                                response_cleanup_failed = True
                        raise
                    else:
                        try:
                            await response_context.__aexit__(None, None, None)
                        except BaseException:
                            response_cleanup_failed = True
                            raise
                except BaseException as exc:
                    primary_error = exc
                    raise
                finally:
                    if not response_cleanup_failed:
                        try:
                            if client is None:
                                await transport.aclose()
                            else:
                                await client.aclose()
                        except BaseException:
                            if primary_error is None:
                                raise
            except BaseException:
                if client is None:
                    try:
                        await transport.aclose()
                    except BaseException:
                        pass
                raise
        except OutboundRequestError as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise
        except asyncio.CancelledError as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise
        except (
            DeadlineExpired,
            TimeoutError,
            httpx.TimeoutException,
            httpcore.TimeoutException,
        ) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _timeout() from None
        except (
            httpx.DecodingError,
            httpx.ProtocolError,
            httpcore.ProtocolError,
        ) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _bad_response() from None
        except (httpx.RequestError, httpcore.NetworkError, OSError) as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _connect_failed() from None
        except Exception as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise _bad_response() from None
        except BaseException as exc:
            _clear_displaced_cleanup_artifacts(exc)
            raise
        finally:
            if token is not None:
                _SUPPRESS_RUNTIME_HTTP_LOGS.reset(token)
