# AI Routing & 连接测试

## ModelRouter
- **文件**: `backend/app/ai/model_router.py`
- **用途**: 根据 capability 选择具体提供商/模型，并允许覆盖。
- **配置来源**: `config.py` 的 `settings`、`/config/test-api` 动态测试。

### 常见 capability
| 名称 | 默认 provider/model | 使用位置 |
| --- | --- | --- |
| `turn_report` | local/template-narrator | `ReportBuilder` |
| `speciation` | openai/gpt-4o-mini | `SpeciationService` |
| `terrain_evolution` | openai/gpt-4o | `TerrainEvolutionService` |

## `/config/test-api`
- **Method**: `POST`
- **实现**: `routes.py:715`
- **payload**:
  ```json
  { "type": "chat" | "embedding", "base_url": "...", "api_key": "...", "model": "..." }
  ```
- **流程**:
  1. 拼接 URL (`/chat/completions` 或 `/embeddings`).
  2. 发送 httpx 请求，捕获响应。
  3. 返回 `{ success, message, details }`。
- **前端**: `testApiConnection`（api.ts），显示在“AI 设置”页面。

## 运维指南
- 若需更换默认模型，请更新 `settings.ai_*` 并在此文件记录变更。
- 为确保安全，不要在日志中打印完整 API Key，仅保留前缀。
