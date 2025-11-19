# 属级关系 – `/genus/{code}/relationships`

- **Method**: `GET`
- **实现**: `backend/app/api/routes.py`
- **响应**: 
  ```json
  {
    "genus_code": string,
    "genus_name": string,
    "species": list[str],          // 属内物种列表
    "genetic_distances": dict,     // 遗传距离矩阵
    "can_hybridize_pairs": list    // 可杂交配对
  }
  ```

## 数据源
- `genus_repository` 提供属级节点与关系网。
- `species_repository` 提供属内当前存活物种。

## 用例
- 后台知识图谱可视化。
- 分析属内物种的分化程度和杂交潜力。

## 前端
- 对应 `api.ts` 中的逻辑（暂无独立函数，可能在组件中调用或作为未来扩展）。
