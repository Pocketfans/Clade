# Watchlist – `/watchlist`

- **GET /api/watchlist`**: 返回当前关注物种列表。
- **POST /api/watchlist`**: 覆盖关注列表。

## 模型
- 请求：`WatchlistRequest` (`lineage_codes: list[str]`).
- 响应：`SpeciesListItem[]`（GET）或 `{ success: bool }`（POST）。

## 服务
- `species_repository`：验证 code 是否存在。
- `tiering_service`：关注列表影响物种升降级策略。

## 前端
- `updateWatchlist` (api.ts)
- Watchlist 组件：`frontend/src/components/WatchlistPanel.tsx`（TODO）

## 规则
- 最多 20 个关注对象。
- POST 会替换整份列表，不支持增量添加，前端需先合并本地状态再提交。
