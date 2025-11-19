# Species 模块指南

聚焦物种列表、详情、谱系、编辑与生成工作流。

## 职责
- 暴露物种读取、筛选、关注列表等端点。
- 支持编辑现有物种描述、触发新谱系。
- 调用 AI 生成新物种并写入仓库。
- 提供混种、属级关系等高级查询。

## 依赖
- `backend/app/repositories/species_repository.py`, `genus_repository.py`
- `services/speciation.py`, `services/tiering.py`, `services/species_generator.py`
- `/species/*` 路由位于 `routes.py:492-1005`
- 前端对应 `frontend/src/services/api.ts` 中的物种函数 + 侧栏组件

## 接口总览

| Endpoint | 描述 | Schema | 前端 |
| --- | --- | --- | --- |
| `GET /species/list` | 列表 | `SpeciesList` | `fetchSpeciesList`（待实现） |
| `GET /species/{code}` | 详情 | `SpeciesDetail` | `fetchSpeciesDetail` |
| `POST /species/edit` | 编辑 | `SpeciesEditRequest` | `editSpecies` |
| `POST /species/generate` | AI 生成 | `GenerateSpeciesRequest` | `generateSpecies`（后续暴露） |
| `GET /lineage` | 谱系树 | `LineageTree` | `fetchLineageTree` |
| `GET/POST /watchlist` | 关注列表 | `WatchlistRequest` | `updateWatchlist` |
| `GET /species/{a}/can_hybridize/{b}` | 混种可能性 | bool | 临时调试 UI |
| `GET /genus/{code}/relationships` | 属间关系 | graph | 后台工具 |

## 子文档

| 文档 | 内容 |
| --- | --- |
| [listing.md](listing.md) | `GET /species/list` | 
| [detail-and-lineage.md](detail-and-lineage.md) | 详情与谱系 |
| [editing-and-generation.md](editing-and-generation.md) | 编辑、AI 生成 |
| [watchlist.md](watchlist.md) | Watchlist API |
| [hybridization.md](hybridization.md) | 混种判断 |
| [genus-relations.md](genus-relations.md) | 属级关系 |

维护人：Biology/Content 小组。
