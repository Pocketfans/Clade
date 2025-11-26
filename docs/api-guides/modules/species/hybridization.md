# 混种判断 – `/species/{code1}/can_hybridize/{code2}`

- **Method**: `GET /api/species/{code1}/can_hybridize/{code2}`
- **实现**: `backend/app/api/routes.py#check_hybridization`

## 响应格式

```json
{
  "can_hybridize": true,
  "fertility": 0.72,
  "genetic_distance": 0.214,
  "reason": "近缘物种，遗传距离0.21，可杂交"
}
```

- `can_hybridize`: `HybridizationService.can_hybridize` 的布尔结果。
- `fertility`: 返回三位小数的可育程度。
- `genetic_distance`: 来自 `genus.genetic_distances`（键格式：`"A1-B1"`）。
- `reason`: 根据属一致性与距离阈值生成的人类可读说明。

## 评估逻辑

1. 使用 `species_repository.get_by_code` 读取两个物种；若任意不存在则返回 `404`。
2. 若 `genus_code` 不一致直接拒绝（`"不同属物种无法杂交"`）。
3. 查找属级遗传距离矩阵，默认值 `0.5`。
4. 调用 `HybridizationService.can_hybridize(species_a, species_b, distance)`，内部依赖 `GeneticDistanceCalculator` 和 trait 向量。
5. 按结果拼装响应消息。

## 用途

- 支撑工具/后台面板，判断两物种是否可能形成杂交谱系。
- 搭配 `/genus/{code}/relationships` 可视化属内杂交网络。

## 性能

- 完全在内存中运行，单次调用只遍历两个 `Species` 对象；可安全用于调试 UI。
