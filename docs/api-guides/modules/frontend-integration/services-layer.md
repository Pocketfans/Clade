# Service Layer 映射

展示 `frontend/src/services/api.ts` 中函数与后端端点的映射。

| 函数 | Endpoint | 模块 | 备注 |
| --- | --- | --- | --- |
| `fetchQueueStatus` | `GET /queue` | Simulation | 返回 `ActionQueueStatus`（含 `queue_preview`） |
| `runTurn` | `POST /turns/run` | Simulation | 目前固定 `rounds=1` |
| `fetchMapOverview` | `GET /map` | Environment | 支持 `viewMode`, `speciesCode` |
| `fetchUIConfig` | `GET /config/ui` | Config | 读取 `UIConfig` |
| `updateUIConfig` | `POST /config/ui` | Config | 写入并触发热更新 |
| `fetchPressureTemplates` | `GET /pressures/templates` | Simulation | 静态模板 |
| `addQueue` | `POST /queue/add` | Simulation | 发送 `PressureDraft[]` |
| `clearQueue` | `POST /queue/clear` | Simulation | 清空排队任务 |
| `fetchSpeciesDetail` | `GET /species/{code}` | Species | 返回 `SpeciesDetail` |
| `fetchLineageTree` | `GET /lineage` | Species | 返回 `LineageTree`（一次性加载） |
| `fetchHistory` | `GET /history` | Simulation | `limit` 默认 10 |
| `fetchExports` | `GET /exports` | Simulation | 返回 `ExportRecord[]` |
| `editSpecies` | `POST /species/edit` | Species | 后端返回 `LineageNode`（需调整前端类型） |
| `updateWatchlist` | `POST /watchlist` | Species | 目前缺少 GET/refresh 函数 |
| `testApiConnection` | `POST /config/test-api` | Analytics/Config | Settings Drawer 使用 |
| `listSaves` | `GET /saves/list` | Saves | 返回数组（非对象包装） |
| `createSave` | `POST /saves/create` | Saves | 可能耗时，需 loading 状态 |
| `saveGame` | `POST /saves/save` | Saves | 返回 `{ success, save_dir, turn_index }` |
| `loadGame` | `POST /saves/load` | Saves | 返回 `{ success, turn_index }` |
| `deleteSave` | `DELETE /saves/{name}` | Saves | 404 表示找不到 |
| `generateSpecies` | `POST /species/generate` | Species | 用于空白剧本 |
| `fetchSpeciesList` | `GET /species/list` | Species | 服务层直接返回 `SpeciesListItem[]` |
| `compareNiche` | `POST /niche/compare` | Analytics | 依赖真实 Embedding 配置 |
| `checkHealth` | `GET /admin/health` | Admin | 面板或 CLI |
| `resetWorld` | `POST /admin/reset` | Admin | 会清理数据库/目录 |

## 约定
- Service 函数负责处理 HTTP 层错误，抛出 Error 供 hooks/UI 捕获。
- 若接口要求附加 headers（鉴权），在此层统一设置。
