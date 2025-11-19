# 存档生命周期 – `/saves/*`

## 创建 – `POST /saves/create`
- **实现**: `backend/app/api/routes.py:573`
- **请求**: `CreateSaveRequest` (save_name, scenario, species_prompts)
- **行为**: 调用 `SaveManager.bootstrap_save_dir`，可选 AI 生成初始物种。

## 保存 – `POST /saves/save`
- **实现**: `routes.py:653`
- **流程**:
  1. 读取最新 `turn_index` (`history_repository`).
  2. `save_manager.save_game` 写入文件（地图、物种、日志）。
  3. 返回 `{ success, save_dir, turn_index }`。

## 加载 – `POST /saves/load`
- **实现**: `routes.py:669`
- **行为**: 调用 `save_manager.load_game`，恢复状态至内存。

## 删除 – `DELETE /saves/{save_name}`
- **实现**: `routes.py:682`
- **行为**: 删除目录。若不存在返回 404。

## 前端
- `createSave`, `saveGame`, `loadGame`, `deleteSave`（api.ts）。
- UI：`frontend/src/modals/SaveModal.tsx`（计划）。

## 错误
- 400：`save_name` 无效或重复。
- 500：磁盘写入失败，detail 包含路径。
