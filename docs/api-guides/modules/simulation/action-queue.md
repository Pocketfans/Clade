# 行动队列 – `/queue*`

| Method | Path | 描述 |
| --- | --- | --- |
| `GET` | `/api/queue` | 返回当前排队状态 |
| `POST` | `/api/queue/add` | 追加 `QueueRequest` |
| `POST` | `/api/queue/clear` | 清空队列并重置计数 |

## 数据模型

- `QueueRequest`
  - `pressures: PressureConfig[]`（与 `TurnCommand.pressures` 相同字段）
  - `rounds: int`，`1 ≤ rounds ≤ 20`
- `ActionQueueStatus`
  - `queued_rounds: int`：尚待执行的批次数
  - `running: bool`：`/turns/run` 是否正在处理
  - `queue_preview: string[]`：对每个批次的快速标签，例如 `["自然演化", "drought_period+predator_rise"]`

## 工作机制

1. `/queue/add` 将 `rounds` 次复制的压力批次推入 `pressure_queue`。路由会即时刷新 `queue_preview`，便于前端展示。
2. `/turns/run` 在接收到空的 `pressures` 参数时，会自动 pop 队首批次并递减 `queued_rounds`。
3. `/queue/clear` 清空 `pressure_queue` 并将 `queued_rounds` 置 0，不会终止当前正在执行的回合。
4. 所有队列数据存活于 FastAPI 进程内存；若需跨进程/重启保留，应扩展为持久化存储（TODO）。

## 关联服务

- `SimulationEngine.run_turns_async`：执行实际回合。
- `PressureEscalationService`：在批处理时统计高压事件。
- `Watchlist` & `SpeciesTieringService`：路由在进入引擎前会同步最新 watchlist。

## 前端

- `frontend/src/services/api.ts`：`fetchQueueStatus`, `addQueue`, `clearQueue`。
- UI：Queue/Control Panel（位于 `frontend/src/components/ControlPanel.tsx` 及相关浮层）。

## 注意事项

- 同一个批次内可提供多个压力，队列预览以 `+` 连接。
- 当 `queued_rounds` 很大时（>20），前端应提示用户分批执行，避免长时间占用 AI/IO。
- API 层只做轻量校验；若提供未知 `kind`，`EnvironmentSystem.parse_pressures` 会抛出 400。
