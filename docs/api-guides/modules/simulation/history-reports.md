# 历史与报告 – `/history`, `/exports`

## `/history`

- **Method**: `GET /api/history?limit=<int>`
- **默认参数**: `limit=10`（无分页，按 `turn_index` 倒序）
- **响应**: `list[TurnReport]`，直接从 `TurnLog.record_data` 还原
- **实现**: `backend/app/api/routes.py#list_history` → `history_repository.list_turns`

`TurnReport` 字段完全等同模拟输出：`species`、`branching_events`、`map_changes`、`sea_level` 等。前端常见用法：

- `HistoryTimeline` / `TurnReportPanel`：展示叙事文本与关键事件。
- 存档：`/saves/save` 在写出游戏状态前会读取最新 `turn_index`。

> **性能提示**：`limit` 不要大于 50——每条报告都包含完整 species snapshot，体积较大。

## `/exports`

- **Method**: `GET /api/exports`
- **响应**: `list[ExportRecord]`
  - `turn_index`: 报告对应回合
  - `markdown_path`, `json_path`: 相对 `data/exports` 的文件路径
- **实现**: `routes.py#list_exports` → `ExportService.list_records`

### 流程

1. 每次 `SimulationEngine` 完成回合后都会调用 `ExportService.export_turn`，生成 `.md` 与 `.json`。
2. `GET /exports` 读取 `data/exports/index.json` 中的缓存列表，按时间倒序返回。
3. 前端在“导出/下载”面板调用 `fetchExports`，用户再通过静态文件服务下载指定路径。

若导出目录缺失或文件损坏，路由会抛出 `500` 并在日志打印 `[report] export failed ...`。

## 前端函数

- `frontend/src/services/api.ts#fetchHistory`
- `frontend/src/services/api.ts#fetchExports`

## TODO

- 若未来提供 `/exports/{turn_index}` 直接下载接口，需另起文档说明鉴权与 Content-Type。
