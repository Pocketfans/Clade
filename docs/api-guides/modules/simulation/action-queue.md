# 行动队列 – /queue 系列

- `GET /api/queue` → 返回 `ActionQueueStatus`
- `POST /api/queue/add` → 接受 `QueueRequest`
- `POST /api/queue/clear` → 清空队列

## 数据模型

- `QueueRequest`：`pressures: PressureDraft[]`, `rounds: int`
- `ActionQueueStatus`：`pending_rounds`, `pressures`, `last_updated`

## 流程

1. `queue/add` 校验 pressures，推入后台行动列表。
2. `queue` 查询当前待执行批次、正在运行的 round。
3. `queue/clear` 清理内存结构并记录日志。

## 服务依赖

- `PressureEscalationService`：处理压力叠加。
- `FocusBatchProcessor`：批量处理焦点物种。
- `ReportBuilder`：如果存在排队任务，完成后产出报告。

## 前端

- `frontend/src/services/api.ts`：`fetchQueueStatus`, `addQueue`, `clearQueue`。
- UI：Queue 面板、回合控制组件（`frontend/src/components/QueuePanel.tsx`）。

## 注意

- 避免 rounds=0，路由已校验但文档强调。
- 若 `Pressures` 过多导致性能问题，返回 400 并在 detail 中提示。
