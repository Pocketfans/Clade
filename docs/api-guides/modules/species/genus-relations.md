# 属级关系 – `/genus/{code}/relationships`

- **Method**: `GET /api/genus/{code}/relationships`
- **实现**: `backend/app/api/routes.py#get_genetic_relationships`

## 响应示例

```json
{
  "genus_code": "AVS",
  "genus_name": "Avosyn",
  "species": ["A1", "A3", "A5"],
  "genetic_distances": {
    "A1-A3": 0.212,
    "A1-A5": 0.487
  },
  "can_hybridize_pairs": [
    { "pair": ["A1", "A3"], "distance": 0.212 }
  ]
}
```

- `species`: 仅包含当前存活 (`status == "alive"`) 且 `genus_code` 匹配的物种。
- `genetic_distances`: 来自 `genus.genetic_distances`，键格式固定为 `"codeA-codeB"`。
- `can_hybridize_pairs`: 只列出遗传距离 `< 0.5` 的配对，方便快速渲染关系图。

## 数据源

- `genus_repository.get_by_code`：提供属级元数据与遗传距离矩阵。
- `species_repository.list_species`：筛选属内存活物种。

## 用例

- 后台知识图谱 / 可视化工具。
- 支撑 `Hybridization` 调试界面：可以先获取所有潜在组合，再调用 `/species/{a}/can_hybridize/{b}` 获取详细诊断。

## 注意

- 若属不存在返回 `404 {"detail": "属不存在"}`。
- 目前没有缓存机制；当属内物种数量很大时（>200）调用会遍历所有对组合，建议谨慎使用。
