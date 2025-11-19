# 物种列表 – `GET /species/list`

- **Method**: `GET`
- **Path**: `/api/species/list?limit=&offset=&tier=&keyword=`
- **实现**: `backend/app/api/routes.py:492`
- **响应模型**: `SpeciesList`

## 参数
- `limit` (int, default 50)
- `offset` (int, default 0)
- `tier` (optional, `critical/focus/background`)
- `keyword` (optional, 搜索中文/拉丁名)

## 数据来源
- `species_repository.search_species`
- `tiering_service` 决定默认排序

## 前端
- `frontend/src/services/api.ts` 尚需实现 `fetchSpeciesList`（TODO）。
- UI：Species 列表视图（`frontend/src/components/SpeciesList.tsx` 计划）。

## 示例
```bash
curl "http://localhost:8000/api/species/list?limit=20&tier=critical"
```
