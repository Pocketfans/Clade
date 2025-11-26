# Analytics & AI 模块指南

聚焦生态位分析、遗传距离计算、AI 路由配置与诊断工具。

## 职责

- 暴露 `/niche/compare` 供物种生态位对比/竞争分析。
- 提供 `/config/test-api` 用于验证 LLM / Embedding 服务连通性。
- 维护 `ModelRouter`、`EmbeddingService`、`NicheAnalyzer` 等跨模块能力。

## 依赖

- `backend/app/services/niche.py`, `embedding.py`, `genetic_distance.py`
- `backend/app/ai/model_router.py`
- `frontend/src/services/api.ts`：`compareNiche`, `testApiConnection`

## 接口

| Endpoint | 描述 | Schema | 前端 |
| --- | --- | --- | --- |
| `POST /niche/compare` | 生态位向量对比、竞争度计算 | `NicheCompareRequest` → `NicheCompareResult` | `compareNiche` |
| `POST /config/test-api` | 测试 chat / embedding API | `{ type, base_url, api_key, model }` → `{ success, message, details }` | `testApiConnection`（Settings Drawer） |

## 子文档

| 文档 | 内容 |
| --- | --- |
| [niche-compare.md](niche-compare.md) | `/niche/compare` 细节 |
| [genetic-distance.md](genetic-distance.md) | 遗传距离算法、混种依赖 |
| [ai-routing.md](ai-routing.md) | ModelRouter、UI 配置、诊断端点 |

维护人：Data/AI 小组。
