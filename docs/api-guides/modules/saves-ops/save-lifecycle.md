# 存档生命周期 – `/saves/*`

## 创建 – `POST /saves/create`
- **实现**: `backend/app/api/routes.py`
- **请求**: `CreateSaveRequest` (save_name, scenario, species_prompts)
- **行为**: 调用 `SaveManager.bootstrap_save_dir`，可选 AI 生成初始物种。
- **剧本逻辑**:
  - "空白剧本": 根据 `species_prompts` 使用 AI 生成全新的初始物种。
  - "原初大陆": 加载默认的种子物种。

## 保存 – `POST /saves/save`
- **实现**: `backend/app/api/routes.py`
- **流程**:
  1. 读取最新 `turn_index` (`history_repository`).
  2. `save_manager.save_game` 写入文件（地图、物种、日志）。
  3. 返回 `{ success, save_dir, turn_index }`。

## 加载 – `POST /saves/load`
- **实现**: `backend/app/api/routes.py`
- **行为**: 调用 `save_manager.load_game`，恢复状态至内存。

## 删除 – `DELETE /saves/{save_name}`
- **实现**: `backend/app/api/routes.py`
- **行为**: 删除目录。若不存在返回 404。

## 前端
- `createSave`, `saveGame`, `loadGame`, `deleteSave`（api.ts）。

## 错误
- 400：`save_name` 无效或重复。
- 500：磁盘写入失败，detail 包含路径。
