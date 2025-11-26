# 详情 & 谱系 – `/species/{code}` 与 `/lineage`

## `/species/{lineage_code}` – SpeciesDetail

- **Method**: `GET`
- **实现**: `backend/app/api/routes.py#get_species_detail`
- **响应**: `SpeciesDetail`
- **前端**: `fetchSpeciesDetail` → `SpeciesDetailPanel`, `OrganismBlueprint`, `NicheCompareView`

### 字段要点

| 字段 | 说明 |
| --- | --- |
| `morphology_stats` | 仅保留数值字段（路由会剔除字符串，避免 `extinction_reason` 等脏数据） |
| `abstract_traits` / `hidden_traits` | AI/规则混合生成的抽象维度，直接映射数据库 |
| `organs` | 器官蓝图，结构为 `Dict[str, Dict]`，可能包含层级描述 |
| `capabilities` | 便于 UI 打标签的特性数组 |
| `genus_code` / `taxonomic_rank` | 供谱系/属级关系组件使用 |
| `hybrid_parent_codes` / `hybrid_fertility` | 杂交追踪 |
| `dormant_genes` / `stress_exposure` | 表观遗传状态，前端需判空处理 |

> **提示**：返回值目前不包含地图分布信息；如需空间数据请结合 `/map?species_code=`。

## `/lineage` – LineageTree

- **Method**: `GET`
- **实现**: `routes.py#get_lineage_tree`
- **响应**: `LineageTree`（`nodes: LineageNode[]`）
- **前端**: `fetchLineageTree` → `GenealogyGraphView/GenealogyView`

### 生成逻辑

1. 遍历 `species_repository.list_species()`。
2. 使用 `PopulationSnapshot`（最新/峰值）补全 `current_population` 与 `peak_population`。
3. 根据描述文本推断 `ecological_role`（简单关键词匹配）。
4. 统计 `descendant_count`、`hybrid_parent_codes`、`genetic_distances`（由 `genus_repository` 提供）。
5. 若 `status == "extinct"`，再次查询 `PopulationSnapshot` 推断 `extinction_turn`。

返回的 `LineageNode` 包含以下与 UI 强绑定的字段：

- `lineage_code`, `parent_code`, `speciation_type`
- `state`（`alive`/`extinct`/`split`）
- `birth_turn`, `extinction_turn`
- `tier`（当 `Species.is_background` 为真时标记为 `"background"`）
- `current_population`, `peak_population`, `population_share`
- `major_events`：当前仅包含 `"manual_edit"` 等占位符，供未来扩展。

## 注意事项

- `/lineage` 暂无分页/裁剪参数；在物种数量 > 500 时响应会较大，建议前端缓存或懒加载。
- `/species/{code}` 若找不到对应物种直接返回 `404 {"detail":"Species not found"}`。
- 如需 `lineage_path` 或 `niche_profile` 信息，需要在前端基于 `LineageTree` 自行推导，或扩展 API。

## 示例

```bash
curl http://localhost:8000/api/species/A1
curl http://localhost:8000/api/lineage
```
