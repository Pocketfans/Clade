from __future__ import annotations

import ast
import hashlib
import json
import math
import threading
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from app.security import (
    EMBEDDING_JSON_MAX_BYTES,
    DeadlineBudget,
    OutboundRequestError,
)
from app.services.system import embedding as embedding_module
from app.services.system.embedding import EmbeddingService


FORBIDDEN_NETWORK_MODULES = (
    "httpx",
    "requests",
    "urllib.request",
    "urllib3",
    "aiohttp",
    "httpcore",
    "socket",
)
FORBIDDEN_NETWORK_CALLS = {
    "httpx.post",
    "httpx.Client",
    "httpx.AsyncClient",
    "httpx.request",
    "httpx.stream",
    "httpx.get",
    "httpx.put",
    "httpx.patch",
    "httpx.delete",
    "httpx.head",
    "httpx.options",
}


def _find_forbidden_network_uses(source: str) -> list[str]:
    tree = ast.parse(source)
    findings: list[str] = []
    aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                aliases[bound_name] = alias.name if alias.asname else bound_name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = ".".join(
                    part for part in (module, alias.name) if part
                )

    def name_of(node: ast.AST) -> str | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            resolved = list(reversed(parts))
            resolved[0] = aliases.get(resolved[0], resolved[0])
            return ".".join(resolved)
        return None

    assignments: list[tuple[list[str], ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = [
                target.id for target in node.targets if isinstance(target, ast.Name)
            ]
            if target_names:
                assignments.append((target_names, node.value))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            assignments.append(([node.target.id], node.value))

    for _ in range(len(assignments) + 1):
        changed = False
        for target_names, value in assignments:
            assigned_name = name_of(value)
            if assigned_name is None:
                continue
            for target_name in target_names:
                if aliases.get(target_name) != assigned_name:
                    aliases[target_name] = assigned_name
                    changed = True
        if not changed:
            break

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(
                    alias.name == module or alias.name.startswith(module + ".")
                    for module in FORBIDDEN_NETWORK_MODULES
                ):
                    findings.append(alias.name)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imported_name = ".".join(
                    part for part in (module, alias.name) if part
                )
                if any(
                    imported_name == banned
                    or imported_name.startswith(banned + ".")
                    for banned in FORBIDDEN_NETWORK_MODULES
                ):
                    findings.append(imported_name)
        if isinstance(node, ast.Call):
            call_name = name_of(node.func)
            if call_name in FORBIDDEN_NETWORK_CALLS or (
                call_name is not None
                and any(
                    call_name == module or call_name.startswith(module + ".")
                    for module in FORBIDDEN_NETWORK_MODULES
                )
            ):
                findings.append(call_name)
    return findings


class ForbiddenSyncClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("DIRECT_HTTPX_FORBIDDEN")


@pytest.fixture(autouse=True)
def forbid_direct_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("DIRECT_HTTPX_FORBIDDEN")

    for verb in ("delete", "get", "head", "options", "patch", "post", "put", "request", "stream"):
        monkeypatch.setattr(httpx, verb, forbidden_request)
    monkeypatch.setattr(httpx, "Client", ForbiddenSyncClient)
    monkeypatch.setattr(httpx, "AsyncClient", ForbiddenSyncClient)


class RecordingSafeRuntimeClient:
    def __init__(self, results: list[dict[str, Any] | BaseException]) -> None:
        self.calls: list[dict[str, Any]] = []
        self.results = results
        self.on_call: Callable[[int], None] | None = None

    def post_json(self, base_url: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"base_url": base_url, **kwargs})
        if self.on_call is not None:
            self.on_call(len(self.calls))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class AdvancingSafeRuntimeClient(RecordingSafeRuntimeClient):
    def __init__(
        self,
        clock: ManualClock,
        outcomes: list[tuple[float, dict[str, Any] | BaseException]],
    ) -> None:
        super().__init__([])
        self._clock = clock
        self._outcomes = outcomes

    def post_json(self, base_url: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"base_url": base_url, **kwargs})
        advance, outcome = self._outcomes.pop(0)
        self._clock.advance(advance)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def remote_service(client: RecordingSafeRuntimeClient) -> EmbeddingService:
    return EmbeddingService(
        base_url="https://embedding.example/v1/",
        api_key="secret-key",
        model="text-embedding-3-small",
        enabled=True,
        timeout=23,
        runtime_client=client,
        allow_local_ai_endpoints=True,
    )


def _remote_cache_namespace(
    provider: str,
    model: str,
    normalized_endpoint: str,
) -> tuple[str, str]:
    endpoint_identity = hashlib.sha256(normalized_endpoint.encode()).hexdigest()
    namespace = (
        f"embedding-cache-v2:remote:{provider}:{model}:{endpoint_identity}"
    )
    return namespace, endpoint_identity


def _timeout_errors(count: int = 3) -> list[OutboundRequestError]:
    return [
        OutboundRequestError("outbound_timeout", 504, "PUBLIC-TIMEOUT")
        for _ in range(count)
    ]


def test_embedding_chunk_retries_share_one_total_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(6.0, clock=clock)
    client = AdvancingSafeRuntimeClient(
        clock,
        outcomes=[
            (
                4.0,
                OutboundRequestError(
                    "outbound_timeout", 504, "外部服务请求超时"
                ),
            ),
            (
                2.0,
                OutboundRequestError(
                    "outbound_timeout", 504, "外部服务请求超时"
                ),
            ),
        ],
    )
    service = remote_service(client)
    monkeypatch.setattr(
        embedding_module.time,
        "sleep",
        lambda seconds: clock.advance(seconds),
    )

    result = service._request_embedding_chunk_result(
        ["oak"], require_real=False, budget=budget
    )

    assert result.items[0].source == "remote_fallback_fake"
    assert result.items[0].cacheable is False
    assert len(client.calls) == 2
    assert all(call["budget"] is budget for call in client.calls)


def test_embedding_expired_budget_never_starts_another_retry() -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(3.0, clock=clock)
    client = AdvancingSafeRuntimeClient(
        clock,
        outcomes=[
            (
                3.0,
                OutboundRequestError(
                    "outbound_timeout", 504, "外部服务请求超时"
                ),
            ),
        ],
    )
    service = remote_service(client)

    with pytest.raises(RuntimeError, match="外部服务请求超时"):
        service._request_embedding_chunk_result(
            ["oak"], require_real=True, budget=budget
        )

    assert len(client.calls) == 1


def test_embedding_backoff_cannot_start_retry_at_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(4.0, clock=clock)
    client = AdvancingSafeRuntimeClient(
        clock,
        outcomes=[
            (
                3.0,
                OutboundRequestError(
                    "outbound_timeout", 504, "外部服务请求超时"
                ),
            ),
        ],
    )
    service = remote_service(client)
    monkeypatch.setattr(
        embedding_module.time,
        "sleep",
        lambda seconds: clock.advance(seconds),
    )

    result = service._request_embedding_chunk_result(
        ["oak"], require_real=False, budget=budget
    )

    assert result.items[0].source == "remote_fallback_fake"
    assert result.items[0].cacheable is False
    assert len(client.calls) == 1


def test_embedding_chunk_budget_starts_before_config_and_payload_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_started_at = embedding_module.time.monotonic()
    clock = ManualClock()
    clock.now = expected_started_at
    client = RecordingSafeRuntimeClient(
        [{"data": [{"index": 0, "embedding": [1.0]}]}]
    )
    service = remote_service(client)
    real_snapshot = service._runtime_config_snapshot

    def advancing_snapshot() -> Any:
        clock.advance(4.0)
        return real_snapshot()

    monkeypatch.setattr(embedding_module.time, "monotonic", clock)
    monkeypatch.setattr(service, "_runtime_config_snapshot", advancing_snapshot)

    assert service._request_embedding_chunk(["oak"], True) == [[1.0]]

    budget = client.calls[0]["budget"]
    assert isinstance(budget, DeadlineBudget)
    assert budget.deadline == expected_started_at + 23.0


@pytest.mark.parametrize("require_real", [True, False])
def test_embedding_parse_cannot_finish_after_chunk_budget(
    require_real: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = ManualClock()
    budget = DeadlineBudget.from_timeout(1.0, clock=clock)
    client = RecordingSafeRuntimeClient(
        [{"data": [{"index": 0, "embedding": [1.0]}]}]
    )
    service = remote_service(client)
    real_parser = service._parse_embedding_response

    def advancing_parser(data: Any, expected_count: int) -> list[list[float]]:
        result = real_parser(data, expected_count)
        clock.advance(1.0)
        return result

    monkeypatch.setattr(
        service, "_parse_embedding_response", advancing_parser
    )

    if require_real:
        with pytest.raises(RuntimeError, match="外部服务请求超时"):
            service._request_embedding_chunk_result(
                ["oak"], require_real=True, budget=budget
            )
        assert service._stats["fake_embeds"] == 0
    else:
        result = service._request_embedding_chunk_result(
            ["oak"], require_real=False, budget=budget
        )
        assert result.items[0].source == "remote_fallback_fake"
        assert result.items[0].cacheable is False
        assert result.items[0].vector == service._fake_embed("oak")
        assert service._stats["fake_embeds"] == 1

    assert len(client.calls) == 1
    assert client.calls[0]["budget"] is budget
    assert service._stats["api_calls"] == 0


def test_embedding_request_uses_safe_client_and_preserves_payload() -> None:
    client = RecordingSafeRuntimeClient(
        [{"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]}]
    )

    assert remote_service(client)._request_embedding_chunk(["x" * 2001, "oak"], True) == [[1.0], [2.0]]

    call = client.calls[0]
    assert isinstance(call["budget"], DeadlineBudget)
    assert 0 < call["budget"].remaining() <= 23
    assert {key: value for key, value in call.items() if key != "budget"} == {
        "base_url": "https://embedding.example/v1/",
        "request_target": "/embeddings",
        "headers": {"Authorization": "Bearer secret-key"},
        "json_body": {"model": "text-embedding-3-small", "input": ["x" * 2000 + "...", "oak"]},
        "allow_local": True,
        "max_bytes": EMBEDDING_JSON_MAX_BYTES,
    }


@pytest.mark.parametrize("payload", [
    {},
    {"data": "not-a-list"},
    {"data": []},
    {"data": ["not-a-dict"]},
    {"data": [{"embedding": [1.0]}]},
    {"data": [{"index": "0", "embedding": [1.0]}]},
    {"data": [{"index": 0, "embedding": []}]},
    {"data": [{"index": 0, "embedding": [True]}]},
    {"data": [{"index": 0, "embedding": [math.inf]}]},
])
def test_malformed_embedding_schema_has_fixed_public_error(payload: dict[str, Any]) -> None:
    client = RecordingSafeRuntimeClient([payload])

    with pytest.raises(RuntimeError, match="外部服务响应无效"):
        remote_service(client)._request_embedding_chunk(["oak"], False)


@pytest.mark.parametrize("code", ["outbound_connect_failed", "outbound_timeout"])
@pytest.mark.parametrize(
    ("require_real", "allow_fake", "uses_fake"),
    [(False, True, True), (False, False, False), (True, True, False), (True, False, False)],
)
def test_only_exhausted_availability_errors_can_use_fake_vectors(
    monkeypatch: pytest.MonkeyPatch,
    code: str,
    require_real: bool,
    allow_fake: bool,
    uses_fake: bool,
) -> None:
    public_message = "PUBLIC-AVAILABILITY-ERROR"
    client = RecordingSafeRuntimeClient(
        [OutboundRequestError(code, 504, public_message) for _ in range(3)]
    )
    service = remote_service(client)
    service.allow_fake_embeddings = allow_fake
    sleeps: list[int] = []
    monkeypatch.setattr("app.services.system.embedding.time.sleep", sleeps.append)

    if uses_fake:
        assert len(service._request_embedding_chunk(["oak"], require_real)) == 1
        assert service._stats["fake_embeds"] == 1
    else:
        with pytest.raises(RuntimeError, match=public_message):
            service._request_embedding_chunk(["oak"], require_real)
        assert service._stats["fake_embeds"] == 0

    assert len(client.calls) == 3
    assert sleeps == [1, 2]
    assert {call["base_url"] for call in client.calls} == {"https://embedding.example/v1/"}


@pytest.mark.parametrize(
    "error",
    [
        OutboundRequestError("private_network_blocked", 400, "PUBLIC-POLICY"),
        OutboundRequestError("outbound_bad_response", 502, "PUBLIC-SCHEMA"),
        OutboundRequestError("outbound_response_too_large", 502, "PUBLIC-SIZE"),
    ],
)
def test_nonretryable_outbound_errors_never_use_fake_vectors(
    error: OutboundRequestError,
) -> None:
    client = RecordingSafeRuntimeClient([error])
    service = remote_service(client)

    with pytest.raises(RuntimeError, match=error.public_message):
        service._request_embedding_chunk(["oak"], False)

    assert len(client.calls) == 1
    assert service._stats["fake_embeds"] == 0


def test_chunk_uses_one_local_policy_snapshot_for_all_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingSafeRuntimeClient(
        [OutboundRequestError("outbound_timeout", 504, "PUBLIC") for _ in range(3)]
    )
    service = remote_service(client)
    service.allow_fake_embeddings = False
    client.on_call = lambda _: setattr(service, "allow_local_ai_endpoints", False)
    monkeypatch.setattr("app.services.system.embedding.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="PUBLIC"):
        service._request_embedding_chunk(["oak"], False)

    assert [call["allow_local"] for call in client.calls] == [True, True, True]


def test_chunk_snapshots_complete_provider_config_across_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingSafeRuntimeClient([
        OutboundRequestError("outbound_timeout", 504, "PUBLIC-A"),
        {"data": [{"index": 0, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": [2.0]}]},
    ])
    service = EmbeddingService(
        provider="provider-a",
        base_url="https://provider-a.example/v1",
        api_key="key-a",
        model="model-a",
        enabled=True,
        timeout=11,
        allow_fake_embeddings=False,
        runtime_client=client,
        allow_local_ai_endpoints=True,
    )

    def switch_to_provider_b(call_number: int) -> None:
        if call_number != 1:
            return
        service.provider = "provider-b"
        service.api_base_url = "https://provider-b.example/v1"
        service.api_key = "key-b"
        service.model = "model-b"
        service.enabled = True
        service.timeout = 29
        service.allow_local_ai_endpoints = False
        service.allow_fake_embeddings = True

    client.on_call = switch_to_provider_b
    monkeypatch.setattr("app.services.system.embedding.time.sleep", lambda _: None)

    assert service._request_embedding_chunk(["first"], True) == [[1.0]]
    assert service._request_embedding_chunk(["second"], True) == [[2.0]]

    assert client.calls[0]["budget"] is client.calls[1]["budget"]
    assert client.calls[2]["budget"] is not client.calls[0]["budget"]
    assert [
        {key: value for key, value in call.items() if key != "budget"}
        for call in client.calls
    ] == [
        {
            "base_url": "https://provider-a.example/v1",
            "request_target": "/embeddings",
            "headers": {"Authorization": "Bearer key-a"},
            "json_body": {"model": "model-a", "input": ["first"]},
            "allow_local": True,
            "max_bytes": EMBEDDING_JSON_MAX_BYTES,
        },
        {
            "base_url": "https://provider-a.example/v1",
            "request_target": "/embeddings",
            "headers": {"Authorization": "Bearer key-a"},
            "json_body": {"model": "model-a", "input": ["first"]},
            "allow_local": True,
            "max_bytes": EMBEDDING_JSON_MAX_BYTES,
        },
        {
            "base_url": "https://provider-b.example/v1",
            "request_target": "/embeddings",
            "headers": {"Authorization": "Bearer key-b"},
            "json_body": {"model": "model-b", "input": ["second"]},
            "allow_local": False,
            "max_bytes": EMBEDDING_JSON_MAX_BYTES,
        },
    ]


def test_chunk_does_not_enable_fake_fallback_after_first_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RecordingSafeRuntimeClient([
        OutboundRequestError("outbound_timeout", 504, "PUBLIC")
        for _ in range(6)
    ])
    service = remote_service(client)
    service.allow_fake_embeddings = False

    def enable_fake_after_first_failure(call_number: int) -> None:
        if call_number == 1:
            service.allow_fake_embeddings = True

    client.on_call = enable_fake_after_first_failure
    monkeypatch.setattr("app.services.system.embedding.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="PUBLIC"):
        service._request_embedding_chunk(["strict-chunk"], False)
    assert service._stats["fake_embeds"] == 0

    assert len(service._request_embedding_chunk(["next-chunk"], False)) == 1
    assert service._stats["fake_embeds"] == 1


def test_public_embed_binds_cache_and_metadata_to_generation_config(
    tmp_path: Path,
) -> None:
    client = RecordingSafeRuntimeClient([
        {"data": [{"index": 0, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": [2.0]}]},
    ])
    service = EmbeddingService(
        provider="provider-a",
        dimension=1,
        base_url="https://provider-a.example/v1",
        api_key="key-a",
        model="model-a",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
        allow_local_ai_endpoints=True,
    )

    def switch_to_provider_b(call_number: int) -> None:
        if call_number == 1:
            service.configure_runtime_config(
                provider="provider-b",
                base_url="https://provider-b.example/v1",
                api_key="key-b",
                model="model-b",
                enabled=True,
                allow_local_ai_endpoints=False,
            )

    client.on_call = switch_to_provider_b

    first = service.embed(["same text"], require_real=True)
    second = service.embed(["same text"], require_real=True)

    assert first == [[1.0]]
    assert (second, len(client.calls)) == ([[2.0]], 2)
    assert [call["base_url"] for call in client.calls] == [
        "https://provider-a.example/v1",
        "https://provider-b.example/v1",
    ]
    assert service._stats["cache_hits"] == 0

    cache_files = list((tmp_path / "vectors").glob("*/*.json"))
    assert len(cache_files) == 2
    namespace, endpoint_identity = _remote_cache_namespace(
        "provider-a",
        "model-a",
        "https://provider-a.example/v1",
    )
    provider_a_key = hashlib.sha256(
        f"{namespace}:same text".encode()
    ).hexdigest()
    provider_a_file = next(path for path in cache_files if path.stem == provider_a_key)
    provider_a_data = json.loads(provider_a_file.read_text(encoding="utf-8"))
    assert provider_a_data["metadata"] == {
        "source": "remote",
        "endpoint_identity": endpoint_identity,
        "cache_namespace": namespace,
        "provider": "provider-a",
        "model": "model-a",
        "dimension": 1,
        "model_identifier": "provider-a_model-a",
        "text_preview": "same text",
    }


def test_remote_fallback_fake_does_not_satisfy_later_require_real(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = RecordingSafeRuntimeClient([
        *_timeout_errors(),
        {"data": [{"index": 0, "embedding": [2.0]}]},
    ])
    service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1",
        api_key="secret-key",
        model="model-a",
        enabled=True,
        allow_fake_embeddings=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )
    monkeypatch.setattr("app.services.system.embedding.time.sleep", lambda _: None)

    fallback = service.embed(["oak"], require_real=False)
    real = service.embed(["oak"], require_real=True)

    assert real == [[2.0]]
    assert real != fallback
    assert len(client.calls) == 4


def test_remote_fallback_fake_is_not_reused_from_disk_by_new_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_client = RecordingSafeRuntimeClient(_timeout_errors())
    first_service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1",
        api_key="first-key",
        model="model-a",
        enabled=True,
        allow_fake_embeddings=True,
        cache_dir=tmp_path,
        runtime_client=first_client,
    )
    monkeypatch.setattr("app.services.system.embedding.time.sleep", lambda _: None)

    fallback = first_service.embed(["oak"], require_real=False)

    second_client = RecordingSafeRuntimeClient([
        {"data": [{"index": 0, "embedding": [3.0]}]},
    ])
    second_service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1",
        api_key="second-key",
        model="model-a",
        enabled=True,
        allow_fake_embeddings=False,
        cache_dir=tmp_path,
        runtime_client=second_client,
    )

    real = second_service.embed(["oak"], require_real=True)

    assert real == [[3.0]]
    assert real != fallback
    assert len(second_client.calls) == 1
    assert second_service._stats["disk_cache_hits"] == 0


def test_require_real_does_not_read_cached_local_fake(tmp_path: Path) -> None:
    service = EmbeddingService(
        provider="local",
        dimension=2,
        enabled=False,
        cache_dir=tmp_path,
    )

    assert len(service.embed(["oak"], require_real=False)) == 1
    assert list((tmp_path / "vectors").glob("*/*.json"))

    with pytest.raises(RuntimeError, match="需要真实 embedding，但服务未配置"):
        service.embed(["oak"], require_real=True)


def test_same_provider_model_at_different_endpoints_do_not_share_cache(
    tmp_path: Path,
) -> None:
    client = RecordingSafeRuntimeClient([
        {"data": [{"index": 0, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": [2.0]}]},
    ])
    service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://provider-a.example/v1",
        api_key="key-a",
        model="shared-model",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )

    assert service.embed(["oak"], require_real=True) == [[1.0]]
    service.configure_runtime_config(
        provider="openai",
        base_url="https://provider-b.example/v1",
        api_key="key-b",
        model="shared-model",
        enabled=True,
        allow_local_ai_endpoints=False,
    )
    assert service.embed(["oak"], require_real=True) == [[2.0]]

    assert len(client.calls) == 2
    assert [call["base_url"] for call in client.calls] == [
        "https://provider-a.example/v1",
        "https://provider-b.example/v1",
    ]


def test_successful_remote_vector_can_satisfy_require_real_cache(
    tmp_path: Path,
) -> None:
    client = RecordingSafeRuntimeClient([
        {"data": [{"index": 0, "embedding": [4.0]}]},
    ])
    service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1",
        api_key="secret-key",
        model="model-a",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )

    assert service.embed(["oak"], require_real=False) == [[4.0]]
    assert service.embed(["oak"], require_real=True) == [[4.0]]
    assert len(client.calls) == 1
    assert service._stats["memory_cache_hits"] == 1


def test_invalid_remote_endpoint_cannot_reuse_valid_memory_cache(
    tmp_path: Path,
) -> None:
    client = RecordingSafeRuntimeClient(
        [{"data": [{"index": 0, "embedding": [4.0]}]}]
    )
    service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1",
        api_key="secret-key",
        model="model-a",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )

    assert service.embed(["oak"], require_real=True) == [[4.0]]
    service.api_base_url = "https://embedding.example/v1?tenant=other"

    with pytest.raises(OutboundRequestError) as exc_info:
        service.embed(["oak"], require_real=True)

    assert exc_info.value.code == "outbound_url_invalid"
    assert len(client.calls) == 1


def test_invalid_remote_endpoint_cannot_reuse_valid_disk_cache(
    tmp_path: Path,
) -> None:
    client = RecordingSafeRuntimeClient(
        [{"data": [{"index": 0, "embedding": [4.0]}]}]
    )
    writer = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1",
        api_key="secret-key",
        model="model-a",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )

    assert writer.embed(["oak"], require_real=True) == [[4.0]]
    assert list((tmp_path / "vectors").glob("*/*.json"))

    reader = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url="https://embedding.example/v1?tenant=other",
        api_key="secret-key",
        model="model-a",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )

    with pytest.raises(OutboundRequestError) as exc_info:
        reader.embed(["oak"], require_real=True)

    assert exc_info.value.code == "outbound_url_invalid"
    assert len(client.calls) == 1


def test_remote_cache_metadata_uses_digest_and_never_stores_endpoint_or_key(
    tmp_path: Path,
) -> None:
    raw_base_url = "https://Endpoint-Secret.Example:443/v1/"
    api_key = "KEY-CACHE-SECRET"
    client = RecordingSafeRuntimeClient([
        {"data": [{"index": 0, "embedding": [5.0]}]},
    ])
    service = EmbeddingService(
        provider="openai",
        dimension=1,
        base_url=raw_base_url,
        api_key=api_key,
        model="model-secret",
        enabled=True,
        cache_dir=tmp_path,
        runtime_client=client,
    )

    assert service.embed(["secret text"], require_real=True) == [[5.0]]

    namespace, endpoint_identity = _remote_cache_namespace(
        "openai",
        "model-secret",
        "https://endpoint-secret.example:443/v1/",
    )
    expected_key = hashlib.sha256(
        f"{namespace}:secret text".encode()
    ).hexdigest()
    cache_files = list((tmp_path / "vectors").glob("*/*.json"))
    assert [path.stem for path in cache_files] == [expected_key]
    raw_cache = cache_files[0].read_text(encoding="utf-8")
    metadata = json.loads(raw_cache)["metadata"]
    assert metadata["source"] == "remote"
    assert metadata["endpoint_identity"] == endpoint_identity
    assert metadata["cache_namespace"] == namespace
    combined = cache_files[0].name + raw_cache
    assert raw_base_url not in combined
    assert api_key not in combined
    assert "/embeddings" not in combined


@pytest.mark.parametrize("enable_concurrency", [False, True])
def test_mixed_remote_chunks_only_cache_real_vectors_and_preserve_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    enable_concurrency: bool,
) -> None:
    class MixedChunkClient:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.recover_fallback = False
            self._lock = threading.Lock()

        def post_json(self, base_url: str, **kwargs: Any) -> dict[str, Any]:
            text = kwargs["json_body"]["input"][0]
            with self._lock:
                self.calls.append(text)
                recover_fallback = self.recover_fallback
            if text == "fallback" and not recover_fallback:
                raise OutboundRequestError(
                    "outbound_timeout", 504, "PUBLIC-TIMEOUT"
                )
            vectors = {
                "first": [1.0, 0.0],
                "fallback": [0.5, 0.5],
                "third": [0.0, 1.0],
            }
            return {"data": [{"index": 0, "embedding": vectors[text]}]}

    client = MixedChunkClient()
    service = EmbeddingService(
        provider="openai",
        dimension=2,
        base_url="https://embedding.example/v1",
        api_key="secret-key",
        model="model-a",
        enabled=True,
        allow_fake_embeddings=True,
        cache_dir=tmp_path,
        max_parallel_requests=3,
        enable_concurrency=enable_concurrency,
        runtime_client=client,  # type: ignore[arg-type]
    )
    monkeypatch.setattr("app.services.system.embedding.time.sleep", lambda _: None)
    fake_vector = service._fake_embed("fallback")

    first = service.embed(
        ["first", "fallback", "third"],
        require_real=False,
        batch_size=1,
    )
    assert first == [[1.0, 0.0], fake_vector, [0.0, 1.0]]
    assert len(list((tmp_path / "vectors").glob("*/*.json"))) == 2

    client.recover_fallback = True
    second = service.embed(
        ["first", "fallback", "third"],
        require_real=True,
        batch_size=1,
    )
    assert second == [[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]]
    assert client.calls.count("first") == 1
    assert client.calls.count("third") == 1
    assert client.calls.count("fallback") == 4


def test_concurrent_chunks_preserve_input_order_and_stats() -> None:
    client = RecordingSafeRuntimeClient([])
    first_started = threading.Event()
    second_started = threading.Event()

    def delayed_post(base_url: str, **kwargs: Any) -> dict[str, Any]:
        text = kwargs["json_body"]["input"][0]
        client.calls.append({"base_url": base_url, **kwargs})
        if text == "first":
            first_started.set()
            assert second_started.wait(timeout=2)
        elif text == "second":
            assert first_started.wait(timeout=2)
            second_started.set()
        return {"data": [{"index": 0, "embedding": [float(len(text))]}]}

    client.post_json = delayed_post  # type: ignore[method-assign]
    service = remote_service(client)
    service.enable_concurrency = True
    service.max_parallel_requests = 2

    assert service._remote_embed_batch(
        ["first", "second", "third", "fourth"], require_real=True, batch_size=1
    ) == [[5.0], [6.0], [5.0], [6.0]]
    assert service._stats["api_calls"] == 4
    assert len(client.calls) == 4


def test_secrets_are_redacted_from_unexpected_client_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = RecordingSafeRuntimeClient([RuntimeError("UNDERLYING-SECRET")])
    service = EmbeddingService(
        base_url="https://BASE-SECRET.example",
        api_key="KEY-SECRET",
        model="model",
        enabled=True,
        runtime_client=client,
    )

    with pytest.raises(RuntimeError) as exc_info:
        with caplog.at_level("WARNING"):
            service._request_embedding_chunk(["TEXT-SECRET"], True)

    combined = caplog.text + str(exc_info.value)
    for secret in ("UNDERLYING-SECRET", "BASE-SECRET", "KEY-SECRET", "TEXT-SECRET"):
        assert secret not in combined


def test_malformed_response_content_is_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = RecordingSafeRuntimeClient([{"data": "RESPONSE-SECRET"}])

    with pytest.raises(RuntimeError) as exc_info:
        with caplog.at_level("WARNING"):
            remote_service(client)._request_embedding_chunk(["TEXT-SECRET"], False)

    assert "RESPONSE-SECRET" not in caplog.text + str(exc_info.value)


@pytest.mark.parametrize(
    ("payload", "expected_count"),
    [
        ({"data": [{"index": 0, "embedding": [1.0]}]}, 2),
        ({"data": [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [2.0]}, {"index": 2, "embedding": [3.0]}]}, 2),
        ({"data": [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}]}, 2),
        ({"data": [{"index": 0, "embedding": [1.0]}, {"index": 2, "embedding": [2.0]}]}, 2),
        ({"data": [{"index": 0, "embedding": ["not-a-number"]}]}, 1),
    ],
)
def test_embedding_parser_rejects_complete_schema_failure_matrix(
    payload: dict[str, Any], expected_count: int,
) -> None:
    with pytest.raises(OutboundRequestError) as exc_info:
        EmbeddingService._parse_embedding_response(payload, expected_count)
    assert exc_info.value.code == "outbound_bad_response"
    assert str(exc_info.value) == "外部服务响应无效"


def test_embedding_parser_orders_valid_out_of_order_indices() -> None:
    assert EmbeddingService._parse_embedding_response(
        {"data": [{"index": 2, "embedding": [3]}, {"index": 0, "embedding": [1.5]}, {"index": 1, "embedding": [2]}]},
        3,
    ) == [[1.5], [2.0], [3.0]]


def test_embedding_module_has_no_direct_network_bypass() -> None:
    source = Path(embedding_module.__file__).read_text(encoding="utf-8")
    assert _find_forbidden_network_uses(source) == []


@pytest.mark.parametrize(
    "source",
    [
        "from urllib import request as req\nreq.urlopen('https://example.com')\n",
        "import urllib as u\nu.request.urlopen('https://example.com')\n",
        "import urllib as u\nreq = u.request\nreq.urlopen('https://example.com')\n",
    ],
)
def test_embedding_network_guard_rejects_urllib_alias_mutations(source: str) -> None:
    assert _find_forbidden_network_uses(source)
