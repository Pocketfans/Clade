# 生态位对比 – `/niche/compare`

- **Method**: `POST /api/niche/compare`
- **实现**: `backend/app/api/routes.py#compare_niche`
- **请求**: `NicheCompareRequest`

```json
{
  "species_a": "A1",
  "species_b": "B1"
}
```

- **响应**: `NicheCompareResult`

## 用例

- 评估两个物种生态位重叠度、竞争强度以及关键维度差异。
- 前端 `NicheCompareView` 以蛛网图/表格展示结果。

## 处理流程

1. `species_repository.get_by_lineage` 读取物种数据并校验存在性。
2. `EmbeddingService.embed` 在 `require_real=True` 模式下请求外部向量服务（当前要求真实 API）。
3. `numpy` 计算余弦相似度 → `similarity`（0–1），并直接作为 `overlap`。
4. 按人口规模计算 `competition_intensity = similarity * pop_factor`，其中 `pop_factor` 基于两者人口比值归一化。
5. 组装 `niche_dimensions`：
   - 形态：体长 (`body_length_cm`)、体重 (`body_weight_g`)、寿命、代谢率。
   - 种群规模：`种群数量`。
   - 抽象特质：`繁殖速度`、`运动能力`、`社会性`。
   - 环境耐性：若 `abstract_traits` 包含 `耐寒性`、`耐热性`、`耐旱性`、`耐盐性`、`光照需求`、`氧气需求`，将追加对应维度。

## 响应示例

```json
{
  "species_a": { "lineage_code": "A1", "...": "..." },
  "species_b": { "lineage_code": "B1", "...": "..." },
  "similarity": 0.82,
  "overlap": 0.82,
  "competition_intensity": 0.37,
  "niche_dimensions": {
    "种群数量": { "species_a": 1200000, "species_b": 800000 },
    "体长(cm)": { "species_a": 65, "species_b": 40 },
    "繁殖速度": { "species_a": 0.8, "species_b": 0.5 },
    "耐寒性": { "species_a": 0.2, "species_b": 0.9 }
  }
}
```

## 前端

- `frontend/src/services/api.ts#compareNiche`
- 错误提示：若返回 `503 detail="无法计算生态位向量"`，需要提示用户检查 Embedding 服务配置。

## 性能注意

- 每次调用都会触发两次 Embedding API 请求，应避免在 `hover` 等高频场景中调用。
- 如需本地离线模式，可在 `EmbeddingService` 中配置 `local` provider，并更新文档。
