# UI 配置 – `/config/ui`

- **GET /api/config/ui**：读取 `data/settings.json`（默认路径可在 `.env` 中通过 `UI_CONFIG_PATH` 覆盖）。
- **POST /api/config/ui`**：写入 `UIConfig`，并立即调用 `apply_ui_config` 让 `ModelRouter`/`EmbeddingService` 使用最新设置。
- **模型定义**：`backend/app/models/config.py#UIConfig`

## 字段结构

```json
{
  "providers": {
    "default": {
      "id": "default",
      "name": "OpenAI Proxy",
      "type": "openai",
      "base_url": "https://api.openai.com/v1",
      "api_key": "sk-***",
      "models": ["gpt-4o-mini", "gpt-4o"]
    }
  },
  "default_provider_id": "default",
  "default_model": "gpt-4o-mini",
  "ai_concurrency_limit": 15,
  "capability_routes": {
    "speciation": {
      "provider_id": "default",
      "model": "gpt-4o-mini",
      "timeout": 60,
      "enable_thinking": false
    }
  },
  "embedding_provider_id": "default",
  "embedding_model": "text-embedding-3-large",
  "ai_provider": null,      // legacy 字段，自动迁移
  "capability_configs": null
}
```

### 关键部分

- `providers`: ProviderConfig 字典。新增服务商时请生成唯一 `id`，前端以此引用。
- `default_provider_id`/`default_model`: ModelRouter 的全局默认值，当 `capability_routes` 未指定 provider 时使用。
- `ai_concurrency_limit`: 影响 ModelRouter semaphore（默认 15）。
- `capability_routes`: 细化到某一能力的 provider/model/timeout 配置。
- `embedding_provider_id` & `embedding_model`: `EmbeddingService` 默认值。
- Legacy 字段 (`ai_provider`, `ai_model`, `ai_base_url`, `ai_api_key`, `capability_configs` 等) 仍被接受，`apply_ui_config` 会在运行时迁移到新结构。

## 存储与热更新

- 文件格式为 JSON，POST 成功后立即覆盖旧文件。
- `apply_ui_config` 会：
  1. 检测旧字段并创建默认 Provider。
  2. 调用 `ModelRouter.set_concurrency_limit`。
  3. 根据 `capability_routes` 设置 overrides（base_url/API Key 优先使用 provider 设置）。

## 前端

- `frontend/src/services/api.ts#fetchUIConfig`, `updateUIConfig`
- `SettingsDrawer`（`frontend/src/components/SettingsDrawer.tsx`）提供 UI 以增删 Provider、配置 capability 路由、校验并发限制。

## 校验规则

- Pydantic `extra="ignore"`：未知字段会被忽略，但建议前端保持 schema 同步。
- 若 `providers` 为空且仍提供 `ai_api_key`，后端会自动创建一个临时 Provider 并写回。
- POST 请求失败时返回 `422 Unprocessable Entity`，请将 `detail` 展示给用户。
