# Clade Phase 2C-1 Outbound URL Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为当前已注册的“测试连接”和“获取模型列表”端点建立统一的外部 URL 安全边界，并加入受管理员令牌保护、永久保存、立即生效的本地 AI 开关。

**Architecture:** 后端由纯 URL 策略、固定解析地址的同步传输层和限时限量探测客户端三层组成；API 路由只负责读取当前配置、解析凭据、调用安全客户端并返回稳定错误码。前端把本地 AI 权限作为 `UIConfig` 普通字段保存，但管理员令牌只通过请求头从设置面板局部内存传递，不进入配置对象、浏览器存储或日志。

**Tech Stack:** Python 3.12、FastAPI 0.139.0、Pydantic 2.13.4、httpx 0.28.1、httpcore 1.0.9、pytest 9.1.1；React 18.3、TypeScript 5.5、Vitest 1.3、Testing Library、Vite 5.4。

## Global Constraints

- 本计划只实施 Phase 2C-1；不得修改 `ModelRouter`、负载均衡实际请求、流式 AI 请求或 `EmbeddingService` 运行时请求。
- 默认 `allow_local_ai_endpoints=False`；旧配置缺少字段时必须按关闭读取。
- 开关开启后仅允许规范化后的 `localhost`、字面量 `127.0.0.1` 和 `::1`；家庭局域网及其他私有地址始终拒绝。
- 公网服务必须使用 HTTPS，且域名本次解析出的每个 IP 都必须全局可路由。
- 实际 TCP 连接只能使用本次策略批准的 IP；HTTP Host、HTTPS SNI 和证书验证继续使用原始规范主机名。
- `trust_env=False`、`follow_redirects=False`；不使用系统代理，不自动访问 3xx 目标。
- 连接测试超时：connect/read/write/pool 各不超过 5 秒，总截止时间 10 秒。
- 模型列表超时：connect 5 秒、read 10 秒、write/pool 5 秒，总截止时间 15 秒。
- 模型列表正文上限精确为 `1_048_576` 字节；连接测试不读取完整正文。
- 修改开关的两个方向都要求 `CLADE_ADMIN_TOKEN`；验证失败时整个配置更新不得保存、失效缓存或刷新运行时。
- 管理员令牌不得写入配置请求体、设置文件、URL、浏览器存储、全局前端状态、响应或日志。
- 两个批次保留在 `phase-2c-outbound-url-security` 隔离分支；2C-1 不单独合并或发布。
- 不增加生产依赖；传输固定使用锁文件中的 httpx 0.28.1/httpcore 1.0.9 公共类型，并由契约测试固定行为。
- 不减少现有测试：后端基线 556 项（554 通过、2 跳过、45 警告），前端基线 52/52、ESLint 0 错误/162 警告。

---

## Execution Environment

从以下工作区执行所有命令：

```powershell
Set-Location 'E:\my word\https-github-com-pocketfans-clade-tree\.worktrees\phase-2c-outbound-url-security'
$PYTHON = '..\phase-2b2-save-path-boundary\backend\.venv\Scripts\python.exe'
```

前端 `node_modules` 已连接到主仓库的已验证依赖目录，不运行 `npm install`。如果 Python 环境路径不存在，暂停并报告环境变化，不自行重建或升级依赖。

## File Responsibility Map

| 文件 | 单一职责 |
| --- | --- |
| `backend/app/security/outbound_url.py` | URL 解析、主机规范化、DNS/IP 分类、公开安全错误类型 |
| `backend/app/security/safe_http.py` | 固定批准 IP 的 httpcore 传输、总截止时间、代理/重定向/响应大小限制 |
| `backend/app/security/admin_token.py` | 管理员令牌的纯验证函数及现有 FastAPI 依赖适配 |
| `backend/app/api/analytics.py` | 配置保存的条件鉴权、服务商端点选择、安全探测结果转换 |
| `frontend/src/services/api/base.ts` | 兼容字符串与结构化 `detail` 的统一 API 错误解析 |
| `frontend/src/services/api/config.ts` | 配置保存请求头及探测错误码到用户提示的转换 |
| `frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.tsx` | 本地 AI 状态、风险、保留地址提示和密码输入的呈现 |
| `frontend/src/components/SettingsDrawer/SettingsPanel.tsx` | 管理员令牌局部内存、保存/关闭时清除、未保存表单保留 |

---

### Task 1: Central outbound URL policy

**Files:**
- Create: `backend/app/security/outbound_url.py`
- Create: `backend/app/security/tests/test_outbound_url.py`

**Interfaces:**
- Consumes: Python `urllib.parse.urlsplit/urlunsplit`、`ipaddress.ip_address`、`socket.getaddrinfo`。
- Produces: `ValidatedOutboundURL`、`OutboundRequestError`、`OutboundURLPolicy.validate(url: str, *, allow_local: bool) -> ValidatedOutboundURL`。

- [ ] **Step 1: Write the failing policy tests**

创建表驱动测试，使用下列确定性解析器，测试不得访问真实 DNS：

```python
from ipaddress import ip_address

import pytest

from app.security.outbound_url import OutboundRequestError, OutboundURLPolicy


class FakeResolver:
    def __init__(self, answers: dict[str, list[str]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, int]] = []

    def __call__(self, hostname: str, port: int):
        self.calls.append((hostname, port))
        answer = self.answers.get(hostname)
        if answer is None:
            raise OSError("resolver sentinel must not be exposed")
        return tuple(ip_address(value) for value in answer)


@pytest.mark.parametrize(
    ("url", "allow_local", "expected_code"),
    [
        ("http://public.example/v1", False, "outbound_https_required"),
        ("http://localhost:11434/v1", False, "local_ai_disabled"),
        ("http://127.0.0.1:11434/v1", False, "local_ai_disabled"),
        ("http://[::1]:11434/v1", False, "local_ai_disabled"),
        ("http://127.0.0.2:11434/v1", True, "private_network_blocked"),
        ("https://router.lan/v1", True, "private_network_blocked"),
        ("https://public.example/v1?key=secret", False, "outbound_url_invalid"),
        ("https://user:pass@public.example/v1", False, "outbound_url_invalid"),
        ("https://public.example/v1#fragment", False, "outbound_url_invalid"),
        ("file:///etc/passwd", False, "outbound_url_invalid"),
    ],
)
def test_policy_rejects_unsafe_urls(url, allow_local, expected_code):
    resolver = FakeResolver(
        {
            "public.example": ["93.184.216.34"],
            "localhost": ["127.0.0.1", "::1"],
            "router.lan": ["192.168.1.1"],
        }
    )
    with pytest.raises(OutboundRequestError) as exc_info:
        OutboundURLPolicy(resolver=resolver).validate(url, allow_local=allow_local)
    assert exc_info.value.code == expected_code
    assert "secret" not in str(exc_info.value)


def test_policy_accepts_only_public_https_or_explicit_loopback_exception():
    resolver = FakeResolver(
        {
            "public.example": ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"],
            "localhost": ["127.0.0.1", "::1"],
        }
    )
    public = OutboundURLPolicy(resolver=resolver).validate(
        "HTTPS://PUBLIC.EXAMPLE./v1", allow_local=False
    )
    local = OutboundURLPolicy(resolver=resolver).validate(
        "http://localhost.:11434/v1", allow_local=True
    )
    assert public.hostname == "public.example"
    assert public.port == 443
    assert public.is_local is False
    assert local.hostname == "localhost"
    assert local.port == 11434
    assert local.is_local is True


def test_mixed_public_and_private_resolution_rejects_entire_host():
    resolver = FakeResolver({"mixed.example": ["93.184.216.34", "169.254.169.254"]})
    with pytest.raises(OutboundRequestError) as exc_info:
        OutboundURLPolicy(resolver=resolver).validate(
            "https://mixed.example/v1", allow_local=False
        )
    assert exc_info.value.code == "private_network_blocked"
```

在同一文件继续覆盖：空解析结果、重复 IP 去重且保持顺序、DNS 异常映射 `outbound_dns_failed`、`*.localhost`、RFC1918、ULA、链路本地、CGNAT、文档/保留、多播、未指定地址、错误端口、空主机、控制字符、反斜杠和 IDNA 主机。

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_outbound_url.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.security.outbound_url'`.

- [ ] **Step 3: Implement the pure policy**

实现以下最终公共数据结构和错误字段，错误文本只使用固定中文消息：

```python
OutboundErrorCode = Literal[
    "outbound_url_invalid",
    "outbound_https_required",
    "local_ai_disabled",
    "private_network_blocked",
    "outbound_dns_failed",
    "outbound_connect_failed",
    "outbound_response_too_large",
    "outbound_bad_response",
    "outbound_timeout",
]


@dataclass(frozen=True)
class ValidatedOutboundURL:
    url: str
    scheme: Literal["http", "https"]
    hostname: str
    port: int
    resolved_ips: tuple[IPv4Address | IPv6Address, ...]
    is_local: bool


class OutboundRequestError(Exception):
    def __init__(self, code: OutboundErrorCode, status_code: int, public_message: str) -> None:
        super().__init__(public_message)
        self.code = code
        self.status_code = status_code
        self.public_message = public_message
```

`OutboundURLPolicy.validate()` 必须按此顺序完成：拒绝空白/控制字符/反斜杠；`urlsplit`；校验 scheme、host、userinfo、query、fragment 和端口；小写、去尾点并 IDNA 规范化；识别字面量 IP或调用注入解析器；去重解析结果；先处理精确回环例外，再拒绝任意非全局地址，最后对公网要求 HTTPS。使用 `urlunsplit` 重建不含凭据、query、fragment 的规范 URL；IPv6 主机在 URL 中保留方括号。

- [ ] **Step 4: Run policy tests and the existing security suite**

Run:

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_outbound_url.py backend/app/security/tests -q
```

Expected: all selected tests pass; existing admin/config/save-path tests remain present; warnings do not exceed their prior focused-suite count.

- [ ] **Step 5: Commit Task 1**

```powershell
git add backend/app/security/outbound_url.py backend/app/security/tests/test_outbound_url.py
git commit -m "feat: add outbound URL policy"
```

---

### Task 2: Pinned, bounded probe client

**Files:**
- Create: `backend/app/security/safe_http.py`
- Create: `backend/app/security/tests/test_safe_http.py`
- Modify: `backend/app/security/__init__.py:1-11`

**Interfaces:**
- Consumes: `OutboundURLPolicy.validate()` and `ValidatedOutboundURL` from Task 1.
- Produces: `SafeProbeClient.probe_status(base_url, endpoint, headers, allow_local) -> int`、`SafeProbeClient.fetch_json(base_url, endpoint, headers, allow_local, max_bytes) -> dict[str, Any]`、`CONNECTION_TEST_TIMEOUTS`、`MODEL_LIST_TIMEOUTS`。

- [ ] **Step 1: Write transport and client contract tests**

测试文件必须使用假 resolver、记录型 `httpcore.NetworkBackend`/`NetworkStream` 或本机临时 HTTP 服务，不访问公网。建立 `RecordingBackend`，让 `connect_tcp()` 记录 `(host, port, timeout)` 并返回 `RecordingStream`；后者记录 `start_tls(server_hostname)`、累计 `read()` 字节数和 `close()` 次数。建立 `CannedHTTPStream`，按测试提供完整 HTTP/1.1 响应字节。

至少定义并验证以下命名测试与断言：

| 测试 | 固定输入 | 必须断言 |
| --- | --- | --- |
| `test_pinned_backend_connects_to_approved_ip_not_original_hostname` | 原始主机 `public.example`，批准 IP `93.184.216.34` | delegate 收到 `93.184.216.34`，调用记录不含 `public.example` |
| `test_transport_preserves_original_host_header_and_tls_server_name` | HTTPS 原始主机 `public.example` | 请求头含 `Host: public.example`；`start_tls` 收到 `server_hostname="public.example"` |
| `test_transport_preserves_nondefault_port_in_host_header` | HTTP `localhost:11434` | 请求头含 `Host: localhost:11434`；TCP 端口为 11434 |
| `test_probe_disables_environment_proxy_and_redirect_following` | `HTTPS_PROXY=http://proxy-sentinel.invalid`，上游返回 302/Location | 返回 302；连接记录只含批准 IP；Location 目标无连接记录 |
| `test_fetch_json_rejects_content_length_over_exact_one_mib` | `Content-Length: 1048577` | 正文读取数为 0；错误码为 `outbound_response_too_large`；stream 关闭一次 |
| `test_fetch_json_stops_after_one_mib_plus_one_without_content_length` | 分块正文累计 `1048577` 字节 | 最多消费 `1048577` 字节；错误码为 `outbound_response_too_large`；stream 关闭一次 |
| `test_probe_status_closes_without_consuming_response_body` | 200 响应头后跟 2 MiB 哨兵正文 | 返回 200；哨兵正文读取数为 0；stream 关闭一次 |
| `test_total_deadline_includes_dns_and_body_read` | 注入 runner 分别在解析和读取阶段阻塞超过毫秒级测试 deadline | 两种情况均返回 `outbound_timeout`；测试墙钟小于 1 秒；并发槽位不超过 4 |
| `test_errors_and_logs_never_contain_headers_query_or_response_body` | Authorization、query、正文分别含不同哨兵 secret | 异常字符串和 `caplog.text` 均不含三个哨兵，只含固定错误码/类别 |

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_safe_http.py -q
```

Expected: collection fails because `app.security.safe_http` does not exist.

- [ ] **Step 3: Implement the pinned public-api transport**

使用 `httpcore.ConnectionPool(network_backend=pinned_backend)`，不导入 `httpx._*` 或 `httpcore._*`。传输适配器按 httpx 0.28.1 的公开请求字段构造 httpcore 请求：

```python
req = httpcore.Request(
    method=request.method,
    url=httpcore.URL(
        scheme=request.url.raw_scheme,
        host=request.url.raw_host,
        port=request.url.port,
        target=request.url.raw_path,
    ),
    headers=request.headers.raw,
    content=request.stream,
    extensions=request.extensions,
)
```

`PinnedNetworkBackend.connect_tcp()` 必须拒绝非预期原始 host/port，并按本次批准顺序尝试 `ValidatedOutboundURL.resolved_ips`；单个 TCP 连接失败才尝试下一个批准 IP，不得引入新解析结果。`connect_unix_socket()` 始终拒绝，`sleep()` 只委托给底层 `SyncBackend`。连接池显式使用 `ssl.create_default_context()` 和 `retries=0`；不得设置 `verify=False`。TLS 由 httpcore 在返回 stream 上以原始 origin host 调用 `start_tls`。自定义 `httpx.SyncByteStream` 只代理迭代与 `close()`，从而不依赖 httpx 私有 `ResponseStream`。每次操作在 `finally` 中关闭 httpx client、connection pool 和 response stream。

- [ ] **Step 4: Implement deadlines, endpoint construction, and bounded reads**

最终接口固定为下表，所有关键字参数保持 keyword-only：

```python
@dataclass(frozen=True)
class ProbeTimeouts:
    connect: float
    read: float
    write: float
    pool: float
    total: float


CONNECTION_TEST_TIMEOUTS = ProbeTimeouts(5.0, 5.0, 5.0, 5.0, 10.0)
MODEL_LIST_TIMEOUTS = ProbeTimeouts(5.0, 10.0, 5.0, 5.0, 15.0)
MODEL_LIST_MAX_BYTES = 1_048_576


```

| 方法 | 精确签名 | 返回 |
| --- | --- | --- |
| 状态探测 | `probe_status(self, base_url: str, *, endpoint: Literal["models", "messages"], headers: Mapping[str, str], allow_local: bool) -> int` | 上游 HTTP 状态码 |
| 模型 JSON | `fetch_json(self, base_url: str, *, endpoint: Literal["models", "messages"], headers: Mapping[str, str], allow_local: bool, max_bytes: int = MODEL_LIST_MAX_BYTES) -> dict[str, Any]` | 已验证为 JSON object 的字典 |

实现时只允许 `models`/`messages` 两个受控尾段，并追加到保留的基础路径；不得接受任意完整 endpoint URL。每次调用先记录总截止时间，再执行 URL 策略与连接。整体操作放入最多 4 个并发槽位的有界 daemon worker；调用方在 10/15 秒到点返回 `outbound_timeout`，未结束 worker 继续占用原槽位直至自行退出，防止阻塞 DNS 造成无限线程增长。httpx client 同时设置 phase timeout、`trust_env=False`、`follow_redirects=False`。

连接测试用 `client.stream()` 读取状态后立即关闭。模型列表先检查 `Content-Length`，再累计 `iter_bytes()`；读取到上限加 1 字节立即关闭并抛 `outbound_response_too_large`。JSON 必须是对象，否则抛 `outbound_bad_response`。连接、DNS、超时、正文超限和解析异常只映射固定错误码/中文消息，不拼接底层异常。

- [ ] **Step 5: Export the public interfaces and verify the suite**

在 `backend/app/security/__init__.py` 只导出 Task 1/2 的公共类、常量，不导出 `_Pinned*` 或 worker 实现。

Run:

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_outbound_url.py backend/app/security/tests/test_safe_http.py -q
& $PYTHON -m pytest backend/app/security/tests -q
```

Expected: both commands pass; no test accesses a public Internet address.

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/app/security/safe_http.py backend/app/security/__init__.py backend/app/security/tests/test_safe_http.py
git commit -m "feat: add pinned API probe client"
```

---

### Task 3: Persistent local-AI setting and conditional admin authentication

**Files:**
- Modify: `backend/app/models/config.py:1760-1785`
- Modify: `backend/app/security/admin_token.py:1-28`
- Modify: `backend/app/security/tests/test_admin_token.py`
- Modify: `backend/app/api/analytics.py:396-440`
- Modify: `backend/app/api/tests/test_api_integration.py:300-680`

**Interfaces:**
- Consumes: existing `_UI_CONFIG_UPDATE_LOCK`、`merge_ui_config_secrets()`、atomic `save_ui_config()`、`invalidate_cache()`。
- Produces: `UIConfig.allow_local_ai_endpoints: bool`、`validate_admin_token(provided_token, configured_token)`。

- [ ] **Step 1: Write failing model and pure-token tests**

Add exact assertions:

```python
def test_ui_config_defaults_local_ai_endpoints_to_disabled():
    assert UIConfig.model_validate({"providers": {}}).allow_local_ai_endpoints is False


def test_ui_config_round_trips_local_ai_endpoint_setting():
    config = UIConfig(allow_local_ai_endpoints=True)
    assert UIConfig.model_validate_json(config.model_dump_json()).allow_local_ai_endpoints is True


@pytest.mark.parametrize("provided", [None, "wrong-token"])
def test_validate_admin_token_uses_same_safe_rejection(provided):
    with pytest.raises(AdminTokenValidationError) as exc_info:
        validate_admin_token(provided, "expected-token")
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "admin_token_invalid"
```

Also test unconfigured token maps to 503/`admin_token_unconfigured`, correct token returns `None`, and no exception text contains either supplied or configured token.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_admin_token.py -q
```

Expected: fails because the field and pure validation interface are absent.

- [ ] **Step 3: Add the field and extract pure validation**

Add beside the global connection settings:

```python
allow_local_ai_endpoints: bool = False
```

Implement public failure data and reuse it inside `require_admin_token`. Use a normal exception class rather than a frozen dataclass so Python can attach traceback state safely:

```python
class AdminTokenValidationError(Exception):
    def __init__(
        self,
        code: Literal["admin_token_unconfigured", "admin_token_invalid"],
        status_code: Literal[403, 503],
        public_message: str,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.status_code = status_code
        self.public_message = public_message


def validate_admin_token(provided_token: str | None, configured_token: str | None) -> None:
    if not configured_token:
        raise AdminTokenValidationError(
            "admin_token_unconfigured", 503, "管理员功能未启用"
        )
    if not secrets.compare_digest(
        (provided_token or "").encode("utf-8"), configured_token.encode("utf-8")
    ):
        raise AdminTokenValidationError(
            "admin_token_invalid", 403, "管理员令牌无效"
        )
```

现有 `/api/admin` 依赖捕获该异常并继续返回原有字符串 `detail`，保持旧管理 API 响应兼容。

- [ ] **Step 4: Write failing conditional-save API tests**

在 `TestConfigEndpoints` 添加：普通保存无需 token；False→True 和 True→False 在未配置时返回结构化 503、缺失/错误时返回结构化 403；正确 token 成功；拒绝时 `save_ui_config`、`invalidate_cache`、`configure_model_router`、`apply_ui_config`、`reload_configs` 全部未调用；成功时开关与其他字段一起只保存一次并按原顺序刷新。

错误断言固定为：

```python
assert response.json() == {
    "detail": {
        "code": "admin_token_invalid",
        "message": "管理员令牌无效",
    }
}
```

- [ ] **Step 5: Run API tests and verify RED**

Run:

```powershell
& $PYTHON -m pytest backend/app/api/tests/test_api_integration.py -q -k "local_ai or admin_token"
```

Expected: new cases fail because `/api/config/ui` does not inspect the header or compare the stored flag.

- [ ] **Step 6: Add conditional validation inside the existing transaction**

Add `X-Clade-Admin-Token` as an optional `Header` parameter to `update_ui_config()` and pass it to `_update_ui_config()`. Under `_UI_CONFIG_UPDATE_LOCK`, after `current = config_service.get_ui_config()` and before `merge_ui_config_secrets()`:

```python
if request.config.allow_local_ai_endpoints != current.allow_local_ai_endpoints:
    try:
        validate_admin_token(
            x_clade_admin_token,
            container.settings.clade_admin_token,
        )
    except AdminTokenValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.public_message},
        ) from None
```

不要新增第二个保存端点或写文件路径。

- [ ] **Step 7: Verify backend config/auth behavior**

Run:

```powershell
& $PYTHON -m pytest backend/app/security/tests/test_admin_token.py backend/app/api/tests/test_admin_auth.py backend/app/api/tests/test_api_integration.py -q
```

Expected: all selected tests pass; existing admin write/read behavior and config secret preservation tests remain green.

- [ ] **Step 8: Commit Task 3**

```powershell
git add backend/app/models/config.py backend/app/security/admin_token.py backend/app/security/tests/test_admin_token.py backend/app/api/analytics.py backend/app/api/tests/test_api_integration.py
git commit -m "feat: protect persistent local AI setting"
```

---

### Task 4: Protect the registered probe endpoints

**Files:**
- Modify: `backend/app/api/analytics.py:487-601`
- Modify: `backend/app/api/tests/test_api_integration.py:690-860`

**Interfaces:**
- Consumes: `SafeProbeClient`、`OutboundRequestError`、current `UIConfig.allow_local_ai_endpoints`。
- Produces: protected `POST /api/config/test-api` and `POST /api/config/fetch-models` with stable HTTP/error contracts.

- [ ] **Step 1: Replace direct-httpx mocks with failing security-boundary tests**

Patch one module-level `_SAFE_PROBE_CLIENT` fake instead of `httpx.Client`. Cover both request-supplied and stored credentials. Required cases:

`test_probe_routes_pass_current_local_flag_before_network` 对两个路由参数化：令当前配置为 `allow_local_ai_endpoints=True`，分别调用连接测试和模型列表，断言 fake 的最后一次调用包含 `allow_local=True`、规范 endpoint 名和当前 headers。

`test_probe_routes_return_stable_redacted_errors` 使用以下参数表，每一行都断言 HTTP 状态和完整结构化 `detail` 相等：

```python
ERROR_CASES = [
    (OutboundRequestError("local_ai_disabled", 400, "本地 AI 访问未开启"), 400),
    (OutboundRequestError("private_network_blocked", 400, "该网络地址不允许访问"), 400),
    (OutboundRequestError("outbound_dns_failed", 502, "域名解析失败"), 502),
    (OutboundRequestError("outbound_timeout", 504, "外部服务请求超时"), 504),
]

assert response.status_code == expected_status
assert response.json() == {
    "detail": {"code": error.code, "message": error.public_message}
}
```

Add tests that Anthropic model listing returns the existing hardcoded list without calling `_SAFE_PROBE_CLIENT`; model JSON larger than 1 MiB and invalid JSON use the stable 502 codes; sentinel API key, query and upstream body never appear in response/caplog.

- [ ] **Step 2: Run the endpoint tests and verify RED**

Run:

```powershell
& $PYTHON -m pytest backend/app/api/tests/test_api_integration.py -q -k "api_connection or fetch_models or probe_routes"
```

Expected: failures show direct `httpx.Client` use and missing structured security errors.

- [ ] **Step 3: Route both endpoints through one safe client**

At module scope create one stateless facade:

```python
_SAFE_PROBE_CLIENT = SafeProbeClient()
```

Each endpoint must read the current config once and reuse it for credentials plus the flag:

```python
current = container.config_service.get_ui_config()
credentials = resolve_provider_credentials(request, current)
allow_local = current.allow_local_ai_endpoints
```

Use `probe_status(base_url, endpoint="messages", headers=headers, allow_local=allow_local)` for Anthropic connection testing and `endpoint="models"` otherwise. Use `fetch_json(base_url, endpoint="models", headers=headers, allow_local=allow_local)` for non-Anthropic model lists. Keep current Authorization/x-api-key headers and hardcoded Anthropic list; do not add new provider business behavior.

Catch only `OutboundRequestError` at the route boundary and raise:

```python
raise HTTPException(
    status_code=exc.status_code,
    detail={"code": exc.code, "message": exc.public_message},
) from None
```

Upstream non-200 status remains a redacted `200 {"success": false, "error": "API 返回非成功状态"}` business result；不得包含上游正文。Policy/DNS/connect/timeout/size/parse failures use the documented HTTP statuses.

- [ ] **Step 4: Verify endpoint, security, and OpenAPI tests**

Run:

```powershell
& $PYTHON -m pytest backend/app/api/tests/test_api_integration.py backend/app/security/tests -q
```

Expected: all selected tests pass; current JSON-object request validation and OpenAPI body contract remain unchanged.

- [ ] **Step 5: Commit Task 4**

```powershell
git add backend/app/api/analytics.py backend/app/api/tests/test_api_integration.py
git commit -m "feat: secure API connectivity probes"
```

---

### Task 5: Frontend API error and admin-header contract

**Files:**
- Modify: `frontend/src/services/api.types.ts:825-910`
- Modify: `frontend/src/services/api/base.ts:8-72`
- Create: `frontend/src/services/api/base.test.ts`
- Modify: `frontend/src/services/api/config.ts:1-100`
- Modify: `frontend/src/services/api/config.test.ts`
- Modify: `frontend/src/services/api/index.ts:50-65`
- Modify: `frontend/src/providers/types.ts:62-82`
- Modify: `frontend/src/providers/GameProvider.tsx:210-214`
- Modify: `frontend/src/components/ModalsLayer.tsx:110-122`

**Interfaces:**
- Consumes: backend `{"detail":{"code": string, "message": string}}` failures.
- Produces: `UpdateUIConfigOptions`、`OutboundErrorCode`、`ApiError.code` and optional admin header propagation.

- [ ] **Step 1: Write failing base/config service tests**

Test structured and legacy details separately, then assert token placement:

```typescript
it("parses a structured FastAPI detail without object stringification", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ detail: { code: "local_ai_disabled", message: "本地 AI 访问未开启" } }),
    { status: 400, statusText: "Bad Request", headers: { "Content-Type": "application/json" } },
  )));
  await expect(http.get("/probe")).rejects.toMatchObject({
    code: "local_ai_disabled",
    detail: "本地 AI 访问未开启",
  });
});


it("sends the admin token only in the header when the setting changes", async () => {
  mocks.post.mockResolvedValue(config);
  await updateUIConfig(config, { adminToken: "admin-secret" });
  expect(mocks.post).toHaveBeenCalledWith(
    "/api/config/ui",
    expect.not.objectContaining({ adminToken: expect.anything() }),
    { headers: { "X-Clade-Admin-Token": "admin-secret" } },
  );
  expect(JSON.stringify(mocks.post.mock.calls[0][1])).not.toContain("admin-secret");
});
```

Keep the three existing config credential tests unchanged and passing when no options are provided.

- [ ] **Step 2: Run the service tests and verify RED**

Run:

```powershell
Set-Location frontend
npx vitest run src/services/api/base.test.ts src/services/api/config.test.ts
Set-Location ..
```

Expected: structured detail is currently returned as an object and `updateUIConfig` lacks the options/header argument.

- [ ] **Step 3: Implement backward-compatible error parsing**

Extend `ApiError` with `code?: string`. `parseErrorResponse` must return `{ message, code }`; accept `detail` as a string, `{code,message}`, legacy `message`, legacy string `error`, then `statusText`. Pass the parsed code into `createApiError`. Do not log response bodies.

Export a structural guard:

```typescript
export function isApiError(error: unknown): error is ApiError {
  return error instanceof Error && typeof (error as Partial<ApiError>).status === "number";
}
```

- [ ] **Step 4: Add types, safe messages, and optional header propagation**

Add `allow_local_ai_endpoints?: boolean` to `UIConfig`. Define:

```typescript
export type OutboundErrorCode =
  | "outbound_url_invalid"
  | "outbound_https_required"
  | "local_ai_disabled"
  | "private_network_blocked"
  | "outbound_dns_failed"
  | "outbound_connect_failed"
  | "outbound_response_too_large"
  | "outbound_bad_response"
  | "outbound_timeout"
  | "admin_token_unconfigured"
  | "admin_token_invalid";

export interface UpdateUIConfigOptions {
  adminToken?: string;
}
```

`updateUIConfig(config, options = {})` must preserve the existing two-argument `http.post` call when no token exists; when present, add only `{headers:{"X-Clade-Admin-Token": token}}`. Propagate the optional options type through `GameDataActions`、`GameProvider` and `ModalsLayer`.

Export this fixed guidance map and one shared formatter; use it in `testApiConnection`、`fetchProviderModels` and Task 6's settings-save catch path. Do not expose raw URL/query/body:

```typescript
export const SECURITY_GUIDANCE: Partial<Record<OutboundErrorCode, string>> = {
  local_ai_disabled: "配置已保留；请在本页使用管理员令牌开启本地 AI 访问。",
  private_network_blocked: "该地址属于局域网或特殊网络，Clade 不允许访问。",
  outbound_https_required: "公网 AI 地址必须使用 HTTPS。",
  admin_token_unconfigured: "服务端尚未配置 CLADE_ADMIN_TOKEN。",
  admin_token_invalid: "管理员令牌不正确，请重新输入。",
};

export function getConfigErrorMessage(error: unknown): string {
  if (!isApiError(error)) return "请求失败";
  const code = error.code as OutboundErrorCode | undefined;
  return (code && SECURITY_GUIDANCE[code]) || error.detail || "请求失败";
}
```

`ApiTestResult` and `FetchModelsResult` add `code?: OutboundErrorCode`. Their catch blocks return `message: getConfigErrorMessage(error)` and never use `String(error)` for structured API failures.

从 `frontend/src/services/api/index.ts` 重导出 `getConfigErrorMessage`、`UpdateUIConfigOptions`、`OutboundErrorCode`，让设置面板继续使用统一的 `@/services/api` 入口。

- [ ] **Step 5: Verify frontend service and type checks**

Run:

```powershell
Set-Location frontend
npx vitest run src/services/api/base.test.ts src/services/api/config.test.ts
npx tsc --noEmit
Set-Location ..
```

Expected: focused tests pass and TypeScript reports no errors.

- [ ] **Step 6: Commit Task 5**

```powershell
git add frontend/src/services/api.types.ts frontend/src/services/api/base.ts frontend/src/services/api/base.test.ts frontend/src/services/api/config.ts frontend/src/services/api/config.test.ts frontend/src/services/api/index.ts frontend/src/providers/types.ts frontend/src/providers/GameProvider.tsx frontend/src/components/ModalsLayer.tsx
git commit -m "feat: add secure local AI config contract"
```

---

### Task 6: Settings UI and in-memory token lifecycle

**Files:**
- Create: `frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.tsx`
- Create: `frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.test.tsx`
- Create: `frontend/src/components/SettingsDrawer/SettingsPanel.security.test.tsx`
- Modify: `frontend/src/components/SettingsDrawer/sections/index.ts:1-12`
- Modify: `frontend/src/components/SettingsDrawer/SettingsPanel.tsx:12-120,210-235,290-340`
- Modify: `frontend/src/components/SettingsDrawer/Settings.css`

**Interfaces:**
- Consumes: `UIConfig.allow_local_ai_endpoints` and `onSave(config, {adminToken})` from Task 5.
- Produces: security card, loopback-config warning, password-only local state, safe save/close behavior.

- [ ] **Step 1: Write failing presentational component tests**

Render the component with providers containing `http://localhost:11434/v1`, `http://127.0.0.1:8080/v1`, `http://[::1]:11434/v1` and a public URL. Assert:

```typescript
expect(screen.getByText("本地 AI 访问")).toBeInTheDocument();
expect(screen.getByText(/配置已保留，当前被安全策略阻止/)).toBeInTheDocument();
expect(screen.getByLabelText("管理员令牌")).toHaveAttribute("type", "password");
expect(screen.getByText(/不放行家庭局域网/)).toBeInTheDocument();
```

Also verify no blocked warning for public-only providers, `localhost.` normalization is recognized for display, and toggling calls `onEnabledChange` without mutating the providers object.

- [ ] **Step 2: Write failing SettingsPanel lifecycle tests**

Cover these user flows with `userEvent` and a mocked `onSave`:

1. Normal field save calls `onSave(config)` without token options.
2. Changing the security switch without a token blocks the request and shows “请输入管理员令牌”。
3. Changing the switch with a token calls `onSave(config, {adminToken:"admin-secret"})`.
4. Success clears the password input.
5. 403/503 failure clears the password, keeps the switch in its unsaved position, and shows the fixed guidance.
6. Cancel, overlay close and Escape unmount/clear token state.
7. Spies on `localStorage.setItem` and `sessionStorage.setItem` remain untouched; serialized form never contains the token.

- [ ] **Step 3: Run the component tests and verify RED**

Run:

```powershell
Set-Location frontend
npx vitest run src/components/SettingsDrawer/sections/LocalAIEndpointControl.test.tsx src/components/SettingsDrawer/SettingsPanel.security.test.tsx
Set-Location ..
```

Expected: tests fail because the security card and token-aware save flow do not exist.

- [ ] **Step 4: Implement the security card**

`LocalAIEndpointControl` must remain presentational. Its props are exactly:

```typescript
interface Props {
  enabled: boolean;
  savedEnabled: boolean;
  providers: Record<string, ProviderConfig>;
  adminToken: string;
  saveError: string | null;
  onEnabledChange: (enabled: boolean) => void;
  onAdminTokenChange: (value: string) => void;
}
```

Use `new URL()` only for display detection; compare normalized hostname against `localhost`/`localhost.`、`127.0.0.1`、`[::1]`/`::1`. This helper is not a security decision and must be named `hasLoopbackProviderForDisplay` to avoid later backend reuse. Show the password input only when `enabled !== savedEnabled`.

- [ ] **Step 5: Implement local token state and safe save/close handling**

In `SettingsPanel`, add only component-local state:

```typescript
const [adminToken, setAdminToken] = useState("");
const [saveError, setSaveError] = useState<string | null>(null);
const savedLocalAI = config.allow_local_ai_endpoints ?? false;
const draftLocalAI = state.form.allow_local_ai_endpoints ?? false;
const localAIChanged = draftLocalAI !== savedLocalAI;
```

Update the component prop to `onSave: (config: UIConfig, options?: UpdateUIConfigOptions) => Promise<void>` and import `getConfigErrorMessage` plus `UpdateUIConfigOptions` from `@/services/api`.

Use this save contract:

```typescript
if (localAIChanged && !adminToken) {
  setSaveError("请输入管理员令牌");
  return;
}
dispatch({ type: "SET_SAVING", saving: true });
setSaveError(null);
try {
  if (localAIChanged) {
    await onSave(state.form, { adminToken });
  } else {
    await onSave(state.form);
  }
  dispatch({ type: "SET_SAVE_SUCCESS", success: true });
} catch (error) {
  setSaveError(getConfigErrorMessage(error));
} finally {
  setAdminToken("");
  dispatch({ type: "SET_SAVING", saving: false });
}
```

Create `handleClose` that calls `setAdminToken("")` and `setSaveError(null)` before `onClose()`. Route overlay click、关闭按钮、取消按钮和 Escape through `handleClose`. Render `LocalAIEndpointControl` above `ConnectionSection` only in the connection tab; update the form through existing `UPDATE_GLOBAL` action.

Add scoped CSS using existing `.config-group`、`.info-box`、`.form-control` visual language; no new dependency, global font or full settings redesign.

- [ ] **Step 6: Verify focused and existing settings tests**

Run:

```powershell
Set-Location frontend
npx vitest run src/components/SettingsDrawer/sections/LocalAIEndpointControl.test.tsx src/components/SettingsDrawer/SettingsPanel.security.test.tsx src/components/SettingsDrawer/sections/credentialState.test.tsx src/components/SettingsDrawer/reducer.test.ts
npx tsc --noEmit
Set-Location ..
```

Expected: all selected tests pass; existing provider credential behavior is unchanged.

- [ ] **Step 7: Commit Task 6**

```powershell
git add frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.tsx frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.test.tsx frontend/src/components/SettingsDrawer/SettingsPanel.security.test.tsx frontend/src/components/SettingsDrawer/sections/index.ts frontend/src/components/SettingsDrawer/SettingsPanel.tsx frontend/src/components/SettingsDrawer/Settings.css
git commit -m "feat: add local AI security control"
```

---

### Task 7: Documentation, full gates, and 2C-1 handoff

**Files:**
- Modify: `docs/api-guides/modules/config-ui/api-connectivity.md`
- Modify: `docs/api-guides/modules/config-ui/ui-config.md`
- Create: `docs/superpowers/reports/2026-07-14-phase-2c1-verification.md`

**Interfaces:**
- Consumes: completed backend/frontend behavior and exact test evidence.
- Produces: user-facing API documentation and a durable 2C-1 verification record explicitly marked “Phase 2C 尚未完成”。

- [ ] **Step 1: Update connectivity documentation**

Correct the stale implementation path from `backend/app/api/routes.py` to `backend/app/api/analytics.py`. Document:

- request-supplied and stored base URLs use the same policy;
- public HTTPS requirement;
- default local/private blocking and exact loopback exception;
- no proxy/no redirect behavior;
- 10/15-second deadlines and 1 MiB model-list limit;
- the complete status/error-code table from the design;
- no API key, admin token, sensitive query or upstream body in errors/logs.

Remove claims that failure details contain portions of upstream response bodies.

- [ ] **Step 2: Update UI config documentation**

Add `allow_local_ai_endpoints: false` to the JSON example. State that changing it requires `X-Clade-Admin-Token`, both directions require validation, the field is atomically saved with the rest of the config, and the token is never part of JSON. Explain that old local URLs are retained but blocked while disabled.

- [ ] **Step 3: Run the full backend gates**

Run:

```powershell
& $PYTHON -m pytest backend/app -q
& $PYTHON -m pytest backend/app/core/tests/test_plugin_registry_fresh_process.py -q
```

Expected: at least 556 tests collected plus all new tests; 0 failures/collection errors; exactly the 2 existing Windows symlink skips; warnings no more than 45; fresh-process plugin guard passes.

- [ ] **Step 4: Run the full frontend gates**

Run:

```powershell
Set-Location frontend
npm run test:run
npm run lint
npx tsc --noEmit
npm run build
Set-Location ..
```

Expected: original 52 tests plus all new tests pass; ESLint 0 errors and no more than 162 warnings; TypeScript and Vite build exit 0.

- [ ] **Step 5: Run repository hygiene and secret scans**

Run:

```powershell
git diff --check
rg -n "admin-secret|sk-unsaved|resolver sentinel|upstream echoed" backend/app frontend/src docs/api-guides -g '!**/test_*.py' -g '!**/*.test.ts' -g '!**/*.test.tsx'
git status --short
```

Expected: `git diff --check` has no output; sentinel scan has no production/docs matches; status lists only the intended Task 7 documentation/report changes.

- [ ] **Step 6: Write the verification report from fresh command output**

Record command, exit code, collected/pass/skip/warning counts, frontend test count, lint error/warning counts, TypeScript/build results, commit range, and these explicit limitations:

```text
Phase 2C-1 protects configuration probes and the persistent local-AI control.
Phase 2C is not complete: actual AI, load-balancing, streaming, and embedding requests remain for Phase 2C-2.
This branch must not be merged or released before Phase 2C-2 and final review.
```

Do not copy secrets, complete URLs with query strings, response bodies or raw exception text into the report.

- [ ] **Step 7: Commit Task 7**

```powershell
git add docs/api-guides/modules/config-ui/api-connectivity.md docs/api-guides/modules/config-ui/ui-config.md docs/superpowers/reports/2026-07-14-phase-2c1-verification.md
git commit -m "docs: record phase 2c1 security verification"
```

- [ ] **Step 8: Review the complete 2C-1 commit range without merging**

Run:

```powershell
git log --oneline 89eec7b..HEAD
git diff --stat 89eec7b..HEAD
git status --short
```

Expected: seven intentional implementation commits, a clean worktree, and no changes to `backend/app/ai/model_router.py` or `backend/app/services/system/embedding.py`. Proceed to a separate Phase 2C-2 design review; do not offer merge at this checkpoint.

---

## Review Checkpoints

After each task, inspect the exact commit diff before continuing. Reject the task if it broadens the address allowlist, performs a second unrestricted DNS lookup, stores the admin token, follows redirects, reads an unbounded response, weakens existing secret preservation, or changes runtime AI/Embedding paths.

After Task 4, perform a backend security review of URL normalization, IP classification, DNS rebinding resistance and error redaction. After Task 6, perform a frontend review of token lifetime and unchanged ordinary-save behavior. After Task 7, review the complete range and begin Phase 2C-2 design only; the branch remains isolated.
