# Environment 模块指南

涵盖地图概览、地形演化、背景物种管理等环境系统能力。

## 职责
- 提供 `/map` 数据供前端展示。
- 控制 Terrain/Map 演化服务，影响模拟输入。
- 管理背景 species（未被聚焦但仍存在的群体）。

## 依赖
- `backend/app/services/map_manager.py`, `map_evolution.py`, `terrain_evolution.py`
- `EnvironmentSystem`, `BackgroundSpeciesManager`
- 前端 `fetchMapOverview` + 地图组件

## 接口

| Endpoint | 描述 | 响应 | 前端 |
| --- | --- | --- | --- |
| `GET /map` | 返回地图概览 | `MapOverview` | `fetchMapOverview` |
| （WIP） `/map/evolve` | 触发地形演化 | `TerrainEvolutionResult` | 管理工具 |

## 子文档

| 文档 | 内容 |
| --- | --- |
| [map-overview.md](map-overview.md) | `/map` 端点 |
| [terrain-evolution.md](terrain-evolution.md) | 地形演化流程 |
| [background-species.md](background-species.md) | 背景物种策略 |

维护人：Map Squad。
