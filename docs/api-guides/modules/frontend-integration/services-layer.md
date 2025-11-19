# Service Layer 映射

展示 `frontend/src/services/api.ts` 中函数与后端端点的映射。使用 `rg -n "function" frontend/src/services/api.ts` 可获取行号。

| 函数 | 行号 (approx) | Endpoint | 模块 |
| --- | --- | --- | --- |
| `fetchQueueStatus` | 1 | `GET /queue` | Simulation |
| `runTurn` | 12 | `POST /turns/run` | Simulation |
| `fetchMapOverview` | 24 | `GET /map` | Environment |
| `fetchUIConfig` | 36 | `GET /config/ui` | Config |
| `updateUIConfig` | 41 | `POST /config/ui` | Config |
| `fetchPressureTemplates` | 49 | `GET /pressures/templates` | Simulation |
| `addQueue` | 54 | `POST /queue/add` | Simulation |
| `clearQueue` | 62 | `POST /queue/clear` | Simulation |
| `fetchSpeciesDetail` | 68 | `GET /species/{code}` | Species |
| `fetchLineageTree` | 74 | `GET /lineage` | Species |
| `fetchHistory` | 79 | `GET /history` | Simulation |
| `fetchExports` | 84 | `GET /exports` | Simulation |
| `editSpecies` | 89 | `POST /species/edit` | Species |
| `updateWatchlist` | 101 | `POST /watchlist` | Species |
| `testApiConnection` | 109 | `POST /config/test-api` | Analytics/Config |
| `listSaves` | 118 | `GET /saves/list` | Saves |
| `createSave` | 124 | `POST /saves/create` | Saves |
| `saveGame` | 137 | `POST /saves/save` | Saves |
| `loadGame` | 146 | `POST /saves/load` | Saves |
| `deleteSave` | 157 | `DELETE /saves/{name}` | Saves |

> 其余端点（如 `generateSpecies`, `compareNiche`）尚未封装，添加时请同步此表。

## 约定
- Service 函数负责处理 HTTP 层错误，抛出 Error 供 hooks/UI 捕获。
- 若接口要求附加 headers（鉴权），在此层统一设置。
