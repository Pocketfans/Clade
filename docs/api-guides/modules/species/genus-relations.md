# 属级关系 – `/genus/{code}/relationships`

- **Method**: `GET`
- **实现**: `routes.py:1005`
- **响应**: `{ "genus": str, "related": [ { "genus": str, "affinity": float } ] }`

## 数据源
- `genus_repository` 提供属级节点与关系网。
- `history_repository` 补充共同事件统计。

## 用例
- 后台知识图谱可视化。
- 为 AI 描述提供额外上下文（`SpeciesGenerator`）。

## 前端
- 暂无对应视图，若添加请更新 `frontend-integration` 文档。
