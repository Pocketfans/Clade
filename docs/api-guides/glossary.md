# 术语表（Glossary）

| 术语 | 说明 | 参考 |
| --- | --- | --- |
| Turn | 一次完整的模拟回合，包含压力应用、物种演化、报告生成 | `backend/app/simulation/engine.py` |
| Pressure | 场景压力配置，影响物种行为 | `backend/app/services/pressure.py` |
| Queue | 待执行的回合批次及压力列表 | `/queue` 端点 |
| Species Tier | 物种等级（critical/focus/background） | `services/tiering.py` |
| Lineage Code | 物种谱系唯一标识 | `schemas/responses.py#SpeciesDetail` |
| Map Overview | 前端展示用的地图抽样数据信息 | `/map` 端点 |
| Save Slot | 玩家存档目录，由 `save_manager` 管理 | `/saves/*` |
| Model Router | 对接多种 AI 模型/供应商的路由器 | `backend/app/ai/model_router.py` |
| Frontend Service Layer | `frontend/src/services/api.ts` 中封装 fetch 调用的函数集合 | `modules/frontend-integration/services-layer.md` |

> 如新增核心术语，请在这里补充并保持与 `api.types.ts`、`schemas/*` 中命名一致。
