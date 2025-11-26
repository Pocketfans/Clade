# Environment 模块指南

涵盖地图概览、地形/气候演化与背景物种管理。

## 职责

- 向前端暴露 `/map` 概览（六边形地块、栖息地、河流、植被）。
- 在回合执行期间驱动 `MapEvolutionService`、`HydrologyService`。
- 通过 `BackgroundSpeciesManager`、`MapStateManager` 维护生态基线。

## 依赖

- `backend/app/services/map_manager.py`
- `map_evolution.py`, `hydrology.py`, `background.py`
- `EnvironmentSystem`（解析压力并提供 modifiers）
- 前端 `fetchMapOverview` + `MapCanvas` / `MapPanel`

## 接口

| Endpoint | 描述 | 响应 | 备注 |
| --- | --- | --- | --- |
| `GET /map` | 地图 + 栖息地概览 | `MapOverview` | 支持 `species_code`、`view_mode` 等参数 |

## 子文档

| 文档 | 内容 |
| --- | --- |
| [map-overview.md](map-overview.md) | `/map` 端点 |
| [background-species.md](background-species.md) | 背景物种策略及配置 |

维护人：Map Squad。
