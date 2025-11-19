# /turns/run – Turn Execution

- **Method/Path**: `POST /api/turns/run`
- **后端实现**: `backend/app/api/routes.py:240`
- **请求模型**: `TurnCommand` (`backend/app/schemas/requests.py`)
- **响应模型**: `list[TurnReport]` (`backend/app/schemas/responses.py`)

## 请求体

```json
{
  "rounds": 1,
  "pressures": [PressureDraft]
}
```
- `rounds`：默认 1，最大值由 `settings.batch_rule_limit` 控制。
- `pressures`：可选数组，结构参考 `/pressures/templates` 输出。

## 执行流程

1. 路由解析请求，校验 `TurnCommand`。
2. `SimulationEngine` 根据 `EnvironmentSystem` 状态迭代执行。
3. `ReportBuilder` 通过 `ModelRouter` 生成叙述，合并 `TurnReport`。
4. 结果写入 `history_repository` 并返回。

## 前端调用

- 函数：`frontend/src/services/api.ts` 中 `runTurn`。
- UI：`frontend/src/components/ControlPanel/*`（触发按钮），`frontend/src/components/HistoryPanel/*`（消费响应）。

## 错误与重试

- 429（预留）：排队过多。
- 500：`SimulationEngine` 异常，日志关键字 `[turns/run]`。
- 前端需捕获错误信息并弹出通知，建议至少显示 `detail`。

## 示例（curl）

```bash
curl -X POST http://localhost:8000/api/turns/run \
  -H "Content-Type: application/json" \
  -d '{"rounds": 1, "pressures": []}'
```
