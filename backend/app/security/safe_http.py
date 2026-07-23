from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar, cast

import httpcore
import httpx

from .bounded_runner import DEFAULT_BOUNDED_RUNNER
from .outbound_url import (
    OutboundRequestError,
    OutboundURLPolicy,
    ValidatedOutboundURL,
)
from .pinned_transport import PinnedSyncTransport


Endpoint = Literal["models", "messages"]
T = TypeVar("T")


_LOG_CONTEXT = threading.local()


class _SafeProbeTraceFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not bool(getattr(_LOG_CONTEXT, "suppress_httpcore_trace", False))


_TRACE_FILTER = _SafeProbeTraceFilter()
for _logger_name in (
    "httpcore.connection",
    "httpcore.http11",
    "httpcore.http2",
    "httpcore.proxy",
    "httpcore.socks",
):
    logging.getLogger(_logger_name).addFilter(_TRACE_FILTER)


@dataclass(frozen=True)
class ProbeTimeouts:
    connect: float
    read: float
    write: float
    pool: float
    total: float


@dataclass(frozen=True)
class ProbeJSONResponse:
    status_code: int
    data: dict[str, Any] | None


CONNECTION_TEST_TIMEOUTS = ProbeTimeouts(5.0, 5.0, 5.0, 5.0, 10.0)
MODEL_LIST_TIMEOUTS = ProbeTimeouts(5.0, 10.0, 5.0, 5.0, 15.0)
MODEL_LIST_MAX_BYTES = 1_048_576


def _invalid_url() -> OutboundRequestError:
    return OutboundRequestError("outbound_url_invalid", 400, "外部服务地址无效")


def _connect_failed() -> OutboundRequestError:
    return OutboundRequestError("outbound_connect_failed", 502, "外部服务连接失败")


def _response_too_large() -> OutboundRequestError:
    return OutboundRequestError(
        "outbound_response_too_large", 502, "外部服务响应过大"
    )


def _bad_response() -> OutboundRequestError:
    return OutboundRequestError("outbound_bad_response", 502, "外部服务响应无效")


def _timeout() -> OutboundRequestError:
    return OutboundRequestError("outbound_timeout", 504, "外部服务请求超时")


class _Runner(Protocol):
    def run(self, operation: Callable[[], T], *, timeout: float) -> T: ...


_DEFAULT_RUNNER = DEFAULT_BOUNDED_RUNNER


class SafeProbeClient:
    def __init__(
        self,
        policy: OutboundURLPolicy | None = None,
        *,
        network_backend: httpcore.NetworkBackend | None = None,
        runner: _Runner | None = None,
        connection_timeouts: ProbeTimeouts = CONNECTION_TEST_TIMEOUTS,
        model_list_timeouts: ProbeTimeouts = MODEL_LIST_TIMEOUTS,
    ) -> None:
        self._policy = OutboundURLPolicy() if policy is None else policy
        self._network_backend = (
            httpcore.SyncBackend() if network_backend is None else network_backend
        )
        self._runner = _DEFAULT_RUNNER if runner is None else runner
        self._connection_timeouts = connection_timeouts
        self._model_list_timeouts = model_list_timeouts

    def probe_status(
        self,
        base_url: str,
        *,
        endpoint: Literal["models", "messages"],
        headers: Mapping[str, str],
        allow_local: bool,
    ) -> int:
        return self._run_with_deadline(
            lambda: self._probe_status(
                base_url,
                endpoint=endpoint,
                headers=headers,
                allow_local=allow_local,
                timeouts=self._connection_timeouts,
            ),
            self._connection_timeouts.total,
        )

    def fetch_json(
        self,
        base_url: str,
        *,
        endpoint: Literal["models", "messages"],
        headers: Mapping[str, str],
        allow_local: bool,
        max_bytes: int = MODEL_LIST_MAX_BYTES,
    ) -> dict[str, Any]:
        response = self.fetch_json_response(
            base_url,
            endpoint=endpoint,
            headers=headers,
            allow_local=allow_local,
            max_bytes=max_bytes,
        )
        if response.status_code != 200 or response.data is None:
            raise _bad_response()
        return response.data

    def fetch_json_response(
        self,
        base_url: str,
        *,
        endpoint: Literal["models", "messages"],
        headers: Mapping[str, str],
        allow_local: bool,
        max_bytes: int = MODEL_LIST_MAX_BYTES,
    ) -> ProbeJSONResponse:
        return self._run_with_deadline(
            lambda: self._fetch_json_response(
                base_url,
                endpoint=endpoint,
                headers=headers,
                allow_local=allow_local,
                max_bytes=max_bytes,
                timeouts=self._model_list_timeouts,
            ),
            self._model_list_timeouts.total,
        )

    def _run_with_deadline(self, operation: Callable[[], T], total: float) -> T:
        def guarded_operation() -> T:
            previous = bool(
                getattr(_LOG_CONTEXT, "suppress_httpcore_trace", False)
            )
            _LOG_CONTEXT.suppress_httpcore_trace = True
            try:
                return operation()
            finally:
                _LOG_CONTEXT.suppress_httpcore_trace = previous

        try:
            return self._runner.run(guarded_operation, timeout=total)
        except OutboundRequestError:
            raise
        except (TimeoutError, httpx.TimeoutException, httpcore.TimeoutException):
            raise _timeout() from None
        except (httpx.DecodingError, httpx.ProtocolError, httpcore.ProtocolError):
            raise _bad_response() from None
        except (
            httpx.RequestError,
            httpcore.NetworkError,
            OSError,
        ):
            raise _connect_failed() from None

    def _validated_endpoint(
        self,
        base_url: str,
        *,
        endpoint: Endpoint,
        allow_local: bool,
    ) -> tuple[ValidatedOutboundURL, str]:
        if endpoint not in ("models", "messages"):
            raise _invalid_url()
        validated = self._policy.validate(base_url, allow_local=allow_local)
        request_url = f"{validated.url.rstrip('/')}/{endpoint}"
        return validated, request_url

    def _client(
        self,
        validated: ValidatedOutboundURL,
        timeouts: ProbeTimeouts,
    ) -> httpx.Client:
        return httpx.Client(
            transport=PinnedSyncTransport(validated, self._network_backend),
            timeout=httpx.Timeout(
                connect=timeouts.connect,
                read=timeouts.read,
                write=timeouts.write,
                pool=timeouts.pool,
            ),
            trust_env=False,
            follow_redirects=False,
        )

    @staticmethod
    def _request_headers(headers: Mapping[str, str]) -> dict[str, str]:
        request_headers = {
            key: value
            for key, value in headers.items()
            if key.lower() not in ("host", "accept-encoding")
        }
        request_headers["Accept-Encoding"] = "identity"
        return request_headers

    def _probe_status(
        self,
        base_url: str,
        *,
        endpoint: Endpoint,
        headers: Mapping[str, str],
        allow_local: bool,
        timeouts: ProbeTimeouts,
    ) -> int:
        validated, request_url = self._validated_endpoint(
            base_url, endpoint=endpoint, allow_local=allow_local
        )
        client = self._client(validated, timeouts)
        try:
            with client.stream(
                "GET", request_url, headers=self._request_headers(headers)
            ) as response:
                return response.status_code
        finally:
            client.close()

    def _fetch_json_response(
        self,
        base_url: str,
        *,
        endpoint: Endpoint,
        headers: Mapping[str, str],
        allow_local: bool,
        max_bytes: int,
        timeouts: ProbeTimeouts,
    ) -> ProbeJSONResponse:
        if max_bytes < 0:
            raise _invalid_url()
        max_bytes = min(max_bytes, MODEL_LIST_MAX_BYTES)
        validated, request_url = self._validated_endpoint(
            base_url, endpoint=endpoint, allow_local=allow_local
        )
        client = self._client(validated, timeouts)
        try:
            with client.stream(
                "GET", request_url, headers=self._request_headers(headers)
            ) as response:
                if response.status_code != 200:
                    return ProbeJSONResponse(
                        status_code=response.status_code,
                        data=None,
                    )

                content_encoding = response.headers.get("Content-Encoding")
                if content_encoding is not None:
                    encodings = [
                        value.strip().lower()
                        for value in content_encoding.split(",")
                        if value.strip()
                    ]
                    if not encodings or any(
                        value != "identity" for value in encodings
                    ):
                        raise _bad_response()

                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except ValueError:
                        raise _bad_response() from None
                    if declared_length < 0:
                        raise _bad_response()
                    if declared_length > max_bytes:
                        raise _response_too_large()

                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=max_bytes + 1):
                    remaining = max_bytes + 1 - len(content)
                    content.extend(chunk[:remaining])
                    if len(content) > max_bytes or len(chunk) > remaining:
                        raise _response_too_large()
                try:
                    parsed = json.loads(content)
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    raise _bad_response() from None
                if not isinstance(parsed, dict):
                    raise _bad_response()
                return ProbeJSONResponse(
                    status_code=200,
                    data=cast(dict[str, Any], parsed),
                )
        finally:
            client.close()
