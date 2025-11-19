# 存档元数据 – `/saves/list`

- **Method**: `GET`
- **实现**: `backend/app/api/routes.py:561`
- **响应**: `list[SaveMetadata]`

## 字段
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `save_name` | str | 目录名/唯一标识 |
| `scenario` | str | 场景描述 |
| `created_at` | datetime | 创建时间 |
| `last_turn` | int | 记录的 turn index |
| `species_count` | int | 存档时物种数量 |

## 数据来源
- `SaveManager.list_saves`
- 汇集 `metadata.json` + 目录统计

## 前端
- `listSaves` (api.ts)
- 存档管理 UI 依赖此接口渲染列表。
