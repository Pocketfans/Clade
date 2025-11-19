# 混种判断 – `/species/{code1}/can_hybridize/{code2}`

- **Method**: `GET`
- **实现**: `backend/app/api/routes.py:972`
- **响应**: `{ "can_hybridize": bool, "score": float }`

## 逻辑
1. 读取两个物种基因特征 (`species_repository`).
2. 使用 `HybridizationService` 与 `GeneticDistanceCalculator` 评估兼容度。
3. 若兼容度 > 阈值返回 true。

## 用途
- 供研究工具或调试界面使用，当前前端未默认展示。
- 可扩展至“混种挑战”玩法。

## 性能
- 调用包含向量计算，建议限制前端频率。
