# 背景物种策略

- **实现**: `backend/app/services/background.py#BackgroundSpeciesManager`
- **配置**: `BackgroundConfig` 从 `settings` 注入
  - `population_threshold = 50_000`
  - `mass_extinction_threshold = 0.6`
  - `promotion_quota = 3`

## 流程

1. 每个回合结束后，`SimulationEngine` 将 mortality 结果分成 critical/focus/background 三组并传给 `BackgroundSpeciesManager`.
2. `summarize(...)` 统计各生态角色（producer/herbivore/carnivore/...）的背景物种数量，用于 `TurnReport.background_summary`。
3. `detect_mass_extinction(combined_results)`：若背景物种存活率低于 `mass_extinction_threshold`，返回 `True`。
4. 如触发大灭绝，`promote_candidates(background_results)` 会从 background 中选出 `promotion_quota` 个候选升级为 focus/critical，随后 `SimulationEngine` 可触发 `reemergence_events`。

## 与 API 的关系

- 没有独立 REST 端点，但结果体现在：
  - `/turns/run` → `TurnReport.background_summary`, `reemergence_events`
  - `/species/list` → `tier` 字段（`background`）与 `status`
  - `/map` → 间接影响 `HabitatEntry`（被晋升的物种将拥有更高优先级的栖息地更新）

## 调整指南

- 修改阈值需同步 `backend/app/core/config.py` 与此文档。
- 若未来暴露背景物种管理接口，建议放在 `environment` 模块并沿用同一配置结构。
