# EvoSandbox 开发文档

本文件面向开发者，聚焦架构、目录与关键模块。玩家向的描述、测试步骤等细节已省略，避免干扰日常迭代。部署与运行命令请同时参考 `README.md`。

## 1. 架构概览

- **后端栈**：FastAPI + SQLModel + SQLite。`SimulationEngine` 串联环境、地形、死亡、规则、AI 推理与导出服务，统一暴露在 `app/api/routes.py`。
- **前端栈**：React + Vite。`src/App.tsx` 维护顶层状态，`components/` 目录包含地图、HUD、浮窗、族谱、历史等 UI。
- **AI/嵌入服务**：`app/ai/ModelRouter` 根据 `settings.json` 的 provider/model 路由请求，endpoint 默认为 `/chat/completions`（适配base_url已包含/v1的API），`EmbeddingService` 支持远程或伪随机嵌入并带 SHA256 缓存。
- **数据持久化**：SQLite (`egame.db`) 保存物种、事件、地图与历史；`reports/`、`exports/`、`saves/` 用于导出与独立存档。

## 2. 关键数据与配置

| 路径 | 说明 |
|------|------|
| `backend/.env` | 由 `pydantic-settings` 读取，配置 `DATABASE_URL`、AI Base URL/Key |
| `backend/egame.db` | 运行时数据库，`core/database.py` 负责初始化 |
| `settings.json` | 前端设置抽屉保存的模型/Embedding 配置，通过 `/api/config/ui` 读写 |
| `backend/cache/embeddings/` | `EmbeddingService` 的本地缓存目录（SHA256 命名） |
| `reports/` & `exports/` | `ExportService` 每回合输出的 Markdown/JSON |
| `saves/` | 存档目录，`SaveManager` 负责加载/保存 |

## 3. 后端模块

### 3.1 核心入口
- `app/main.py`：创建 FastAPI 应用，挂载路由与启动事件，启动时初始化数据库和默认物种。
- `core/config.py`：`Settings` 模型以及 `get_settings()` 缓存，统一读取目录、AI、地图尺寸等配置。
- `core/database.py`：SQLModel engine、`init_db()` 与 `session_scope()`。
- `core/seed.py`：在空库时写入默认物种场景，自动计算并设置所有物种的营养级（trophic_level）。

### 3.2 模型与仓储
- `models/species.py`：`Species`（包含 `abstract_traits` 字段存储耐寒性/耐热性/耐旱性/耐盐性等属性，1.0-15.0浮点数标度，支持动态添加新属性；`trophic_level` 字段存储营养级1.0-6.0+；`organs` 字典记录结构化器官数据，格式为 `{category: {type, parameters, acquired_turn, is_active}}`；`capabilities` 列表存储能力标签如 `["photosynthesis", "flagellar_motion"]`；`genus_code` 记录所属属；`taxonomic_rank` 标记分类等级如 subspecies/species/hybrid；`hybrid_parent_codes` 记录杂交亲本；`hybrid_fertility` 存储杂交可育性；`dormant_genes` 记录个体休眠基因（格式 `{"traits": {}, "organs": {}}`）；`stress_exposure` 记录历史压力暴露计数）、`PopulationSnapshot`、`LineageEvent`。
- `models/genus.py`：`Genus` 记录属的基本信息、遗传距离矩阵 `genetic_distances`（格式为 `{"code1-code2": distance}`）和基因库 `gene_library`（格式为 `{"traits": {}, "organs": {}}`，存储该属所有物种的潜在遗传特质和器官）。
- `models/environment.py`：`EnvironmentEvent`、`MapTile`、`MapState`、`HabitatPopulation`、`TerrainEvolutionHistory` 等地形/气候模型。
- `models/history.py` 与 `models/config.py`：回合日志、UI 配置与模型能力配置。
- `repositories/*`：按实体划分的查询与写入封装，例如 `species_repository`、`history_repository`、`map_repository`、`genus_repository`。
- `schemas/responses.py`：API 响应模型，`MapChange` 包含 `change_type` 字段（uplift/erosion/volcanic/climate_change 等），`BranchingEvent` 包含 `reason` 字段记录分化原因，`SpeciesSnapshot` 新增 `grazing_pressure`（啃食压力）与 `predation_pressure`（捕食压力）字段，`notes` 字段为 AI 生成的文本段落列表。`LineageNode` 包含 `taxonomic_rank`（subspecies/species/hybrid）、`genus_code`、`hybrid_parent_codes`、`hybrid_fertility`、`genetic_distances` 字段，用于谱系图展示亚种和杂交关系。

### 3.3 服务与子系统
- simulation/SimulationEngine：回合 orchestrator，顺序调用环境输入、地形演化、全图营养级互动计算、物种死亡、AI 报告、繁殖、渐进演化、基因流动、亚种晋升与导出；模块导入时会将 sys.stdout 统一配置为 UTF-8，避免 Windows 控制台打印中文日志时抛出编码异常。
- services/environment_system.py：解析压力输入、更新全球温度/海平面、通知地图与物种计算。
- services/terrain_evolution.py：优先结合板块阶段与 AI 建议对地块执行隆起/侵蚀/下沉，新增 rule-based fallback（缺省模型或 API Key 时）会基于候选区与阶段偏好选择演化类型、注入火山/侵蚀幅度并产出 MapChange 日志，同时维护 TerrainEvolutionHistory 以保证持续过程可跨回合延续；最坏情况下执行有限随机漂移保持地图刷新。
- services/tiering.py：`SpeciesTieringService` 按生态学原理将物种分为 Critical（玩家关注，最多3个）、Focus（生态强度排序，默认24个）、Background（低种群/低强度）三层，基于营养级权重、种群规模、濒危程度与特殊角色多维度评分；
- services/niche.py：`NicheAnalyzer` 通过 `EmbeddingService` 计算物种描述的向量，使用余弦相似度计算生态位重叠度与资源饱和度，应用生态学规则修正。 `/api/niche/compare` 端点支持前端对比两个物种的生态位维度。
- services/critical_analyzer.py、services/focus_processor.py：为 Critical 层逐个物种生成详细叙事（每物种1次调用），为 Focus 层批量生成简述（每8个物种1次调用），Background 层使用规则计算不消耗 AI。
- services/trait_config.py：`TraitConfig` 统一管理属性定义、验证和营养级限制。提供标准属性默认值、属性到环境压力的映射（TRAIT_PRESSURE_MAPPING）、营养级对应的属性上限（base/specialized/total）三层验证机制。
- services/speciation.py：支持四类分化模式（地理隔离、生态隔离、协同演化、极端环境特化），AI prompt 直接生成物种学名和俗名。分化遵循奠基者效应（Founder Effect），父代保留大部分种群，子代由边缘小群体建立。分化时继承父代器官并应用 AI 返回的 `structural_innovations`（包含 category、type、parameters），自动更新能力标签。新分化物种初始为亚种（taxonomic_rank=subspecies），并自动更新遗传距离矩阵。使用 `TraitConfig` 处理属性继承和营养级限制验证。
- services/adaptation.py：`AdaptationService` 实现渐进演化和退化机制。渐进演化动态处理所有属性对环境压力的响应，自动检查营养级限制（总和上限、特化上限）。退化机制检测长期不使用的能力（`is_active=False`），每5回合执行一次退化检查。
- services/gene_activation.py：`GeneActivationService` 处理休眠基因激活，激活前验证属性是否符合营养级限制，只有通过验证才应用激活。
- services/gene_library.py：`GeneLibraryService` 管理属级基因库（Genus.gene_library），记录 AI 发现的新特质和器官，处理子代对休眠基因的继承。
- services/genetic_distance.py：`GeneticDistanceCalculator` 基于形态学差异、属性差异、器官差异、时间分化四个维度计算物种间遗传距离（0.0-1.0）。
- services/hybridization.py：`HybridizationService` 处理物种杂交，遗传距离<0.5的同属物种可杂交，杂交种继承双亲属性和器官，可育性随遗传距离降低。
- services/gene_flow.py：`GeneFlowService` 模拟同属近缘物种间的基因流动，基于种群规模的非对称流动（大种群对小种群影响更大），每回合产生微小属性趋同。
- services/trophic.py：`TrophicLevelCalculator` 根据物种description中的食性关键词或食物比例自动计算营养级，提供营养级对应的属性上限，并基于克莱伯定律（Kleiber's Law, R ∝ M^-0.25）计算非线性代谢率。
- services/mortality_engine.py：规则驱动死亡率计算，基于压力类型、生态位重叠、资源饱和度、以及跨营养级的啃食/捕食压力（Grazing/Predation Pressure）计算，体型、繁殖策略、环境适应属性提供抗性修正。
- services/reproduction_service.py：基于世代时间和r/K策略计算增长因子，生态位竞争和资源压力施加限制，全球承载力1亿（每回合50万年）。
- services/migration_advisor.py、pressure_escalation_service.py：规则驱动的迁徙推荐与重大事件升级。
- services/export_service.py：同步写入 TurnLog、导出 Markdown/JSON，供前端查询。

## 4. 前端结构

- `src/App.tsx`：顶层状态管理（回合、地图、队列、设置），协调左右 HUD。
- `src/components/MapPanel`：渲染 80×40 六边形网格，提供视图切换与图例；地图数据来自 `/api/map?view_mode=`。
- `src/components/ControlPanel`、`PressureModal`、`GameSettingsMenu`：负责回合操作、压力编排、存档和模型设置。
- `src/components/GenealogyView`、`HistoryTimeline`、`TurnReportPanel`：族谱与历史展示，按需请求 `/api/lineage`、`/api/history`。`GenealogyGraphView` 使用 d3.js 绘制谱系树，支持亚种（橙色虚线+SUB徽章）、杂交种（紫色曲线+HYB徽章）视觉标识，鼠标悬停显示遗传距离。节点详情面板展示分类等级、所属属、杂交亲本信息和遗传距离列表。
- `src/components/NicheCompareView`：生态位对比页面。调用 `/api/niche/compare` 计算生态位相似度、重叠度、竞争强度，并展示多维度对比图表。
- `src/services/api.ts`：集中封装前端请求路径与类型， `fetchSpeciesList()` 和 `compareNiche()` 方法，调整 API 时需同步。新增 `/api/species/{code1}/can_hybridize/{code2}` 检查杂交可行性，`/api/genus/{code}/relationships` 查看属内遗传关系。

## 5. 配置与运行要点

- FastAPI/数据库/AI 配置集中在 `Settings`，通过环境变量覆盖；前端的设置抽屉保存后会调用 `apply_ui_config` 同步后端。`ModelRouter` 支持 capability-specific overrides（base_url、api_key、timeout），通过 `settings.json` 的 `capability_configs` 字段配置。
- 地图数据始终基于相对海拔（`elevation - sea_level`）重计算，以确保海平面变化后分类正确；`MapStateManager` 提供快照。地块资源为 1-1000 绝对值，综合考虑温度、海拔、湿度与纬度（温度越低资源越少、浅海与低地平原资源丰富、深海与极高山资源稀少）。
- 物种分层参数：`critical_limit=3`（玩家关注上限）、`focus_batch_size=8`（批处理大小）、`focus_batch_limit=3`（批次上限，共24个）、`background_population_threshold=50000`（背景层种群阈值）。玩家通过 `/api/watchlist` 管理关注列表。
- 演化参数：物种 `abstract_traits` 包含耐寒性/耐热性/耐旱性/耐盐性等标准属性（1.0-15.0浮点数），支持动态添加新属性。初始物种配备基础器官和所属属（genus_code）。AI 分化时返回 `structural_innovations` 数组和可选的 `genetic_discoveries`（新发现的特质/器官添加到属基因库）。新分化物种初始为亚种。同属物种遗传距离<0.4时每回合发生基因流动。`TraitConfig` 提供统一的属性验证和环境压力映射。
- 回合导出、UI 视图、AI 模型等信息高度耦合，修改接口后请更新 `README.md` 与本文件以保证文档一致。

## 6. 开发建议

1. 常用命令：`uvicorn app.main:app --reload`、`npm run dev`、`npm run build`，修改 API 后务必运行前后端确认无断链。
2. 与 AI 相关的功能应优先复用 `ModelRouter` 的能力标签，保持 `settings.json` 与 `app/ai/prompts/` 的一致性。新增 AI 能力时在 `app/ai/prompts/` 目录添加 prompt 模板并注册到 `PROMPT_TEMPLATES`。
3. 涉及地图或地形的改动请同时检查 `TerrainEvolutionService`、`map_coloring_service` 和前端 `MapPanel`，避免颜色或分类滞后。
4. 数据目录（`egame.db`、`reports/`、`exports/`、`saves/`）属于玩家资产，调试时勿清空；必要时使用新的 SQLite 实例或独立存档。
5. 生态位对比功能依赖 `EmbeddingService`，需配置有效的 embedding provider 和 API key；本地模式会使用伪随机向量，可能影响准确性。
6. ModelRouter 调试：invoke 方法输出详细日志（capability、provider、override 状态），用于追踪 API 调用问题。

## 7. 地形演化测试
-  test_terrain_evolution.py 通过 REST API 自动创建存档并运行 10 轮推演，后端会在日志中输出阶段信息、MapChange 描述及每轮的海拔/地形统计。
- TerrainEvolutionService 缺省 AI 模型时会调用 rule-based fallback：基于候选区、阶段偏好与 turn index 注入侵蚀/火山/造山演化，幅度分别限制在 5-30m、200-800m、100-500m，并在必要时生成随机漂移以保持地图刷新。
- 需要人工核对脚本末尾的 5 个验证点，确保阶段→事件匹配、至少出现 1 次火山抬升、持续过程能跨回合延续、幅度落在约束区间、规则分析文本符合地质逻辑。
- 测试结果会写入根目录  est_output.log，若出现回合失败可直接根据 log 与 server.log 追溯原因。
