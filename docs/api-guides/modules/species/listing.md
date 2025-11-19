# 物种列表 – `GET /species/list`

- **Method**: `GET`
- **Path**: `/api/species/list`
- **实现**: `backend/app/api/routes.py`
- **响应模型**: `SpeciesList`

## 描述
获取当前所有存活或灭绝物种的简要列表。

## 参数
当前版本暂不支持分页或过滤参数，返回全量数据。

## 数据来源
- `species_repository.list_species`
- 包含字段：谱系代码、拉丁名、俗名、种群数量、状态、生态角色。

## 前端
- `frontend/src/services/api.ts`: `fetchSpeciesList`
- UI：Species 列表视图。
