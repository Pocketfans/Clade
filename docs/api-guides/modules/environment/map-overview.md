# 地图概览 – `/map`

- **Method**: `GET`
- **Path**: `/api/map?limit_tiles=&limit_habitats=&view_mode=`
- **实现**: `backend/app/api/routes.py:431` 调用 `MapStateManager.get_overview`
- **响应模型**: `MapOverview`

## 参数
- `limit_tiles`: 限制返回瓦片数量（默认 3200）
- `limit_habitats`: 限制栖息地条目数
- `view_mode`: `terrain` (默认), `biome`, `population`

## 数据构成
- `tiles`: 精简地形数据 `[x, y, elevation, biome]`
- `hotspots`: 物种热点
- `metrics`: 全局统计（面积、平均丰度）

## 前端
- `frontend/src/services/api.ts#fetchMapOverview`（见文件顶部）
- UI：`frontend/src/map/MapCanvas.tsx`

## 性能
- MapManager 会缓存最近一次结果，避免频繁磁盘读取。
- 建议前端在 view_mode 变化时再调用。

## 示例
```bash
curl "http://localhost:8000/api/map?view_mode=biome&limit_tiles=2000"
```
