# 压力模板与编排

## `/pressures/templates`

- **Method**: `GET /api/pressures/templates`
- **实现**: `backend/app/api/routes.py#list_pressure_templates`
- **数据来源**: `routes.py` 中的常量 `pressure_templates`（`PressureTemplate(kind, label, description)` 列表）

示例返回：

```json
{
  "kind": "glacial_period",
  "label": "冰河时期",
  "description": "气温下降，冰川扩张……"
}
```

> 目前模板只包含 `kind`, `label`, `description`，具体强度/范围由前端在 `PressureDraft` 中决定。

## 模型

- `PressureTemplate`：供 UI 展示。
- `PressureConfig` / `PressureDraft`（请求体）字段：
  - `kind`: 与模板 `kind` 对应。
  - `intensity`: 1–10。
  - `target_region`: `[x, y]`（可选）。
  - `radius`: 区域半径（可选，≥1）。
  - `label`: 自定义标题。
  - `narrative_note`: 会写入 `ReportBuilder` 的 AI 提示。

## 执行链路

1. 前端调用 `fetchPressureTemplates` 渲染列表。
2. 用户选择模板并补充 `intensity`、区域等信息得到 `PressureDraft`。
3. `/turns/run` 或 `/queue/add` 接收到 `PressureConfig` 后，`EnvironmentSystem.parse_pressures` 会转换为内部枚举结构，`PressureEscalationService` 则追踪“重大事件”窗口（默认窗口 `minor_pressure_window=10`，阈值 `escalation_threshold=80`）。
4. AI 叙事：`PROMPT_TEMPLATES['pressure_escalation']` 会注入模板描述和 `narrative_note`，用于战报与迁徙建议。

## 前端

- 数据源：`frontend/src/services/api.ts#fetchPressureTemplates`
- 典型 UI：`PressureModal` / `ControlPanel`。
- 建议在 UI 中同时展示 `label` 与 `description`，并允许自定义 `narrative_note` 以获得更细致的 AI 报告。

## 注意

- 模板列表静态保存在后端，若要扩展请直接修改 `routes.py` 中的 `pressure_templates` 常量并补充描述。
- 如果需要额外字段（例如 `recommended_intensity`），需要同步更新 `schemas/responses.PressureTemplate` 与前端 `api.types.ts`。
