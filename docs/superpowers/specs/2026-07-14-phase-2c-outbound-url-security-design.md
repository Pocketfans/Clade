# Clade Phase 2C 外部 URL 与 SSRF 防护设计

日期：2026-07-14

状态：用户已确认，等待书面规格复核

起点分支：`phase-2b2-save-path-boundary`

起点提交：`9f0c26bf30321f19db76828b61daa12f3f5ed2ad`

工作分支：`phase-2c-outbound-url-security`

## 1. 结论

Phase 2C 为 Clade 建立统一的服务端外部 URL 安全边界，防止用户可配置的 AI 地址诱导后端访问本机、家庭局域网、云元数据服务或其他特殊网络地址。

本阶段采用两个独立审查批次：

1. **Phase 2C-1：安全入口。** 建立统一 URL 策略和受限探测请求，保护“测试连接”和“获取模型列表”，并加入受管理员令牌保护、永久保存、立即生效的“允许本地 AI”设置。
2. **Phase 2C-2：运行时收口。** 把相同策略接入实际 AI 对话、报告、负载均衡和 Embedding 请求。2C-2 在 2C-1 验收后另行细化实施设计，但必须复用本规格定义的策略接口和安全不变量。

两个批次在同一隔离分支中分别提交和审查。2C-1 完成后不单独合并，也不宣称 Phase 2C 完成；只有 2C-2 和最终全量门禁完成后才提供合并选项。

## 2. 用户确认的产品选择

- 默认禁止后端访问本机和私有网络 AI 地址。
- 在设置页面提供“允许本地 AI”开关。
- 开关默认关闭。
- 开启和关闭都必须通过 `CLADE_ADMIN_TOKEN` 验证。
- 开关状态永久写入现有 UI 配置文件，保存成功后立即生效。
- 管理员令牌只存在于当前前端组件内存，不写入设置文件、浏览器存储、URL 或日志。
- 开启后只允许当前电脑的 `localhost`、`127.0.0.1` 和 `::1`；不放开家庭局域网或其他私有地址。
- 已保存的本地或不安全地址继续保留，不自动删除，也不自动打开权限；被策略阻止时显示可操作说明。

以上选择取代早期总设计中仅使用 `ALLOW_LOCAL_AI_ENDPOINTS` 环境变量控制本地 AI 的方案。管理员令牌仍由环境变量提供；如果服务端未配置管理员令牌，安全开关不能被修改。

## 3. 当前状态与风险

当前实际注册的配置路由位于 `backend/app/api/analytics.py`：

- `POST /api/config/test-api`
- `POST /api/config/fetch-models`

两个端点会从请求或已保存配置中取得 `base_url`，拼接服务商端点后直接交给 `httpx.Client`。当前没有统一的协议、主机、DNS/IP、重定向、系统代理或响应大小策略。

旧 `backend/app/api/routes.py` 仍包含历史实现，但不属于当前注册路由。Phase 2C 不迁移、不恢复也不修改旧路由架构。

实际 AI 与 Embedding 请求还分散在 `ModelRouter` 和 `EmbeddingService` 中。2C-1 只建立可复用安全基础和保护配置探测端点；2C-2 负责运行时收口。两个批次未全部完成前，不能把分支当作完整 SSRF 修复发布或合并。

## 4. Phase 2C-1 范围

### 4.1 包含

- 新增集中式 `OutboundURLPolicy`。
- 新增只用于配置探测的受限同步 HTTP 客户端。
- 保护当前注册的连接测试和模型列表端点。
- 在 `UIConfig` 中新增永久设置 `allow_local_ai_endpoints: bool = False`。
- 只有该设置发生变化时，`POST /api/config/ui` 才要求管理员令牌。
- 设置保存继续复用现有更新锁、密钥合并、原子文件替换和缓存失效流程。
- 在设置抽屉中显示本地 AI 安全控制、风险说明和管理员令牌确认。
- 为前后端提供稳定、安全、可操作的错误分类。
- 更新相关配置 API 文档。

### 4.2 不包含

- 不在 2C-1 中修改 `ModelRouter`、负载均衡请求或 `EmbeddingService` 的实际请求流程。
- 不允许其他电脑或家庭局域网中的本地模型服务。
- 不建设用户自定义 IP/CIDR 白名单。
- 不支持经系统代理访问自定义 AI 地址。
- 不改变 AI 服务商选择、模型选择、提示词、响应内容或重试策略。
- 不改变数据库、存档格式、模拟规则或前端整体视觉体系。
- 不清理与本阶段无关的旧代码、警告或类型问题。

## 5. 安全策略

### 5.1 策略接口

`OutboundURLPolicy` 是不执行网络请求的纯策略组件。它接收候选 URL、当前本地 AI 开关和可替换的 DNS 解析器，返回不可变的验证结果：

```python
@dataclass(frozen=True)
class ValidatedOutboundURL:
    url: str
    scheme: Literal["http", "https"]
    hostname: str
    port: int
    resolved_ips: tuple[IPv4Address | IPv6Address, ...]
    is_local: bool


class OutboundURLPolicy:
    def validate(
        self,
        url: str,
        *,
        allow_local: bool,
    ) -> ValidatedOutboundURL: ...
```

DNS 解析器通过构造函数注入，生产环境使用系统解析，测试使用确定性假解析器。策略错误使用受控异常类型和稳定错误码，不携带 API Key、管理员令牌或底层异常全文。

### 5.2 URL 语法规则

- 仅接受绝对 `http` 或 `https` URL。
- 必须存在主机名。
- 拒绝 URL 用户名和密码。
- 拒绝 fragment。
- 用户提供的基础 URL 不接受 query；服务商所需 query 只能由受控端点构造器添加。
- 显式端口必须在 `1..65535`；未提供端口时，`https` 使用 443，`http` 使用 80。
- 允许基础路径，例如 `https://api.example.com/v1`，但端点拼接必须使用集中构造器，不能字符串重复拼接斜杠或替换主机。
- 主机名先做大小写、尾随点和 IDNA 规范化，再进行分类和解析。

### 5.3 地址分类规则

公网服务：

- 必须使用 `https`。
- 域名解析得到的每个地址都必须是全局可路由地址。
- 只要解析结果混入一个不安全地址，整个 URL 都被拒绝。

默认拒绝：

- IPv4/IPv6 回环地址。
- RFC1918 私网和 IPv6 ULA。
- 链路本地地址。
- 保留、文档、基准测试、运营商共享地址。
- 多播和未指定地址。
- 不能解析或解析结果为空的主机。

本地 AI 例外：

- 仅在 `allow_local=True` 时生效。
- 只接受规范化后的 `localhost`、字面量 `127.0.0.1` 和 `::1`。
- `localhost` 的全部解析结果必须是回环地址。
- 本地例外允许 `http` 或 `https` 以及合法自定义端口。
- `*.localhost`、其他 `127.0.0.0/8` 地址、私有网段和局域网主机名不属于例外。

### 5.4 防止检查后换地址

只做“先 DNS 检查、再让 HTTP 客户端重新解析域名”仍可能遭受 DNS rebinding。

受限客户端必须遵守以下连接契约：

- 每次请求都重新执行策略校验。
- 实际连接目标只能从本次 `resolved_ips` 中选择。
- 连接阶段不能再进行不受策略约束的第二次 DNS 解析。
- HTTP `Host` 和 HTTPS TLS SNI/证书验证仍使用原始规范主机名。
- 单个已验证地址连接失败时，可以尝试同一次验证结果中的下一个安全地址；不能改用验证结果之外的地址。

具体传输适配方式由实施计划根据锁定的 `httpx/httpcore` 版本确定，但不得弱化以上行为契约，也不得依赖未固定版本的偶然内部行为而无回归测试。

## 6. 受限探测客户端

2C-1 新增专用于连接测试和模型列表的同步客户端。它不替代 2C-2 的流式运行时客户端。

### 6.1 请求规则

- `trust_env=False`，不读取系统代理变量。
- `follow_redirects=False`，3xx 不自动访问下一地址。
- 每次请求都通过 `OutboundURLPolicy` 验证最终 URL。
- 连接测试不需要读取完整正文，只根据受限响应状态判断结果。
- 模型列表使用流式读取；最大正文为 `1_048_576` 字节。
- 如果 `Content-Length` 已超过上限，读取正文前立即拒绝。
- 没有或伪造 `Content-Length` 时，累计读取到上限加 1 字节即停止并拒绝。
- 不记录请求头、响应正文、完整含 query URL 或底层异常文本。

### 6.2 超时

连接测试：

- 连接超时 5 秒。
- 单次读取超时 5 秒。
- 整体截止时间 10 秒。

模型列表：

- 连接超时 5 秒。
- 单次读取超时 10 秒。
- 整体截止时间 15 秒。

写入和连接池等待均不得超过 5 秒。整体截止时间包含 DNS、连接、响应头和正文读取。

### 6.3 服务商兼容

- OpenAI 兼容服务继续访问其受控 `/models` 端点。
- Anthropic 的现有测试端点和硬编码模型列表行为保持不变，但任何真实探测请求仍必须先验证 URL。
- Google 等服务商如果需要把 API Key 放入 query，只能在策略通过后由受控构造器添加；完整 URL 不进入日志或错误响应。
- 本阶段不顺便修正服务商既有业务差异或模型列表格式。

## 7. 永久本地 AI 开关

### 7.1 配置模型

`UIConfig` 新增：

```python
allow_local_ai_endpoints: bool = False
```

该字段通过现有 `data/settings.json` 原子保存，并包含在脱敏后的公开 UI 配置中。它不是密钥。

旧配置没有该字段时按 `False` 读取。旧本地地址和模型配置原样保留，不迁移、不删除。

### 7.2 条件管理员验证

现有 `POST /api/config/ui` 继续处理整个设置对象。请求可以额外携带 `X-Clade-Admin-Token`，但只有以下条件满足时才验证它：

```text
incoming.allow_local_ai_endpoints != current.allow_local_ai_endpoints
```

验证必须发生在密钥合并和文件保存之前：

- 服务端未配置 `CLADE_ADMIN_TOKEN`：返回 503。
- 请求令牌缺失或错误：返回统一 403。
- 验证使用常量时间比较。
- 开启和关闭都要求令牌。
- 验证失败时，整个设置更新不落盘、不刷新缓存、不应用到运行时。

现有管理员依赖应提取或复用一个纯验证函数，保证 `/api/admin` 和条件配置验证的状态码、常量时间比较和脱敏规则一致。

### 7.3 原子保存与立即生效

验证通过后继续使用现有 `_UI_CONFIG_UPDATE_LOCK`、`merge_ui_config_secrets()`、`EnvironmentRepository.save_ui_config()` 和 `ConfigService.invalidate_cache()`。

这样保证：

- 安全开关和同次其他设置一起成功或一起失败。
- 不新增第二条会与普通设置保存竞争的写文件路径。
- 保存成功后，下一次探测请求读取到新开关值，无需重启。
- API Key 的保留、替换、清除语义保持不变。

### 7.4 前端交互

设置抽屉的连接区域新增“本地 AI 访问”安全卡片，沿用现有表单、提示和确认样式，不重做整个设置界面。

- 显示当前已保存状态和未保存状态。
- 默认关闭，并说明公网服务不受影响。
- 开启时明确说明只放行当前电脑回环服务，不放行家庭局域网。
- 当用户保存且开关发生变化时，显示管理员令牌确认。
- 令牌使用密码输入框，只保存在局部组件状态。
- 请求完成、取消或关闭抽屉时清除令牌。
- 不使用 `localStorage`、`sessionStorage`、URL、全局状态或配置对象保存令牌。
- 保存失败时保留用户未保存的表单值，便于纠正令牌后重试。
- 已保存本地地址在权限关闭时仍显示，并标记“配置已保留，当前被安全策略阻止”。

## 8. 数据流

### 8.1 普通配置保存

```text
设置表单
→ POST /api/config/ui
→ 开关未变化
→ 密钥合并
→ 原子保存
→ 缓存失效与运行时刷新
→ 返回脱敏配置
```

### 8.2 安全开关变化

```text
用户修改开关并保存
→ 前端要求管理员令牌
→ X-Clade-Admin-Token 请求头
→ 后端比较当前值与新值
→ 常量时间验证
→ 验证成功后与其他设置一起原子保存
→ 缓存失效
→ 下一请求立即使用新策略
→ 前端清除令牌
```

### 8.3 外部探测

```text
请求或已保存服务商配置
→ 解析凭据但不回显
→ 构造最终服务商端点
→ URL 语法和主机规范化
→ DNS/IP 分类
→ 固定到本次批准地址
→ 关闭代理和重定向的受限请求
→ 状态或限长正文解析
→ 安全结果/安全错误
```

## 9. 错误契约

后端使用稳定错误码和中文安全说明。前端根据错误码显示操作建议，不解析底层异常字符串。

| HTTP | 错误码 | 场景 | 用户提示方向 |
| ---: | --- | --- | --- |
| 400 | `outbound_url_invalid` | URL 格式、协议、凭据、query、fragment 或端口非法 | 检查 Base URL |
| 400 | `outbound_https_required` | 公网地址使用 HTTP | 改用 HTTPS |
| 400 | `local_ai_disabled` | 回环地址但开关关闭 | 前往设置并用管理员令牌开启 |
| 400 | `private_network_blocked` | 私网、链路本地或其他特殊地址 | 该地址不允许访问 |
| 502 | `outbound_dns_failed` | DNS 失败或无地址 | 检查域名/DNS |
| 502 | `outbound_connect_failed` | 外部服务不可达 | 检查服务状态和地址 |
| 502 | `outbound_response_too_large` | 模型列表超过 1 MiB | 服务返回内容过大 |
| 502 | `outbound_bad_response` | 非预期或无法解析的模型列表 | 服务响应格式异常 |
| 504 | `outbound_timeout` | 连接、读取或总体超时 | 稍后重试或检查服务 |
| 503 | `admin_token_unconfigured` | 修改开关但服务端未配置令牌 | 启动前设置 `CLADE_ADMIN_TOKEN` |
| 403 | `admin_token_invalid` | 令牌缺失或错误 | 重新输入管理员令牌 |

错误响应不得包含：

- API Key 或管理员令牌。
- Authorization、`x-api-key` 等请求头内容。
- 带敏感 query 的完整 URL。
- DNS 解析器、socket 或 `httpx` 的内部异常全文。
- 超限响应正文。

## 10. 兼容与迁移

- `UIConfig` 使用 `extra="ignore"`，新增布尔字段对旧文件向后兼容。
- 不重写、不删除旧 `base_url`。
- 权限关闭时，旧本地地址可查看和编辑，但测试/获取模型请求被拒绝。
- 用户通过管理员令牌开启权限后，合法回环配置立即恢复使用。
- 家庭局域网地址不会因开关开启而恢复；需改为本机回环服务或公网 HTTPS。
- 2C-1 不修改存档、数据库和游戏状态，因此没有数据迁移。

## 11. Phase 2C-2 交接契约

2C-2 必须复用而不是复制 2C-1 的：

- URL 规范化和地址分类。
- DNS 解析注入边界。
- `ValidatedOutboundURL` 结果。
- 本地 AI 开关语义。
- 错误脱敏规则。
- 不使用系统代理、不自动跟随重定向的默认值。

2C-2 需要覆盖：

- `ModelRouter` 默认服务商请求。
- capability override。
- 负载均衡 provider pool。
- 同步、异步和流式 AI 请求。
- `EmbeddingService` 批量向量请求。
- 环境变量/旧版配置提供的 base URL。

配置探测的 1 MiB 限制不直接套用到 AI 流式输出或 Embedding 响应；2C-2 必须依据各响应类型另行定义不会破坏合法使用的上限和中止行为。

## 12. 测试设计

### 12.1 策略单元测试

使用注入 DNS 解析器，至少覆盖：

- 公网域名 → 全部公网 IPv4/IPv6 → 允许 HTTPS。
- 公网 HTTP → 拒绝。
- `localhost`、`localhost.`、`127.0.0.1`、`::1` 在开关关闭/开启两种状态。
- `*.localhost`、其他 `127/8`、RFC1918、ULA、链路本地、保留、多播、未指定和运营商共享地址。
- 域名混合解析出公网与不安全地址 → 全部拒绝。
- URL 凭据、query、fragment、空主机、错误端口和非 HTTP(S) 协议。
- DNS 失败、空结果、重复地址和规范化顺序。

### 12.2 受限客户端测试

不访问真实公网，使用假传输和可控本地测试服务验证：

- 连接只使用验证结果中的地址。
- 保留原始 Host/TLS 主机语义。
- 不读取系统代理。
- 不跟随 3xx。
- `Content-Length` 超限和流式实际超限。
- 连接、读取和整体截止时间。
- 错误和日志不含密钥、请求头、敏感 URL 或正文。

### 12.3 API 测试

- 两个配置探测端点都在发送请求前调用策略。
- 请求内新凭据和已保存凭据都受策略保护。
- Anthropic 无真实模型列表请求时不制造无意义网络调用。
- 开关未变化时普通配置保存不要求令牌。
- False→True、True→False 都要求正确令牌。
- 503、403 时不保存、不失效缓存、不刷新运行时。
- 正确令牌下开关与其他设置原子保存并立即可读。
- 旧本地地址保留，开关关闭时阻止、开启时允许。
- API 和日志不回显任何密钥或管理员令牌。

### 12.4 前端测试

- 显示已保存和未保存状态。
- 开关变化时要求管理员令牌，普通保存不要求。
- 令牌不写入 localStorage、sessionStorage、URL、配置请求体或全局状态。
- 请求使用 `X-Clade-Admin-Token`，结束后清除局部令牌。
- 403、503、`local_ai_disabled`、`private_network_blocked` 和公网 HTTP 错误显示正确说明。
- 旧本地地址保持可见，不被清空。

### 12.5 基线和门槛

隔离工作区在起点提交已验证：

- 后端收集 556 项：554 通过、2 项 Windows 符号链接预期跳过、45 条既有警告。
- fresh-process 插件注册检查通过。
- 前端 52/52 测试通过。
- ESLint 0 错误、162 条既有警告。
- TypeScript 类型检查和 Vite 生产构建通过。

Phase 2C 要求：

- 新测试只能增加总数，不能删除、跳过或漏收现有测试。
- 后端 0 失败、0 初始化错误；2 个既有跳过不增加。
- 后端既有 45 条警告不因本阶段增加。
- 前端 ESLint 0 错误，警告不超过 162。
- 前端测试 0 失败，现有 52 项全部保留。
- TypeScript、Vite build、`git diff --check` 全部通过。
- 每个批次独立审查，最终整分支再次审查。

## 13. 预计影响文件

2C-1 预计涉及：

新建：

- `backend/app/security/outbound_url.py`
- `backend/app/security/safe_http.py`
- `backend/app/security/tests/test_outbound_url.py`
- `backend/app/security/tests/test_safe_http.py`
- `frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.tsx`
- `frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.test.tsx`

修改：

- `backend/app/models/config.py`
- `backend/app/security/admin_token.py`
- `backend/app/security/__init__.py`
- `backend/app/api/analytics.py`
- `backend/app/api/tests/test_api_integration.py`
- `backend/app/security/tests/test_admin_token.py`
- `frontend/src/services/api/config.ts`
- `frontend/src/components/SettingsDrawer/sections/ConnectionSection.tsx`
- 设置抽屉的相关类型、状态和测试文件（以实施计划核实后的最小集合为准）
- `docs/api-guides/modules/config-ui/api-connectivity.md`

2C-2 的精确文件集合在 2C-1 验收后单独设计；不得仅凭本列表直接开始修改运行时 AI 文件。

## 14. 风险与控制

### DNS rebinding 与传输适配

风险：策略校验正确但客户端重新解析域名，造成检查与连接目标不一致。

控制：连接只能使用本次验证结果中的固定地址，并测试 Host/TLS 主机语义。若锁定版本无法以稳定公开接口满足该契约，应暂停实施计划并重新评估传输方案，不能退化为“只检查一次 DNS”。

### 永久本地 AI 权限

风险：用户开启后可能忘记关闭，任何能调用本地 Clade API 的页面都可以利用已开启的本地访问能力。

控制：默认关闭、修改需管理员令牌、页面持续显示状态和风险、本地范围严格限制为当前电脑回环地址。该残余风险是用户明确选择永久开关后的已接受权衡。

### 配置竞争

风险：单独新增安全设置保存接口会与普通配置保存互相覆盖。

控制：不新增第二条写文件路径；开关放入现有原子配置更新事务，并复用同一更新锁。

### 半完成安全状态

风险：2C-1 的设置和测试连接已安全，但实际运行时请求尚未全部收口。

控制：两批保留在同一隔离分支；2C-1 不单独合并或发布；2C-2 完成前不宣称 Phase 2C 完成。

### 敏感信息泄露

风险：Google query key、Authorization、底层异常或超量响应进入日志。

控制：日志只记录错误码、服务商类型和异常类别；不记录完整 URL、请求头、凭据或正文；用自动测试扫描哨兵密钥。

## 15. 验收结果

Phase 2C-1 完成时应能证明：

1. 默认情况下两个配置探测端点不能访问本机、私网或公网 HTTP。
2. 公网 HTTPS 继续可测试和获取模型。
3. 正确管理员令牌可永久开启或关闭本地 AI，且立即生效。
4. 开启后仅当前电脑回环地址可用，局域网仍被拒绝。
5. 旧地址和模型配置不丢失。
6. DNS 检查与实际连接目标一致，不能通过重绑定绕过。
7. 重定向、系统代理、超时和超量响应受到约束。
8. API Key、管理员令牌和内部错误不泄露。
9. 全量后端、前端、类型检查、构建和代码审查全部通过。
10. 分支明确标记为“2C-1 已完成，Phase 2C 尚未完成”，随后进入 2C-2 设计与实施。
