# 存档元数据 – `/saves/list`

- **Method**: `GET /api/saves/list`
- **实现**: `backend/app/api/routes.py#list_saves` → `SaveManager.list_saves`
- **响应**: `list[SaveMetadata]`（在前端直接作为数组使用）

## 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `name` | str | 存档对外显示名（来自 `metadata.save_name`） |
| `turn` | int | 最近保存的回合数 |
| `species_count` | int | 保存时的物种数量 |
| `timestamp` | float | `last_saved` 的 UNIX 时间戳（秒） |
| `scenario` | str | 剧本名称 |
| `save_name` | str | 与 `name` 相同，兼容旧实现 |
| `turn_index` | int | 同 `turn`（为旧版组件保留） |
| `last_saved` | str | ISO8601 字符串 |

> `SaveManager` 会过滤掉没有 `metadata.json` 或 `game_state.json` 的目录，并按 `timestamp` 降序排序。

## 数据来源

- `metadata.json`: 存档的主描述文件。
- `game_state.json`: 仅用于校验是否为完整存档，不直接解析。

## 前端

- `frontend/src/services/api.ts#listSaves`
- `SaveModal` / `MainMenu` 使用 `name`, `turn`, `species_count`, `timestamp` 渲染列表，点击后再调用 `loadGame`。
