# 生态位对比 – `/niche/compare`

- **Method**: `POST`
- **实现**: `backend/app/api/routes.py:821`
- **请求模型**: `NicheCompareRequest`
- **响应模型**: `NicheCompareResult`

## 用例
- 比较两个或多个物种在资源使用、环境偏好方面的相似度。
- 支持前端对比视图或研究报告。

## 流程
1. `NicheAnalyzer` 读取物种向量（EmbeddingService）。
2. 计算余弦相似度、资源重叠度。
3. 返回 `scores`, `overlaps`, 建议行动（ex: 竞争、共存）。

## 请求示例
```json
{
  "primary_lineage": "CRIT-001",
  "comparisons": ["FOC-100", "FOC-221"],
  "dimensions": ["habitat", "diet", "behavior"]
}
```

## 前端
- 待实现 `compareNiche` API 函数与 UI 组件。

## 性能注意
- 每次调用需要多次向量检索，建议限制 `comparisons` 数量 <= 5。
