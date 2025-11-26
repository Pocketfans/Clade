# 术语表（Glossary）

| 术语 | 说明 | 参考 |
| --- | --- | --- |
| Turn | 一次完整的模拟回合，包含压力、规则运算、报告生成 | `backend/app/simulation/engine.py` |
| Pressure | 场景压力配置，影响环境与物种 | `backend/app/schemas/requests.py#PressureConfig` |
| Action Queue | 待执行的压力批次及其 `queue_preview` | `/queue` 端点 |
| Species Tier | 物种等级（critical/focus/background） | `services/tiering.py` |
| Lineage Code | 物种谱系唯一标识 | `schemas/responses.py#SpeciesDetail` |
| Map Overview | 六边形地图、栖息地、河流、植被的聚合视图 | `/map` 端点 |
| Save Slot | `SaveManager` 管理的存档目录 | `/saves/*` |
| ModelRouter | 对接多种 AI 模型/供应商的路由器 | `backend/app/ai/model_router.py` |
| UIConfig | 多 provider AI 配置、能力路由与并发限制 | `/config/ui`, `backend/app/models/config.py` |
| Frontend Service Layer | `frontend/src/services/api.ts` 中封装的 fetch 函数集合 | `modules/frontend-integration/services-layer.md` |

> 如新增核心术语，请在这里补充并保持与 `api.types.ts`、`schemas/*` 中命名一致。
