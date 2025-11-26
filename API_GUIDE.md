# API 接口指南（2025.11）

本文面向需要和 Clade 后端交互的前后端开发者。更细分的模块说明请参考 `docs/api-guides/modules/*`。

> **Base URL**：业务接口统一挂载在 `/api/*`；管理接口挂载在 `/api/admin/*`；根路径另暴露 `GET /health`。

---

## 0. 全局约定

- 所有请求/响应均为 `application/json`，除 `DELETE` 外均返回 JSON 体。
- 未实现认证，若部署到公网请在 API Gateway 层添加鉴权。
- 错误：校验失败返回 `422`；资源找不到返回 `404`；模拟/AI 失败多为 `500` 并包含 `detail`。
- 数据模型位于 `backend/app/schemas/requests.py` 与 `backend/app/schemas/responses.py`，修改后务必同步 `frontend/src/services/api.types.ts`。

---

## 1. 模拟循环（Simulation Core）

### 1.1 `POST /api/turns/run`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `rounds` | `int` | 1–100；如果回合队列存在排队批次且本次 `pressures` 为空，会自动消耗队首批次。 |
| `pressures` | `PressureConfig[]` | 详见 [`PressureConfig`](docs/api-guides/modules/simulation/pressure-orchestration.md)。 |
| `auto_reports` | `bool` | 当前固定 `true`；用于控制前端是否立即呈现战报。 |

响应：`TurnReport[]`。每次调用都会刷新 Watchlist/SpeciesTiering，并写入 `data/reports` 与 `history_repository`。

### 1.2 行动队列 `/api/queue*`

详解参见 [`docs/api-guides/modules/simulation/action-queue.md`](docs/api-guides/modules/simulation/action-queue.md)。

| 方法 | 路径 | 描述 |
| --- | --- | --- |
| `GET` | `/api/queue` | 返回 `ActionQueueStatus`（包含 `queue_preview`）。 |
| `POST` | `/api/queue/add` | 接受 `QueueRequest`：将 `pressures` 复制 `rounds` 次推入内存队列。 |
| `POST` | `/api/queue/clear` | 清空队列并将 `queued_rounds` 重置为 0。 |

---

## 2. 压力模板与历史追踪

| 方法 | 路径 | 描述 |
| --- | --- | --- |
| `GET` | `/api/pressures/templates` | 静态模板列表，供前端生成 UI。 |
| `GET` | `/api/history?limit=10` | 最近 `limit` 条 `TurnReport`。 |
| `GET` | `/api/exports` | 已导出的 Markdown/JSON 回合档案（`ExportRecord[]`）。 |

历史模块的详细字段说明见 [`docs/api-guides/modules/simulation/history-reports.md`](docs/api-guides/modules/simulation/history-reports.md)。

---

## 3. 物种系统（Species Services）

| 方法 | 路径 | 描述 / 备注 |
| --- | --- | --- |
| `GET` | `/api/species/list` | 返回 `SpeciesList`，带有推断后的 `ecological_role`。 |
| `GET` | `/api/species/{lineage_code}` | `SpeciesDetail`，包含 `organs`、`capabilities`、`dormant_genes` 等字段。 |
| `POST` | `/api/species/edit` | `SpeciesEditRequest`：支持 `trait_overrides`（数值骨骼）与 `abstract_overrides`（软性特质），`open_new_lineage` 可标记分支。 |
| `POST` | `/api/species/generate` | `GenerateSpeciesRequest`，通过 LLM 生成新物种并立刻写库。 |
| `GET` | `/api/lineage` | 返回 `LineageTree`，节点包含 `current_population`、`peak_population`、`genetic_distances` 等扩展数据。 |
| `GET` | `/api/species/{code1}/can_hybridize/{code2}` | 对应 `HybridizationService` 检查，可返回不育原因。 |
| `GET` | `/api/genus/{code}/relationships` | 属级别的遗传图谱与可杂交配对。 |

更多背景请参考 `docs/api-guides/modules/species/*`。

---

## 4. 地图与环境（Environment）

### 4.1 `GET /api/map`

查询参数：

- `limit_tiles`（默认 6000）与 `limit_habitats`（默认 500）用于控制返回量。
- `view_mode`: `"terrain" | "elevation" | "bio"` 等；参数将直接传给 `MapStateManager.get_overview`。
- `species_code`: 若提供，将仅返回该物种的栖息地条目并在地图上加色。

响应类型：`MapOverview`，包含地块、栖息地、河流、植被、全球温度/海平面。

### 4.2 UI 配置

| 方法 | 路径 | 描述 |
| --- | --- | --- |
| `GET` | `/api/config/ui` | 读取 `data/settings.json` 并通过 `apply_ui_config` 注入 ModelRouter / EmbeddingService。 |
| `POST` | `/api/config/ui` | 写入 `UIConfig`。支持多 Provider、能力路由、并发限制、Embedding 指定等。 |

详细 schema 见 [`docs/api-guides/modules/config-ui/ui-config.md`](docs/api-guides/modules/config-ui/ui-config.md)。

---

## 5. Watchlist、分析与 AI 调试

| 方法 | 路径 | 描述 |
| --- | --- | --- |
| `GET` | `/api/watchlist` | 返回当前 watchlist：`{"watching": ["A1", ...]}`。 |
| `POST` | `/api/watchlist` | `WatchlistRequest`，刷新 SimulationEngine 的关注列表。 |
| `POST` | `/api/niche/compare` | `NicheCompareRequest`，需要真实 Embedding 服务；若禁用会返回 `503`。 |
| `POST` | `/api/config/test-api` | AI/Embedding 连通性测试，用于 Settings Drawer 验证第三方服务。 |

更多细节见 `docs/api-guides/modules/analytics-ai/*`。

---

## 6. 存档与导入导出（Saves & Ops）

| 方法 | 路径 | 描述 |
| --- | --- | --- |
| `GET` | `/api/saves/list` | `SaveMetadata[]`，从 `data/saves/*/metadata.json` 读取。 |
| `POST` | `/api/saves/create` | `CreateSaveRequest`：字段包含 `save_name`, `scenario`, `species_prompts?`, `map_seed?`。根据剧本自动初始化地图、栖息地、人口快照和第 0 回合报告。 |
| `POST` | `/api/saves/save` | `SaveGameRequest`，立即序列化当前数据库至对应存档目录。 |
| `POST` | `/api/saves/load` | `LoadGameRequest`，加载并重建世界状态。 |
| `DELETE` | `/api/saves/{save_name}` | 删除存档目录。 |

脚本版操作位于 `scripts/reset_world.py`，与这些 API 共用同一服务层。

---

## 7. 管理与运维（Admin Router）

| 方法 | 路径 | 描述 |
| --- | --- | --- |
| `GET` | `/api/admin/health` | 检查数据库、关键目录以及初始物种是否存在。 |
| `POST` | `/api/admin/reset` | `ResetRequest {keep_saves, keep_map}`；重置数据库、清理导出/存档目录。 |

这些接口需要谨慎调用，生产环境建议加鉴权。

---

## 8. 根级健康检查

- `GET /health`：不在 `/api` 前缀下，用于部署探活。

---

## 9. 前端集成指引

- **Service 层**：业务接口封装在 `frontend/src/services/api.ts`，Admin 相关封装在 `frontend/src/services/api_admin.ts`。组件层禁止直接 `fetch`。
- **错误处理**：捕获 `res.ok`，并优先展示 `detail` 字段。模拟失败日志在后端以 `[推演错误]` 打头。
- **类型**：`frontend/src/services/api.types.ts` 同步 `SpeciesDetail`, `TurnReport`, `UIConfig` 等定义；`MapPanel`, `GlobalTrendsPanel`, `OrganismBlueprint`, `QueuePanel` 等组件依赖这些类型。
- **参考**：更多前端接口用法见 `docs/api-guides/modules/frontend-integration/*`。

---

## 10. 数据模型速查

| 模型 | 位置 | 用途 |
| --- | --- | --- |
| `TurnCommand`, `PressureConfig`, `QueueRequest` | `backend/app/schemas/requests.py` | 模拟执行与行动队列。 |
| `SpeciesEditRequest`, `GenerateSpeciesRequest` | 同上 | 物种干预与 AI 生成。 |
| `CreateSaveRequest`, `SaveGameRequest`, `LoadGameRequest` | 同上 | 存档操作。 |
| `UIConfig`, `ProviderConfig`, `CapabilityRouteConfig` | `backend/app/models/config.py` | 多 Provider/Embedding 配置。 |
| `ActionQueueStatus`, `TurnReport`, `LineageTree`, `MapOverview` | `backend/app/schemas/responses.py` | 主要响应体。 |
| `NicheCompareResult` | 同上 | 生态位分析结果。 |

如需深入某个模块，请查看 `docs/api-guides/modules/<domain>/README.md` 获取设计背景与调试提示。
