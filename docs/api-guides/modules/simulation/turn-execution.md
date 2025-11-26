# /turns/run – Turn Execution

- **Method / Path**: `POST /api/turns/run`
- **实现**: `backend/app/api/routes.py` → `SimulationEngine.run_turns_async`
- **请求模型**: `TurnCommand`
- **响应模型**: `list[TurnReport]`

## 请求体

```json
{
  "rounds": 1,
  "pressures": [
    {
      "kind": "volcanic_eruption",
      "intensity": 7,
      "target_region": [32, 10],
      "radius": 4,
      "label": "极昼火山链",
      "narrative_note": "点燃极昼群岛的火山带"
    }
  ],
  "auto_reports": true
}
```

- `rounds`：执行的回合数，`1 ≤ rounds ≤ 100`。路由会在运行后递减排队计数。
- `pressures`：`PressureConfig[]`。每个元素字段如下：
  - `kind`：枚举值，等同 `/pressures/templates` 的 `kind`。
  - `intensity`：1–10。
  - `target_region`：`[x, y]`，对局部事件选填。
  - `radius`：影响范围（可选，≥1）。
  - `label` / `narrative_note`：供日志与 Prompt 使用的描述。
- `auto_reports`：预留字段，当前默认为 `true`。如设为 `false`，仍会生成 `TurnReport`，但前端可据此决定是否保存。

若 `pressures` 为空且 `pressure_queue` 中仍有排队批次，路由会自动提取队首批次并同步更新 `ActionQueueStatus`。

## 执行流程（精简版）

1. **压力解析**：`EnvironmentSystem.parse_pressures` 将 `PressureConfig` 转为模拟内部结构，并交给 `PressureEscalationService` 记录重大事件。
2. **环境更新**：`MapEvolutionService` 根据压力和板块阶段修改 `MapState`，并派生海平面/温度变化（AI 地形模块已退役）。
3. **物种处理**：`SpeciesTieringService` 根据 watchlist/人口分层；`MortalityEngine` 分别对 critical/focus/background 计算死亡率；`ReproductionService`、`AdaptationService`、`GeneActivationService`、`GeneFlowService` 依序应用种群更新与缓慢演化。
4. **分化与迁徙**：`SpeciationService.process_async`、`MigrationAdvisor.plan`、`BackgroundSpeciesManager` 负责分化、迁徙建议与背景物种晋升。
5. **报告生成**：`ReportBuilder`（通过 `ModelRouter`）组装 `TurnReport`，并由 `ExportService` 写入 `data/reports` / `data/exports`。
6. **快照与历史**：`MapStateManager.snapshot_habitats` 更新空间分布，随后 `history_repository.log_turn` 持久化。

## 前端调用

- 函数：`frontend/src/services/api.ts#runTurn`（当前仍固定 `rounds=1`，后续可扩展）。
- 典型 UI：`ControlPanel`/`TurnProgressOverlay` 触发，`HistoryTimeline` / `TurnReportPanel` 消费响应。

## 错误处理

- `500 Internal Server Error`：模拟异常，`detail` 字段包含异常摘要；日志关键字 `[推演错误]`。
- `404`：仅当内部读取线索失败（极少出现）。
- 建议前端捕获消息并提示“推演执行失败：{detail}”，同时刷新 `ActionQueueStatus`。

## 示例（curl）

```bash
curl -X POST http://localhost:8000/api/turns/run \
  -H "Content-Type: application/json" \
  -d '{"rounds": 2, "pressures": [{"kind":"drought_period","intensity":6}]}'
```
