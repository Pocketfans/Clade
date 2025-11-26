# AI 接入连通性 – `/config/test-api`

> 同步记录在 Analytics & AI 模块，此处强调与 UI 配置的联动。

- **Method**: `POST /api/config/test-api`
- **实现**: `backend/app/api/routes.py#test_api_connection`

## 请求体

```json
{
  "type": "chat",           // "chat" 或 "embedding"
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-xxxx",
  "model": "gpt-4o-mini",
  "provider": "openai"      // 可选，当前仅用于提示
}
```

`type=chat`：路由会自动补全 `/chat/completions`，兼容以下情况：
- Base URL 已以 `/v1` 结尾：直接拼接 `/chat/completions`
- Azure OpenAI：若 URL 已包含 `chat/completions` 则不会重复追加

`type=embedding`：调用 `{base_url}/embeddings`。

## 响应

```json
{
  "success": true,
  "message": "✅ API 连接成功！",
  "details": "模型：gpt-4o-mini | 响应时间：0.42s"
}
```

- 失败时 `success=false`，`message` 包含图标 + 错误类型（HTTP、超时等），`details` 包含返回的部分报文。
- `httpx.TimeoutException`、`HTTPStatusError`、JSON 解析错误都会被捕获并转化为易读信息。

## 作用

- Settings Drawer 可先调用该接口验证第三方配置，再将成功的 base_url/api_key 写入 `UIConfig.providers`。
- 可用于快速测试不同 provider（DeepSeek、SiliconFlow、自建代理等）的可访问性与响应时间。

## 安全

- 后端日志不会打印完整 `api_key`。
- 建议在前端只保存必要信息；成功后立刻调用 `/config/ui` 写入，避免将 key 存在浏览器本地。

## 前端

- `frontend/src/services/api.ts#testApiConnection`
- `SettingsDrawer` 在“AI 服务”标签页中使用，验证成功后可以提示“写入路由表”。
