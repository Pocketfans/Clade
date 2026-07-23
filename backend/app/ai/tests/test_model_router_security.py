import ast
import asyncio
import json
import logging
import re
import threading
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, urlencode

import httpx
import pytest

from app.ai import model_router as model_router_module
from app.ai.model_router import (
    PROVIDER_TYPE_ANTHROPIC,
    PROVIDER_TYPE_GOOGLE,
    PROVIDER_TYPE_OPENAI,
    ModelConfig,
    ModelRouter,
    ProviderPoolConfig,
)
from app.core.ai_router_config import configure_model_router
from app.models.config import ProviderConfig, UIConfig
from app.security import (
    AI_JSON_MAX_BYTES,
    DeadlineBudget,
    STREAM_EVENT_MAX_BYTES,
    STREAM_MAX_BYTES,
    OutboundRequestError,
)
from app.security.deadline import StreamBudget


PUBLIC_BLOCKED = "That network address is not allowed"
PUBLIC_CONNECT_FAILED = "The upstream service could not be reached"
PUBLIC_TIMEOUT = "The upstream request timed out"
PRIMARY_RESPONSE_ERROR = "AI response error"
UPSTREAM_STREAM_ERROR = "AI stream response error"


class ForbiddenAsyncResponseContext:
    async def __aenter__(self) -> None:
        raise httpx.ConnectError("DIRECT_HTTPX_FORBIDDEN")

    async def __aexit__(self, *args: object) -> None:
        return None


class ForbiddenAsyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "ForbiddenAsyncClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("DIRECT_HTTPX_FORBIDDEN")

    def stream(self, *args: object, **kwargs: object) -> ForbiddenAsyncResponseContext:
        return ForbiddenAsyncResponseContext()


class ForbiddenSyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("DIRECT_HTTPX_FORBIDDEN")


@pytest.fixture(autouse=True)
def forbid_direct_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_request(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("DIRECT_HTTPX_FORBIDDEN")

    for verb in (
        "delete",
        "get",
        "head",
        "options",
        "patch",
        "post",
        "put",
        "request",
        "stream",
    ):
        monkeypatch.setattr(httpx, verb, forbidden_request)
    monkeypatch.setattr(httpx, "Client", ForbiddenSyncClient)
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenAsyncClient)


class RecordingAsyncLines(AsyncIterator[str]):
    def __init__(
        self,
        lines: list[str] | None = None,
        error: BaseException | None = None,
        close_error: BaseException | None = None,
        block_on_exhaustion: bool = False,
    ) -> None:
        self._lines = iter(lines or [])
        self._error = error
        self._close_error = close_error
        self._block_on_exhaustion = block_on_exhaustion
        self._raised_error = False
        self.next_started = asyncio.Event()
        self.next_release = asyncio.Event()
        self.close_count = 0
        self.iter_count = 0

    def __aiter__(self) -> "RecordingAsyncLines":
        self.iter_count += 1
        return self

    async def __anext__(self) -> str:
        try:
            return next(self._lines)
        except StopIteration:
            if self._error is not None and not self._raised_error:
                self._raised_error = True
                raise self._error
            if self._block_on_exhaustion:
                self.next_started.set()
                await self.next_release.wait()
            raise StopAsyncIteration from None

    async def aclose(self) -> None:
        self.close_count += 1
        if self._close_error is not None:
            raise self._close_error


class RecordingSafeRuntimeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.sync_results: list[dict[str, Any] | BaseException] = []
        self.async_results: list[dict[str, Any] | BaseException] = []
        self.stream_lines: list[str] = []
        self.stream_error: BaseException | None = None
        self.stream_close_error: BaseException | None = None
        self.stream_block_on_exhaustion = False
        self.stream_iterator: RecordingAsyncLines | None = None
        self.on_sync_call: Callable[[int], None] | None = None
        self.on_async_call: Callable[[int], None] | None = None
        self.async_started: asyncio.Event | None = None
        self.async_release: asyncio.Event | None = None

    @staticmethod
    def _provider_type(headers: dict[str, str]) -> str:
        if "x-api-key" in headers:
            return PROVIDER_TYPE_ANTHROPIC
        if "Authorization" in headers:
            return PROVIDER_TYPE_OPENAI
        return PROVIDER_TYPE_GOOGLE

    def _record(self, method: str, base_url: str, **kwargs: Any) -> None:
        self.calls.append(
            {
                "method": method,
                "base_url": base_url,
                "provider_type": self._provider_type(dict(kwargs["headers"])),
                **kwargs,
            }
        )

    @staticmethod
    def _next_result(results: list[dict[str, Any] | BaseException]) -> dict[str, Any]:
        result = results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def post_json(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        allow_local: bool,
        budget: DeadlineBudget,
        max_bytes: int,
    ) -> dict[str, Any]:
        self._record(
            "post_json",
            base_url,
            request_target=request_target,
            headers=headers,
            json_body=json_body,
            allow_local=allow_local,
            budget=budget,
            max_bytes=max_bytes,
        )
        if self.on_sync_call is not None:
            self.on_sync_call(len(self.calls))
        return self._next_result(self.sync_results)

    async def apost_json(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        allow_local: bool,
        budget: DeadlineBudget,
        max_bytes: int,
    ) -> dict[str, Any]:
        self._record(
            "apost_json",
            base_url,
            request_target=request_target,
            headers=headers,
            json_body=json_body,
            allow_local=allow_local,
            budget=budget,
            max_bytes=max_bytes,
        )
        if self.on_async_call is not None:
            self.on_async_call(len(self.calls))
        if self.async_started is not None:
            self.async_started.set()
        if self.async_release is not None:
            await self.async_release.wait()
        return self._next_result(self.async_results)

    def astream_lines(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        allow_local: bool,
        budget: StreamBudget,
        max_bytes: int,
        max_event_bytes: int,
    ) -> AsyncIterator[str]:
        self._record(
            "astream_lines",
            base_url,
            request_target=request_target,
            headers=headers,
            json_body=json_body,
            allow_local=allow_local,
            budget=budget,
            max_bytes=max_bytes,
            max_event_bytes=max_event_bytes,
        )
        self.stream_iterator = RecordingAsyncLines(
            self.stream_lines,
            self.stream_error,
            self.stream_close_error,
            self.stream_block_on_exhaustion,
        )
        return self.stream_iterator


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class AdvancingRuntimeClient(RecordingSafeRuntimeClient):
    def __init__(
        self,
        clock: ManualClock,
        outcomes: list[tuple[float, dict[str, Any] | BaseException]],
    ) -> None:
        super().__init__()
        self._clock = clock
        self._outcomes = outcomes

    async def apost_json(
        self,
        base_url: str,
        *,
        request_target: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        allow_local: bool,
        budget: DeadlineBudget,
        max_bytes: int,
    ) -> dict[str, Any]:
        self._record(
            "apost_json",
            base_url,
            request_target=request_target,
            headers=headers,
            json_body=json_body,
            allow_local=allow_local,
            budget=budget,
            max_bytes=max_bytes,
        )
        advance, outcome = self._outcomes.pop(0)
        self._clock.advance(advance)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class ExplodingSemaphore:
    def __init__(self) -> None:
        self.release_count = 0

    async def acquire(self) -> None:
        raise RuntimeError("ACQUIRE-SENTINEL")

    def release(self) -> None:
        self.release_count += 1


@pytest.fixture
def router() -> ModelRouter:
    runtime_client = RecordingSafeRuntimeClient()
    router = ModelRouter(api_key="GLOBAL", runtime_client=runtime_client)
    assert router._runtime_client is runtime_client
    return router


def test_provider_request_location_for_openai_without_version_suffix(router: ModelRouter) -> None:
    assert router._provider_request_location(
        PROVIDER_TYPE_OPENAI,
        "https://public.example/",
        "model",
        "/chat/completions",
        api_key="selected-key",
        stream=False,
    ) == ("https://public.example", "/v1/chat/completions")


def test_provider_request_location_for_openai_with_version_suffix(router: ModelRouter) -> None:
    assert router._provider_request_location(
        PROVIDER_TYPE_OPENAI,
        "https://public.example/v1/",
        "model",
        "/chat/completions",
        api_key="selected-key",
        stream=False,
    ) == ("https://public.example/v1", "/chat/completions")


def test_provider_request_location_keeps_custom_openai_endpoint(router: ModelRouter) -> None:
    assert router._provider_request_location(
        PROVIDER_TYPE_OPENAI,
        "https://public.example/v1/",
        "model",
        "/custom/chat?format=json",
        api_key="selected-key",
        stream=False,
    ) == ("https://public.example/v1", "/custom/chat?format=json")


def test_provider_request_location_for_anthropic(router: ModelRouter) -> None:
    assert router._provider_request_location(
        PROVIDER_TYPE_ANTHROPIC,
        "https://public.example/",
        "model",
        None,
        api_key="selected-key",
        stream=False,
    ) == ("https://public.example", "/messages")


@pytest.mark.parametrize(
    ("stream", "action"),
    [(False, "generateContent"), (True, "streamGenerateContent")],
)
def test_provider_request_location_for_google_escapes_model_and_key(
    router: ModelRouter, caplog: pytest.LogCaptureFixture, stream: bool, action: str
) -> None:
    model_name = "gemini/2 ?#\u2603"
    selected_api_key = "SELECTED+&="

    with caplog.at_level(logging.DEBUG):
        base_url, request_target = router._provider_request_location(
            PROVIDER_TYPE_GOOGLE,
            "https://public.example/v1/",
            model_name,
            None,
            api_key=selected_api_key,
            stream=stream,
        )

    assert base_url == "https://public.example/v1"
    assert request_target == (
        f"/models/{quote(model_name, safe='')}:{action}?"
        f"{urlencode({'key': selected_api_key})}"
    )
    assert model_name not in request_target
    assert selected_api_key not in request_target
    assert "GLOBAL" not in request_target
    assert request_target not in caplog.text
    assert selected_api_key not in caplog.text
    assert "GLOBAL" not in caplog.text


def _remote_router(
    runtime_client: RecordingSafeRuntimeClient,
    *,
    provider_type: str = PROVIDER_TYPE_OPENAI,
    base_url: str = "https://default.example/api",
    api_key: str = "default-key",
    timeout: int = 17,
    max_retries: int = 3,
    allow_local: bool = True,
) -> ModelRouter:
    router = ModelRouter(
        defaults={
            "generate": ModelConfig(
                provider=provider_type,
                model="default-model",
                provider_type=provider_type,
                extra_body={"temperature": 0},
            )
        },
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        runtime_client=runtime_client,
        allow_local_ai_endpoints=allow_local,
    )
    router.set_prompt("generate", "Answer for {name}")
    return router


def _assert_json_call(
    call: dict[str, Any],
    *,
    method: str,
    base_url: str,
    request_target: str,
    provider_type: str,
    timeout: float,
    allow_local: bool,
) -> None:
    assert call["method"] == method
    assert call["base_url"] == base_url
    assert call["request_target"] == request_target
    assert call["provider_type"] == provider_type
    assert isinstance(call["budget"], DeadlineBudget)
    assert 0 < call["budget"].remaining() <= timeout
    assert call["max_bytes"] == AI_JSON_MAX_BYTES
    assert call["allow_local"] is allow_local


def test_invoke_uses_safe_sync_client_and_preserves_parsing() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    raw = {"choices": [{"message": {"content": '```json\n{"answer": 7}\n```'}}]}
    runtime_client.sync_results = [raw]
    router = _remote_router(runtime_client)

    result = router.invoke("generate", {"name": "oak"})

    assert result == {
        "provider": PROVIDER_TYPE_OPENAI,
        "model": "default-model",
        "prompt": "Answer for oak",
        "payload": {"name": "oak"},
        "content": {"answer": 7},
        "raw": raw,
    }
    assert len(runtime_client.calls) == 1
    call = runtime_client.calls[0]
    _assert_json_call(
        call,
        method="post_json",
        base_url="https://default.example/api",
        request_target="/v1/chat/completions",
        provider_type=PROVIDER_TYPE_OPENAI,
        timeout=17,
        allow_local=True,
    )
    assert call["headers"] == {"Authorization": "Bearer default-key"}
    assert call["json_body"] == {
        "model": "default-model",
        "messages": [
            {"role": "system", "content": "Answer for oak"},
            {
                "role": "user",
                "content": json.dumps({"name": "oak"}, ensure_ascii=False, indent=2),
            },
        ],
        "temperature": 0,
    }


def test_constructor_base_url_from_settings_uses_the_same_safe_client() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.sync_results = [
        {"choices": [{"message": {"content": "constructor route"}}]}
    ]
    router = _remote_router(
        runtime_client,
        base_url="https://settings.example/v1/",
        api_key="settings-key",
    )

    assert router.invoke("generate", {"name": "fir"})["content"] == "constructor route"

    assert len(runtime_client.calls) == 1
    assert runtime_client.calls[0]["base_url"] == "https://settings.example/v1"
    assert runtime_client.calls[0]["request_target"] == "/chat/completions"
    assert runtime_client.calls[0]["headers"] == {
        "Authorization": "Bearer settings-key"
    }


def test_invoke_blocked_url_returns_only_public_error() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.sync_results = [
        OutboundRequestError("private_network_blocked", 400, PUBLIC_BLOCKED)
    ]
    router = _remote_router(runtime_client)

    result = router.invoke("generate", {"name": "oak"})

    assert result["error"] == PUBLIC_BLOCKED
    assert len(runtime_client.calls) == 1


def test_invoke_uses_business_start_local_policy_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.sync_results = [
        {"choices": [{"message": {"content": "snapshot"}}]}
    ]
    router = _remote_router(runtime_client, allow_local=True)
    original_prepare = router._prepare_request

    def prepare_then_change_policy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        request = original_prepare(*args, **kwargs)
        router.allow_local_ai_endpoints = False
        return request

    monkeypatch.setattr(router, "_prepare_request", prepare_then_change_policy)

    assert router.invoke("generate", {"name": "oak"})["content"] == "snapshot"
    assert runtime_client.calls[0]["allow_local"] is True


def test_ainvoke_revalidates_on_every_retry_for_same_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.async_results = [
        OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT),
        OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT),
        {
            "candidates": [
                {"content": {"parts": [{"text": '{"answer": "cedar"}'}]}}
            ]
        },
    ]
    router = _remote_router(runtime_client, allow_local=False)
    router.configure_load_balance(True)
    router.set_provider_pool(
        "generate",
        [
            ProviderPoolConfig(
                provider_id="selected-google",
                base_url="https://pool.example/v1beta",
                api_key="selected+key",
                provider_type=PROVIDER_TYPE_GOOGLE,
                model="gemini pool/model",
            ),
            ProviderPoolConfig(
                provider_id="must-not-select",
                base_url="https://other.example/v1",
                api_key="other-key",
                provider_type=PROVIDER_TYPE_OPENAI,
                model="other-model",
            ),
        ],
    )
    runtime_client.on_async_call = lambda count: setattr(
        router, "allow_local_ai_endpoints", count >= 1
    )

    async def no_backoff(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_backoff)

    result = asyncio.run(router.ainvoke("generate", {"name": "cedar"}))

    assert result["content"] == {"answer": "cedar"}
    assert router._lb_counters["generate"] == 1
    assert len(runtime_client.calls) == 3
    expected_target = (
        "/models/gemini%20pool%2Fmodel:generateContent?"
        + urlencode({"key": "selected+key"})
    )
    for call in runtime_client.calls:
        _assert_json_call(
            call,
            method="apost_json",
            base_url="https://pool.example/v1beta",
            request_target=expected_target,
            provider_type=PROVIDER_TYPE_GOOGLE,
            timeout=17,
            allow_local=False,
        )
        assert call["headers"] == {"Content-Type": "application/json", "Connection": "close"}
        assert call["json_body"]["contents"][0]["role"] == "user"
        assert "generationConfig" not in call["json_body"]


def test_ainvoke_unsafe_selected_pool_provider_does_not_fail_over() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.async_results = [
        OutboundRequestError("private_network_blocked", 400, PUBLIC_BLOCKED)
    ]
    router = _remote_router(runtime_client, allow_local=False)
    router.configure_load_balance(True)
    router.set_provider_pool(
        "generate",
        [
            ProviderPoolConfig(
                provider_id="unsafe-selected",
                base_url="https://unsafe.example/v1",
                api_key="unsafe-key",
                model="selected-model",
            ),
            ProviderPoolConfig(
                provider_id="safe-but-must-not-fail-over",
                base_url="https://safe.example/v1",
                api_key="safe-key",
                model="other-model",
            ),
        ],
    )

    result = asyncio.run(router.ainvoke("generate", {"name": "oak"}))

    assert result["error"] == PUBLIC_BLOCKED
    assert len(runtime_client.calls) == 1
    assert runtime_client.calls[0]["base_url"] == "https://unsafe.example/v1"
    assert router._lb_counters["generate"] == 1


@pytest.mark.parametrize(
    "entry_name",
    ["invoke", "ainvoke", "call_capability", "acall_capability", "chat"],
)
def test_normal_entries_pass_same_budget_object_to_runtime(entry_name: str) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    response = {"choices": [{"message": {"content": "oak"}}]}
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    router = _remote_router(runtime_client, allow_local=False)
    budget = DeadlineBudget.from_timeout(30.0)

    if entry_name == "invoke":
        router.invoke("generate", {"name": "oak"}, budget=budget)
    elif entry_name == "ainvoke":
        asyncio.run(router.ainvoke("generate", {"name": "oak"}, budget=budget))
    elif entry_name == "call_capability":
        router.call_capability("generate", _messages(), budget=budget)
    elif entry_name == "acall_capability":
        asyncio.run(
            router.acall_capability("generate", _messages(), budget=budget)
        )
    else:
        asyncio.run(
            router.chat("Name a tree", capability="generate", budget=budget)
        )

    assert len(runtime_client.calls) == 1
    assert runtime_client.calls[0]["budget"] is budget


@pytest.mark.parametrize(
    "entry_name",
    ["invoke", "ainvoke", "call_capability", "acall_capability", "chat"],
)
def test_normal_entry_parsing_cannot_finish_after_total_budget(
    entry_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(1.0, clock=clock)
    runtime_client = RecordingSafeRuntimeClient()
    response = {"choices": [{"message": {"content": "oak"}}]}
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    router = _remote_router(
        runtime_client, max_retries=1, allow_local=False
    )
    router.configure_load_balance(True)
    router.set_provider_pool(
        "generate",
        [
            ProviderPoolConfig(
                provider_id="selected-provider",
                base_url="https://pool.example/v1",
                api_key="pool-key",
                model="pool-model",
            )
        ],
    )
    monkeypatch.setattr(model_router_module.time, "monotonic", clock)

    if entry_name in {"invoke", "ainvoke"}:
        real_parser = router._parse_content

        def advancing_parser(content: str) -> Any:
            result = real_parser(content)
            clock.advance(1.0)
            return result

        monkeypatch.setattr(router, "_parse_content", advancing_parser)
    else:
        real_extractor = router._extract_capability_content

        def advancing_extractor(
            data: dict[str, Any], provider_type: str, capability: str
        ) -> str:
            result = real_extractor(data, provider_type, capability)
            clock.advance(1.0)
            return result

        monkeypatch.setattr(
            router, "_extract_capability_content", advancing_extractor
        )

    if entry_name == "invoke":
        result = router.invoke("generate", {"name": "oak"}, budget=budget)
        assert result["error"] == PUBLIC_TIMEOUT
        assert "content" not in result and "raw" not in result
    elif entry_name == "ainvoke":
        result = asyncio.run(
            router.ainvoke("generate", {"name": "oak"}, budget=budget)
        )
        assert result["error"] == PUBLIC_TIMEOUT
        assert "content" not in result and "raw" not in result
    elif entry_name == "call_capability":
        with pytest.raises(RuntimeError, match=PUBLIC_TIMEOUT):
            router.call_capability("generate", _messages(), budget=budget)
    elif entry_name == "acall_capability":
        with pytest.raises(RuntimeError, match=PUBLIC_TIMEOUT):
            asyncio.run(
                router.acall_capability(
                    "generate", _messages(), budget=budget
                )
            )
    else:
        with pytest.raises(RuntimeError, match=PUBLIC_TIMEOUT):
            asyncio.run(
                router.chat(
                    "Name a tree", capability="generate", budget=budget
                )
            )

    assert len(runtime_client.calls) == 1
    assert runtime_client.calls[0]["budget"] is budget
    diagnostics = router.get_diagnostics()
    stats = diagnostics["request_stats"]["generate"]
    assert diagnostics["total_requests"] == 1
    assert diagnostics["total_timeouts"] == 1
    assert stats["total"] == 1
    assert stats["timeout"] == 1
    assert stats["success"] == 0
    assert stats["error"] == 0
    assert router._provider_latencies == {}


@pytest.mark.parametrize(
    "entry_name",
    ["invoke", "ainvoke", "call_capability", "acall_capability", "chat"],
)
def test_normal_entry_preparation_is_inside_total_budget(
    entry_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    response = {"choices": [{"message": {"content": "must-not-run"}}]}
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    router = _remote_router(
        runtime_client, timeout=0.001, max_retries=1, allow_local=False
    )
    clock = ManualClock()
    original_resolve = router.resolve
    original_from_timeout = DeadlineBudget.from_timeout

    def from_timeout(
        cls: type[DeadlineBudget],
        timeout: float,
        *,
        started_at: float | None = None,
        clock_arg: Callable[[], float] | None = None,
    ) -> DeadlineBudget:
        del cls, clock_arg
        return original_from_timeout(
            timeout, started_at=started_at, clock=clock
        )

    def slow_resolve(capability: str) -> ModelConfig:
        clock.advance(0.01)
        return original_resolve(capability)

    monkeypatch.setattr(model_router_module.time, "monotonic", clock)
    monkeypatch.setattr(
        DeadlineBudget, "from_timeout", classmethod(from_timeout)
    )
    monkeypatch.setattr(router, "resolve", slow_resolve)

    if entry_name == "invoke":
        result = router.invoke("generate", {"name": "oak"})
        assert result["error"] == PUBLIC_TIMEOUT
    elif entry_name == "ainvoke":
        result = asyncio.run(router.ainvoke("generate", {"name": "oak"}))
        assert result["error"] == PUBLIC_TIMEOUT
    elif entry_name == "call_capability":
        with pytest.raises(RuntimeError, match=PUBLIC_TIMEOUT):
            router.call_capability("generate", _messages())
    elif entry_name == "acall_capability":
        with pytest.raises(RuntimeError, match=PUBLIC_TIMEOUT):
            asyncio.run(router.acall_capability("generate", _messages()))
    else:
        with pytest.raises(RuntimeError, match=PUBLIC_TIMEOUT):
            asyncio.run(router.chat("Name a tree", capability="generate"))

    assert runtime_client.calls == []


def test_ainvoke_queue_wait_is_inside_total_budget() -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        router = _remote_router(
            runtime_client, timeout=0.02, max_retries=3, allow_local=False
        )
        router.set_concurrency_limit(1)
        await router._semaphore.acquire()
        try:
            result = await router.ainvoke("generate", {"name": "elm"})
        finally:
            router._semaphore.release()

        assert result["error"] == PUBLIC_TIMEOUT
        assert runtime_client.calls == []
        diagnostics = router.get_diagnostics()
        assert diagnostics["queued_requests"] == 0
        assert diagnostics["active_requests"] == 0
        assert diagnostics["total_timeouts"] == 1
        assert diagnostics["request_stats"]["generate"]["timeout"] == 1

    asyncio.run(scenario())


def test_ainvoke_retries_share_one_budget_and_count_one_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(6.0, clock=clock)
    runtime_client = AdvancingRuntimeClient(
        clock,
        outcomes=[
            (4.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
            (2.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
        ],
    )
    router = _remote_router(
        runtime_client, max_retries=3, allow_local=False
    )

    async def no_backoff(_: float) -> None:
        return None

    monkeypatch.setattr(model_router_module.asyncio, "sleep", no_backoff)

    result = asyncio.run(
        router.ainvoke("generate", {"name": "elm"}, budget=budget)
    )

    assert result["error"] == PUBLIC_TIMEOUT
    assert len(runtime_client.calls) == 2
    assert all(call["budget"] is budget for call in runtime_client.calls)
    diagnostics = router.get_diagnostics()
    assert diagnostics["total_requests"] == 1
    assert diagnostics["total_timeouts"] == 1
    assert diagnostics["request_stats"]["generate"]["timeout"] == 1
    assert diagnostics["request_stats"]["generate"]["error"] == 0


def test_ainvoke_max_retry_exhaustion_preserves_linear_capped_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(100.0, clock=clock)
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.async_results = [
        OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)
        for _ in range(5)
    ]
    router = _remote_router(
        runtime_client, max_retries=5, allow_local=False
    )
    sleep_calls: list[float] = []

    async def record_backoff(delay: float) -> None:
        sleep_calls.append(delay)
        clock.advance(delay)

    monkeypatch.setattr(model_router_module.asyncio, "sleep", record_backoff)

    result = asyncio.run(
        router.ainvoke("generate", {"name": "elm"}, budget=budget)
    )

    assert result["error"] == f"{PUBLIC_TIMEOUT} (after 5 attempts)"
    assert len(runtime_client.calls) == 5
    assert all(call["budget"] is budget for call in runtime_client.calls)
    assert sleep_calls == [0.5, 1.0, 1.5, 2.0]
    diagnostics = router.get_diagnostics()
    assert diagnostics["total_requests"] == 1
    assert diagnostics["total_timeouts"] == 1
    stats = diagnostics["request_stats"]["generate"]
    assert stats["total"] == 1
    assert stats["timeout"] == 1
    assert stats["error"] == 0


def test_ainvoke_does_not_backoff_or_retry_after_budget_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(1.0, clock=clock)
    runtime_client = AdvancingRuntimeClient(
        clock,
        outcomes=[
            (1.0, OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)),
        ],
    )
    router = _remote_router(
        runtime_client, max_retries=3, allow_local=False
    )
    sleep_calls: list[float] = []

    async def record_backoff(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(model_router_module.asyncio, "sleep", record_backoff)

    result = asyncio.run(
        router.ainvoke("generate", {"name": "elm"}, budget=budget)
    )

    assert result["error"] == PUBLIC_TIMEOUT
    assert len(runtime_client.calls) == 1
    assert sleep_calls == []


def test_ainvoke_provider_latency_excludes_queue_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        clock = ManualClock()
        budget = DeadlineBudget.from_timeout(100.0, clock=clock)
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.async_results = [
            {"choices": [{"message": {"content": "oak"}}]}
        ]
        runtime_client.on_async_call = lambda _: clock.advance(2.0)
        router = _remote_router(
            runtime_client, max_retries=1, allow_local=False
        )
        router.configure_load_balance(True)
        router.set_provider_pool(
            "generate",
            [
                ProviderPoolConfig(
                    provider_id="selected-provider",
                    base_url="https://pool.example/v1",
                    api_key="pool-key",
                    model="pool-model",
                )
            ],
        )
        router.set_concurrency_limit(1)
        monkeypatch.setattr(model_router_module.time, "monotonic", clock)

        await router._semaphore.acquire()
        task = asyncio.create_task(
            router.ainvoke("generate", {"name": "oak"}, budget=budget)
        )
        try:
            for _ in range(10):
                if router._queued_requests == 1:
                    break
                await asyncio.sleep(0)
            assert router._queued_requests == 1
            clock.advance(7.0)
        finally:
            router._semaphore.release()

        result = await task
        assert result["content"] == "oak"
        assert router._provider_latencies["selected-provider"] == 2.0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "entry_name", ["ainvoke", "acall_capability", "chat"]
)
def test_async_entry_releases_exact_acquired_semaphore_after_replacement(
    entry_name: str,
) -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.async_results = [
            {"choices": [{"message": {"content": "oak"}}]}
        ]
        runtime_client.async_started = asyncio.Event()
        runtime_client.async_release = asyncio.Event()
        router = _remote_router(runtime_client, allow_local=False)
        router.set_concurrency_limit(1)
        old_semaphore = router._semaphore

        if entry_name == "ainvoke":
            task = asyncio.create_task(
                router.ainvoke("generate", {"name": "oak"})
            )
        elif entry_name == "acall_capability":
            task = asyncio.create_task(
                router.acall_capability("generate", _messages())
            )
        else:
            task = asyncio.create_task(
                router.chat("Name a tree", capability="generate")
            )

        await runtime_client.async_started.wait()
        assert old_semaphore._value == 0
        router.set_concurrency_limit(1)
        new_semaphore = router._semaphore
        assert new_semaphore is not old_semaphore
        assert new_semaphore._value == 1

        runtime_client.async_release.set()
        await task

        assert old_semaphore._value == 1
        assert new_semaphore._value == 1
        diagnostics = router.get_diagnostics()
        assert diagnostics["queued_requests"] == 0
        assert diagnostics["active_requests"] == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "entry_name", ["ainvoke", "acall_capability", "chat"]
)
def test_async_entry_redacts_unexpected_acquire_error_and_cleans_up(
    entry_name: str,
) -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        router = _remote_router(runtime_client, allow_local=False)
        semaphore = ExplodingSemaphore()
        router._semaphore = semaphore  # type: ignore[assignment]

        if entry_name == "ainvoke":
            result = await router.ainvoke("generate", {"name": "oak"})
            assert result["error"] == "AI request failed"
            assert "ACQUIRE-SENTINEL" not in repr(result)
        elif entry_name == "acall_capability":
            with pytest.raises(RuntimeError) as exc_info:
                await router.acall_capability("generate", _messages())
            assert str(exc_info.value) == "AI request failed"
        else:
            with pytest.raises(RuntimeError) as exc_info:
                await router.chat("Name a tree", capability="generate")
            assert str(exc_info.value) == "AI request failed"

        assert runtime_client.calls == []
        assert semaphore.release_count == 0
        diagnostics = router.get_diagnostics()
        assert diagnostics["queued_requests"] == 0
        assert diagnostics["active_requests"] == 0
        assert diagnostics["total_timeouts"] == 0
        assert diagnostics["total_cancellations"] == 0
        stats = diagnostics["request_stats"]["generate"]
        assert stats["total"] == 1
        assert stats["error"] == 1
        assert stats["timeout"] == 0
        assert stats["cancelled"] == 0

    asyncio.run(scenario())


def test_ainvoke_cancellation_while_waiting_for_semaphore_restores_counters() -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        router = _remote_router(runtime_client, allow_local=False)
        router.set_concurrency_limit(1)
        await router._semaphore.acquire()
        task = asyncio.create_task(router.ainvoke("generate", {"name": "oak"}))
        try:
            for _ in range(10):
                if router._queued_requests == 1:
                    break
                await asyncio.sleep(0)
            assert router._queued_requests == 1
            assert router._active_requests == 0
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert router._queued_requests == 0
            assert router._active_requests == 0
            diagnostics = router.get_diagnostics()
            assert diagnostics["total_timeouts"] == 0
            assert diagnostics["total_cancellations"] == 1
            assert diagnostics["request_stats"]["generate"]["cancelled"] == 1
        finally:
            router._semaphore.release()

    asyncio.run(scenario())


def test_ainvoke_cancellation_during_safe_call_restores_counters() -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.async_results = [
            {"choices": [{"message": {"content": "unused"}}]}
        ]
        runtime_client.async_started = asyncio.Event()
        runtime_client.async_release = asyncio.Event()
        router = _remote_router(runtime_client, allow_local=False)
        task = asyncio.create_task(router.ainvoke("generate", {"name": "oak"}))

        await runtime_client.async_started.wait()
        assert router._queued_requests == 0
        assert router._active_requests == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert router._queued_requests == 0
        assert router._active_requests == 0
        diagnostics = router.get_diagnostics()
        assert diagnostics["total_timeouts"] == 0
        assert diagnostics["total_cancellations"] == 1
        assert diagnostics["request_stats"]["generate"]["cancelled"] == 1

    asyncio.run(scenario())


def test_ainvoke_cancellation_during_retry_backoff_restores_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        backoff_started = asyncio.Event()
        backoff_release = asyncio.Event()

        async def blocking_backoff(_: float) -> None:
            backoff_started.set()
            await backoff_release.wait()

        monkeypatch.setattr(model_router_module.asyncio, "sleep", blocking_backoff)
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.async_results = [
            OutboundRequestError("outbound_timeout", 504, PUBLIC_TIMEOUT)
        ]
        router = _remote_router(runtime_client, allow_local=False)
        task = asyncio.create_task(router.ainvoke("generate", {"name": "oak"}))

        await backoff_started.wait()
        assert router._queued_requests == 1
        assert router._active_requests == 0
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert router._queued_requests == 0
        assert router._active_requests == 0
        diagnostics = router.get_diagnostics()
        assert diagnostics["total_timeouts"] == 0
        assert diagnostics["total_cancellations"] == 1
        assert diagnostics["request_stats"]["generate"]["cancelled"] == 1

    asyncio.run(scenario())


def _json_response(provider_type: str, content: Any) -> dict[str, Any]:
    if provider_type == PROVIDER_TYPE_ANTHROPIC:
        return {"content": [{"type": "text", "text": content}]}
    if provider_type == PROVIDER_TYPE_GOOGLE:
        return {"candidates": [{"content": {"parts": [{"text": content}]}}]}
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "provider_type",
    [PROVIDER_TYPE_OPENAI, PROVIDER_TYPE_ANTHROPIC, PROVIDER_TYPE_GOOGLE],
)
@pytest.mark.parametrize("response_kind", ["malformed", "upstream_error"])
def test_invoke_family_redacts_invalid_provider_json_shapes(
    mode: str,
    provider_type: str,
    response_kind: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = f"JSON-{mode}-{provider_type}-{response_kind}-SENTINEL"
    response = (
        _json_response(provider_type, {"secret": sentinel})
        if response_kind == "malformed"
        else {"error": {"message": sentinel}}
    )
    runtime_client = RecordingSafeRuntimeClient()
    if mode == "sync":
        runtime_client.sync_results = [response]
    else:
        runtime_client.async_results = [response]
    router = _remote_router(runtime_client, provider_type=provider_type)

    with caplog.at_level(logging.DEBUG):
        result = (
            router.invoke("generate", {"name": "oak"})
            if mode == "sync"
            else asyncio.run(router.ainvoke("generate", {"name": "oak"}))
        )

    assert result["error"] == PRIMARY_RESPONSE_ERROR
    assert "raw" not in result
    assert "content" not in result
    assert sentinel not in repr(result)
    assert sentinel not in caplog.text


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "provider_type",
    [PROVIDER_TYPE_OPENAI, PROVIDER_TYPE_ANTHROPIC, PROVIDER_TYPE_GOOGLE],
)
def test_invoke_family_preserves_plain_text_without_logging_preview(
    mode: str,
    provider_type: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    plain_text = f"VALID-PLAIN-{mode}-{provider_type}-SENTINEL"
    response = _json_response(provider_type, plain_text)
    runtime_client = RecordingSafeRuntimeClient()
    if mode == "sync":
        runtime_client.sync_results = [response]
    else:
        runtime_client.async_results = [response]
    router = _remote_router(runtime_client, provider_type=provider_type)

    with caplog.at_level(logging.DEBUG):
        result = (
            router.invoke("generate", {"name": "oak"})
            if mode == "sync"
            else asyncio.run(router.ainvoke("generate", {"name": "oak"}))
        )

    assert result["content"] == plain_text
    assert result["raw"] == response
    assert plain_text not in caplog.text


async def _collect_stream(router: ModelRouter) -> list[Any]:
    return [event async for event in router.astream("generate", {"name": "elm"})]


async def _collect_router_stream(
    router: ModelRouter,
    entry: str,
    *,
    budget: StreamBudget | None = None,
) -> list[Any]:
    if entry == "template":
        stream = router.astream("generate", {"name": "elm"}, budget=budget)
    else:
        stream = router.astream_capability(
            "generate", _messages(), budget=budget
        )
    return [event async for event in stream]


@pytest.mark.parametrize("entry", ["template", "capability"])
def test_partial_timeout_emits_interrupted_without_completed(entry: str) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = [
        'data: {"choices":[{"delta":{"content":"partial"}}]}'
    ]
    runtime_client.stream_error = OutboundRequestError(
        "outbound_timeout", 504, PUBLIC_TIMEOUT
    )
    router = _remote_router(runtime_client)

    events = asyncio.run(_collect_router_stream(router, entry))

    assert "partial" in events
    terminals = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("state") in {"completed", "interrupted"}
    ]
    assert terminals == [
        {
            "type": "status",
            "state": "interrupted",
            "capability": "generate",
            "reason": "outbound_timeout",
            "partial": True,
            "timestamp": terminals[0]["timestamp"],
        }
    ]
    diagnostics = router.get_diagnostics()
    assert diagnostics["total_requests"] == 1
    assert diagnostics["total_timeouts"] == 1
    assert diagnostics["request_stats"]["generate"]["timeout"] == 1
    assert diagnostics["request_stats"]["generate"]["success"] == 0


@pytest.mark.parametrize("entry", ["template", "capability"])
@pytest.mark.parametrize("cross_hard_deadline", [True, False])
def test_google_buffered_event_checks_hard_deadline_between_content_parts(
    entry: str,
    cross_hard_deadline: bool,
) -> None:
    async def scenario() -> tuple[list[Any], ModelRouter]:
        clock = ManualClock()
        budget = StreamBudget.from_timeouts(
            10.0, hard_timeout=1.0, clock=clock
        )
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [
            '[{"candidates":['
            '{"content":{"parts":[{"text":"first"},{"text":"second"}]}},'
            '{"content":{"parts":[{"text":"third"}]}}]}]'
        ]
        router = _remote_router(
            runtime_client,
            provider_type=PROVIDER_TYPE_GOOGLE,
            allow_local=False,
        )
        stream = (
            router.astream("generate", {"name": "elm"}, budget=budget)
            if entry == "template"
            else router.astream_capability(
                "generate", _messages(), budget=budget
            )
        )
        events: list[Any] = []
        while "first" not in events:
            events.append(await anext(stream))
        if cross_hard_deadline:
            clock.advance(1.0)
        events.extend([event async for event in stream])
        return events, router

    events, router = asyncio.run(scenario())
    text_events = [event for event in events if isinstance(event, str)]
    terminals = [
        event["state"]
        for event in events
        if isinstance(event, dict)
        and event.get("state") in {"completed", "interrupted"}
    ]
    stats = router.get_diagnostics()["request_stats"]["generate"]

    if cross_hard_deadline:
        assert text_events == ["first"]
        assert terminals == ["interrupted"]
        assert stats["timeout"] == 1
        assert stats["success"] == 0
    else:
        assert text_events == ["first", "second", "third"]
        assert terminals == ["completed"]
        assert stats["timeout"] == 0
        assert stats["success"] == 1


@pytest.mark.parametrize("entry", ["template", "capability"])
def test_timeout_before_content_emits_one_fixed_error(entry: str) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_error = OutboundRequestError(
        "outbound_timeout", 504, PUBLIC_TIMEOUT
    )
    router = _remote_router(runtime_client)

    events = asyncio.run(_collect_router_stream(router, entry))

    errors = [
        event
        for event in events
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
    diagnostics = router.get_diagnostics()
    assert diagnostics["total_requests"] == 1
    assert diagnostics["total_timeouts"] == 1
    assert diagnostics["request_stats"]["generate"]["timeout"] == 1


@pytest.mark.parametrize("entry", ["template", "capability"])
def test_stream_entry_passes_one_caller_budget_by_identity(entry: str) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = ["data: [DONE]"]
    router = _remote_router(runtime_client)
    budget = StreamBudget.from_timeouts(23.0, hard_timeout=600.0)

    events = asyncio.run(_collect_router_stream(router, entry, budget=budget))

    assert events[-1]["state"] == "completed"
    assert runtime_client.calls[0]["budget"] is budget
    diagnostics = router.get_diagnostics()
    assert diagnostics["request_stats"]["generate"]["success"] == 1


@pytest.mark.parametrize("entry", ["template", "capability"])
def test_stream_queue_uses_caller_budget_before_network(entry: str) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    router = _remote_router(runtime_client)
    clock = ManualClock()
    budget = StreamBudget.from_timeouts(
        1.0, hard_timeout=600.0, clock=clock
    )
    clock.advance(1.1)

    events = asyncio.run(_collect_router_stream(router, entry, budget=budget))

    assert [
        event.get("state")
        for event in events
        if isinstance(event, dict) and event.get("type") == "status"
    ] == ["connecting"]
    assert [
        (event["code"], event["message"])
        for event in events
        if isinstance(event, dict) and event.get("type") == "error"
    ] == [("outbound_timeout", PUBLIC_TIMEOUT)]
    assert runtime_client.calls == []
    diagnostics = router.get_diagnostics()
    assert diagnostics["request_stats"]["generate"]["timeout"] == 1


@pytest.mark.parametrize("entry", ["template", "capability"])
def test_stream_releases_the_exact_acquired_semaphore(entry: str) -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat"]
        runtime_client.stream_block_on_exhaustion = True
        router = _remote_router(runtime_client)
        router.set_concurrency_limit(1)
        acquired_semaphore = router._semaphore
        task = asyncio.create_task(_collect_router_stream(router, entry))

        while runtime_client.stream_iterator is None:
            await asyncio.sleep(0)
        await runtime_client.stream_iterator.next_started.wait()
        assert acquired_semaphore._value == 0

        router.set_concurrency_limit(2)
        replacement_semaphore = router._semaphore
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert acquired_semaphore._value == 1
        assert replacement_semaphore._value == 2
        diagnostics = router.get_diagnostics()
        assert diagnostics["request_stats"]["generate"]["cancelled"] == 1

    asyncio.run(scenario())


def test_astream_uses_safe_lines_and_preserves_status_heartbeat_and_chunks() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = [
        ": heartbeat",
        "",
        'data: {"choices":[{"delta":{"content":"hel"}}]}',
        ": heartbeat",
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        "data: [DONE]",
    ]
    router = _remote_router(runtime_client, allow_local=False)
    router.configure_overrides(
        {
            "generate": {
                "base_url": "https://override.example/v1/",
                "api_key": "override-key",
                "provider_type": PROVIDER_TYPE_OPENAI,
                "model": "override-model",
                "timeout": 23,
            }
        }
    )

    events = asyncio.run(_collect_stream(router))

    assert [(event.get("type"), event.get("state")) for event in events if isinstance(event, dict)] == [
        ("status", "connecting"),
        ("status", "connected"),
        ("status", "receiving"),
        ("status", "completed"),
    ]
    assert [event for event in events if isinstance(event, str)] == ["hel", "lo"]
    assert len(runtime_client.calls) == 1
    call = runtime_client.calls[0]
    assert call == {
        "method": "astream_lines",
        "base_url": "https://override.example/v1",
        "request_target": "/chat/completions",
        "provider_type": PROVIDER_TYPE_OPENAI,
        "headers": {
            "Authorization": "Bearer override-key",
            "Connection": "close",
        },
        "json_body": {
            "model": "override-model",
            "messages": [
                {"role": "system", "content": "Answer for elm"},
                {
                    "role": "user",
                    "content": json.dumps({"name": "elm"}, ensure_ascii=False, indent=2),
                },
            ],
            "temperature": 0,
            "stream": True,
        },
        "allow_local": False,
        "budget": call["budget"],
        "max_bytes": STREAM_MAX_BYTES,
        "max_event_bytes": STREAM_EVENT_MAX_BYTES,
    }
    budget = call["budget"]
    assert isinstance(budget, StreamBudget)
    assert budget.idle_timeout == 23
    assert 0 < budget.hard_deadline - budget.clock() <= 600


def test_astream_uses_business_start_local_policy_snapshot() -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat", "data: [DONE]"]
        router = _remote_router(runtime_client, allow_local=False)
        stream = router.astream("generate", {"name": "elm"})

        connecting = await stream.__anext__()
        assert connecting["state"] == "connecting"
        router.allow_local_ai_endpoints = True
        remaining = [event async for event in stream]

        assert remaining[-1]["state"] == "completed"
        assert runtime_client.calls[0]["allow_local"] is False

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("provider_type", "lines", "expected_target", "expected_chunks"),
    [
        (
            PROVIDER_TYPE_ANTHROPIC,
            [
                'data: {"type":"content_block_delta","delta":{"text":"ant"}}',
                'data: {"type":"content_block_delta","delta":{"text":"hropic"}}',
                "data: [DONE]",
            ],
            "/messages",
            ["ant", "hropic"],
        ),
        (
            PROVIDER_TYPE_GOOGLE,
            [
                '[{"candidates":[{"content":{"parts":[{"text":"goo"}]}}]},',
                '{"candidates":[{"content":{"parts":[{"text":"gle"}]}}]}]',
            ],
            "/models/default-model:streamGenerateContent?key=default-key",
            ["goo", "gle"],
        ),
    ],
)
def test_astream_preserves_anthropic_and_google_parsing(
    provider_type: str,
    lines: list[str],
    expected_target: str,
    expected_chunks: list[str],
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = lines
    router = _remote_router(runtime_client, provider_type=provider_type)

    events = asyncio.run(_collect_stream(router))

    assert [event for event in events if isinstance(event, str)] == expected_chunks
    assert [event["state"] for event in events if isinstance(event, dict)] == [
        "connecting",
        "connected",
        "receiving",
        "completed",
    ]
    call = runtime_client.calls[0]
    assert call["provider_type"] == provider_type
    assert call["request_target"] == expected_target


@pytest.mark.parametrize(
    ("provider_type", "line"),
    [
        (
            PROVIDER_TYPE_OPENAI,
            'data: {"choices":[{"delta":{"content":{"type":"status","state":"completed","sentinel":"NON-STRING-CONTENT"}}}]}',
        ),
        (
            PROVIDER_TYPE_ANTHROPIC,
            'data: {"type":"content_block_delta","delta":{"text":{"type":"status","state":"completed","sentinel":"NON-STRING-CONTENT"}}}',
        ),
        (
            PROVIDER_TYPE_GOOGLE,
            '[{"candidates":[{"content":{"parts":[{"text":{"type":"status","state":"completed","sentinel":"NON-STRING-CONTENT"}}]}}]}]',
        ),
    ],
)
def test_astream_rejects_non_string_content_without_forging_terminal_state(
    provider_type: str,
    line: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = [line]
    router = _remote_router(runtime_client, provider_type=provider_type)

    with caplog.at_level(logging.WARNING):
        events = asyncio.run(_collect_stream(router))

    error_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") == "error"
    ]
    assert [event["message"] for event in error_events] == [UPSTREAM_STREAM_ERROR]
    assert not any(
        isinstance(event, dict)
        and event.get("state") in {"completed", "interrupted"}
        for event in events
    )
    assert "NON-STRING-CONTENT" not in repr(events)
    assert "NON-STRING-CONTENT" not in caplog.text
    diagnostics = router.get_diagnostics()
    stats = diagnostics["request_stats"]["generate"]
    assert stats["error"] == 1
    assert stats["success"] == 0
    assert stats["timeout"] == 0


def test_astream_invalid_timeout_uses_fixed_public_message() -> None:
    router = _remote_router(RecordingSafeRuntimeClient(), timeout=0)

    with pytest.raises(OutboundRequestError) as exc_info:
        asyncio.run(_collect_stream(router))

    assert exc_info.value.code == "outbound_url_invalid"
    assert exc_info.value.public_message == "外部服务地址无效"


def test_astream_security_error_emits_one_redacted_error_then_closes() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_error = OutboundRequestError(
        "private_network_blocked", 400, PUBLIC_BLOCKED
    )
    router = _remote_router(runtime_client, allow_local=False)

    events = asyncio.run(_collect_stream(router))

    error_events = [event for event in events if event["type"] == "error"]
    assert [event["state"] for event in events if event["type"] == "status"] == [
        "connecting"
    ]
    assert len(error_events) == 1
    assert error_events[0]["message"] == PUBLIC_BLOCKED
    assert len(runtime_client.calls) == 1
    assert runtime_client.stream_iterator is not None
    assert runtime_client.stream_iterator.close_count == 1


def test_astream_cancellation_survives_inner_close_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat"]
        runtime_client.stream_block_on_exhaustion = True
        runtime_client.stream_close_error = OutboundRequestError(
            "outbound_connect_failed", 502, "CLOSE-CANCEL-SENTINEL"
        )
        router = _remote_router(runtime_client)
        task = asyncio.create_task(_collect_stream(router))

        while runtime_client.stream_iterator is None:
            await asyncio.sleep(0)
        await runtime_client.stream_iterator.next_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime_client.stream_iterator.close_count == 1
        diagnostics = router.get_diagnostics()
        assert diagnostics["total_cancellations"] == 1
        assert diagnostics["total_timeouts"] == 0
        assert diagnostics["request_stats"]["generate"]["cancelled"] == 1

    with caplog.at_level(logging.DEBUG):
        asyncio.run(scenario())
    assert "CLOSE-CANCEL-SENTINEL" not in caplog.text


def test_astream_preserves_outer_cancellation_over_inner_close_cancellation() -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat"]
        runtime_client.stream_block_on_exhaustion = True
        runtime_client.stream_close_error = asyncio.CancelledError("INNER-CLOSE")
        router = _remote_router(runtime_client)
        task = asyncio.create_task(_collect_stream(router))

        while runtime_client.stream_iterator is None:
            await asyncio.sleep(0)
        await runtime_client.stream_iterator.next_started.wait()
        task.cancel("OUTER-CANCEL")
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task
        assert exc_info.value.args == ("OUTER-CANCEL",)
        assert runtime_client.stream_iterator.close_count == 1

    asyncio.run(scenario())


def test_astream_propagates_inner_close_cancellation_without_outer_cancel() -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat", "data: [DONE]"]
        runtime_client.stream_close_error = asyncio.CancelledError("INNER-CLOSE")
        router = _remote_router(runtime_client)

        with pytest.raises(asyncio.CancelledError) as exc_info:
            await _collect_stream(router)
        assert exc_info.value.args == ("INNER-CLOSE",)
        assert runtime_client.stream_iterator is not None
        assert runtime_client.stream_iterator.close_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_kind", ["security", "protocol"])
def test_astream_error_is_not_replaced_by_inner_close_error(
    failure_kind: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    if failure_kind == "security":
        runtime_client.stream_error = OutboundRequestError(
            "private_network_blocked", 400, PUBLIC_BLOCKED
        )
        expected_message = PUBLIC_BLOCKED
    else:
        runtime_client.stream_lines = [
            'data: {"error":{"message":"PROTOCOL-UPSTREAM-SENTINEL"}}'
        ]
        expected_message = UPSTREAM_STREAM_ERROR
    runtime_client.stream_close_error = RuntimeError("CLOSE-ERROR-SENTINEL")
    router = _remote_router(runtime_client)

    with caplog.at_level(logging.DEBUG):
        events = asyncio.run(_collect_stream(router))

    error_events = [
        event for event in events if isinstance(event, dict) and event["type"] == "error"
    ]
    assert len(error_events) == 1
    assert error_events[0]["message"] == expected_message
    assert runtime_client.stream_iterator is not None
    assert runtime_client.stream_iterator.close_count == 1
    assert "CLOSE-ERROR-SENTINEL" not in repr(events)
    assert "CLOSE-ERROR-SENTINEL" not in caplog.text
    assert "PROTOCOL-UPSTREAM-SENTINEL" not in caplog.text


def test_astream_outer_aclose_swallows_inner_close_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat", "data: [DONE]"]
        runtime_client.stream_close_error = RuntimeError("EARLY-CLOSE-SENTINEL")
        router = _remote_router(runtime_client)
        stream = router.astream("generate", {"name": "elm"})

        assert (await stream.__anext__())["state"] == "connecting"
        assert (await stream.__anext__())["state"] == "connected"
        await stream.aclose()
        assert runtime_client.stream_iterator is not None
        assert runtime_client.stream_iterator.close_count == 1
        diagnostics = router.get_diagnostics()
        assert diagnostics["total_cancellations"] == 1
        assert diagnostics["total_timeouts"] == 0
        assert diagnostics["request_stats"]["generate"]["cancelled"] == 1

    with caplog.at_level(logging.DEBUG):
        asyncio.run(scenario())
    assert "EARLY-CLOSE-SENTINEL" not in caplog.text


@pytest.mark.parametrize(
    "lines",
    [
        ['data: {"error":{"message":"UPSTREAM-SENTINEL"}}'],
        ['data: {"malformed":"MALFORMED-SENTINEL"'],
    ],
)
def test_astream_upstream_error_and_malformed_fragment_are_redacted(
    lines: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = lines
    router = _remote_router(runtime_client)

    with caplog.at_level(logging.WARNING):
        events = asyncio.run(_collect_stream(router))

    error_events = [event for event in events if isinstance(event, dict) and event["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["message"] == UPSTREAM_STREAM_ERROR
    rendered_events = repr(events)
    assert "UPSTREAM-SENTINEL" not in rendered_events
    assert "MALFORMED-SENTINEL" not in rendered_events
    assert "UPSTREAM-SENTINEL" not in caplog.text
    assert "MALFORMED-SENTINEL" not in caplog.text
    assert runtime_client.stream_iterator is not None
    assert runtime_client.stream_iterator.close_count == 1


NETWORK_ENTRY_TRANSPORTS = (
    ("invoke", "post_json"),
    ("ainvoke", "apost_json"),
    ("astream", "astream_lines"),
    ("call_capability", "post_json"),
    ("acall_capability", "apost_json"),
    ("chat", "apost_json"),
    ("astream_capability", "astream_lines"),
)


def _messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Be concise"},
        {"role": "user", "content": "Name a tree"},
    ]


@pytest.mark.parametrize(
    ("entry_name", "expected_transport"),
    NETWORK_ENTRY_TRANSPORTS,
    ids=[entry_name for entry_name, _ in NETWORK_ENTRY_TRANSPORTS],
)
def test_seven_network_entries_delegate_once_through_safe_runtime_client(
    entry_name: str,
    expected_transport: str,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    response = {"choices": [{"message": {"content": "oak"}}]}
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    runtime_client.stream_lines = [
        ": heartbeat",
        'data: {"choices":[{"delta":{"content":"oak"}}]}',
        "data: [DONE]",
    ]
    router = _remote_router(runtime_client, allow_local=False)

    if entry_name == "invoke":
        router.invoke("generate", {"name": "oak"})
    elif entry_name == "ainvoke":
        asyncio.run(router.ainvoke("generate", {"name": "oak"}))
    elif entry_name == "astream":
        asyncio.run(_collect_stream(router))
    elif entry_name == "call_capability":
        assert router.call_capability("generate", _messages()) == "oak"
    elif entry_name == "acall_capability":
        assert asyncio.run(router.acall_capability("generate", _messages())) == "oak"
    elif entry_name == "chat":
        assert asyncio.run(router.chat("Name a tree", capability="generate")) == "oak"
    else:
        events = asyncio.run(
            _collect_capability_stream(router, "generate", _messages())
        )
        assert "oak" in events

    assert [call["method"] for call in runtime_client.calls] == [expected_transport]


async def _collect_capability_stream(
    router: ModelRouter,
    capability: str,
    messages: list[dict[str, str]],
) -> list[Any]:
    return [
        event
        async for event in router.astream_capability(capability, messages)
    ]


def _credential_call_signature(call: dict[str, Any]) -> tuple[str, str, str]:
    endpoint_source = {
        "https://global.example/v1": "global",
        "https://override.example/v1": "override",
        "https://old.example/v1": "old",
        "https://environment.example/v1": "environment",
        "https://new.example/v1": "new",
    }.get(call["base_url"], "unknown")
    headers = call["headers"]
    raw_key = headers.get("x-api-key")
    if raw_key is None:
        authorization = headers.get("Authorization", "")
        raw_key = authorization.removeprefix("Bearer ")
    key_source = {
        "global-test-key": "global",
        "override-test-key": "override",
        "old-test-key": "old",
        "environment-test-key": "environment",
        "new-test-key": "new",
    }.get(raw_key, "unknown")
    return endpoint_source, key_source, call["provider_type"]


def _credential_call_source(call: dict[str, Any]) -> str:
    signature = _credential_call_signature(call)
    if signature == ("global", "global", PROVIDER_TYPE_OPENAI):
        return "global"
    if signature == ("override", "override", PROVIDER_TYPE_ANTHROPIC):
        return "override"
    return "mixed-or-unknown"


@pytest.mark.parametrize(
    ("entry_name", "expected_transport"),
    NETWORK_ENTRY_TRANSPORTS,
    ids=[entry_name for entry_name, _ in NETWORK_ENTRY_TRANSPORTS],
)
@pytest.mark.parametrize(
    ("override", "expected_source"),
    [
        pytest.param(
            {
                "base_url": "https://override.example/v1",
                "api_key": None,
                "provider_type": "openai",
                "model": "override-model",
            },
            None,
            id="both-credential-fields-incomplete",
        ),
        pytest.param(
            {
                "base_url": "https://override.example/v1",
                "provider_type": "openai",
                "model": "override-model",
            },
            None,
            id="base-url-only",
        ),
        pytest.param(
            {
                "api_key": "override-test-key",
                "provider_type": "openai",
                "model": "override-model",
            },
            None,
            id="api-key-only",
        ),
        pytest.param(
            {
                "base_url": "https://override.example/v1",
                "api_key": "override-test-key",
                "model": "override-model",
            },
            None,
            id="endpoint-key-without-provider-type",
        ),
        pytest.param(
            {
                "provider_type": PROVIDER_TYPE_ANTHROPIC,
                "model": "override-model",
            },
            None,
            id="provider-type-only",
        ),
        pytest.param(
            {
                "base_url": "https://override.example/v1",
                "api_key": "override-test-key",
                "provider_type": PROVIDER_TYPE_ANTHROPIC,
                "model": "override-model",
            },
            "override",
            id="complete-credential-tuple",
        ),
        pytest.param(
            {
                "model": "override-model",
            },
            "global",
            id="model-only",
        ),
    ],
)
def test_network_entries_select_override_credentials_atomically(
    entry_name: str,
    expected_transport: str,
    override: dict[str, Any],
    expected_source: str | None,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    response = {
        "choices": [{"message": {"content": "oak"}}],
        "content": [{"type": "text", "text": "oak"}],
    }
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    runtime_client.stream_lines = [
        'data: {"choices":[{"delta":{"content":"oak"}}]}',
        "data: [DONE]",
    ]
    router = _remote_router(
        runtime_client,
        base_url="https://global.example/v1",
        api_key="global-test-key",
        allow_local=False,
    )
    router.configure_overrides({"generate": override})

    try:
        if entry_name == "invoke":
            router.invoke("generate", {"name": "oak"})
        elif entry_name == "ainvoke":
            asyncio.run(router.ainvoke("generate", {"name": "oak"}))
        elif entry_name == "astream":
            asyncio.run(_collect_stream(router))
        elif entry_name == "call_capability":
            router.call_capability("generate", _messages())
        elif entry_name == "acall_capability":
            asyncio.run(router.acall_capability("generate", _messages()))
        elif entry_name == "chat":
            asyncio.run(router.chat("Name a tree", capability="generate"))
        else:
            asyncio.run(
                _collect_capability_stream(router, "generate", _messages())
            )
    except RuntimeError as exc:
        assert "missing configuration" in str(exc)

    if expected_source is None:
        assert len(runtime_client.calls) == 0
        return

    assert len(runtime_client.calls) == 1
    call = runtime_client.calls[0]
    assert call["method"] == expected_transport
    assert _credential_call_source(call) == expected_source


class CoordinatedCredentialRouter(ModelRouter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._coordinate_credential_publications = False
        self.credential_published = threading.Barrier(2)
        self.credential_resume = threading.Barrier(2)
        super().__init__(*args, **kwargs)

    def _pause_after_credential_publication(self) -> None:
        self.credential_published.wait(timeout=5)
        self.credential_resume.wait(timeout=5)

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if (
            name == "api_base_url"
            and getattr(self, "_coordinate_credential_publications", False)
        ):
            self._pause_after_credential_publication()

    def configure_runtime_credentials(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        provider_type: str | None,
    ) -> None:
        super().configure_runtime_credentials(
            base_url=base_url,
            api_key=api_key,
            provider_type=provider_type,
        )
        if self._coordinate_credential_publications:
            self._pause_after_credential_publication()


def test_config_refresh_publishes_only_complete_credential_snapshots() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.sync_results = [{}, {}, {}]
    router = CoordinatedCredentialRouter(
        defaults={
            "generate": ModelConfig(
                provider=PROVIDER_TYPE_ANTHROPIC,
                provider_type=PROVIDER_TYPE_ANTHROPIC,
                model="old-model",
            )
        },
        base_url="https://old.example/v1",
        api_key="old-test-key",
        runtime_client=runtime_client,
        allow_local_ai_endpoints=False,
    )
    router.set_prompt("generate", "Answer for {name}")
    config = UIConfig(
        providers={
            "new": ProviderConfig(
                id="new",
                name="New",
                type=PROVIDER_TYPE_ANTHROPIC,
                provider_type=PROVIDER_TYPE_ANTHROPIC,
                base_url="https://new.example/v1",
                api_key="new-test-key",
                selected_models=["new-model"],
            )
        },
        default_provider_id="new",
    )
    settings = SimpleNamespace(
        speciation_model="fallback",
        embedding_provider=PROVIDER_TYPE_OPENAI,
        ai_base_url="https://environment.example/v1",
        ai_api_key="environment-test-key",
    )
    refresh_errors: list[BaseException] = []

    def refresh() -> None:
        try:
            configure_model_router(
                config,
                router,
                None,  # type: ignore[arg-type]
                settings,
            )
        except BaseException as exc:
            refresh_errors.append(exc)

    def invoke_signature() -> tuple[str, str, str]:
        router.invoke("generate", {"name": "oak"})
        return _credential_call_signature(runtime_client.calls[-1])

    signatures = [invoke_signature()]
    router._coordinate_credential_publications = True
    refresh_thread = threading.Thread(target=refresh)
    refresh_thread.start()
    for _ in range(2):
        router.credential_published.wait(timeout=5)
        signatures.append(invoke_signature())
        router.credential_resume.wait(timeout=5)
    refresh_thread.join(timeout=5)

    assert not refresh_thread.is_alive()
    assert refresh_errors == []
    assert signatures == [
        ("old", "old", PROVIDER_TYPE_ANTHROPIC),
        ("environment", "environment", PROVIDER_TYPE_OPENAI),
        ("new", "new", PROVIDER_TYPE_ANTHROPIC),
    ]


LEGACY_JSON_ENTRIES = ("call_capability", "acall_capability", "chat")


def _run_legacy_json_entry(router: ModelRouter, entry_name: str) -> str:
    if entry_name == "call_capability":
        return router.call_capability("generate", _messages())
    if entry_name == "acall_capability":
        return asyncio.run(router.acall_capability("generate", _messages()))
    return asyncio.run(
        router.chat(
            "Name a tree",
            capability="generate",
            system_prompt="Be concise",
            max_tokens=123,
        )
    )


@pytest.mark.parametrize("entry_name", LEGACY_JSON_ENTRIES)
@pytest.mark.parametrize(
    ("provider_type", "expected_target"),
    [
        (PROVIDER_TYPE_OPENAI, "/v1/chat/completions"),
        (PROVIDER_TYPE_ANTHROPIC, "/messages"),
        (
            PROVIDER_TYPE_GOOGLE,
            "/models/default-model:generateContent?key=default-key",
        ),
    ],
)
def test_legacy_json_entries_preserve_provider_formats_through_safe_client(
    entry_name: str,
    provider_type: str,
    expected_target: str,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    response = _json_response(provider_type, "maple")
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    router = _remote_router(
        runtime_client,
        provider_type=provider_type,
        allow_local=False,
    )

    assert _run_legacy_json_entry(router, entry_name) == "maple"

    expected_method = "post_json" if entry_name == "call_capability" else "apost_json"
    assert len(runtime_client.calls) == 1
    _assert_json_call(
        runtime_client.calls[0],
        method=expected_method,
        base_url="https://default.example/api",
        request_target=expected_target,
        provider_type=provider_type,
        timeout=17,
        allow_local=False,
    )


@pytest.mark.parametrize("entry_name", LEGACY_JSON_ENTRIES)
@pytest.mark.parametrize(
    ("code", "public_message"),
    [
        ("private_network_blocked", PUBLIC_BLOCKED),
        ("outbound_connect_failed", PUBLIC_CONNECT_FAILED),
        ("outbound_timeout", PUBLIC_TIMEOUT),
    ],
)
def test_legacy_json_safety_and_timeout_errors_are_fixed_and_never_retried(
    entry_name: str,
    code: str,
    public_message: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    failure = OutboundRequestError(code, 504, public_message)
    response = {"choices": [{"message": {"content": "must-not-retry"}}]}
    runtime_client.sync_results = [failure, response]
    runtime_client.async_results = [failure, response]
    router = _remote_router(
        runtime_client,
        base_url="https://url-secret.example/v1",
        api_key="KEY-ERROR-SENTINEL",
        allow_local=False,
    )

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError) as exc_info:
            _run_legacy_json_entry(router, entry_name)

    assert str(exc_info.value) == public_message
    assert len(runtime_client.calls) == 1
    assert "KEY-ERROR-SENTINEL" not in caplog.text
    assert "url-secret.example" not in caplog.text


@pytest.mark.parametrize("entry_name", LEGACY_JSON_ENTRIES)
@pytest.mark.parametrize(
    "provider_type",
    [PROVIDER_TYPE_OPENAI, PROVIDER_TYPE_ANTHROPIC, PROVIDER_TYPE_GOOGLE],
)
@pytest.mark.parametrize("response_kind", ["malformed", "upstream_error"])
def test_legacy_json_invalid_provider_shapes_are_fixed_and_redacted(
    entry_name: str,
    provider_type: str,
    response_kind: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = f"LEGACY-{entry_name}-{provider_type}-{response_kind}-SENTINEL"
    response = (
        _json_response(provider_type, {"secret": sentinel})
        if response_kind == "malformed"
        else {"error": {"message": sentinel}}
    )
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    router = _remote_router(runtime_client, provider_type=provider_type)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(RuntimeError) as exc_info:
            _run_legacy_json_entry(router, entry_name)

    assert str(exc_info.value) == PRIMARY_RESPONSE_ERROR
    assert sentinel not in repr(exc_info.value)
    assert sentinel not in caplog.text
    assert len(runtime_client.calls) == 1


@pytest.mark.parametrize("entry_name", LEGACY_JSON_ENTRIES)
def test_legacy_json_uses_business_start_local_policy_snapshot(
    entry_name: str,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    response = {"choices": [{"message": {"content": "fir"}}]}
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    router = _remote_router(runtime_client, allow_local=False)

    def enable_local(_: int) -> None:
        router.allow_local_ai_endpoints = True

    runtime_client.on_sync_call = enable_local
    runtime_client.on_async_call = enable_local

    assert _run_legacy_json_entry(router, entry_name) == "fir"
    assert runtime_client.calls[0]["allow_local"] is False


@pytest.mark.parametrize("entry_name", LEGACY_JSON_ENTRIES)
def test_legacy_json_selected_google_pool_key_builds_request_target(
    entry_name: str,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    response = _json_response(PROVIDER_TYPE_GOOGLE, "cedar")
    runtime_client.sync_results = [response]
    runtime_client.async_results = [response]
    router = _remote_router(runtime_client, allow_local=False)
    router.configure_load_balance(True)
    router.set_provider_pool(
        "generate",
        [
            ProviderPoolConfig(
                provider_id="selected-google",
                base_url="https://selected.example/v1beta",
                api_key="selected+&key",
                provider_type=PROVIDER_TYPE_GOOGLE,
                model="gemini pool/model",
            ),
            ProviderPoolConfig(
                provider_id="must-not-select",
                base_url="https://other.example/v1",
                api_key="other-key",
                provider_type=PROVIDER_TYPE_OPENAI,
                model="other-model",
            ),
        ],
    )

    assert _run_legacy_json_entry(router, entry_name) == "cedar"

    assert router._lb_counters["generate"] == 1
    assert len(runtime_client.calls) == 1
    assert runtime_client.calls[0]["base_url"] == "https://selected.example/v1beta"
    assert runtime_client.calls[0]["request_target"] == (
        "/models/gemini%20pool%2Fmodel:generateContent?"
        + urlencode({"key": "selected+&key"})
    )


@pytest.mark.parametrize("configuration", ["local", "missing"])
def test_legacy_local_and_missing_configuration_shapes_are_unchanged(
    configuration: str,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    router = ModelRouter(
        defaults={
            "generate": ModelConfig(
                provider="local" if configuration == "local" else "openai",
                model="default-model",
            )
        },
        base_url=None,
        api_key=None,
        runtime_client=runtime_client,
    )

    expected = "Cannot call AI for capability generate: missing configuration"
    with pytest.raises(RuntimeError, match=re.escape(expected)):
        router.call_capability("generate", _messages())
    with pytest.raises(RuntimeError, match=re.escape(expected)):
        asyncio.run(router.acall_capability("generate", _messages()))
    assert asyncio.run(router.chat("Name a tree", capability="generate")) == (
        "[本地模式] 无法生成响应: Name a tree..."
    )
    events = asyncio.run(_collect_capability_stream(router, "generate", _messages()))
    assert [event["message"] for event in events] == [
        "Missing configuration for streaming"
    ]
    assert runtime_client.calls == []


@pytest.mark.parametrize(
    ("provider_type", "lines", "expected_target", "expected_chunks"),
    [
        (
            PROVIDER_TYPE_OPENAI,
            [
                ": heartbeat",
                'data: {"choices":[{"delta":{"content":"open"}}]}',
                ": heartbeat",
                'data: {"choices":[{"delta":{"content":"ai"}}]}',
                "data: [DONE]",
            ],
            "/v1/chat/completions",
            ["open", "ai"],
        ),
        (
            PROVIDER_TYPE_ANTHROPIC,
            [
                ": heartbeat",
                'data: {"type":"content_block_delta","delta":{"text":"anth"}}',
                'data: {"type":"content_block_delta","delta":{"text":"ropic"}}',
                "data: [DONE]",
            ],
            "/messages",
            ["anth", "ropic"],
        ),
        (
            PROVIDER_TYPE_GOOGLE,
            [
                ": heartbeat",
                '[{"candidates":[{"content":{"parts":[{"text":"goo"}]}}]},',
                '{"candidates":[{"content":{"parts":[{"text":"gle"}]}}]}]',
            ],
            "/models/default-model:streamGenerateContent?key=default-key",
            ["goo", "gle"],
        ),
    ],
)
def test_legacy_stream_preserves_provider_formats_status_and_heartbeat(
    provider_type: str,
    lines: list[str],
    expected_target: str,
    expected_chunks: list[str],
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = lines
    router = _remote_router(
        runtime_client,
        provider_type=provider_type,
        allow_local=False,
    )

    events = asyncio.run(
        _collect_capability_stream(router, "generate", _messages())
    )

    assert [event for event in events if isinstance(event, str)] == expected_chunks
    assert [
        event["state"]
        for event in events
        if isinstance(event, dict) and event.get("type") == "status"
    ] == [
        "connecting",
        "connected",
        "receiving",
        "completed",
    ]
    assert len(runtime_client.calls) == 1
    call = runtime_client.calls[0]
    assert call["method"] == "astream_lines"
    assert call["base_url"] == "https://default.example/api"
    assert call["request_target"] == expected_target
    assert call["provider_type"] == provider_type
    assert call["allow_local"] is False
    assert call["max_bytes"] == STREAM_MAX_BYTES
    assert call["max_event_bytes"] == STREAM_EVENT_MAX_BYTES
    assert isinstance(call["budget"], StreamBudget)
    assert call["budget"].idle_timeout == 17
    assert 0 < call["budget"].hard_deadline - call["budget"].clock() <= 600
    assert runtime_client.stream_iterator is not None
    assert runtime_client.stream_iterator.iter_count == 1
    assert runtime_client.stream_iterator.close_count == 1


def test_legacy_stream_uses_business_start_local_policy_snapshot() -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat", "data: [DONE]"]
        router = _remote_router(runtime_client, allow_local=False)
        stream = router.astream_capability("generate", _messages())

        assert (await stream.__anext__())["state"] == "connecting"
        router.allow_local_ai_endpoints = True
        remaining = [event async for event in stream]

        assert remaining[-1]["state"] == "completed"
        assert runtime_client.calls[0]["allow_local"] is False

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("code", "public_message"),
    [
        ("private_network_blocked", PUBLIC_BLOCKED),
        ("outbound_connect_failed", PUBLIC_CONNECT_FAILED),
        ("outbound_timeout", PUBLIC_TIMEOUT),
    ],
)
def test_legacy_stream_safe_error_stops_redacted_without_retry(
    code: str,
    public_message: str,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_error = OutboundRequestError(code, 504, public_message)
    router = _remote_router(runtime_client, allow_local=False)

    events = asyncio.run(
        _collect_capability_stream(router, "generate", _messages())
    )

    assert [event["state"] for event in events if event.get("type") == "status"] == [
        "connecting"
    ]
    assert [event["message"] for event in events if event.get("type") == "error"] == [
        public_message
    ]
    assert len(runtime_client.calls) == 1
    assert runtime_client.stream_iterator is not None
    assert runtime_client.stream_iterator.close_count == 1


@pytest.mark.parametrize(
    ("provider_type", "lines"),
    [
        (
            PROVIDER_TYPE_OPENAI,
            ['data: {"error":{"message":"STREAM-UPSTREAM-SENTINEL"}}'],
        ),
        (
            PROVIDER_TYPE_OPENAI,
            ['data: {"malformed":"STREAM-MALFORMED-SENTINEL"'],
        ),
        (
            PROVIDER_TYPE_ANTHROPIC,
            [
                'data: {"type":"error","error":{"message":"STREAM-UPSTREAM-SENTINEL"}}'
            ],
        ),
        (
            PROVIDER_TYPE_ANTHROPIC,
            ['data: {"malformed":"STREAM-MALFORMED-SENTINEL"'],
        ),
        (
            PROVIDER_TYPE_GOOGLE,
            ['[{"error":{"message":"STREAM-UPSTREAM-SENTINEL"}}]'],
        ),
        (
            PROVIDER_TYPE_GOOGLE,
            ['[{"malformed":"STREAM-MALFORMED-SENTINEL"'],
        ),
    ],
)
def test_legacy_stream_upstream_and_malformed_data_are_fixed_and_redacted(
    provider_type: str,
    lines: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = lines
    router = _remote_router(runtime_client, provider_type=provider_type)

    with caplog.at_level(logging.DEBUG):
        events = asyncio.run(
            _collect_capability_stream(router, "generate", _messages())
        )

    assert [event["message"] for event in events if event.get("type") == "error"] == [
        UPSTREAM_STREAM_ERROR
    ]
    assert not any(event.get("state") == "completed" for event in events)
    assert "STREAM-UPSTREAM-SENTINEL" not in repr(events)
    assert "STREAM-MALFORMED-SENTINEL" not in repr(events)
    assert "STREAM-UPSTREAM-SENTINEL" not in caplog.text
    assert "STREAM-MALFORMED-SENTINEL" not in caplog.text
    assert runtime_client.stream_iterator is not None
    assert runtime_client.stream_iterator.close_count == 1


def test_legacy_stream_cancellation_preserves_outer_cancel_and_closes_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat"]
        runtime_client.stream_block_on_exhaustion = True
        runtime_client.stream_close_error = OutboundRequestError(
            "outbound_connect_failed", 502, "STREAM-CLOSE-SENTINEL"
        )
        router = _remote_router(runtime_client)
        task = asyncio.create_task(
            _collect_capability_stream(router, "generate", _messages())
        )

        while runtime_client.stream_iterator is None:
            await asyncio.sleep(0)
        await runtime_client.stream_iterator.next_started.wait()
        task.cancel("OUTER-CANCEL")
        with pytest.raises(asyncio.CancelledError) as exc_info:
            await task
        assert exc_info.value.args == ("OUTER-CANCEL",)
        assert runtime_client.stream_iterator.close_count == 1
        diagnostics = router.get_diagnostics()
        assert diagnostics["total_cancellations"] == 1
        assert diagnostics["total_timeouts"] == 0
        assert diagnostics["request_stats"]["generate"]["cancelled"] == 1

    with caplog.at_level(logging.DEBUG):
        asyncio.run(scenario())
    assert "STREAM-CLOSE-SENTINEL" not in caplog.text


def test_legacy_stream_early_close_swallows_inner_close_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def scenario() -> None:
        runtime_client = RecordingSafeRuntimeClient()
        runtime_client.stream_lines = [": heartbeat", "data: [DONE]"]
        runtime_client.stream_close_error = RuntimeError("EARLY-CLOSE-SENTINEL")
        router = _remote_router(runtime_client)
        stream = router.astream_capability("generate", _messages())

        assert (await stream.__anext__())["state"] == "connecting"
        assert (await stream.__anext__())["state"] == "connected"
        await stream.aclose()
        assert runtime_client.stream_iterator is not None
        assert runtime_client.stream_iterator.close_count == 1
        diagnostics = router.get_diagnostics()
        assert diagnostics["total_cancellations"] == 1
        assert diagnostics["total_timeouts"] == 0
        assert diagnostics["request_stats"]["generate"]["cancelled"] == 1

    with caplog.at_level(logging.DEBUG):
        asyncio.run(scenario())
    assert "EARLY-CLOSE-SENTINEL" not in caplog.text


def test_legacy_stream_selected_google_pool_key_builds_encoded_target() -> None:
    runtime_client = RecordingSafeRuntimeClient()
    runtime_client.stream_lines = [": heartbeat"]
    router = _remote_router(runtime_client, allow_local=False)
    router.configure_load_balance(True)
    router.set_provider_pool(
        "generate",
        [
            ProviderPoolConfig(
                provider_id="selected-google",
                base_url="https://selected.example/v1beta",
                api_key="selected+&key",
                provider_type=PROVIDER_TYPE_GOOGLE,
                model="gemini pool/model",
            ),
            ProviderPoolConfig(
                provider_id="must-not-select",
                base_url="https://other.example/v1",
                api_key="other-key",
                provider_type=PROVIDER_TYPE_OPENAI,
                model="other-model",
            ),
        ],
    )

    asyncio.run(_collect_capability_stream(router, "generate", _messages()))

    assert router._lb_counters["generate"] == 1
    assert len(runtime_client.calls) == 1
    assert runtime_client.calls[0]["request_target"] == (
        "/models/gemini%20pool%2Fmodel:streamGenerateContent?"
        + urlencode({"key": "selected+&key"})
    )


MODEL_ROUTER_PATH = Path(model_router_module.__file__)


def _attribute_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def find_forbidden_network_calls(tree: ast.AST) -> list[str]:
    forbidden: list[str] = []
    forbidden_imports = {
        "httpx",
        "requests",
        "urllib.request",
        "urllib3",
        "aiohttp",
        "httpcore",
        "socket",
    }
    forbidden_httpx_calls = {
        "httpx.AsyncClient",
        "httpx.Client",
        "httpx.delete",
        "httpx.get",
        "httpx.head",
        "httpx.options",
        "httpx.patch",
        "httpx.post",
        "httpx.put",
        "httpx.request",
        "httpx.stream",
    }

    def is_forbidden_import(module_name: str) -> bool:
        return any(
            module_name == forbidden_module
            or module_name.startswith(f"{forbidden_module}.")
            for forbidden_module in forbidden_imports
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if is_forbidden_import(alias.name):
                    forbidden.append(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imported = f"{module}.{alias.name}" if module else alias.name
                if is_forbidden_import(module) or is_forbidden_import(imported):
                    forbidden.append(f"import:{imported}")
        elif isinstance(node, ast.Call):
            call_name = _attribute_name(node.func)
            if call_name in forbidden_httpx_calls:
                forbidden.append(f"call:{call_name}")
    return forbidden


@pytest.mark.parametrize(
    "snippet",
    [
        "import httpx as hx\nhx.get('https://example.com')",
        "from httpx import post as send\nsend('https://example.com')",
        "httpx.request('GET', 'https://example.com')",
        "httpx.get('https://example.com')",
        "from httpx import AsyncClient as AC\nAC()",
    ],
)
def test_forbidden_network_guard_rejects_httpx_aliases_and_direct_calls(
    snippet: str,
) -> None:
    tree = ast.parse(snippet)
    assert find_forbidden_network_calls(tree) != []


def test_model_router_has_no_direct_network_client_bypass() -> None:
    tree = ast.parse(MODEL_ROUTER_PATH.read_text(encoding="utf-8"))
    assert find_forbidden_network_calls(tree) == []
    assert all(
        not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_get_client"
        )
        for node in ast.walk(tree)
    )
    assert all(
        not (isinstance(node, ast.Attribute) and node.attr == "_client_session")
        for node in ast.walk(tree)
    )


def test_seven_network_entries_each_call_one_expected_safe_transport() -> None:
    tree = ast.parse(MODEL_ROUTER_PATH.read_text(encoding="utf-8"))
    model_router_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ModelRouter"
    )
    methods = {
        node.name: node
        for node in model_router_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    expected = dict(NETWORK_ENTRY_TRANSPORTS)
    implementation_method = {
        "astream": "_astream_impl",
        "astream_capability": "_astream_capability_impl",
    }
    safe_names = {"post_json", "apost_json", "astream_lines"}
    actual_safe_callers: dict[str, list[str]] = {}
    for method_name, method in methods.items():
        calls = [
            node.func.attr
            for node in ast.walk(method)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in safe_names
        ]
        if calls:
            actual_safe_callers[method_name] = calls

    assert len(expected) == 7
    expected_callers = {
        implementation_method.get(entry_name, entry_name): transport
        for entry_name, transport in NETWORK_ENTRY_TRANSPORTS
    }
    assert set(actual_safe_callers) == set(expected_callers)
    assert actual_safe_callers == {
        entry_name: [transport]
        for entry_name, transport in expected_callers.items()
    }


def test_legacy_compatibility_methods_do_not_create_or_reset_network_client(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_client = RecordingSafeRuntimeClient()
    router = _remote_router(runtime_client)
    router._active_requests = 2
    router._queued_requests = 3

    with caplog.at_level(logging.INFO, logger=model_router_module.__name__):
        asyncio.run(router.reset_client())
        asyncio.run(router.set_keepalive_mode(True))

    assert router.use_keepalive is True
    assert router._active_requests == 2
    assert router._queued_requests == 3
    assert not hasattr(router, "_client_session")
    assert runtime_client.calls == []
    assert "高效并发" in caplog.text
