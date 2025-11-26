# 地图概览 – `/map`

- **Method**: `GET /api/map`
- **实现**: `backend/app/api/routes.py#get_map_overview` → `MapStateManager.get_overview`
- **响应**: `MapOverview`

## 查询参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `limit_tiles` | `6000` | 欲返回的六边形数量（最多 126×40=5040）。若小于地图总量则截断。 |
| `limit_habitats` | `500` | 栖息地记录上限，按最新快照排序。 |
| `view_mode` | `"terrain"` | 可选：`terrain`, `terrain_type`, `elevation`, `biodiversity`, `climate`。用于选择 `tiles[].color`。 |
| `species_code` | `None` | 若提供，将 `habitats` 过滤为指定物种。 |

## 响应结构（节选）

```json
{
  "tiles": [
    {
      "id": 1,
      "x": 0,
      "y": 0,
      "biome": "苔原",
      "cover": "苔藓层",
      "temperature": -5.2,
      "humidity": 0.41,
      "resources": 0.32,
      "neighbors": [2, 127, 128],
      "elevation": 120.0,
      "terrain_type": "高山",
      "climate_zone": "寒带",
      "color": "#9fb3d4",
      "colors": { "terrain": "#9fb3d4", "biodiversity": "#44784a", ... },
      "salinity": 0.5,
      "is_lake": false
    }
  ],
  "habitats": [
    {
      "species_id": 12,
      "lineage_code": "A1",
      "common_name": "银潮广叶树",
      "tile_id": 233,
      "population": 350000,
      "suitability": 0.82
    }
  ],
  "rivers": { "233": { "source_id": 233, "target_id": 332, "flux": 0.61 } },
  "vegetation": { "233": { "density": 0.74, "type": "forest" } },
  "sea_level": 3.4,
  "global_avg_temperature": 18.1,
  "turn_index": 142
}
```

### 生成细节

- `MapStateManager.get_overview` 在需要时会自动初始化地图（空数据库场景）。
- `colors` 字典中预先计算了所有可选 `view_mode` 的颜色，前端切换视图时可直接复用，无需重新请求。
- `habitats` 由 `environment_repository.latest_habitats` 读取最新快照；若结合 `species_code`，将只返回该物种的分布。
- `rivers` 使用 `HydrologyService.calculate_flow` 即时推算；`vegetation` 通过遍历栖息地并识别生产者物种得出。

## 前端

- `frontend/src/services/api.ts#fetchMapOverview`
- 主要消费组件：`MapCanvas`, `MapPanel`, `TileDetailPanel`, `SpeciesDetailPanel`（地图切换）。

## 性能建议

- `limit_tiles` 设置为默认值即可覆盖完整地图；仅在缩略视图中才需要降低。
- `view_mode` 发生切换时，可优先使用 `tiles[].colors` 本地更新，必要时再重新请求。

## 示例

```bash
curl "http://localhost:8000/api/map?view_mode=biodiversity&species_code=A1"
```
