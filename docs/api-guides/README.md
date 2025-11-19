# 总 API 指南

本指南是 FastAPI 后端与 Node/Vite 前端协同时的入口，概述系统架构、接口分类以及如何深入到各模块与端点文档。

## 系统总览

- **后端**：`backend/app/`，核心由 FastAPI (`main.py` + `api/routes.py`)、Service 层、Repository 层以及 Simulation/Environment 引擎组成。
- **前端**：`frontend/src/`，通过 `services/api.ts` 和 React 组件调用 API。
- **共享模型**：`backend/app/schemas` 内的请求/响应模型，部分在前端 `api.types.ts` 中有对应类型。
- **AI/数据依赖**：`backend/app/ai`、`services/niche.py`、`services/genetic_distance.py`。

> 视觉化架构：请在 `docs/api-guides/diagrams/`（后续创建）放置体系结构图。

## 文档层级

| 层级 | 文件/目录 | 内容 | 读者 |
| --- | --- | --- | --- |
| Level 1 | `docs/api-guides/README.md` | 全局综述、规范入口、模块索引 | 全体开发者 |
| Level 1 扩展 | `glossary.md`, `conventions.md` | 术语、错误模型、版本、分页、鉴权 | API 设计/QA |
| Level 2 | `modules/<module>/README.md` | 模块职责、流程、接口总览、前端锚点 | 模块负责人 |
| Level 3 | `modules/<module>/*.md` | 具体端点说明、Schema、调用路径、示例 | 接口实现者、前端联调 |

## 模块索引

| 模块 | 职责 | 关键端点 | 联系人 |
| --- | --- | --- | --- |
| [Simulation](modules/simulation/README.md) | 回合运行、压力、队列、报告 | `/turns/run`, `/queue*`, `/history`, `/pressures/templates` | Backend Simulation |
| [Species](modules/species/README.md) | 物种列表/详情、谱系、生成、守望 | `/species/*`, `/lineage`, `/watchlist` | Biology/Content |
| [Environment](modules/environment/README.md) | 地图、地形演化、背景种群 | `/map` + Terrain services | Map Squad |
| [Analytics & AI](modules/analytics-ai/README.md) | 生态位、遗传距离、AI 接口 | `/niche/compare`, `/config/test-api` | Data/AI |
| [Saves & Ops](modules/saves-ops/README.md) | 存档生命周期、导出 | `/saves/*`, `/exports` | Ops |
| [Config & UI](modules/config-ui/README.md) | UI 配置、AI 连接设置 | `/config/ui`, `/config/test-api` | Frontend Platform |
| [Frontend Integration](modules/frontend-integration/README.md) | 前端服务层、hooks、UI 依赖关系 | `frontend/src/services/api.ts` | Frontend |

## 使用方法

1. 先阅读本文件了解全局原则与模块列表。
2. 按需查阅 `glossary.md` 和 `conventions.md` 获取统一约束。
3. 跳转到模块 README 获取业务上下文与接口矩阵。
4. 若需实现或联调具体端点，进入 Level 3 文档（示例：`modules/simulation/turn-execution.md`）。
5. 在 PR 中若新增/修改接口，需同步对应 Level 2、Level 3 文档，并在根 README 的“模块索引”中标注状态。

## 快速跳转

- [`API_GUIDE.md`](../../API_GUIDE.md) – 仓库根索引
- [术语表](glossary.md)
- [统一规范](conventions.md)
- [模块文档](modules/)
