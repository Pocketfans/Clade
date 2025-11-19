# 详情 & 谱系 – `/species/{code}` + `/lineage`

## 物种详情
- **Method**: `GET`
- **Path**: `/api/species/{lineage_code}`
- **实现**: `routes.py:526`
- **响应**: `SpeciesDetail`
- **服务**: `species_repository.get` + `MapStateManager`（提供地理分布）
- **前端**: `fetchSpeciesDetail` → Species Detail Panel

### 字段说明
- `traits_summary`：由 `TraitConfig` 计算
- `lineage_path`：谱系节点 breadcrumb
- `niche_profile`：`NicheAnalyzer` 输出

## 谱系树
- **Method**: `GET`
- **Path**: `/api/lineage`
- **实现**: `routes.py:309`
- **响应**: `LineageTree`
- **服务**: `history_repository`, `species_repository`
- **前端**: `fetchLineageTree` → Lineage View

### 注意
- 谱系树数据量大，响应会裁剪深度；参数 `depth` （TODO）后续加在请求上。
- 若请求码不存在返回 404。

## 示例
```bash
curl http://localhost:8000/api/species/CRIT-001
curl http://localhost:8000/api/lineage
```
