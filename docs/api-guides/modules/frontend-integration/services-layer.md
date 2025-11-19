# Service Layer 映射

展示 `frontend/src/services/api.ts` 中函数与后端端点的映射。

| 函数 | Endpoint | 模块 |
| --- | --- | --- |
| `fetchQueueStatus` | `GET /queue` | Simulation |
| `runTurn` | `POST /turns/run` | Simulation |
| `fetchMapOverview` | `GET /map` | Environment |
| `fetchUIConfig` | `GET /config/ui` | Config |
| `updateUIConfig` | `POST /config/ui` | Config |
| `fetchPressureTemplates` | `GET /pressures/templates` | Simulation |
| `addQueue` | `POST /queue/add` | Simulation |
| `clearQueue` | `POST /queue/clear` | Simulation |
| `fetchSpeciesDetail` | `GET /species/{code}` | Species |
| `fetchLineageTree` | `GET /lineage` | Species |
| `fetchHistory` | `GET /history` | Simulation |
| `fetchExports` | `GET /exports` | Simulation |
| `editSpecies` | `POST /species/edit` | Species |
| `updateWatchlist` | `POST /watchlist` | Species |
| `testApiConnection` | `POST /config/test-api` | Analytics/Config |
| `listSaves` | `GET /saves/list` | Saves |
| `createSave` | `POST /saves/create` | Saves |
| `saveGame` | `POST /saves/save` | Saves |
| `loadGame` | `POST /saves/load` | Saves |
| `deleteSave` | `DELETE /saves/{name}` | Saves |
| `generateSpecies` | `POST /species/generate` | Species |
| `fetchSpeciesList` | `GET /species/list` | Species |
| `compareNiche` | `POST /niche/compare` | Analytics |
| `checkHealth` | `GET /admin/health` | Admin |
| `resetWorld` | `POST /admin/reset` | Admin |
| `simulateTerrain` | `POST /admin/simulate-terrain` | Admin |

## 约定
- Service 函数负责处理 HTTP 层错误，抛出 Error 供 hooks/UI 捕获。
- 若接口要求附加 headers（鉴权），在此层统一设置。
