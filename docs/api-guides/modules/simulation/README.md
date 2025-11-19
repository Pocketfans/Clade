# Simulation 模块指南

负责调度单回合运行、压力模板、行动队列及历史报告。

## 职责

1. 组装压力并触发 `SimulationEngine`，生成 `TurnReport`。
2. 维护 `/queue` 系列接口，控制批量执行计划。
3. 暴露历史、导出数据供前端展示。
4. 为 AI 模型提供必要上下文（压力描述、环境状态）。

## 关键依赖

- `backend/app/api/routes.py:240-482` – turn/queue 相关端点
- `backend/app/services/pressure.py`, `map_manager.py`, `report_builder.py`
- `backend/app/simulation/engine.py`, `simulation/environment.py`
- 前端服务：`frontend/src/services/api.ts` 中 `runTurn`, `addQueue`, `clearQueue`, `fetchHistory`, `fetchPressureTemplates`

## 接口矩阵

| Endpoint | 描述 | Schema | 前端函数 |
| --- | --- | --- | --- |
| `POST /turns/run` | 执行 1+ 回合 | `TurnCommand`, `TurnReport[]` | `runTurn` |
| `GET /queue` | 查看行动队列 | `ActionQueueStatus` | `fetchQueueStatus` |
| `POST /queue/add` | 添加压力批次 | `QueueRequest`, `ActionQueueStatus` | `addQueue` |
| `POST /queue/clear` | 清空队列 | `ActionQueueStatus` | `clearQueue` |
| `GET /history` | 查询最近回合 | `TurnReport[]` | `fetchHistory` |
| `GET /exports` | 列出导出文件 | `ExportRecord[]` | `fetchExports` |
| `GET /pressures/templates` | 压力模板列表 | `PressureTemplate[]` | `fetchPressureTemplates` |

## 子文档

| 文档 | 内容 |
| --- | --- |
| [turn-execution.md](turn-execution.md) | `/turns/run` 请求/响应、服务流转 |
| [action-queue.md](action-queue.md) | `/queue` 系列端点、状态图 |
| [history-reports.md](history-reports.md) | `/history`、`/exports`、ReportBuilder |
| [pressure-orchestration.md](pressure-orchestration.md) | 压力模板、AI Prompt 管理 |

维护人：Simulation 小组。
