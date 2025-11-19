# Watchlist – `/watchlist`

- **GET /api/watchlist**: 返回当前关注物种列表。
- **POST /api/watchlist**: 更新关注列表。

## 模型
- 请求：`WatchlistRequest` (`lineage_codes: list[str]`).
- 响应：`{ "watching": list[str] }` (GET 和 POST 相同).

## 服务
- `species_repository`：验证 code 是否存在。
- `tiering_service`：关注列表影响物种升降级策略。
- `simulation_engine`：在运行时更新关注列表。

## 前端
- `updateWatchlist` (api.ts)

## 规则
- 通常限制关注 `critical_limit` 个物种（默认为 3 个）。
- 这些物种将获得最详细的 AI 分析和报告。
- POST 操作会完全覆盖当前的关注列表。
