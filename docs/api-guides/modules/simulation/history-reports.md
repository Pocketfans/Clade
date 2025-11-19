# 历史与报告 – /history, /exports

## `/history`
- **Method**: `GET`
- **Path**: `/api/history?limit=<int>`
- **响应**: `list[TurnReport]`
- **实现**: `backend/app/api/routes.py:419`
- **数据来源**: `history_repository.list_turns`

### 用途
- 前端历史面板（`HistoryPanel`）读取最近 N 条记录。
- 存档流程会使用最新 turn_index。

## `/exports`
- **Method**: `GET`
- **响应**: `list[ExportRecord]`
- **实现**: `routes.py:425`, `services/exporter.py`
- **数据**: 读取 `reports_dir` / `exports_dir` 的生成文件

### 交互
1. 用户在前端触发“导出”，后台 `ExportService` 写入文件。
2. `GET /exports` 返回 metadata（文件名、类型、创建时间）。
3. 前端展示下载列表，实际下载走静态文件路由。

## 日志
- 成功：`[report] exported ...`
- 异常：`HTTPException` with detail。

## 前端函数
- `fetchHistory(limit)`
- `fetchExports()`

## 待办
- 需要为 `/exports/{id}` 单独写文档（若后续开放下载 API）。
