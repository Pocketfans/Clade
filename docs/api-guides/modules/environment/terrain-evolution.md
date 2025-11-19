# 地形演化流程

- **服务**: `backend/app/services/terrain_evolution.py`
- **触发**: Turn 执行后或管理端调用（未来 `/map/evolve`）
- **输入**: 当前 `EnvironmentSystem`、`MigrationAdvisor` 建议、压力上下文
- **输出**: 更新的地形、资源分布

## 步骤
1. `TerrainEvolutionService.apply_events` 根据压力/事件产生地形修改。
2. `MapEvolutionService` 重新计算区域聚类、资源产出。
3. `MapStateManager` 刷新缓存供 `/map` 端点使用。

## 配置
- `settings.map_width/height` 控制栅格大小。
- `settings.terrain_event_intensity`（TODO）

## 文档 TODO
- 当 `/map/evolve` 端点就绪后补充请求/响应示例。
