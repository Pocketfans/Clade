# 存档生命周期 – `/saves/*`

## 创建 – `POST /api/saves/create`

- **请求模型**: `CreateSaveRequest`
  - `save_name`: 自定义名称（会映射为 `save_{timestamp}_{safe_name}` 目录）
  - `scenario`: `"原初大陆"`（默认）或 `"空白剧本"`
  - `species_prompts`: 仅在空白剧本下使用，按顺序生成新物种
  - `map_seed`: 可选数值，用于 `MapStateManager.ensure_initialized`
- **实现**: `routes.py#create_save`

### 执行步骤

1. **清空当前数据库**：删除所有 `Species`, `MapTile`, `MapState`, `HabitatPopulation`, `TurnLog`，确保新存档从干净状态开始。
2. **初始化地图**：调用 `map_manager.ensure_initialized(map_seed)` 生成 126×40 地图。
3. **注入初始物种**：
   - `原初大陆`: 调用 `seed_defaults()` 写入 A_SCENARIO 物种。
   - `空白剧本`: 遍历 `species_prompts`，用 `SpeciesGenerator.generate_from_prompt` 生成物种。`lineage_code` 会根据可用字母自动分配（A,B,C...）。
4. **生成栖息地快照**：`map_manager.snapshot_habitats(all_species, turn_index=0)`。
5. **创建 metadata**：在新目录写入 `metadata.json`，并立即保存一次初始 `game_state.json`。

> **风险**：接口会直接删除运行中的所有数据，请在调用前确保已有备份。

## 保存 – `POST /api/saves/save`

- 读取最新 `turn_index`（`history_repository.list_turns(limit=1)`）。
- `save_manager.save_game(save_name, turn_index)` 会写入：
  - `species`（所有字段）
  - `map_tiles`, `map_state`, `habitats`
  - 最近 1000 条 `history_logs`
- 返回 `{ "success": true, "save_dir": "...", "turn_index": N }`。

## 加载 – `POST /api/saves/load`

- `save_manager.load_game(save_name)`：
  1. 清空当前数据库（species/environment/history）。
  2. 将 `game_state.json` 中的数据重新写回仓库。
  3. 返回 `{"success": true, "turn_index": <saved_turn>}`。
- 若路径或文件缺失分别抛出 `404` / `500`。

## 删除 – `DELETE /api/saves/{save_name}`

- `save_manager.delete_save(save_name)` 删除整个目录。
- 如果找不到对应目录/metadata，返回 `404 {"detail": "存档不存在"}`。

## 列表 – `GET /api/saves/list`

- 返回 `SaveManager.list_saves()` 的数组（见 [save-metadata.md](save-metadata.md)）。
- 排序依据 `last_saved` 时间戳。

## 前端

- `frontend/src/services/api.ts`: `createSave`, `saveGame`, `loadGame`, `deleteSave`, `listSaves`
- `SettingsDrawer` / `SaveModal` 等组件会组合这些调用。

## 常见错误

- `400`: 空白剧本时 `species_prompts` 超过可用首字母数量。
- `500`: 磁盘写入失败或 JSON 序列化异常（detail 提供路径/栈）。
- `404`: `load`/`delete` 目标不存在。
