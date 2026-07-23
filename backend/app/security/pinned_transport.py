from __future__ import annotations

import ssl
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpcore
import httpx

from .deadline import DeadlineExpired, TimeoutBudget
from .outbound_url import ValidatedOutboundURL


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


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(
        self,
        validated: ValidatedOutboundURL,
        delegate: httpcore.NetworkBackend,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        self._validated = validated
        self._delegate = delegate
        self._budget = budget

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        if host != self._validated.hostname or port != self._validated.port:
            raise httpcore.ConnectError("outbound origin does not match approval")

        last_error: BaseException | None = None
        for approved_ip in self._validated.resolved_ips:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ConnectTimeout,
            )
            try:
                return self._delegate.connect_tcp(
                    str(approved_ip),
                    port,
                    timeout=bounded_timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_error = exc
        raise httpcore.ConnectError("all approved addresses failed") from last_error

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    def sleep(self, seconds: float) -> None:
        self._delegate.sleep(seconds)


class _PinnedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        validated: ValidatedOutboundURL,
        delegate: httpcore.AsyncNetworkBackend,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        self._validated = validated
        self._delegate = delegate
        self._budget = budget

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        if host != self._validated.hostname or port != self._validated.port:
            raise httpcore.ConnectError("outbound origin does not match approval")

        last_error: BaseException | None = None
        for approved_ip in self._validated.resolved_ips:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ConnectTimeout,
            )
            try:
                return await self._delegate.connect_tcp(
                    str(approved_ip),
                    port,
                    timeout=bounded_timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_error = exc
        raise httpcore.ConnectError("all approved addresses failed") from last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class _SanitizedNetworkStream(httpcore.NetworkStream):
    """Prevent delegate exception details from reaching httpcore trace logs."""

    def __init__(
        self,
        delegate: httpcore.NetworkStream,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        self._delegate = delegate
        self._budget = budget

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ReadTimeout,
            )
            return self._delegate.read(max_bytes, timeout=bounded_timeout)
        except httpcore.ReadTimeout:
            raise httpcore.ReadTimeout("outbound read timed out") from None
        except Exception:
            raise httpcore.ReadError("outbound read failed") from None

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.WriteTimeout,
            )
            self._delegate.write(buffer, timeout=bounded_timeout)
        except httpcore.WriteTimeout:
            raise httpcore.WriteTimeout("outbound write timed out") from None
        except Exception:
            raise httpcore.WriteError("outbound write failed") from None

    def close(self) -> None:
        try:
            self._delegate.close()
        except Exception:
            raise httpcore.NetworkError("outbound close failed") from None

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ConnectTimeout,
            )
            stream = self._delegate.start_tls(
                ssl_context,
                server_hostname=server_hostname,
                timeout=bounded_timeout,
            )
        except httpcore.ConnectTimeout:
            raise httpcore.ConnectTimeout("outbound TLS timed out") from None
        except Exception:
            raise httpcore.ConnectError("outbound TLS failed") from None
        return _SanitizedNetworkStream(stream, budget=self._budget)


class _SanitizedAsyncNetworkStream(httpcore.AsyncNetworkStream):
    """Prevent delegate exception details from reaching httpcore trace logs."""

    def __init__(
        self,
        delegate: httpcore.AsyncNetworkStream,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        self._delegate = delegate
        self._budget = budget

    async def read(
        self, max_bytes: int, timeout: float | None = None
    ) -> bytes:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ReadTimeout,
            )
            return await self._delegate.read(
                max_bytes, timeout=bounded_timeout
            )
        except httpcore.ReadTimeout:
            raise httpcore.ReadTimeout("outbound read timed out") from None
        except Exception:
            raise httpcore.ReadError("outbound read failed") from None

    async def write(
        self, buffer: bytes, timeout: float | None = None
    ) -> None:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.WriteTimeout,
            )
            await self._delegate.write(buffer, timeout=bounded_timeout)
        except httpcore.WriteTimeout:
            raise httpcore.WriteTimeout("outbound write timed out") from None
        except Exception:
            raise httpcore.WriteError("outbound write failed") from None

    async def aclose(self) -> None:
        try:
            await self._delegate.aclose()
        except Exception:
            raise httpcore.NetworkError("outbound close failed") from None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ConnectTimeout,
            )
            stream = await self._delegate.start_tls(
                ssl_context,
                server_hostname=server_hostname,
                timeout=bounded_timeout,
            )
        except httpcore.ConnectTimeout:
            raise httpcore.ConnectTimeout("outbound TLS timed out") from None
        except Exception:
            raise httpcore.ConnectError("outbound TLS failed") from None
        return _SanitizedAsyncNetworkStream(stream, budget=self._budget)


class _SanitizedNetworkBackend(httpcore.NetworkBackend):
    def __init__(
        self,
        delegate: httpcore.NetworkBackend,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        self._delegate = delegate
        self._budget = budget

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ConnectTimeout,
            )
            stream = self._delegate.connect_tcp(
                host,
                port,
                timeout=bounded_timeout,
                local_address=local_address,
                socket_options=socket_options,
            )
        except httpcore.ConnectTimeout:
            raise httpcore.ConnectTimeout("outbound connect timed out") from None
        except Exception:
            raise httpcore.ConnectError("outbound connect failed") from None
        return _SanitizedNetworkStream(stream, budget=self._budget)

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    def sleep(self, seconds: float) -> None:
        self._delegate.sleep(seconds)


class _SanitizedAsyncNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        delegate: httpcore.AsyncNetworkBackend,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        self._delegate = delegate
        self._budget = budget

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            bounded_timeout = _bounded_timeout(
                self._budget,
                timeout,
                timeout_error=httpcore.ConnectTimeout,
            )
            stream = await self._delegate.connect_tcp(
                host,
                port,
                timeout=bounded_timeout,
                local_address=local_address,
                socket_options=socket_options,
            )
        except httpcore.ConnectTimeout:
            raise httpcore.ConnectTimeout("outbound connect timed out") from None
        except Exception:
            raise httpcore.ConnectError("outbound connect failed") from None
        return _SanitizedAsyncNetworkStream(stream, budget=self._budget)

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


class _CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def __iter__(self) -> Iterator[bytes]:
        yield from self._stream

    def close(self) -> None:
        self._stream.close()


class _CoreAsyncResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: Any) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


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

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != self._validated.scheme:
            raise httpcore.ConnectError("outbound origin does not match approval")

        extensions = request.extensions.copy()
        extensions.pop("sni_hostname", None)
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=extensions,
        )
        core_response = self._pool.handle_request(core_request)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=_CoreResponseStream(core_response.stream),
            extensions=core_response.extensions,
        )

    def close(self) -> None:
        self._pool.close()


class PinnedAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        validated: ValidatedOutboundURL,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
        *,
        budget: TimeoutBudget | None = None,
    ) -> None:
        delegate = (
            httpcore.AnyIOBackend()
            if network_backend is None
            else network_backend
        )
        self._validated = validated
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            retries=0,
            network_backend=_SanitizedAsyncNetworkBackend(
                _PinnedAsyncNetworkBackend(validated, delegate, budget=budget),
                budget=budget,
            ),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != self._validated.scheme:
            raise httpcore.ConnectError("outbound origin does not match approval")

        extensions = request.extensions.copy()
        extensions.pop("sni_hostname", None)
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=extensions,
        )
        core_response = await self._pool.handle_async_request(core_request)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=_CoreAsyncResponseStream(core_response.stream),
            extensions=core_response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()
