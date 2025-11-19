# UI 配置 – `/config/ui`

- **GET /api/config/ui**：返回 `UIConfig`。
- **POST /api/config/ui**：写入新的配置。
- **实现**: `backend/app/api/routes.py:453-459`
- **模型**: `backend/app/models/config.py#UIConfig`

## 字段示例
```json
{
  "theme": "dark",
  "map": { "default_view": "terrain" },
  "panels": { "species": true, "history": true },
  "ai_overrides": { "speciation": "gpt-4o-mini" }
}
```

## 存储
- 使用 `UIConfig` 模型序列化为 JSON 文件（位于 settings 指定目录）。
- POST 会验证 schema 并立即返回最新配置。

## 前端
- `fetchUIConfig` 在应用初始化时调用。
- `updateUIConfig` 用于设置面板（`frontend/src/ui/ConfigPanel.tsx`）。

## 校验
- 未提供必填值时返回 400，detail 由 Pydantic 生成。
