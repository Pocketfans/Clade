# AI Routing & 连接测试

## ModelRouter 概览

- **实现**: `backend/app/ai/model_router.py`
- **职责**: 基于 capability（如 `turn_report`, `speciation`）选择对应的 provider/model，并支持运行时覆盖。
- **默认配置**: 在 `backend/app/api/routes.py` 初始化

| Capability | Provider / Model | 用途 |
| --- | --- | --- |
| `turn_report` | `local / template-narrator` | `ReportBuilder` 生成回合叙事 |
| `focus_batch` | `local / focus-template` | `FocusBatchProcessor` AI 增润 |
| `critical_detail` | `local / critical-template` | `CriticalAnalyzer` |
| `speciation` | `openai / gpt-4o-mini` | `SpeciationService.process_async` |
| `species_generation` | `openai / gpt-4o-mini` | `/species/generate` |
| `pressure_escalation`, `migration`, `reemergence` | `local` 模板 | 对应服务 |

`PROMPT_TEMPLATES` 会为每个 capability 注册系统 Prompt，如需新增能力请同时更新 `PROMPT_TEMPLATES` 与 ModelRouter 路由表。

## UI 配置如何影响 ModelRouter

`/api/config/ui` 写入的 `UIConfig` 会在 `apply_ui_config` 中：

1. 将旧版 `ai_provider`/`ai_model` 迁移到 `providers` + `capability_routes`。
2. 更新 `model_router.api_base_url`、`api_key` 以及并发限制（`ai_concurrency_limit`）。
3. 对每个 `capability` 设置覆盖（provider_id、model、timeout 等）。

因此修改 UI 设置后无需重启即可生效。

## `/config/test-api`

- **Method**: `POST /api/config/test-api`
- **payload**:

```json
{
  "type": "chat",          // 或 "embedding"
  "base_url": "https://api.example.com/v1",
  "api_key": "sk-xxxx",
  "model": "deepseek-v3"
}
```

- **实现**: `routes.py#test_api_connection`
  - `type=embedding` → 发送 `POST {base_url}/embeddings`
  - `type=chat` → 自动补全 `/chat/completions`（兼容 Azure/OpenAI 风格）
  - 捕获 `httpx` 状态码并返回 `{ success, message, details }`

## 前端集成

- `frontend/src/services/api.ts#testApiConnection`
- `SettingsDrawer` 使用该函数测试第三方 API，成功后可将信息写入 `UIConfig.providers`。

## 运维提示

- 日志中不会打印完整 API Key，仅输出前缀。
- 若更换默认 provider，请同步更新 `docs/api-guides/modules/config-ui/ui-config.md`，并考虑在 `.env` 设置 `AI_BASE_URL`/`AI_API_KEY` 以提供全局默认值。
