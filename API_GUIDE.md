# API 指南文档结构（提案）

本结构用于协调 FastAPI 后端与 Node/Vite 前端在演化模拟项目中的 API 设计、实现与消费方式。目标是让任何人都能从根指南迅速定位到具体接口说明，并理解调用链、依赖服务与前端消费点。

## 快速索引

- [根目录 docs/api-guides/README.md](docs/api-guides/README.md) – 顶层指南入口  
- 模块索引：
  - [Simulation](docs/api-guides/modules/simulation/README.md)
  - [Species](docs/api-guides/modules/species/README.md)
  - [Environment](docs/api-guides/modules/environment/README.md)
  - [Analytics & AI](docs/api-guides/modules/analytics-ai/README.md)
  - [Saves & Ops](docs/api-guides/modules/saves-ops/README.md)
  - [Config & UI](docs/api-guides/modules/config-ui/README.md)
  - [Frontend Integration](docs/api-guides/modules/frontend-integration/README.md)

## 1. 分层逻辑

Level 1（根指南）  
面向全员的入口，定位文件为 `docs/api-guides/README.md`。包含：
1. 系统架构图（后端 FastAPI、Simulation 引擎、AI 服务、前端 UI 的交互）。  
2. 统一规范：命名、版本、鉴权、错误模型、分页/过滤约定。  
3. 模块索引表：列出全部模块级指南、责任边界和对应负责人。  
4. 快速查找索引：可按业务域（模拟、物种、地图、配置等）或按调用方（前端组件/定时任务）跳转。  

Level 2（模块级指南）  
每个模块建立一个 `docs/api-guides/modules/<module>/README.md`，内容包含：
- 模块简介：业务职责、依赖的服务/仓库路径（如 `backend/app/services/map_manager.py`、`backend/app/repositories/*.py`）。  
- 交互流程：典型时序图或任务流程图。  
- 接口总览表：列出本模块涵盖的 API Path + Method、所属子模块文档链接、主要请求/响应模式。  
- 前端锚点：引用 `frontend/src/services/api.ts` 与 UI 组件入口，说明哪些视图会消费这些接口。  
- 子模块列表：若模块内存在进一步细分，在 README 中给出指向 Level 3 文档的跳转。  

Level 3（子模块/具体 API）  
文件示例 `docs/api-guides/modules/simulation/turn-execution.md`。每个文件聚焦一组高度相关的端点或单个端点，统一模板：
1. 场景背景 & 触发条件  
2. Endpoint 概要：Method + Path（引用 `backend/app/api/routes.py:<line>`）  
3. Request Schema：链接到 `backend/app/schemas/requests.py` 中 dataclass 或 Pydantic 模型定义  
4. Response Schema：链接 `backend/app/schemas/responses.py` 或 `models/`  
5. 状态机/副作用：涉及到的 service、repository、queue、task  
6. 前端调用点：`frontend/src/services/api.ts:<line>` 及关键 UI（如 `frontend/src/components/QueuePanel.tsx`）  
7. 错误与重试策略  
8. 示例（curl、前端 hooks 使用片段）  

## 2. 目录树提案

```text
docs/
└─ api-guides/
   ├─ README.md                     # Level 1: 总 API 指南
   ├─ glossary.md                   # 术语表/枚举/缩写
   ├─ conventions.md                # 通用规范（状态码、错误格式、版本策略、分页、速率限制）
   └─ modules/
      ├─ simulation/
      │  ├─ README.md               # Turn & Queue 模块级指南
      │  ├─ turn-execution.md       # /turns/run (routes.py:240)
      │  ├─ action-queue.md         # /queue, /queue/add, /queue/clear (routes.py:412,470,482)
      │  ├─ history-reports.md      # /history, /exports (routes.py:419,425) + report_builder
      │  └─ pressure-orchestration.md# /pressures/templates, GeneFlow/Pressure services
      ├─ species/
      │  ├─ README.md               # 物种情报模块
      │  ├─ listing.md              # /species/list (routes.py:492)
      │  ├─ detail-and-lineage.md   # /species/{code}, /lineage (routes.py:526,309)
      │  ├─ editing-and-generation.md# /species/edit, /species/generate (routes.py:265,695)
      │  ├─ watchlist.md            # /watchlist GET/POST (routes.py:290,296)
      │  ├─ hybridization.md        # /species/{code}/can_hybridize (routes.py:972)
      │  └─ genus-relations.md      # /genus/{code}/relationships (routes.py:1005)
      ├─ environment/
      │  ├─ README.md
      │  ├─ map-overview.md         # /map (routes.py:431, services/map_manager.py)
      │  ├─ terrain-evolution.md    # TerrainEvolutionService hooks
      │  └─ background-species.md   # BackgroundSpeciesManager policies
      ├─ analytics-ai/
      │  ├─ README.md
      │  ├─ niche-compare.md        # /niche/compare (routes.py:821)
      │  ├─ genetic-distance.md     # GeneFlow/GeneDistance services outputs
      │  └─ ai-routing.md           # ModelRouter overrides, /config/test-api (routes.py:715)
      ├─ saves-ops/
      │  ├─ README.md
      │  ├─ save-lifecycle.md       # /saves/create, /saves/save, /saves/load, /saves/{name} (routes.py:573,653,669,682)
      │  └─ save-metadata.md        # /saves/list (routes.py:561)
      ├─ config-ui/
      │  ├─ README.md
      │  ├─ ui-config.md            # /config/ui GET/POST (routes.py:453,459; frontend UI settings面板)
      │  └─ api-connectivity.md     # /config/test-api, embedding provider配置
      └─ frontend-integration/
         ├─ README.md               # 描述前端如何消费 API
         ├─ services-layer.md       # `frontend/src/services/api.ts` 函数映射
         ├─ state-hooks.md          # `frontend/src/hooks/useQueue.ts` 等 hook 与 API 对应
         └─ ui-modules.md           # 关键组件（地图、物种面板、存档模态）的 API 依赖
```

> 若后续新增模块（如“事件系统”、“实验场景”），沿用同样结构直接添加 `modules/<new-module>/` 并在根 README 中补充索引。

## 3. 模块说明要点

### Simulation（模拟与压力队列）
- **作用域**：运行回合、批量压力、行动队列、历史/报告导出。  
- **关键后端**：`backend/app/simulation/engine.py`、`backend/app/services/pressure.py`、`backend/app/services/report_builder.py`。  
- **相关接口**：`/turns/run`、`/queue*`、`/history`、`/exports`、`/pressures/templates`。响应模型 `SpeciesSnapshot` 扩充了 `grazing_pressure` 与 `predation_pressure` 以反映生物链互动。
- **前端入口**：`frontend/src/services/api.ts` 中 `runTurn`、`addQueue`、`clearQueue`、`fetchHistory` 函数（参考 `api.ts` 中相应函数声明行，`rg -n "runTurn" frontend/src/services/api.ts` 获取确切行号）。  
- **子模块建议**：将“执行回合”、“压力模板”、“队列状态”拆成独立文件，方便描述各自的请求负载与压力合成逻辑。  

### Species（物种情报与编辑）
- **作用域**：物种列表、谱系树、详情编辑、AI 物种生成、混种判定、种属关系。  
- **关键后端**：`backend/app/repositories/species_repository.py`、`services/speciation.py`、`services/tiering.py`。  
- **接口映射**：详见目录树中 species 子模块。  
- **前端入口**：`frontend/src/services/api.ts` 的 `fetchSpeciesDetail`、`fetchLineageTree`、`editSpecies`、`updateWatchlist` 等函数；UI 对应 `frontend/src/components/SpeciesPanel/*`（可在后续文档中精确列出组件文件）。  

### Environment（地图与环境系统）
- **作用域**：地图视图、地形演化、背景物种调度。  
- **关键后端**：`backend/app/services/map_manager.py`、`map_evolution.py`、`terrain_evolution.py`。  
- **接口**：`/map` 以及未来潜在的地形演化触发接口。  
- **前端入口**：地图组件 `frontend/src/map/*`，服务函数 `fetchMapOverview`。  

### Analytics & AI（特征分析、模型路由）
- **作用域**：生态位比对、遗传距离、AI 模型路由与健康检查。  
- **关键后端**：`services/niche.py`、`services/genetic_distance.py`、`ai/model_router.py`。  
- **接口**：`/niche/compare`、`/config/test-api` 以及与 AI 配置相关的未来端点。  
- **前端入口**：`frontend/src/services/api.ts` 的 `testApiConnection`、`fetchPressureTemplates` 等。  

### Saves & Operations（存档与场景运维）
- **作用域**：存档列表、创建、保存、加载、删除，及导出的关联。  
- **关键后端**：`services/save_manager.py`、`repositories/history_repository.py`。  
- **接口**：`/saves/*` 族。  
- **前端入口**：`listSaves`、`createSave`、`saveGame`、`loadGame`、`deleteSave`，UI 对应 `frontend/src/modals/SaveModal.tsx`。  

### Config & UI
- **作用域**：UI 配置文件、可视化设置、AI 接入信息。  
- **关键后端**：`backend/app/models/config.py`、`services/focus_processor.py`（影响 UI 的批量策略）。  
- **接口**：`/config/ui`、`/config/test-api`。  
- **前端入口**：`fetchUIConfig`、`updateUIConfig`、`testApiConnection`。  

### Frontend Integration
- **作用域**：将 API 文档与前端服务层/组件的对应关系固定下来。  
- **内容**：  
  - API 函数清单（映射到具体接口及错误处理）。  
  - Hooks/状态管理：如 queue 状态、species detail 缓存策略。  
  - UI 模块：地图、侧栏、模态窗等如何订阅 API。  
  - Mock/Storybook 引导：说明如何加载 API 套件以进行前端开发。  

## 4. 风格指引

- **文档命名**：`kebab-case`，文件内第一行以 `#` 标题起。  
- **元信息区块**：模块/接口文档顶部添加 Frontmatter 或表格（负责人、最近更新、依赖）。  
- **引用方式**：  
  - 后端路径：`backend/app/api/routes.py:240` 形式，便于 IDE 跳转。  
  - 模型定义：`backend/app/schemas/responses.py#TurnReport`。  
  - 前端调用：`frontend/src/services/api.ts:1`（使用 `rg -n` 更新精确行号）。  
- **交叉链接**：模块 README -> 子模块 -> 具体 API -> 相关前端/服务文件，形成 “一层概览，多层纵深” 的可导航链。  
- **版本维护**：在根 README 中留出 “版本矩阵”，标记当前 FastAPI / Node / Schema 版本，以及破坏性变更的落点文档。  

遵循此结构，可在扩展接口或引入新模块时保持统一信息架构，确保前端、后端与 AI/数据团队共享同一份纵深一致的 API 知识库。  
