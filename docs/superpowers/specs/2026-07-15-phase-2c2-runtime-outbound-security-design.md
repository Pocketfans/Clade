# Phase 2C-2 运行时出站请求安全设计

日期：2026-07-15

分支：`phase-2c-outbound-url-security`

前置基线：Phase 2C-1 最终提交 `b52eb91ca1af9acf8473e0bd5cca996bbfc6cea2`

## 1. 背景

Phase 2C-1 已经建立统一的 URL 规范化、特殊地址分类、DNS 解析注入边界、固定目标 IP 的同步探测传输，以及受管理员令牌保护的 `allow_local_ai_endpoints` 持久开关。配置连接测试和模型列表请求已经安全，但实际 AI 与 Embedding 请求仍直接使用 `httpx`。

运行时请求目前分散在以下位置和入口：

- `ModelRouter` 默认服务商请求；
- capability override；
- 负载均衡 provider pool；
- `invoke`、`ainvoke`、`astream`；
- 旧版 capability 同步、异步和流式入口；
- `chat`；
- `EmbeddingService` 的并发批量请求；
- 环境变量和旧版配置提供的 base URL。

仅在这些调用附近增加 URL 检查无法阻止连接层再次解析 DNS，也容易遗漏重复路径。因此 2C-2 必须建立一个统一的运行时安全出口，并让所有实际外连请求经过它。

## 2. 已确认的产品决定

本设计基于用户逐项确认的三个决定：

1. 负载均衡选中的服务商地址不安全时，立即失败并提示配置错误；不得自动切换到池中其他服务商。
2. Embedding 地址被安全策略拦截时，立即失败；即使允许假向量，也不得用假向量掩盖安全错误。
3. 采用统一安全运行时客户端；不逐条散落补丁，也不在本阶段彻底重写 `ModelRouter`。

## 3. 目标

- 所有实际 AI、流式和 Embedding 请求复用 2C-1 的 URL 与地址策略。
- DNS 校验结果直接约束 TCP 连接目标，消除检查后重新解析造成的 DNS rebinding 窗口。
- 同时支持同步、异步和异步流式请求。
- 禁用系统代理、环境代理、Unix socket 和自动重定向。
- 保留原始 Host、TLS SNI 和证书验证语义。
- 对普通 JSON、Embedding 和流式响应分别设置明确上限。
- 超时、取消、调用方提前停止和异常响应都能及时关闭连接。
- 所有错误和日志均不泄露凭据、敏感 URL、请求正文、响应正文或底层异常原文。
- 保持现有调用入口、正常返回格式、并发限制、心跳事件、负载均衡选择和合法降级规则兼容。

## 4. 非目标

- 不重写完整的 `ModelRouter` 路由、提示词或服务商解析逻辑。
- 不改变数据库、存档格式或前端配置 JSON 结构。
- 不新增自动服务商故障转移。
- 不改变 AI 输出内容、模型选择算法、负载均衡策略或 Embedding 数学逻辑。
- 不把配置探测客户端的 1 MiB 限制直接复用于运行时响应。
- 不新增对真实公网的测试。
- 不顺带清理与安全出口无关的历史重复代码或 lint 警告。

## 5. 方案比较

### 5.1 统一安全运行时客户端（采用）

建立一个独立安全出口，统一处理同步、异步、流式和 Embedding 请求。业务代码只负责构造服务商请求与解析正常响应。

优点是安全规则只有一份、连接目标可以真正固定、测试边界清晰，后续新增入口也能复用。代价是需要对现有请求入口做有控制的适配。

### 5.2 在每个 `httpx` 调用附近增加检查（拒绝）

改动表面较小，但无法保证连接层不重新解析 DNS，且 `ModelRouter` 存在多套重复请求代码，长期必然产生遗漏和规则漂移。

### 5.3 完整重写 `ModelRouter`（拒绝）

结构可能更整洁，但会同时改变路由、重试、解析、流式和并发行为，回归范围远大于当前安全目标。

## 6. 总体架构

### 6.1 地址安全层

继续使用 2C-1 的：

- `OutboundURLPolicy`；
- `ValidatedOutboundURL`；
- URL 规范化和 IDNA 处理；
- IPv4、IPv6、嵌入式 IPv4 和 IANA 特殊地址分类；
- 可注入 DNS resolver；
- `allow_local_ai_endpoints` 语义；
- 固定、脱敏的 `OutboundRequestError` 错误码。

不得复制第二份地址分类表或创建弱化版 allowlist。

### 6.2 公用固定目标传输层

从 2C-1 的同步安全探测传输中提取可复用的内部传输原语，并增加等价的异步实现。建议形成一个仅供安全客户端使用的内部模块，例如 `backend/app/security/pinned_transport.py`。

该层负责：

- 接收 `ValidatedOutboundURL`，只连接其中批准的 IP；
- 校验请求 origin 的 host 与 port 和批准结果一致；
- 按批准顺序尝试 IP，禁止加入任何新解析结果；
- TLS 使用原始域名执行 SNI 和证书验证；
- 禁止 Unix socket；
- 对同步和异步底层异常做脱敏；
- 连接、流和连接池在成功、失败、取消时都只关闭一次。

现有 `SafeProbeClient` 改为复用这些内部原语，但其外部接口和 2C-1 测试必须保持不变。

### 6.3 运行时安全客户端

新增高层模块，例如 `backend/app/security/runtime_http.py`，提供以下概念接口：

- 同步 JSON POST；
- 异步 JSON POST；
- 异步逐行流式 POST；
- 分开接收不含 query/fragment 的 `base_url` 与同源 `request_target`；
- 按响应类型传入限制和超时；
- 按请求传入当前 `allow_local_ai_endpoints` 快照；
- 返回状态码与已验证的 JSON 对象，或返回受控流事件；
- 只抛出固定的 `OutboundRequestError`。

客户端每次请求都执行完整流程，不接受业务代码预先校验后再交给普通 `httpx` 的用法。

`OutboundURLPolicy` 继续严格拒绝任何带 query 或 fragment 的输入。运行时客户端只把 `base_url` 交给策略；请求路径和 Google query key 使用独立的 `request_target`。`request_target` 必须满足：

- 以单个 `/` 开头，不能以 `//` 开头；
- 解析后 scheme 和 netloc 都为空；
- 不含 fragment、反斜杠、空白或控制字符；
- 不能包含第二个绝对 URL 或改变协议、域名、端口的语法；
- 动态模型名使用路径段百分号编码，query 使用 `urlencode` 构造；
- 只允许在 `OutboundURLPolicy` 已返回 `ValidatedOutboundURL` 后拼接；
- 使用 `validated.url.rstrip("/") + request_target`，不得使用会丢弃 base path 的 `urljoin`。

固定目标传输层仍会核对最终 `httpx.Request` 的 host 和 port 与批准结果一致，因此 query 永远不能改变连接 origin。

### 6.4 业务适配层

`ModelRouter` 保留 OpenAI、Anthropic、Google 的 URL、headers、body 和正常响应解析。它不再直接建立网络连接，而是把准备好的最终请求交给运行时安全客户端。

`EmbeddingService` 保留文本截断、批次拆分、并发、重试、统计、真实/假向量选择和响应排序，并替换实际网络发送与安全错误分类。缓存读取和写入继续绑定一次公开调用的不可变运行时配置，但在最终安全复审后升级为第 14.1 节定义的 v2 来源隔离命名空间，不能再把不同端点或真假向量视为同一缓存来源。

## 7. 固定请求流程

每次运行时请求严格按照以下顺序执行：

1. 解析 capability 配置。
2. 按现有策略选择负载均衡 provider；没有负载均衡时使用 override 或默认 provider。
3. 生成不含 query/fragment 的 `base_url`、同源 `request_target`、headers 和 body。
4. 读取当前 `allow_local_ai_endpoints` 的不可变快照。
5. 由 `OutboundURLPolicy` 验证 `base_url` 并完成唯一一次 DNS 解析。
6. 验证 `request_target` 后与 `validated.url` 拼接；该步骤不得重新解析 URL origin。
7. 使用本次 `ValidatedOutboundURL.resolved_ips` 建立连接。
8. 以原始 host 执行 Host、SNI 和证书验证。
9. 在响应类型对应的时限与大小限制内读取。
10. 把正常结果交还现有业务解析器；把异常映射为固定、脱敏错误。
11. 在所有退出路径关闭 response、stream、client 和 pool。

Google API key 位于查询参数时，策略只验证不含 query 的 provider `base_url`；Google adapter 使用 `urlencode({"key": api_key})` 构造相对 `request_target`。任何日志、错误和诊断字段都不得包含 query 或完整 target。

## 8. 配置来源与本地 AI 开关

以下来源没有豁免权，必须经过同一运行时策略：

- 默认 provider；
- capability override；
- provider pool；
- UI 持久配置；
- 环境变量；
- 旧版配置迁移后的 base URL；
- Embedding provider。

本地地址只允许 2C-1 已定义的精确回环例外：规范化 `localhost`、字面量 `127.0.0.1` 和字面量 `::1`。只有 `allow_local_ai_endpoints=true` 时才允许。`*.localhost`、其他 `127/8`、IPv4-mapped、NAT64、6to4、Teredo、ULA、链路本地和任何私网地址仍然拒绝。

开关在每次请求开始时读取并形成快照。请求开始后配置变化不改变本次已批准连接；下一次请求使用新值。

## 9. 负载均衡与重试

- 先按现有算法选中 provider，再验证该 provider。
- 安全策略失败时立即结束本次调用，不选择池中下一个 provider。
- URL 无效、HTTP 要求不满足、地址被禁止、DNS 安全失败、响应超限、内容编码异常和响应格式异常均不重试。
- 普通连接失败和超时继续遵守现有请求入口的重试次数与退避策略。
- 每次网络重试都从策略验证开始，重新生成一个独立 `ValidatedOutboundURL`；不得复用过期 DNS 结果，也不得跳过分类。
- 重试始终针对已选中的同一 provider，不扩大为隐式故障转移。
- 只有成功完成的请求才更新现有成功和延迟统计；安全拦截计入错误，不伪装成服务商成功或超时。

## 10. 响应大小与内容编码

采用以下固定上限：

| 响应类型 | 总上限 | 单事件上限 |
|---|---:|---:|
| 普通 AI JSON | 8 MiB | 不适用 |
| Embedding JSON | 16 MiB | 不适用 |
| AI 流式响应 | 16 MiB | 1 MiB |

执行规则：

- `Content-Length` 已超过对应上限时不读取正文，立即关闭。
- 没有 `Content-Length` 时最多读取“上限加 1 字节”，一旦确认超限立即关闭。
- 流式总字节数和单条事件字节数分别计数；任一超限即中止。
- 计数针对客户端实际交给业务解析器的字节。
- 请求头强制 `Accept-Encoding: identity`。
- 响应仍声明非 identity `Content-Encoding` 时，在读取正文前拒绝。
- 非 2xx 响应不读取或记录上游正文，只保留状态类别并返回固定错误。
- JSON 必须是对象；具体 OpenAI、Anthropic、Google 和 Embedding schema 仍由现有业务解析层验证。

## 11. 超时与取消

| 阶段 | 限制 |
|---|---:|
| TCP/TLS 建连 | 10 秒 |
| 请求写入 | 30 秒 |
| 普通读取 | 当前配置值，默认 60 秒 |
| 流式无新内容 | 120 秒 |
| 单次流式总时长 | 10 分钟 |

普通请求仍使用现有 capability 或全局 timeout 作为读取时限，但建连和写入不能放宽上述安全上限。

异步流必须正确处理：

- 正常读完；
- 上游报错；
- 空闲超时；
- 总时限到达；
- 响应超限；
- 调用者提前结束迭代；
- `asyncio.CancelledError`；
- 业务解析器抛错。

所有路径都必须执行同一资源清理契约。取消必须继续向上传播，不能被转换成普通成功或被无限重试。

## 12. 错误契约与日志脱敏

运行时客户端复用现有错误码，不把底层库异常直接暴露给业务层：

- URL/协议/地址/DNS 使用 `OutboundURLPolicy` 的既有错误码；
- 连接、TLS 和底层网络错误映射为 `outbound_connect_failed`；
- 空闲、读取和总时限映射为 `outbound_timeout`；
- 总大小或单事件超限映射为 `outbound_response_too_large`；
- 非 2xx、非 identity 编码、无效 JSON 和无效响应对象映射为 `outbound_bad_response`。

同步和异步非流式入口继续按现有方法签名抛出异常，但异常消息改为固定、可理解的中文提示。流式入口沿用现有 error event 结构，只发送一次固定错误事件，随后关闭流。

日志最多允许：

- 固定错误码；
- provider 类型；
- capability 名；
- 底层异常类别名称；
- 是否处于 sync、async 或 stream 模式。

日志、异常、事件和诊断输出不得包含：

- API key、管理员令牌或 Authorization；
- Google query key 或完整查询参数；
- 完整 URL；
- 请求 headers、body、prompt 或消息；
- 响应正文、流式片段或解析失败原文；
- 含敏感值的底层异常字符串。

## 13. `ModelRouter` 接入范围

以下所有网络入口必须改为统一运行时客户端：

- `invoke`；
- `ainvoke`；
- `astream`；
- `call_capability`；
- `acall_capability`；
- `chat`；
- `astream_capability`。

保留：

- 现有公开方法签名；
- provider 选择与 capability override 优先级；
- OpenAI、Anthropic、Google 请求 body；
- 正常响应解析；
- 并发信号量和排队统计；
- 心跳和流式状态事件；
- timeout/retry 配置；
- provider 延迟统计；
- 本地无凭据时的既有本地逻辑。

实施完成后，`model_router.py` 中不得再存在可以实际发起网络请求的 `httpx.post`、普通 `httpx.AsyncClient` 或其他旁路客户端。可以保留类型导入或兼容壳，但结构测试必须证明所有外连都委托给安全客户端。

## 14. `EmbeddingService` 接入范围

`_request_embedding_chunk` 的每一次尝试都通过同步安全运行时客户端，并使用 Embedding 的 16 MiB 上限。

错误分为两类：

1. **安全错误：** URL、协议、地址、DNS 安全、响应大小、内容编码和响应格式错误。无论 `require_real` 和 `allow_fake_embeddings` 如何设置，都必须抛出，禁止假向量降级。
2. **普通可用性错误：** 允许重试的连接失败和超时。达到现有重试上限后，只有 `require_real=false` 且 `allow_fake_embeddings=true` 时，才能继续使用现有假向量降级。

Embedding 的文本截断、批次大小、并发 worker、指数退避、向量排序和统计保持不变。缓存语义按下节绑定来源、服务商、模型和端点身份。安全错误日志不得包含 URL、key、输入文本、响应数据或底层异常原文。

### 14.1 Embedding v2 缓存来源与端点身份

最终安全复审确认，缓存不能只按 provider 类型和 model 隔离：同一种 provider/model 可以指向不同服务端；远程连接/超时后的假向量也不能伪装成该远程服务的真实结果。因此采用新的 `embedding-cache-v2` 命名空间：

- 真实远程向量的命名空间由版本、来源 `remote`、provider、model 和端点身份组成。端点身份是规范化 base endpoint 的 SHA-256；规范化会统一 scheme/主机大小写、IDNA、默认端口和末尾斜杠，并保留有意义的基础路径。
- 缓存文件名继续只使用完整命名空间与输入文本的 SHA-256。文件名和 metadata 都不得保存原始 endpoint、API key、request target 或其他凭据。
- 本地/未配置服务时生成的确定性假向量使用独立的 `local_fake` v2 命名空间，并按向量维度隔离；它不能与任何远程 provider/model/endpoint 命名空间相交。
- 已配置远程服务在连接失败或超时重试耗尽后产生的 fallback 假向量标记为 `remote_fallback_fake`，逐向量设为不可缓存。混合顺序或并发批次中，只有真实远程结果可写入缓存，结果顺序仍按输入恢复。
- `require_real=true` 只查询当前远程配置对应的 `remote` 命名空间。它不能读取本地假向量，也不能命中曾经由远程故障降级产生的假向量；没有完整远程配置时继续返回既有固定配置错误。
- 磁盘 metadata 必须同时匹配 `source`、完整 `cache_namespace` 和 `endpoint_identity` 才能命中。远程 metadata 记录端点摘要而非原始 endpoint；本地假向量的端点身份必须为空。
- v2 版本进入缓存 key 后，旧版无来源/无端点身份的 key 和 metadata 会自然 miss。旧文件无需危险地批量删除；第一次再次需要对应文本时生成 v2 项，相当于旧缓存一次性失效并自动重建。

一次公开 `embed()` 仍只捕获一份冻结运行时配置。缓存查询、生成、顺序/并发 chunk、缓存写入和 metadata 都使用同一份配置与来源证据，避免刷新期间混入新旧 provider、凭据、端点或缓存命名空间。

## 15. 兼容性与迁移

- 不增加数据库迁移。
- 不改变存档格式。
- 不改变前端 UI 配置 JSON。
- 不要求用户重新填写 provider 或 API key。
- 已保存的本地回环地址继续保留；开关关闭时运行时阻止，开启时允许。
- 公网 provider 必须使用 HTTPS；历史公网 HTTP 配置在第一次实际调用时以固定配置错误失败。
- 现有调用方无需了解安全客户端，也无需修改调用签名。
- 正常 provider 的请求和响应格式保持不变。

## 16. 测试设计

### 16.1 公用传输单元测试

使用假 resolver、假同步/异步 network backend 和可控本地传输，不访问真实公网。至少覆盖：

- 只连接 `resolved_ips` 中的地址；
- mixed DNS answer 全部拒绝；
- 保留 Host、SNI 和证书验证 host；
- 禁止 proxy、redirect 和 Unix socket；
- sync、async 行为一致；
- 多个批准 IP 的受控顺序与失败切换；
- TLS、连接、读取、写入异常脱敏；
- response、stream、client、pool 恰好关闭一次；
- async 取消和调用方提前结束能清理资源。

### 16.2 运行时客户端测试

- 默认禁止本地地址，开关开启仅允许三个精确回环形式；
- `base_url` 含 query/fragment 时继续由 2C-1 策略拒绝；
- 合法 Google 相对 target 保留 base path、编码模型名并发送 query key；
- `//evil.example`、绝对 URL、反斜杠、fragment、控制字符和嵌套 URL target 全部拒绝；
- target 无法改变批准的 host、port、Host header 或 TLS SNI；
- 每次重试重新验证，但只使用本次结果；
- 8 MiB、16 MiB、1 MiB 事件和“上限加 1”边界；
- `Content-Length` 超限时零正文读取；
- 非 2xx 时零正文读取；
- 非 identity 编码时零正文读取；
- 普通、流式、Embedding 超时与总时限；
- 3xx 不跟随；
- 日志和异常哨兵扫描无凭据、query、body 或底层异常文本。

### 16.3 `ModelRouter` 契约测试

每个公开网络入口至少包含正常请求和安全阻止测试，并覆盖：

- 默认 provider；
- capability override；
- provider pool；
- OpenAI、Anthropic、Google；
- 同步、异步和流式；
- 环境变量/旧配置来源；
- 选中 provider 不安全时不切换池成员；
- 正常超时重试仍针对同一 provider；
- 流式错误只发送一次并关闭；
- latency、并发和心跳的既有行为不回归。

增加结构性守卫，禁止 `ModelRouter` 出现新的直接网络旁路。

### 16.4 Embedding 契约测试

- 每个批次通过安全客户端；
- 安全错误不重试为假向量；
- 普通超时保留现有重试；
- 只有原条件满足时才允许普通故障降级；
- 并发批次保持顺序；
- 16 MiB 和 schema 错误受控失败；
- 同一 provider/model 的不同规范化 endpoint 使用不同 v2 cache namespace；
- 远程 fallback 假向量不写入内存或磁盘缓存，也不能满足后续 `require_real=true`；
- local fake、remote real 和 remote fallback fake 的来源隔离；
- 成功远程结果仍可缓存并满足同一端点后续的 `require_real=true`；
- metadata 来源、namespace 和 endpoint SHA-256 必须严格匹配，且不含原始 endpoint 或 API key；
- 旧版缓存自然 miss，并由 v2 缓存按需重建；
- 日志不包含 key、URL、输入文本或响应正文。

增加结构性守卫，禁止 `EmbeddingService` 继续直接调用普通 `httpx.post`。

### 16.5 完整门禁

- 后端全量 pytest；
- fresh-process 插件注册守卫；
- 前端全量 Vitest；
- ESLint 保持 0 error，warning 不超过现有基线；
- TypeScript `--noEmit`；
- Vite production build；
- `git diff --check`；
- 敏感哨兵扫描；
- 完整 Phase 2C 分支审查。

## 17. 实施分解

后续实施计划应拆成四个可独立提交和审查的批次：

1. 提取公用固定目标传输原语，并实现安全运行时客户端。
2. 接入并测试 `ModelRouter` 的全部同步、异步和流式入口。
3. 接入并测试 `EmbeddingService`，验证安全错误与普通降级的边界。
4. 更新文档，跑全量门禁并进行完整 Phase 2C 安全审查。

每个批次都必须先写失败测试，再做最小实现；前一批审查通过后才能进入下一批。

## 18. 预计文件范围

精确清单由实施计划核实，但设计允许的最小范围预计包括：

- 新增 `backend/app/security/pinned_transport.py`；
- 新增 `backend/app/security/runtime_http.py`；
- 调整 `backend/app/security/safe_http.py` 复用公用原语；
- 调整 `backend/app/security/__init__.py`；
- 新增安全传输和运行时客户端测试；
- 调整 `backend/app/ai/model_router.py`；
- 新增 `ModelRouter` 运行时安全测试；
- 调整运行时配置注入位置及其测试；
- 调整 `backend/app/services/system/embedding.py`；
- 新增 Embedding 运行时安全测试；
- 更新相关 API/安全文档和 Phase 2C 验证报告。

如实施必须修改此范围之外的业务算法、数据库、存档或前端状态，应暂停并重新确认，而不是自行扩大范围。

## 19. 风险与控制

### 19.1 异步传输实现错误

风险：异步流在取消或提前退出时泄漏连接。

控制：把资源所有权放在安全客户端，针对每条退出路径做恰好一次关闭测试。

### 19.2 DNS 固定与 TLS 语义不一致

风险：连接固定 IP 后错误地用 IP 验证证书。

控制：连接目标使用批准 IP，Host/SNI/证书验证继续使用原始域名，并由低层测试直接断言。

### 19.3 正常长输出被误伤

风险：限制过小会中止合法响应。

控制：普通 JSON 8 MiB、Embedding 16 MiB、流式总计 16 MiB，并保留现有 token 限制和 120 秒空闲时限；这些上限明显高于当前默认 4096 token 输出。

### 19.4 安全错误被既有降级吞掉

风险：Embedding 安全拦截后生成假向量，用户无法发现配置问题。

控制：错误类型明确分为安全与可用性两类，安全错误不进入假向量分支，并用参数化测试覆盖所有配置组合。

### 19.5 重复入口遗漏

风险：`ModelRouter` 某条旧入口继续直接联网。

控制：逐一列出七个入口做契约测试，并加入直接网络调用的结构性守卫。

### 19.6 敏感信息泄露

风险：Google query key、Authorization、prompt 或上游正文进入异常和日志。

控制：底层异常在安全客户端边界转换；哨兵值覆盖 headers、query、body、DNS 和响应；生产代码与文档执行扫描。

### 19.7 相对请求目标逃逸

风险：Google query key 需要出现在实际请求 target 中；如果使用通用 URL 拼接，恶意模型名或 target 可能改变 origin，或把 key 暴露给日志。

控制：地址策略只接收无 query/fragment 的 base URL；target 使用独立严格校验、路径段编码和 `urlencode`；禁止 `urljoin`、绝对 target 与 network-path reference；固定传输再次核对最终 host/port。

## 20. 验收标准

Phase 2C-2 只有在以下条件全部满足时才完成：

1. 七个 `ModelRouter` 网络入口全部通过统一安全客户端。
2. 默认 provider、override、provider pool、环境变量和旧配置没有旁路。
3. Embedding 每个批次通过统一安全客户端。
4. DNS 校验结果真正固定到同步和异步连接。
5. Google query key 只存在于严格同源的相对 target，不能改变已批准 origin，也不能进入日志和错误。
6. proxy、redirect、Unix socket 和非 identity 编码全部阻止。
7. 所有大小、空闲和总时限边界有自动测试。
8. 安全错误不触发 provider 切换或假向量降级。
9. 正常网络错误的现有合法重试和降级保持兼容。
10. 敏感信息不出现在响应、事件、异常、日志和文档中。
11. 现有后端、前端、类型、lint 和 production build 门禁通过。
12. 完整 Phase 2C 提交范围通过独立安全审查，没有未解决的 Critical 或 Important 问题。
13. 分支在完成最终审查前不合并、不发布。

满足全部条件后，Phase 2C 才可以被标记为完整，并进入分支合并选项。
