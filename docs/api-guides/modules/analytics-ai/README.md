# Analytics & AI 模块指南

面向生态位分析、遗传距离、AI 模型配置与诊断。

## 职责
- 提供 `/niche/compare` 进行生态位匹配。
- 管理 AI 接口连通性测试 `/config/test-api`。
- 文档化 `ModelRouter` 覆盖、Embedding 服务使用方式。

## 依赖
- `backend/app/services/niche.py`, `genetic_distance.py`, `embedding.py`
- `backend/app/ai/model_router.py`
- 前端 `api.ts`：`fetchPressureTemplates`, `testApiConnection`

## 接口

| Endpoint | 描述 | Schema | 前端 |
| --- | --- | --- | --- |
| `POST /niche/compare` | 生态位对比 | `NicheCompareRequest/Result` | `compareNiche`（TODO） |
| `POST /config/test-api` | 测试 AI 连接 | `{ success, details }` | `testApiConnection` |

## 子文档

| 文档 | 内容 |
| --- | --- |
| [niche-compare.md](niche-compare.md) | `/niche/compare` |
| [genetic-distance.md](genetic-distance.md) | 遗传距离计算流程 |
| [ai-routing.md](ai-routing.md) | ModelRouter、测试端点 |

维护人：Data/AI 小组。
