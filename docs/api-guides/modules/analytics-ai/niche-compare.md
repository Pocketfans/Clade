# 生态位对比 – `/niche/compare`

- **Method**: `POST`
- **实现**: `backend/app/api/routes.py`
- **请求模型**: `NicheCompareRequest`
  ```json
  {
    "species_a": "A1",
    "species_b": "B1"
  }
  ```
- **响应模型**: `NicheCompareResult`

## 用例
- 比较两个物种在资源使用、环境偏好方面的相似度。
- 计算竞争强度（Competition Intensity）和重叠度（Overlap）。

## 流程
1. `NicheAnalyzer` 读取物种向量（EmbeddingService，要求真实 Embedding）。
2. 计算向量余弦相似度。
3. 结合种群规模计算竞争强度。
4. 对比关键形态和抽象特征维度。

## 响应示例
```json
{
  "species_a": { ... },
  "species_b": { ... },
  "similarity": 0.85,
  "overlap": 0.85,
  "competition_intensity": 0.42,
  "niche_dimensions": {
    "种群数量": { "species_a": 1000, "species_b": 800 },
    "体长(cm)": { ... },
    ...
  }
}
```

## 前端
- `compareNiche` (api.ts)
- 用于“生态位分析”或“物种对比”视图。

## 性能注意
- 调用 Embedding Service，可能产生 API 延迟。
- 依赖 OpenAI 或其他 Embedding Provider。
