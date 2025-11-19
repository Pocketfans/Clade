# 混种判断 – `/species/{code1}/can_hybridize/{code2}`

- **Method**: `GET`
- **实现**: `backend/app/api/routes.py`
- **响应**: 
  ```json
  {
    "can_hybridize": boolean,
    "fertility": float,       // 繁殖力 (0.0 - 1.0)
    "genetic_distance": float,// 遗传距离
    "reason": string          // 原因说明
  }
  ```

## 逻辑
1. 读取两个物种基因特征 (`species_repository`).
2. 使用 `HybridizationService` 与 `GeneticDistanceCalculator` 评估兼容度。
3. 读取属内遗传距离矩阵 (`genus_repository`).
4. 若兼容度满足条件，返回 true 及计算出的繁殖力。

## 用途
- 供研究工具或调试界面使用。
- 前端可用于显示两个物种之间是否可能发生基因交流。

## 性能
- 计算较为轻量，主要依赖预计算的遗传距离。
