# 压力模板与编排

## `/pressures/templates`
- **Method**: `GET`
- **响应**: `list[PressureTemplate]`
- **实现**: `backend/app/api/routes.py:465`
- **来源**: `PressureEscalationService`, `services/pressure.py`

## 模型与配置
- `PressureTemplate`: `name`, `description`, `effects`, `recommended_duration`
- 与 `PROMPT_TEMPLATES['pressure_escalation']` 相关，ModelRouter 会注入提示词。

## 典型流程
1. 前端请求模板并展示在压力选择器中。
2. 用户选择模板 → 组装 `PressureDraft` → `queue/add`。
3. `PressureEscalationService` 在模拟时解析各 effect。

## AI 交互
- 模板描述用于 AI 文本生成，位于 `backend/app/ai/prompts.py`。
- 如需调整 AI 供应商，在 `config.py` 中修改 `settings` 并更新文档。

## 前端
- `frontend/src/services/api.ts`：`fetchPressureTemplates`。
- UI：压力面板组件。

## 注意
- 文档需同步 effect 字段定义（例如 `habitat_shift`, `population_delta`）。
- 对外暴露的模板请在附录中列出 JSON 示例（TODO）。
