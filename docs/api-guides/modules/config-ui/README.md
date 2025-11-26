# Config & UI 模块指南

关注多服务商 AI 配置、能力路由与连通性测试。

## 职责

- `/config/ui`：读写 `UIConfig`，用于配置 Provider 库、capability 路由、并发限制等。
- `/config/test-api`：即时检测第三方 chat / embedding API，可在 Settings UI 中使用。
- 协调前端设置面板与后端 `ModelRouter` 覆盖逻辑。

## 依赖

- `backend/app/models/config.py#UIConfig`
- `backend/app/api/routes.py` 中的 `get_ui_config`, `update_ui_config`, `test_api_connection`
- `frontend/src/services/api.ts`：`fetchUIConfig`, `updateUIConfig`, `testApiConnection`

## 子文档

| 文档 | 内容 |
| --- | --- |
| [ui-config.md](ui-config.md) | `UIConfig` 模型 & `/config/ui` 行为 |
| [api-connectivity.md](api-connectivity.md) | `/config/test-api` 请求/响应与安全注意 |

维护人：Frontend Platform。
