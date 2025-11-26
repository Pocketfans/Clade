# 遗传距离计算

- **实现**: `backend/app/services/genetic_distance.py`
- **用途**: 为 `HybridizationService`, `GenusRepository`, `NicheAnalyzer` 提供统一的物种特征向量与距离计算。
- **公开状态**: 暂未暴露独立 API，结果通过 `/species/{a}/can_hybridize/{b}`、`/genus/{code}/relationships` 间接呈现。

## 计算流程

1. `GeneticDistanceCalculator.get_vector(species)`：
   - 汇总 `morphology_stats`（体长、体重、寿命、代谢率等）
   - 采样 `abstract_traits`（繁殖速度、运动能力、社会性等）
   - 结合 `GeneLibrary` 中的关键特征（若存在）
2. 归一化向量并计算余弦距离/相似度。
3. 根据阈值（当前在 `HybridizationService` 中写死：`distance < 0.5`）判断可杂交。

## 配置 & 依赖

- `embedding_service`：可选，用于在缺少特征向量时退回文本 embedding。
- `gene_library.py`：提供额外的基因/器官特征映射。
- 阈值位于 `HybridizationService.can_hybridize`（`0.5`），若调整需同步文档与前端提示。

## 扩展建议

- 如需开放 `/genetics/distance` 供调试，可复用该服务返回 `{distance, similarity, vector_a, vector_b}`。
- 若引入更多特征维度，记得在此文档记录新增字段，便于数据团队追踪。
