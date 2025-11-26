# 编辑 & AI 生成 – `/species/edit`, `/species/generate`

## `/species/edit`

- **Method**: `POST /api/species/edit`
- **实现**: `backend/app/api/routes.py#edit_species`
- **请求模型**: `SpeciesEditRequest`
  - `lineage_code`（必填）
  - `description`: 新的文本描述
  - `trait_overrides`: `dict[str, float]` → 合并进 `morphology_stats`
  - `abstract_overrides`: `dict[str, float]` → 合并进 `abstract_traits`
  - `open_new_lineage`: `bool`，为真时将 `status` 标记为 `"split"`，供后续分化逻辑处理
- **响应**: `LineageNode`（简化后的谱系节点）

### 行为

1. 根据 `lineage_code` 读取物种，若不存在返回 `404`。
2. 依次更新描述、形态属性、抽象特质。
3. 若 `open_new_lineage=True`，仅修改状态，不会自动创建新物种；`SpeciationService` 在下一回合可读取该状态。
4. 将结果写回 `species_repository` 并返回一个最小 `LineageNode`（仅包含基础字段，`population` 等值暂为占位）。

> **注意**：当前 `frontend/src/services/api.ts#editSpecies` 仍以 `SpeciesDetail` 为返回类型，需在联调时更新类型定义。

## `/species/generate`

- **Method**: `POST /api/species/generate`
- **实现**: `routes.py#generate_species`
- **请求模型**: `GenerateSpeciesRequest`
  - `prompt`: 描述文本，1–500 字符
  - `lineage_code`: 默认 `"A1"`，在空白剧本中用于手动指定
- **响应**:

```json
{
  "success": true,
  "species": {
    "lineage_code": "H1",
    "latin_name": "Caeloflux titan",
    "common_name": "天流巨兽",
    "description": "..."
  }
}
```

### 流程

1. `SpeciesGenerator.generate_from_prompt` 通过 `ModelRouter` 的 `species_generation` 能力调用远端模型。
2. 生成的 `Species` 会立即 `upsert` 到数据库（包含 morphology/traits/器官等完整结构）。
3. 仅返回摘要，详尽信息可再次调用 `/species/{code}`。

### 典型用例

- “空白剧本”创建存档时，根据玩家提供的若干 prompt 批量生成初始种群。
- 开发者调试新 prompt / 模型配置。

## 错误处理

- `400`：`lineage_code` 冲突或参数不合法（目前由 `HTTPException` 抛出）。
- `500`：AI 调用失败、写库异常等，`detail` 会包含 `"生成物种失败"` 前缀。

## 前端

- `frontend/src/services/api.ts#editSpecies`
- `frontend/src/services/api.ts#generateSpecies`

提交时请同步更新 `frontend/src/services/api.types.ts` 以避免类型漂移。
