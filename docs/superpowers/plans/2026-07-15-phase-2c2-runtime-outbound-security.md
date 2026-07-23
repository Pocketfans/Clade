# Clade Phase 2C-2 Runtime Outbound Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `ModelRouter` 的七个运行时网络入口和 `EmbeddingService` 的每个远程批次全部经过统一安全出口，真正固定 DNS 审批结果，并对同步、异步、流式响应实施脱敏、超时和大小限制。

**Architecture:** 继续复用 Phase 2C-1 的 `OutboundURLPolicy`，把固定 IP 传输原语提取到同步/异步共用模块；新增只接收“无 query 的基础地址 + 严格同源相对请求目标”的运行时客户端。业务层保留服务商选择、请求格式、响应解析、并发、心跳、统计和合法降级，仅把实际网络发送委托给安全客户端。

**Tech Stack:** Python 3.12、httpx 0.28.1、httpcore 1.0.9、asyncio、pytest 9.1.1；既有 FastAPI/React/TypeScript/Vitest/Vite 门禁不升级依赖。

## Global Constraints

- 本计划只实施 Phase 2C-2；不修改数据库、存档格式、前端配置结构、模型选择算法、负载均衡算法或 Embedding 数学逻辑。
- `OutboundURLPolicy` 继续拒绝带 query 或 fragment 的 URL；不得放宽 Phase 2C-1 策略。
- 运行时客户端必须分开接收 `base_url` 与 `request_target`。先验证 `base_url`，再校验和拼接 target；禁止 `urljoin`。
- 每次网络尝试都重新执行 URL/DNS 策略；传输层只连接本次 `ValidatedOutboundURL.resolved_ips`，不得再次解析或加入新 IP。
- 选中的负载均衡 provider 若被安全策略拒绝，立即失败；不得选择池中下一个 provider。
- 公网只允许 HTTPS。本地例外仍仅限开关开启后的规范 `localhost`、字面量 `127.0.0.1`、字面量 `::1`。
- `trust_env=False`、`follow_redirects=False`、禁止 Unix socket；Host、TLS SNI 和证书验证仍使用原始规范主机名。
- 所有请求强制 `Accept-Encoding: identity`；响应声明任何非 identity 编码时，在读取正文前失败。
- 非 2xx、超限 `Content-Length` 和非法编码响应必须零正文读取。
- 普通 AI JSON 上限 `8 * 1024 * 1024` 字节；Embedding JSON 上限 `16 * 1024 * 1024`；流式总量上限 16 MiB、单行事件上限 1 MiB。
- connect 10 秒、write 30 秒、pool 10 秒；普通 read 使用当前配置值（默认 60 秒）；流式空闲 120 秒、总时长 600 秒。
- 运行时客户端不自行做业务重试。调用方每次重试都重新调用客户端，从而重新验证 DNS。
- 只有 `outbound_connect_failed` 和 `outbound_timeout` 属于可重试可用性错误；其他 `OutboundRequestError` 均为不可重试安全/响应错误。
- Embedding 安全/响应错误不得生成假向量；只有连接失败或超时重试耗尽，且 `require_real=False`、`allow_fake_embeddings=True` 时可沿用假向量降级。
- 异常、日志和流式错误事件不得包含 API key、Authorization、query、完整 URL、请求/响应正文或底层异常原文。
- 测试只使用假 resolver、假同步/异步 backend 或注入的安全客户端；不得访问真实公网。
- 不新增生产依赖，不运行 `npm install`，不升级锁文件。
- Phase 2C-2 完成前不合并、不发布；最终需审查 Phase 2C 完整范围且无未解决 Critical/Important 问题。

---

## Execution Environment

从下列隔离工作区执行全部命令：

```powershell
Set-Location 'E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2c-outbound-url-security'
$PYTHON = (Resolve-Path '..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe').Path
```

若 Python 路径不存在，暂停并报告环境变化，不自行创建环境或安装依赖。前端使用已连接的 `node_modules`。

当前 Phase 2C-1 基线：后端 693 passed、2 skipped、45 warnings；前端 84 passed；ESLint 0 errors、162 warnings。新测试必须增加通过数，不得增加失败、跳过或警告基线。

## Final Interfaces

### `backend/app/security/pinned_transport.py`

```python
PinnedSyncTransport(
    validated: ValidatedOutboundURL,
    network_backend: httpcore.NetworkBackend | None = None,
)

PinnedAsyncTransport(
    validated: ValidatedOutboundURL,
    network_backend: httpcore.AsyncNetworkBackend | None = None,
)
```

默认 backend 分别为 `httpcore.SyncBackend()` 和 `httpcore.AnyIOBackend()`。模块内部包含同步/异步 pinned backend、脱敏 backend/stream、httpcore 到 httpx 的 response stream 适配器；业务层不得直接导入私有类。

### `backend/app/security/runtime_http.py`

```python
AI_JSON_MAX_BYTES = 8 * 1024 * 1024
EMBEDDING_JSON_MAX_BYTES = 16 * 1024 * 1024
STREAM_MAX_BYTES = 16 * 1024 * 1024
STREAM_EVENT_MAX_BYTES = 1 * 1024 * 1024

RETRYABLE_OUTBOUND_CODES = frozenset(
    {"outbound_connect_failed", "outbound_timeout"}
)


@dataclass(frozen=True)
class RuntimeTimeouts:
    connect: float = 10.0
    read: float = 60.0
    write: float = 30.0
    pool: float = 10.0
    stream_idle: float = 120.0
    stream_total: float = 600.0


SafeRuntimeClient(
    policy: OutboundURLPolicy | None = None,
    *,
    sync_network_backend: httpcore.NetworkBackend | None = None,
    async_network_backend: httpcore.AsyncNetworkBackend | None = None,
    timeouts: RuntimeTimeouts = RuntimeTimeouts(),
)

SafeRuntimeClient.post_json(
    base_url: str,
    *,
    request_target: str,
    headers: Mapping[str, str],
    json_body: Mapping[str, Any],
    allow_local: bool,
    read_timeout: float,
    max_bytes: int = AI_JSON_MAX_BYTES,
) -> dict[str, Any]

SafeRuntimeClient.apost_json(
    base_url: str,
    *,
    request_target: str,
    headers: Mapping[str, str],
    json_body: Mapping[str, Any],
    allow_local: bool,
    read_timeout: float,
    max_bytes: int = AI_JSON_MAX_BYTES,
) -> dict[str, Any]

SafeRuntimeClient.astream_lines(
    base_url: str,
    *,
    request_target: str,
    headers: Mapping[str, str],
    json_body: Mapping[str, Any],
    allow_local: bool,
    max_bytes: int = STREAM_MAX_BYTES,
    max_event_bytes: int = STREAM_EVENT_MAX_BYTES,
    idle_timeout: float | None = None,
    total_timeout: float | None = None,
) -> AsyncIterator[str]
```

成功的 JSON 调用只返回 JSON 对象；非 2xx 一律抛固定 `outbound_bad_response`，不返回上游正文。三个方法对外只抛 `OutboundRequestError`；`CancelledError` 必须原样向上传播。

### Business injection

`ModelRouter` 和 `EmbeddingService` 都在现有构造参数末尾增加 `runtime_client: SafeRuntimeClient | None = None` 与 `allow_local_ai_endpoints: bool = False`。这样旧调用无需修改。`configure_model_router()` 每次刷新时同时写入两个对象的 `allow_local_ai_endpoints` 当前值。

## File Responsibility Map

| 文件 | 单一职责 |
| --- | --- |
| `backend/app/security/pinned_transport.py` | 同步/异步固定批准 IP、Host/SNI 保留、底层异常脱敏与资源关闭 |
| `backend/app/security/runtime_http.py` | target 校验、请求头清洗、超时、状态/编码/大小/JSON/流式边界、错误映射 |
| `backend/app/security/safe_http.py` | 保持 Phase 2C-1 探测 API 与总截止时间，仅改为复用同步公共传输 |
| `backend/app/ai/model_router.py` | provider 请求构造与现有响应解析；七个入口委托安全客户端 |
| `backend/app/core/ai_router_config.py` | 把当前本地 AI 开关注入 router 与 embedding service |
| `backend/app/services/system/embedding.py` | 保留批次/并发/重试/统计/降级，只替换网络边界与错误分类 |

---

### Task 1: Extract the reusable synchronous pinned transport

**Files:**
- Create: `backend/app/security/pinned_transport.py`
- Create: `backend/app/security/tests/test_pinned_transport.py`
- Modify: `backend/app/security/safe_http.py`

**Interfaces:** Produces `PinnedSyncTransport`; preserves every existing `SafeProbeClient` signature and behavior.

- [ ] **Step 1: Write failing sync transport tests**

建立记录 `connect_tcp()` 参数、Host、SNI、关闭次数的假 backend/stream。至少包含：

测试名与精确断言如下：

- `test_sync_transport_tries_only_approved_ips_in_order`：连接序列严格等于批准 IP 顺序；
- `test_sync_transport_rejects_request_origin_mismatch`：host 或 port 任一不符均在连接前失败；
- `test_sync_transport_rejects_unix_socket`：delegate 的 Unix 方法调用次数保持 0；
- `test_sync_transport_keeps_original_host_and_tls_server_name`：HTTP Host 与 TLS server name 都是规范域名；
- `test_sync_transport_sanitizes_connect_read_write_and_tls_errors`：每类错误不含哨兵；
- `test_sync_transport_closes_response_and_pool_once`：成功和异常路径的关闭次数都精确为 1。

`origin mismatch` 必须分别覆盖 host 和 port。错误断言只允许固定短句，不得包含假 backend 的哨兵异常文本。

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_pinned_transport.py -q
```

Expected: collection fails because `app.security.pinned_transport` does not exist.

- [ ] **Step 3: Move the existing sync primitives without changing semantics**

从 `safe_http.py` 移出 `_PinnedNetworkBackend`、`_SanitizedNetworkBackend`、`_SanitizedNetworkStream`、`_CoreResponseStream`、`_PinnedTransport`。公共类改名为 `PinnedSyncTransport`；其 `handle_request()` 必须继续把 `request.url.raw_host/raw_path/port` 交给 httpcore，连接目标只来自 approved IP：

```python
if host != self._validated.hostname or port != self._validated.port:
    raise httpcore.ConnectError("outbound origin does not match approval")

for approved_ip in self._validated.resolved_ips:
    try:
        return self._delegate.connect_tcp(
            str(approved_ip),
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
    except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
        last_error = exc
raise httpcore.ConnectError("all approved addresses failed") from last_error
```

`safe_http.py` 只导入 `PinnedSyncTransport`，`SafeProbeClient._client()` 继续设置 `trust_env=False`、`follow_redirects=False`、原有超时和 identity header。

- [ ] **Step 4: Run sync and Phase 2C-1 regression suites**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_pinned_transport.py backend/app/security/tests/test_safe_http.py backend/app/security/tests/test_outbound_url.py -q
```

Expected: all selected tests pass; existing Phase 2C-1 test count is unchanged and no new warning appears.

- [ ] **Step 5: Review and commit Task 1**

```powershell
git diff --check
git add backend/app/security/pinned_transport.py backend/app/security/safe_http.py backend/app/security/tests/test_pinned_transport.py
git commit -m "refactor: extract pinned sync transport"
```

Review checkpoint: reject the task if the probe client API changes, if a normal DNS lookup can occur after validation, or if TLS uses an approved IP as SNI.

---

### Task 2: Add the equivalent asynchronous pinned transport

**Files:**
- Modify: `backend/app/security/pinned_transport.py`
- Modify: `backend/app/security/tests/test_pinned_transport.py`

**Interfaces:** Produces `PinnedAsyncTransport(httpx.AsyncBaseTransport)` using `httpcore.AsyncConnectionPool` and injected `httpcore.AsyncNetworkBackend`.

- [ ] **Step 1: Write failing async parity and cleanup tests**

新增五个 `pytest.mark.asyncio` 测试：

- `test_async_transport_tries_only_approved_ips_in_order`；
- `test_async_transport_keeps_original_host_and_tls_server_name`；
- `test_async_transport_rejects_origin_mismatch_and_unix_socket`；
- `test_async_transport_sanitizes_backend_error_text`；
- `test_async_transport_closes_on_success_error_and_cancellation_once`。

前四项断言与同步版本相同；第五项分别断言成功、读取错误和取消时 response stream 与 pool 各关闭一次。

Cancellation test must cancel while fake stream is awaiting `read()` and assert `CancelledError` propagates plus stream/pool `aclose()` count equals one.

- [ ] **Step 2: Verify RED**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_pinned_transport.py -q -k async
```

Expected: imports or assertions fail because `PinnedAsyncTransport` is absent.

- [ ] **Step 3: Implement async counterparts with exact httpcore contracts**

Implement private `_PinnedAsyncNetworkBackend` and sanitized async backend/stream. Methods `connect_tcp`、`read`、`write`、`start_tls`、`aclose` must be `async`; `connect_unix_socket` always raises the fixed connect error. Wrap core stream with:

```python
class _CoreAsyncResponseStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()
```

`PinnedAsyncTransport.handle_async_request()` mirrors the sync request construction and checks final host/port through the pinned backend. `aclose()` delegates once to `AsyncConnectionPool.aclose()`.

- [ ] **Step 4: Run complete transport tests**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_pinned_transport.py backend/app/security/tests/test_safe_http.py -q
```

Expected: sync/async parity and old probe tests all pass; no real network access.

- [ ] **Step 5: Review and commit Task 2**

```powershell
git diff --check
git add backend/app/security/pinned_transport.py backend/app/security/tests/test_pinned_transport.py
git commit -m "feat: add pinned async transport"
```

---

### Task 3: Implement safe synchronous and asynchronous JSON POST

**Files:**
- Create: `backend/app/security/runtime_http.py`
- Create: `backend/app/security/tests/test_runtime_http.py`
- Modify: `backend/app/security/__init__.py`

**Interfaces:** Produces constants, `RuntimeTimeouts`, `RETRYABLE_OUTBOUND_CODES`, `SafeRuntimeClient.post_json()` and `.apost_json()` from the Final Interfaces section.

- [ ] **Step 1: Write target-validation tests first**

Use a fake policy that records every validation and returns a fixed `ValidatedOutboundURL`. Parameterize:

```python
INVALID_TARGETS = [
    "", "relative", "//evil.example/path", "https://evil.example/path",
    "/ok#fragment", "/bad\\path", "/bad path", "/bad\npath",
    "/forward/https://evil.example", "/forward?next=https://evil.example",
]

VALIDATED_BASE = "https://public.example/v1"
VALID_TARGET = "/chat/completions"
EXPECTED_FINAL_URL = "https://public.example/v1/chat/completions"
```

`test_request_target_rejects_origin_escape_and_ambiguous_forms` 对 `INVALID_TARGETS` 全部断言 `outbound_url_invalid`。`test_request_target_preserves_validated_base_path_without_urljoin` 断言传输实际收到 `EXPECTED_FINAL_URL`。

同时断言 `base_url` 中的 query/fragment 仍由真实 `OutboundURLPolicy` 拒绝。合法 Google target 使用已经编码的模型段和 `urlencode({"key": "sentinel"})`，并验证 target 不改变 origin。

- [ ] **Step 2: Write JSON boundary/error tests**

同步和异步共用参数矩阵，至少覆盖：

- 2xx JSON object 成功；JSON array/null/string 拒绝；
- 3xx/4xx/5xx 零正文读取，且不跟随 Location；
- `Content-Encoding: gzip/br/空值` 零正文读取并拒绝；`identity` 或缺失允许；
- `Content-Length` 等于限制允许，限制加一零正文读取；负值/非整数拒绝；
- 无 `Content-Length` 时精确读到 `max_bytes + 1` 后停止；
- connect/read/write/TLS/protocol 错误映射到固定错误码；
- `Host` 与调用者 `Accept-Encoding` 被移除，最终 header 强制 identity；
- `trust_env=False`、`follow_redirects=False`；
- exception 和 `caplog.text` 不含 header/query/body/backend 四个独立哨兵。

Because httpx's own INFO log can include the complete request URL, implement a `ContextVar[bool]`-backed logging filter in `runtime_http.py`. Install it on `httpx` and the existing httpcore logger names; set/reset the context token around each sync/async runtime operation. The filter suppresses only records created inside the protected operation, so unrelated application logs and concurrent non-runtime tasks are unaffected. Tests set the logger levels to DEBUG and prove the Google query sentinel never reaches `caplog`.

- [ ] **Step 3: Verify RED**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_runtime_http.py -q
```

Expected: collection fails because `app.security.runtime_http` does not exist.

- [ ] **Step 4: Implement strict target assembly and shared response guards**

Target helper must implement exactly this order：类型/空值、控制或空白、反斜杠、`#`、单斜杠前缀、`urlsplit()` 后 scheme/netloc/fragment 为空、原始 target 不含 `://`，最后：

```python
request_url = validated.url.rstrip("/") + request_target
```

Do not log or return `request_target`. Before body read, call helpers equivalent to:

```python
def _check_response_headers(response: httpx.Response, max_bytes: int) -> None:
    if not 200 <= response.status_code < 300:
        raise _bad_response()
    _reject_non_identity_encoding(response.headers)
    _reject_oversized_content_length(response.headers, max_bytes)
```

Read raw bytes only (`iter_raw` / `aiter_raw`), cap at `max_bytes + 1`, decode/parse JSON, require `dict`. Always close response/client/transport in `finally` or context managers.

- [ ] **Step 5: Implement per-attempt validation and fixed error mapping**

Each public method starts with:

```python
validated = self._policy.validate(base_url, allow_local=allow_local)
request_url = _validated_request_url(validated, request_target)
```

Create a new pinned transport/client for that call. Map timeout to `outbound_timeout`; connect/TLS/network to `outbound_connect_failed`; protocol/encoding/status/JSON to `outbound_bad_response`; limit to `outbound_response_too_large`. Re-raise existing `OutboundRequestError`; never include `str(exc)` in public errors or logs.

- [ ] **Step 6: Run focused and complete security tests**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_runtime_http.py -q
& $PYTHON -m pytest backend/app/security/tests -q
```

Expected: all tests pass; Phase 2C-1 tests remain green; resolver call count equals one per client invocation.

- [ ] **Step 7: Review and commit Task 3**

```powershell
git diff --check
git add backend/app/security/runtime_http.py backend/app/security/__init__.py backend/app/security/tests/test_runtime_http.py
git commit -m "feat: add safe runtime JSON client"
```

Review checkpoint: inspect `runtime_http.py` for `urljoin`, unrestricted `httpx` transport, `response.read()/aread()` before guards, and any raw exception interpolation; all must be absent.

---

### Task 4: Add bounded asynchronous line streaming

**Files:**
- Modify: `backend/app/security/runtime_http.py`
- Modify: `backend/app/security/tests/test_runtime_http.py`

**Interfaces:** Produces `SafeRuntimeClient.astream_lines()` with 16 MiB total, 1 MiB per yielded line/event, 120-second idle and 600-second total defaults.

- [ ] **Step 1: Write failing stream contract tests**

新增六个 `pytest.mark.asyncio` 流式测试：

- `test_stream_yields_utf8_lines_and_trims_terminal_carriage_return`；
- `test_stream_rejects_event_limit_plus_one_and_total_limit_plus_one`；
- `test_stream_rejects_non_2xx_encoding_and_content_length_before_read`；
- `test_stream_idle_timeout_and_total_deadline_are_distinct`；
- `test_stream_closes_once_on_success_parse_error_early_aclose_and_cancel`；
- `test_stream_error_and_logs_redact_all_sentinels`。

前三项逐字节断言交付内容和零读取边界；后三项断言错误码、关闭次数与哨兵缺失。

边界使用较小的注入值（例如 total=8、event=4）证明“等于允许、加一拒绝”，避免分配真实 16 MiB。调用者提前结束测试必须显式 `await iterator.aclose()`。

- [ ] **Step 2: Verify RED**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_runtime_http.py -q -k stream
```

Expected: tests fail because `astream_lines` is absent.

- [ ] **Step 3: Implement raw bounded line iteration**

Do not use unbounded `response.aiter_lines()`. Iterate `aiter_raw()`, increment total before buffering, split on byte `b"\n"`, reject a buffered line once over `max_event_bytes`, decode each completed line as strict UTF-8, and remove one terminal `\r`. At EOF, validate/yield the final partial line.

Use total and idle boundaries conceptually as:

```python
async with asyncio.timeout(total_limit):
    while True:
        chunk = await asyncio.wait_for(iterator.__anext__(), timeout=idle_limit)
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise _response_too_large()
        line_buffer.extend(chunk)
        while b"\n" in line_buffer:
            raw_line, _, remainder = line_buffer.partition(b"\n")
            line_buffer = bytearray(remainder)
            if len(raw_line) > max_event_bytes:
                raise _response_too_large()
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            yield raw_line.decode("utf-8", errors="strict")
```

Convert `TimeoutError` to fixed `outbound_timeout`, but catch/re-raise `asyncio.CancelledError` unchanged. The async generator owns response/client/transport and closes them on normal completion, error, cancellation, and `aclose()`.

- [ ] **Step 4: Run streaming and full security suites**

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_runtime_http.py -q
& $PYTHON -m pytest backend/app/security/tests -q
```

Expected: all selected tests pass; no leaked task/resource warnings.

- [ ] **Step 5: Review and commit Task 4**

```powershell
git diff --check
git add backend/app/security/runtime_http.py backend/app/security/tests/test_runtime_http.py
git commit -m "feat: bound safe runtime streams"
```

---

### Task 5: Propagate the local-AI switch and centralize provider request locations

**Files:**
- Modify: `backend/app/ai/model_router.py`
- Modify: `backend/app/core/ai_router_config.py`
- Modify: `backend/app/core/tests/test_ai_router_config.py`
- Create: `backend/app/ai/tests/__init__.py`
- Create: `backend/app/ai/tests/test_model_router_security.py`

**Interfaces:** Adds optional runtime-client injection and `_provider_request_location(provider_type, base_url, model_name, endpoint, *, stream) -> tuple[str, str]`; does not switch network calls yet.

- [ ] **Step 1: Write failing configuration propagation tests**

Extend `test_ai_router_config.py` with both true and false refresh cases:

```python
def test_configure_model_router_propagates_local_endpoint_policy():
    configure_model_router(config, router, embedding_service, settings)
    assert router.allow_local_ai_endpoints is config.allow_local_ai_endpoints
    assert embedding_service.allow_local_ai_endpoints is config.allow_local_ai_endpoints
```

Run configuration twice on the same objects (true then false) to prove immediate refresh rather than constructor-only capture.

Add `test_configure_model_router_retains_legacy_embedding_source_for_safe_runtime_validation`: populate only legacy `embedding_base_url`/`embedding_api_key`, run configuration, and assert the values are assigned to `EmbeddingService` but no network call occurs during configuration. Task 8 will prove that this retained source is validated at request time.

- [ ] **Step 2: Write provider-location tests**

Instantiate `ModelRouter` with a recording fake `SafeRuntimeClient`. Test exact `(base_url, request_target)` for:

| Provider | Base | Target |
| --- | --- | --- |
| OpenAI without version suffix | `https://public.example` | `/v1/chat/completions` |
| OpenAI with `/v1` base | `https://public.example/v1` | `/chat/completions` |
| custom OpenAI endpoint | unchanged stripped base | exact configured leading-slash endpoint |
| Anthropic | stripped base | `/messages` |
| Google normal | stripped base | `/models/{quote(model, safe='')}:generateContent?{urlencode(key)}` |
| Google stream | stripped base | `/models/{quote(model, safe='')}:streamGenerateContent?{urlencode(key)}` |

Google test model must contain `/ ? #` and Unicode; key must contain `+ & =`。断言原值不直接成为路径/query 语法，且 helper/日志不输出完整 target。

- [ ] **Step 3: Verify RED**

```powershell
& $PYTHON -m pytest backend/app/core/tests/test_ai_router_config.py backend/app/ai/tests/test_model_router_security.py -q
```

Expected: new attributes/helper are absent and tests fail.

- [ ] **Step 4: Add compatible injection and one location helper**

At the end of the existing `ModelRouter.__init__` parameters add `runtime_client` and `allow_local_ai_endpoints`; store:

```python
self._runtime_client = runtime_client or SafeRuntimeClient()
self.allow_local_ai_endpoints = allow_local_ai_endpoints
```

Implement one helper using `quote(str(model_name), safe="")` and `urlencode({"key": api_key})`. It returns query-free base plus a leading-slash target. Reject a custom endpoint that lacks one leading `/` by allowing the safe client to return the fixed URL error; do not silently use `urljoin` or normalize an absolute endpoint.

- [ ] **Step 5: Propagate the current switch in runtime configuration**

In `configure_model_router()` set both attributes every invocation, before provider calls can begin. Do not alter the persisted config or API schema.

- [ ] **Step 6: Run focused tests and constructor compatibility tests**

```powershell
& $PYTHON -m pytest backend/app/core/tests/test_ai_router_config.py backend/app/ai/tests/test_model_router_security.py -q
& $PYTHON -m pytest backend/app/ai backend/app/core/tests/test_ai_router_config.py -q
```

Expected: all selected tests pass; existing callers can construct `ModelRouter` unchanged.

- [ ] **Step 7: Review and commit Task 5**

```powershell
git diff --check
git add backend/app/ai/model_router.py backend/app/core/ai_router_config.py backend/app/core/tests/test_ai_router_config.py backend/app/ai/tests
git commit -m "refactor: prepare secure provider targets"
```

This intermediate commit is not releasable: direct runtime networking still exists until Tasks 6 and 7.

---

### Task 6: Secure the primary invoke family

**Files:**
- Modify: `backend/app/ai/model_router.py`
- Modify: `backend/app/ai/tests/test_model_router_security.py`

**Interfaces:** Migrates `invoke`、`ainvoke`、`astream`; `_prepare_request()` returns `base_url` and `request_target` instead of a sensitive full `url`.

- [ ] **Step 1: Write failing contract tests for all three entry points**

For each entry point test normal delegation and blocked URL. Recording client assertions must include selected base/target, provider type, headers/body, read timeout, size limit, and local flag snapshot. Add cases for default provider, capability override, and selected provider-pool member.

Required behavioral tests:

测试名与精确契约：

- `test_invoke_uses_safe_sync_client_and_preserves_parsing`：一次 `post_json`，返回原有 meta/content/raw；
- `test_ainvoke_revalidates_on_every_retry_for_same_provider`：三次 `apost_json`，三次相同 provider，前两次超时、第三次成功；
- `test_ainvoke_unsafe_selected_pool_provider_does_not_fail_over`：一次安全调用、一次 provider 选择、立即返回脱敏错误；
- `test_astream_uses_safe_lines_and_preserves_status_heartbeat_and_chunks`：一次 `astream_lines`，状态和文本序列与旧契约一致；
- `test_astream_security_error_emits_one_redacted_error_then_closes`：仅一个固定 error event，随后迭代结束且关闭一次。

Fake client records method call count. For retries, first two calls raise `outbound_timeout` and third succeeds; provider id/base must be identical. For safety error, first call raises `private_network_blocked`; call count must remain one and pool selector must not select again.

Add `test_constructor_base_url_from_settings_uses_the_same_safe_client`: construct the router with its `base_url`/`api_key` arguments (the path used by `AI_BASE_URL` settings), invoke a nonlocal route, and assert the injected safe client receives that base. No source-specific exemption is allowed.

- [ ] **Step 2: Verify RED**

```powershell
& $PYTHON -m pytest backend/app/ai/tests/test_model_router_security.py -q -k "invoke or astream"
```

Expected: fake runtime client receives no calls because the three methods still use direct httpx.

- [ ] **Step 3: Change `_prepare_request` to safe location fields**

Replace full `url` with:

```python
"base_url": request_base_url,
"request_target": request_target,
```

Use `_provider_request_location(provider_type, base_url, model_name, config.endpoint, stream=False)` during preparation; `astream` asks the same helper with `stream=True` instead of string replacement. Never log either full target or base URL. Preserve body, headers, timeout, provider type, selected pool id and meta unchanged.

- [ ] **Step 4: Replace sync and async JSON sends**

`invoke` calls `post_json` with `max_bytes=AI_JSON_MAX_BYTES`; `ainvoke` calls `apost_json` with the same limit. Catch `OutboundRequestError` by code only:

- `outbound_connect_failed` / `outbound_timeout`: retain current retry count and backoff for `ainvoke`;
- all other codes: stop immediately;
- returned error objects/messages use only `public_message`/fixed code, never `str()` of a lower-level exception.

Every retry invokes `apost_json` again. Do not prevalidate once outside the loop.

- [ ] **Step 5: Replace primary streaming send**

`astream` calls `astream_lines` exactly once for its selected provider and preserves the existing OpenAI/Anthropic/Google line parsing and status/chunk shapes. Remove upstream error-body reads. On `OutboundRequestError`, yield exactly one `_stream_error_event(capability, exc.public_message)` and return. On cancellation, re-raise. Normal early business-parser return must close the iterator.

A syntactically valid 2xx stream can still contain an upstream `error` object or malformed fragment. Replace every existing `str(chunk["error"])`、upstream message、candidate preview and raw JSON parse warning with one fixed public stream error and a code/type-only log. Add a sentinel-bearing upstream error/invalid-fragment case and assert neither the event nor `caplog` contains it.

- [ ] **Step 6: Run primary-family and related router tests**

```powershell
& $PYTHON -m pytest backend/app/ai/tests/test_model_router_security.py -q -k "invoke or astream"
& $PYTHON -m pytest backend/app/ai backend/app/core/tests/test_ai_router_config.py -q
```

Expected: all selected tests pass; normal parsed output、stats、semaphore and stream status order match the pre-change contract.

- [ ] **Step 7: Review and commit Task 6**

```powershell
git diff --check
git add backend/app/ai/model_router.py backend/app/ai/tests/test_model_router_security.py
git commit -m "feat: secure primary model invocations"
```

Review checkpoint: verify no Google key is placed in a full URL field or log, and a selected unsafe pool member cannot cause another selection.

---

### Task 7: Secure legacy capability, chat, and streaming entry points

**Files:**
- Modify: `backend/app/ai/model_router.py`
- Modify: `backend/app/ai/tests/test_model_router_security.py`

**Interfaces:** Migrates `call_capability`、`acall_capability`、`chat`、`astream_capability`; removes all direct runtime httpx paths from `ModelRouter`.

- [ ] **Step 1: Add a seven-entry structural/behavior matrix**

Parameterize all public network entry names and assert each delegates through exactly one of `post_json`、`apost_json`、`astream_lines`. For the four remaining methods add provider-format cases so the combined Task 6+7 suite covers OpenAI、Anthropic、Google in sync/async/stream modes.

Add explicit tests:

- safety error stops immediately and is redacted;
- ordinary connect/timeout follows only the entry's existing retry behavior;
- selected provider-pool member remains the same across retry;
- local/missing-config existing result/error shape is unchanged;
- `chat` normal return stays plain extracted content;
- both stream APIs retain connecting/connected/receiving/completed/error event order and heartbeat behavior;
- stream caller cancellation and early close propagate cleanup.

- [ ] **Step 2: Verify RED**

```powershell
& $PYTHON -m pytest backend/app/ai/tests/test_model_router_security.py -q -k "call_capability or chat or seven or legacy"
```

Expected: remaining methods bypass the recording safe client and tests fail.

- [ ] **Step 3: Route the remaining JSON methods through the safe client**

Replace duplicated full URL creation with `_provider_request_location()`. Use `AI_JSON_MAX_BYTES`, the existing configured read timeout, and the current `allow_local_ai_endpoints` snapshot. Preserve service-specific bodies and parsers. Replace raw HTTP exception logs/messages with fixed `OutboundRequestError.code/public_message`.

If a 2xx JSON object fails an existing OpenAI、Anthropic or Google business parser, convert it to the fixed invalid-response message without logging the parsed object or parser exception text. Add one sentinel-bearing malformed object per provider family.

- [ ] **Step 4: Route `astream_capability` through safe lines**

Build Google stream target directly with encoded model/key; Anthropic `/messages`; OpenAI version-aware endpoint. Feed safe lines into the existing provider parsers, remove response-body previews and complete URL diagnostics, and enforce one error event then return.

For upstream `error` events and malformed streamed JSON, apply the same fixed-event/code-only-log rule from Task 6. No upstream error message, chunk preview or candidate fragment may be emitted or logged.

- [ ] **Step 5: Add a structural guard against future bypasses**

Parse `backend/app/ai/model_router.py` with `ast` and fail if it contains runtime calls to `httpx.post` or construction of `httpx.Client`/`httpx.AsyncClient`. Also fail on imports of `requests`、`urllib.request`、`urllib3`、`aiohttp`、`httpcore` and `socket`. A plain `httpx` type annotation/import is allowed only if it cannot send a request; remove it if no longer needed.

Remove the now-unused private `_client_session` and `_get_client()` network client. Preserve public `set_keepalive_mode()` and `reset_client()` signatures for callers: `set_keepalive_mode()` still updates the compatibility flag and diagnostic log; `reset_client()` becomes an async no-op because every safe request owns and closes its own client. Remove the timeout branch that schedules `reset_client()` as a recovery mechanism. Add a test proving both compatibility methods complete without creating a network client.

```python
def test_model_router_has_no_direct_network_client_bypass():
    tree = ast.parse(MODEL_ROUTER_PATH.read_text(encoding="utf-8"))
    assert find_forbidden_network_calls(tree) == []
```

- [ ] **Step 6: Run the complete router contract suite**

```powershell
& $PYTHON -m pytest backend/app/ai/tests/test_model_router_security.py backend/app/core/tests/test_ai_router_config.py -q
& $PYTHON -m pytest backend/app/ai -q
rg -n "httpx\.(post|Client|AsyncClient)|requests\.|aiohttp|urllib\.request|urllib3|httpcore|(^|[^A-Za-z])socket([^A-Za-z]|$)" backend/app/ai/model_router.py
```

Expected: tests pass; `rg` returns no runtime-network matches (exit 1/no output is expected).

- [ ] **Step 7: Review and commit Task 7**

```powershell
git diff --check
git add backend/app/ai/model_router.py backend/app/ai/tests/test_model_router_security.py
git commit -m "feat: secure all model router requests"
```

Review checkpoint: manually account for exactly seven entries. Do not proceed if any entry can instantiate an ordinary network client.

---

### Task 8: Secure every Embedding batch without hiding policy failures

**Files:**
- Modify: `backend/app/services/system/embedding.py`
- Create: `backend/app/services/system/tests/test_embedding_security.py`

**Interfaces:** Adds compatible safe-client injection; each `_request_embedding_chunk` attempt calls `SafeRuntimeClient.post_json` with `request_target="/embeddings"` and `max_bytes=EMBEDDING_JSON_MAX_BYTES`.

- [ ] **Step 1: Write failing delegation and response-schema tests**

Use a recording fake client; no network. Verify truncation/body/model/header, base/target, local switch snapshot, timeout and 16 MiB limit. Add parser cases for:

- `data` missing/not list;
- wrong item count;
- item not dict;
- index missing/non-integer/duplicate/out of range;
- embedding missing/not list/non-numeric/non-finite;
- valid out-of-order indices are sorted and returned in input order.

Map all malformed schemas to fixed `outbound_bad_response`; no raw response text in error/log.

- [ ] **Step 2: Write the retry/fallback truth table**

Parameterize `require_real` and `allow_fake_embeddings` for these errors:

| Error | Retry | Fake fallback |
| --- | ---: | ---: |
| `outbound_connect_failed` | up to existing max | only false/true combination |
| `outbound_timeout` | up to existing max | only false/true combination |
| URL/HTTPS/local/private/DNS policy | 0 | never |
| response too large/bad status/encoding/JSON/schema | 0 | never |

Assert every retry calls the safe client again, call count equals `max_retries`, and the same provider is used. Security errors call once. Preserve existing exponential sleeps by monkeypatching `time.sleep` and asserting `[1, 2]` for three attempts.

- [ ] **Step 3: Write concurrency/order and redaction tests**

Run multiple fake chunks with concurrency enabled and complete them out of order; final vectors must preserve original chunk/input order and existing stats. Put distinct secret sentinels in key、base URL、text、fake response and underlying exception; none may occur in `caplog.text` or raised exception string.

- [ ] **Step 4: Verify RED**

```powershell
& $PYTHON -m pytest backend/app/services/system/tests/test_embedding_security.py -q
```

Expected: tests fail because `EmbeddingService` still calls `httpx.post` and lacks injected runtime client.

- [ ] **Step 5: Inject the client and replace `_request_embedding_chunk` networking**

Add the two optional constructor parameters at the end, store the default safe client/current local flag, and call it inside the existing retry loop. Catch `OutboundRequestError` separately:

```python
except OutboundRequestError as exc:
    if exc.code not in RETRYABLE_OUTBOUND_CODES:
        logger.warning("[Embedding] blocked error_code=%s", exc.code)
        raise RuntimeError(exc.public_message) from None
    # retain current retry/backoff; only final eligible availability failure may fake
```

Do not catch this resulting security `RuntimeError` in the generic fake-fallback branch. Refactor with a small helper if needed so nonretryable errors exit outside that branch.

- [ ] **Step 6: Validate the business response explicitly**

Add `_parse_embedding_response(data, expected_count)` returning `list[list[float]]`. Require exact unique indices `0..expected_count-1`, numeric finite values (`bool` is not accepted as a number), and a non-empty vector list. Raise `OutboundRequestError("outbound_bad_response", 502, "外部服务响应无效")` from none on any mismatch.

- [ ] **Step 7: Add the Embedding structural guard**

AST test forbids direct `httpx.post`/Client/AsyncClient plus `requests`、`urllib.request`、`urllib3`、`aiohttp`、`httpcore` and `socket` in `embedding.py`. Remove now-unused `httpx` import.

- [ ] **Step 8: Run focused and related service suites**

```powershell
& $PYTHON -m pytest backend/app/services/system/tests/test_embedding_security.py -q
& $PYTHON -m pytest backend/app/services/system/tests backend/app/core/tests/test_ai_router_config.py -q
rg -n "httpx\.(post|Client|AsyncClient)|requests\.|aiohttp|urllib\.request|urllib3|httpcore|(^|[^A-Za-z])socket([^A-Za-z]|$)" backend/app/services/system/embedding.py
```

Expected: all tests pass; `rg` has no matches; cache/vector math behavior and stats remain green.

- [ ] **Step 9: Review and commit Task 8**

```powershell
git diff --check
git add backend/app/services/system/embedding.py backend/app/services/system/tests/test_embedding_security.py
git commit -m "feat: secure embedding requests"
```

---

### Task 9: Documentation, complete gates, and final Phase 2C review

**Files:**
- Modify: `docs/api-guides/modules/config-ui/api-connectivity.md`
- Create: `docs/superpowers/reports/2026-07-15-phase-2c2-verification.md`
- Modify only if evidence requires correction: `docs/superpowers/specs/2026-07-15-phase-2c2-runtime-outbound-security-design.md`

**Interfaces:** Produces user-facing runtime policy documentation and an evidence-only Phase 2C verification report; no behavior change.

- [ ] **Step 1: Update connectivity documentation**

Document that actual AI、streaming、Embedding requests now share the Phase 2C boundary. Include exact public/local rules, base/target separation, no proxy/redirect, DNS pinning, response limits, timeouts, retry categories, Embedding fake-vector boundary, and fixed redacted errors. Never include a real API key or a complete Google query example.

- [ ] **Step 2: Run focused Phase 2C security suites fresh**

```powershell
& $PYTHON -m pytest backend/app/security/tests backend/app/ai/tests/test_model_router_security.py backend/app/services/system/tests/test_embedding_security.py backend/app/core/tests/test_ai_router_config.py -q
```

Expected: all new and Phase 2C-1 security tests pass with no real network and no resource-leak warnings.

- [ ] **Step 3: Run the full backend gate**

```powershell
& $PYTHON -m pytest backend/app -q
Push-Location backend
& $PYTHON -c "from app.services.embedding_plugins import PluginRegistry, load_all_plugins; expected={'ancestry','behavior_strategy','evolution_space','food_web','prompt_optimizer','tile_biome'}; loaded=set(load_all_plugins()); registered=set(PluginRegistry.list_plugins()); assert loaded == expected; assert registered == expected; print(sorted(registered))"
Pop-Location
```

Expected: at least the 693 prior tests plus all new tests pass; exactly two existing Windows symlink skips; warnings no more than 45; fresh-process guard prints exactly six plugin names and exits 0.

- [ ] **Step 4: Run the unchanged frontend gates**

```powershell
Push-Location frontend
npm run test:run
npm run lint
npx tsc --noEmit
npm run build
Pop-Location
```

Expected: at least 84 tests pass; ESLint 0 errors and no more than 162 warnings; TypeScript and production build exit 0.

- [ ] **Step 5: Run structural, hygiene, and sentinel scans**

```powershell
git diff --check
rg -n "httpx\.(post|Client|AsyncClient)|requests\.|aiohttp|urllib\.request|urllib3|httpcore|(^|[^A-Za-z])socket([^A-Za-z]|$)" backend/app/ai/model_router.py backend/app/services/system/embedding.py
rg -n "runtime-query-sentinel|runtime-header-sentinel|runtime-body-sentinel|runtime-backend-sentinel" backend/app frontend/src docs/api-guides -g '!**/test_*.py' -g '!**/*.test.ts' -g '!**/*.test.tsx'
git status --short
```

Expected: `git diff --check` empty; both `rg` commands have no production matches (exit 1 is no-match); status contains only intended documentation/report changes.

- [ ] **Step 6: Review every runtime entry and complete Phase 2C range**

Create a checklist with evidence for all seven `ModelRouter` methods, Embedding batch, default/override/pool/environment/legacy sources, sync/async/stream, Google encoded target, DNS pinning, local flag, retry/fallback rules, limits/timeouts, proxy/redirect/Unix rejection, cleanup and redaction.

Run:

```powershell
git log --oneline b52eb91..HEAD
git diff --stat b52eb91..HEAD
git diff --name-only b52eb91..HEAD
```

Any unresolved Critical or Important finding blocks completion. Fixes require a failing regression test first and a separate commit; rerun all affected and full gates afterward.

- [ ] **Step 7: Write the verification report from fresh output**

Record exact commands, exit codes, pass/skip/warning counts, frontend/lint/build evidence, commit range, seven-entry accounting and review findings. State explicitly whether Phase 2C is ready for merge consideration, but do not merge or publish. Do not record secrets, query strings, request/response bodies or raw exception text.

- [ ] **Step 8: Commit Task 9**

```powershell
git add docs/api-guides/modules/config-ui/api-connectivity.md docs/superpowers/reports/2026-07-15-phase-2c2-verification.md
git add docs/superpowers/specs/2026-07-15-phase-2c2-runtime-outbound-security-design.md  # only if evidence required a correction
git commit -m "docs: record phase 2c2 security verification"
git status --short
```

Expected: commit succeeds and worktree is clean.

---

## Review Checkpoints

After every task, inspect `git show --stat --oneline HEAD` and the exact diff before continuing. Each task must have a clean worktree and passing focused tests.

After Task 4, perform a dedicated transport review: approved-IP-only dialing, origin equality, Host/SNI/cert semantics, no proxy/redirect/Unix socket, bounded raw reads, timeout mapping, cancellation and exactly-once cleanup.

After Task 7, account for the seven `ModelRouter` public entries and run the structural guard. Reject any direct network bypass, complete target/key logging, upstream body read on error, hidden provider failover or safety-error retry.

After Task 8, review the full Embedding truth table. Reject any path where URL/DNS/size/encoding/status/JSON/schema errors can retry into fake vectors.

After Task 9, use `superpowers:verification-before-completion` and `superpowers:requesting-code-review`. Do not claim completion from earlier output, do not merge automatically, and do not use `superpowers:finishing-a-development-branch` until the fresh full gates and complete Phase 2C review are clean.
