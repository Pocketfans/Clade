# UI 配置 – `/config/ui`

- **GET `/api/config/ui`**：读取 `data/settings.json`（默认路径可在 `.env` 中通过 `UI_CONFIG_PATH` 覆盖），并返回脱敏后的配置。
- **POST `/api/config/ui`**：接收完整配置更新，原子写入设置文件，使配置缓存失效，并应用现有运行时配置刷新流程。
- **模型定义**：`backend/app/models/config.py#UIConfig`
- **路由实现**：`backend/app/api/analytics.py#update_ui_config`

## 字段结构

下面只展示与 AI 服务商和路由相关的主要字段；实际 `UIConfig` 还包含其他模拟设置。

```json
{
  "providers": {
    "default": {
      "id": "default",
      "name": "OpenAI Proxy",
      "type": "openai",
      "provider_type": "openai",
      "base_url": "https://api.example.com/v1",
      "api_key": "",
      "models": ["example-model"]
    }
  },
  "default_provider_id": "default",
  "default_model": "example-model",
  "ai_concurrency_limit": 15,
  "allow_local_ai_endpoints": false,
  "capability_routes": {
    "speciation": {
      "provider_id": "default",
      "model": "example-model",
      "timeout": 60,
      "enable_thinking": false
    }
  },
  "embedding_provider_id": "default",
  "embedding_model": "example-embedding-model",
  "ai_provider": null,
  "capability_configs": null
}
```

### 关键字段

- `providers`：`ProviderConfig` 字典。新增服务商时应生成唯一 `id`，前端用它引用服务商。
- `default_provider_id` / `default_model`：全局默认服务商和模型；能力路由没有单独指定时使用。
- `ai_concurrency_limit`：AI 并发限制，默认 15。
- `allow_local_ai_endpoints`：是否允许配置探测访问当前电脑上的精确回环 AI 服务，默认 `false`。旧配置缺少该字段时也按 `false` 读取。
- `capability_routes`：按能力指定 provider、model、timeout 等设置。能力自己的 `timeout` 会覆盖全局 AI 超时，但不会改变下述普通请求与流式请求的计时语义。
- `embedding_provider_id` / `embedding_model`：Embedding 的现有默认设置。
- Legacy 字段（`ai_provider`、`ai_model`、`ai_base_url`、`ai_api_key`、`capability_configs` 等）仍被接受，并由现有流程迁移到新结构。

## AI 超时语义

- 对普通 AI 请求，`timeout` 是从逻辑入口到完整结果的端到端总时限。请求准备、并发排队、URL 与 DNS 校验、连接、读写、解析、重试退避和后续尝试共享这一份时间，不会在每个阶段或每次重试时重新计时。
- 对流式 AI 请求，`timeout` 是等待下一段非空真实 AI 内容的最长时间。并发排队到首段内容也属于第一次等待；状态事件、心跳、空行和协议事件不会延长等待时间。
- 每条流式请求从逻辑入口开始最多运行 600 秒（10 分钟），排队时间包含在内，持续输出也不会重置这个总上限。
- 已经显示部分内容后发生中断时，界面保留已显示文字并给出备用结果警告；残缺文字不会保存或解析为完整业务结果，报告和结构化分析会使用现有的完整规则备用结果。
- 用户主动取消会继续按“取消”处理，不计为超时，不触发普通重试，也不会冒充“AI 生成中断”。

## 更新请求与敏感字段

POST 请求体使用包装结构：

```json
{
  "config": {
    "providers": {},
    "allow_local_ai_endpoints": false
  },
  "clear_provider_api_keys": []
}
```

`config` 是完整的 `UIConfig`；`clear_provider_api_keys` 明确列出需要清除 API Key 的服务商。没有明确清除时，空的 API Key 字段会保留服务端已有密钥。GET 和 POST 响应不会回显保存的 API Key，只返回空值及相应的 `*_configured` 状态。

管理员令牌永远不是 JSON 的一部分。只有当 `allow_local_ai_endpoints` 与当前已保存值不同时，调用方才在同一个 POST 请求的 `X-Clade-Admin-Token` 请求头中提供令牌。普通配置保存且开关未变化时，不需要该请求头。

## 本地 AI 开关

- 从关闭改为开启、从开启改为关闭，两个方向都必须验证管理员令牌。
- 服务端没有配置 `CLADE_ADMIN_TOKEN` 时返回 HTTP 503 与 `admin_token_unconfigured`；令牌缺失或错误时返回 HTTP 403 与 `admin_token_invalid`。
- 验证发生在密钥合并、文件写入、缓存失效和运行时刷新之前。验证失败时，整个配置更新都不会保存或应用。
- 验证成功后，`allow_local_ai_endpoints` 与同一次请求中的其他配置一起原子保存：全部成功或全部失败，不存在单独写开关的竞争路径。
- 保存成功后，下一次配置探测立即读取新值，无需重启。
- 已保存的本地 Base URL 和模型配置在开关关闭时仍会保留并显示，不会被迁移或删除；但探测请求会以 `local_ai_disabled` 阻止访问。
- 即使开关开启，也只允许规范化后的 `localhost`、字面量 `127.0.0.1` 和 `::1`。家庭局域网、其他私网地址和其他回环地址始终被阻止。

管理员令牌只通过请求头短暂传输。设置界面将它保存在局部内存，并在请求结束、取消或关闭设置抽屉时清除；它不会进入设置文件、配置对象、URL、浏览器存储、全局前端状态、响应或日志。

## 存储与热更新

配置保存继续使用同一个更新锁和 `EnvironmentRepository.save_ui_config()` 原子写入路径。保存成功后使配置缓存失效，并执行现有的 ModelRouter、Embedding 和模拟配置刷新流程。

运行时 AI、流式请求和 Embedding 都沿用相同的出站安全边界。配置刷新不会改变已开始请求的不可变快照；后续请求才会使用新配置。

## 前端

- `frontend/src/services/api/config.ts`：`fetchUIConfig`、`updateUIConfig`、`testApiConnection`、`fetchModels`
- `frontend/src/components/SettingsDrawer/SettingsPanel.tsx`：配置表单与管理员令牌的局部生命周期
- `frontend/src/components/SettingsDrawer/sections/LocalAIEndpointControl.tsx`：本地 AI 开关、风险说明和管理员令牌输入

## 校验规则

- Pydantic `extra="ignore"`：未知字段会被忽略，但前端仍应与 schema 保持同步。
- POST 请求不是 JSON 对象、媒体类型不正确或配置模型校验失败时，返回 `422 Unprocessable Entity`，且不会回显原始请求内容。
- 本地 AI 开关未变化时，保存行为与原有普通配置保存保持一致。
