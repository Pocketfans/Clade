# 物种列表 – `GET /species/list`

- **Method**: `GET /api/species/list`
- **实现**: `backend/app/api/routes.py#list_all_species`
- **响应模型**: `SpeciesList`

## 行为

- 返回当前数据库中的全部物种（存活 + 灭绝），无分页。
- `SpeciesList.species` 中的每条记录包含：
  - `lineage_code`, `latin_name`, `common_name`
  - `population`: 取自 `morphology_stats["population"]`（若缺失则为 0）
  - `status`: `alive` / `extinct` / `split` 等
  - `ecological_role`: 由描述文本推断（关键词匹配 producer/herbivore/carnivore/omnivore）

> 该端点不再返回 `tier` 或 `trophic_level`；如需更详细数据，请调用 `/species/{code}`。

## 参数

无查询参数。若需要筛选，请在前端本地过滤或扩展 API。

## 数据来源

`species_repository.list_species()` 读取全部 `Species`，以内存生成响应（非流式）。在大型存档下调用会有一定压力，建议前端缓存。

## 前端

- `frontend/src/services/api.ts#fetchSpeciesList`（返回 `SpeciesListItem[]`，前端已在服务层展开 `SpeciesList.species`）
- 典型 UI：`SpeciesLedger`, `WatchlistPanel` 选择器。
