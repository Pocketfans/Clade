# Admin & Ops API – `/admin/*`

提供系统管理、重置和调试功能。

## 健康检查 – `/admin/health`
- **Method**: `GET`
- **实现**: `backend/app/api/admin_routes.py`
- **响应**:
  ```json
  {
    "api": "online",
    "database": "ok", // 或 "degraded", "error: ..."
    "directories": {
      "data/db": "ok",
      "data/logs": "ok",
      ...
    },
    "initial_species": "ok" // 或 "missing: [...]"
  }
  ```
- **用例**: 系统启动自检、监控面板。

## 重置世界 – `/admin/reset`
- **Method**: `POST`
- **实现**: `backend/app/api/admin_routes.py`
- **请求**: `ResetRequest`
  ```json
  {
    "keep_saves": false, // 是否保留 saves/ 目录
    "keep_map": false    // 是否保留当前地图状态
  }
  ```
- **响应**: `{ "success": true, "message": "..." }`
- **行为**:
  1. 清空数据库中的演化历史、非初始物种。
  2. 若 `keep_map=false`，重置地图到初始状态。
  3. 清理 `data/reports` 和 `data/exports`。
  4. 恢复 `A_SCENARIO` 定义的初始物种。

