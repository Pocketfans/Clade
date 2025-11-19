# 背景物种策略

- **组件**: `BackgroundSpeciesManager` (`backend/app/services/background.py`)
- **配置**: `BackgroundConfig`（人口阈值、灭绝阈值、晋升配额）来自环境设置。

## 流程
1. Turn 结束后统计背景物种数量。
2. 若低于 `population_threshold`，从 `species_repository` 选取候选补位。
3. 若出现大灭绝事件（<= `mass_extinction_threshold`），触发重新分配。

## 与 API 的关系
- 虽无独立端点，但影响 `/map` 和 `/species/list` 中背景信息。
- 文档记录在此便于追踪参数含义。

## 调整指南
- 修改阈值需同步 `config.py` 与此文档。
- 若未来开放背景物种管理端点，放入 `environment` 模块下并引用本文。
