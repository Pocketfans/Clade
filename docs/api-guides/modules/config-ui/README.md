# Config & UI 模块指南

集中记录 UI 配置、主题、以及 AI 接入设置端点。

## 职责
- 提供 `/config/ui` 对前端可视化选项进行读取/存储。
- 暴露 `/config/test-api`（与 Analytics 模块共享，用于 AI 诊断）。
- 描述 UI 配置模型 `UIConfig` 与前端状态管理方式。

## 依赖
- `backend/app/models/config.py#UIConfig`
- `backend/app/api/routes.py:453-459`
- 前端：`fetchUIConfig`, `updateUIConfig`, `testApiConnection`

## 子文档

| 文档 | 内容 |
| --- | --- |
| [ui-config.md](ui-config.md) | `/config/ui` 端点 |
| [api-connectivity.md](api-connectivity.md) | `/config/test-api`、AI 设置 |

维护人：Frontend Platform。
