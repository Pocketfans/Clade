# 编辑 & AI 生成 – `/species/edit`, `/species/generate`

## 编辑
- **Method**: `POST`
- **Path**: `/api/species/edit`
- **实现**: `backend/app/api/routes.py`
- **请求模型**: `SpeciesEditRequest`
- **响应**: `LineageNode`（更新后的节点）

### 行为
1. 拉取既有物种并应用描述/形态/特征更新。
2. 可选 `start_new_lineage`，触发 `SpeciationService` 拓展谱系。
3. 更新后写回 `species_repository` 并重建谱系节点。

## AI 生成
- **Method**: `POST`
- **Path**: `/api/species/generate`
- **实现**: `backend/app/api/routes.py`
- **请求模型**: `GenerateSpeciesRequest`
- **响应**: `{ success, species }`
- **服务**: `SpeciesGenerator`, `ModelRouter`, `EmbeddingService`

### 流程
1. 接收 `prompt` + 可选 `lineage_code`。
2. 通过 `SpeciesGenerator.generate_from_prompt` 调用 AI。
3. 生成 `Species` 对象写入 `species_repository`。
4. 返回基本信息供前端展示。

## 前端
- `editSpecies` 已在 `api.ts` 中实现。
- `generateSpecies` 已在 `api.ts` 中实现，用于创建存档时的自定义物种生成。

## 错误处理
- 400：参数缺失或无效。
- 500：AI 服务异常，detail 含 `[AI]` 关键字。
