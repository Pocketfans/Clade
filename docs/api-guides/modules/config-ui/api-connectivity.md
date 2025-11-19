# AI 接入连通性 – `/config/test-api`

> 该端点同时记录在 Analytics & AI 模块；此处强调其与 UI 配置的关系。

- **Method**: `POST`
- **实现**: `routes.py:715`
- **请求**:
  ```json
  {
    "type": "chat",            // 或 "embedding"
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "gpt-4o-mini",
    "provider": "openai"
  }
  ```
- **响应**:
  ```json
  { "success": true, "message": "Chat completion ok", "details": "latency: 1.2s" }
  ```

## 作用
- 在 UI 设置界面中，用户可测试第三方 AI 服务连通性。
- 若成功，可将参数写入 `UIConfig.ai_overrides`，以便后端覆盖默认路由。

## 安全
- 不在日志中打印完整 key；仅保留前 4 位。
- 若需要代理，请在 `settings.ai_base_url` 配置。

## 前端
- `testApiConnection` 函数。
- UI：`frontend/src/ui/AISettings.tsx`（待实现）。
