# Watchlist – `/watchlist`

| Method | Path | 描述 |
| --- | --- | --- |
| `GET` | `/api/watchlist` | 返回 `{ "watching": ["A1", "B2"] }`（已排序） |
| `POST` | `/api/watchlist` | 用 `WatchlistRequest` 全量覆盖列表 |

## 模型

- `WatchlistRequest`: `{ "lineage_codes": ["A1", "B2", ...] }`
- 响应：始终返回 `{ "watching": list[str] }`

## 行为

1. `/watchlist` 内部维护一个 `set[str]`（由 FastAPI 进程持有）。
2. `POST` 时不会逐一验证物种是否存在；请在前端确保只提交有效 code。
3. 路由调用 `simulation_engine.update_watchlist`，下一次 `/turns/run` 将按照 `settings.critical_species_limit`（默认 3）将这些物种固定在 Critical 阶层，获得更详细的 AI 分析。
4. `GET` 返回排序后的列表，便于 UI 直接渲染。

## 服务依赖

- `SimulationEngine.watchlist`：驱动物种分层策略。
- `SpeciesTieringService`：结合 watchlist 决定 critical/focus/background。

## 前端

- `frontend/src/services/api.ts#updateWatchlist`
- 缺省的 `getWatchlist` 可在需要时补充（响应结构简单）。

## 规则

- Watchlist 长度建议 ≤ `settings.critical_species_limit`，否则多余的物种不会进入 Critical，但仍会被记录。
- 提交会完全覆盖现有列表，不支持增量添加。
