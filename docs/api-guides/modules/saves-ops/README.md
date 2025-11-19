# Saves & Ops 模块指南

管理存档、加载、删除以及导出/导入相关操作，包含系统管理接口。

## 职责
- 提供 `/saves/*` REST 端点。
- 提供 `/admin/*` 系统管理端点。
- 维护 `save_manager` 的目录结构与 metadata。
- 与历史日志、报告导出联动，确保存档可回溯。

## 依赖
- `backend/app/services/save_manager.py`
- `backend/app/api/admin_routes.py`
- `history_repository`, `export_service`
- 前端 `api.ts`: `listSaves`, `createSave`, `saveGame`, `loadGame`, `deleteSave`, `checkHealth`, `resetWorld`, `simulateTerrain`

## 子文档

| 文档 | 内容 |
| --- | --- |
| [save-lifecycle.md](save-lifecycle.md) | 创建/保存/加载/删除流程 |
| [save-metadata.md](save-metadata.md) | `/saves/list` 返回字段 |
| [admin-ops.md](admin-ops.md) | 重置、健康检查与地形调试 |

维护人：Ops 团队。
