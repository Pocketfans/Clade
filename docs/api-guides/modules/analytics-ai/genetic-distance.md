# 遗传距离计算

- **服务**: `backend/app/services/genetic_distance.py`
- **输入**: 两个物种的 trait vectors、历史记录。
- **输出**: `distance`, `similarity`, `mutations`

## 与 API 的关系
- 当前未直接暴露端点，内部用于 hybridization、niche compare。
- 若未来开放 `/genetics/distance`，可基于此文档扩展。

## 步骤
1. `GeneticDistanceCalculator.get_vector(species)` 生成特征向量。
2. 计算余弦距离 + 加权特征差异。
3. 返回结构化结果供调用方处理。

## 依赖
- `embedding_service`
- `gene_library.py`

## TODO
- 记录阈值配置位置（settings）。
