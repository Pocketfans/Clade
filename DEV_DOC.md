# EvoSandbox 开发文档

本文档面向开发者，旨在深入解析 **混合演化架构 (Hybrid Evolutionary Architecture)** 的实现原理。如果你想了解系统是如何在“死板的规则”和“灵活的 AI”之间取得平衡的，请阅读本文。

## 1. 核心架构：混合引擎 (The Hybrid Engine)

系统的核心是 `SimulationEngine` (`backend/app/simulation/engine.py`)，它像一个精密的齿轮组，将规则计算与 AI 推理咬合在一起。

### 1.1 演化循环 (The Loop)
每个回合（Turn）代表地质时间尺度上的约 50 万年。处理流程如下：

1.  **环境输入 (Rules)**：解析温度、湿度、海平面变化。
2.  **地形演化 (Hybrid)**：
    *   **Rules**: 板块运动阶段（稳定/分裂/碰撞）决定大趋势。
    *   **AI**: 决定具体发生在哪里（如“赤道附近的火山爆发”），并生成地质描述。
3.  **营养级互动 (Rules)**：
    *   计算全图生物量（Biomass）。
    *   自下而上（Bottom-up）计算资源限制：植物 -> 食草 -> 食肉。
    *   自上而下（Top-down）计算捕食压力。
4.  **死亡判定 (Rules)**：基于适应性、竞争压力、寿命极限计算死亡率。
5.  **AI 叙事 (AI)**：`ReportBuilder` 将枯燥的死亡数据转化为“物种兴衰史”。
6.  **繁殖与变异 (Hybrid)**：
    *   **Rules**: 决定生多少（r/K 策略）。
    *   **AI**: 决定长成什么样（分化、新器官、新特性）。

### 1.2 关键算法服务

#### 🛡️ 规则层 (The Shield)
这些服务保证了系统不会“数值崩坏”：

*   **`TrophicLevelCalculator` (营养级计算)**：
    *   自动分析物种描述，分配 T1.0 (生产者) 到 T5.0+ (顶级掠食者)。
    *   **硬约束**：高营养级物种必须有更低的种群数量上限（能量金字塔）。
*   **`MortalityEngine` (死亡引擎)**：
    *   综合考虑 5 种压力：环境不适、生态位重叠、资源匮乏、被捕食、自然衰老。
    *   引入 **最小生存阈值**，防止种群无限趋近于零而不灭绝。
*   **`GeneticDistanceCalculator` (遗传距离)**：
    *   基于形态学差异、器官差异、分化时间计算 0.0-1.0 的距离。
    *   **硬约束**：距离 > 0.5 的物种绝对无法杂交。

#### 🎨 创意层 (The Brush)
这些服务负责提供无限的可能性：

*   **`SpeciationService` (分化服务)**：
    *   当环境压力过大或生态位空缺时触发。
    *   AI 接收父代特征 + 环境压力，生成全新的子代物种（包括拉丁名、形态描述、新器官）。
*   **`NicheAnalyzer` (生态位分析)**：
    *   使用 Embedding 向量化物种描述。
    *   计算物种间的余弦相似度，判断它们是在“激烈竞争”还是“互利共生”。

#### 🧬 适应层 (The Adapter)
这些服务负责物种在个体系内的动态调整与资源分配：

*   **`GeneActivationService` (基因激活)**：
    *   **表观遗传机制**：当物种面临极高死亡率（>50%）时，沉睡的“休眠基因”会被唤醒。
    *   **压力特异性**：干旱压力激活耐旱基因，寒冷压力激活皮毛基因。这是拉马克式演化在系统中的体现——“用进废退”的紧急版本。
*   **`FocusBatchProcessor` (焦点叙事)**：
    *   **算力分配**：系统不会对所有 100+ 个物种都进行详尽的 AI 叙事。
    *   **智能聚焦**：只对“主角”（发生重大变异、濒临灭绝或种群激增的物种）调用昂贵的 GPT-4 模型生成详细战报，其他物种仅做数值更新。

## 2. 数据模型设计

### 2.1 物种 (Species)
物种不仅仅是一段文本，它是一个结构化的对象：
*   `morphology_stats`: 数值属性（体长、体重、代谢率）。
*   `abstract_traits`: 适应性评分（耐寒: 8.5, 耐旱: 3.0）。
*   `organs`: 结构化器官库（`{ "movement": { "type": "wings", "cost": 0.2 } }`）。
*   `lineage_code`: 唯一标识符（如 "A1-B2"），蕴含了演化路径信息。

### 2.2 地图 (MapTile)
*   采用 **Axial Coordinates (q, r)** 存储六边形坐标。
*   数据分离：`elevation` (绝对海拔) vs `sea_level` (海平面)。
*   动态计算：生物群系 (Biome) 是根据海拔、温度、湿度实时推导的，而非死数据。

## 3. 目录结构详解

```text
backend/
├── app/
│   ├── ai/                 # LLM 集成
│   │   ├── model_router.py # 智能路由（根据任务分发给不同模型）
│   │   └── prompts/        # 精心调优的 Prompt 模板
│   ├── core/               # 基础设施 (DB, Config)
│   ├── models/             # SQLModel 数据定义
│   ├── services/           # 业务逻辑 (上述算法的实现地)
│   │   ├── adaptation.py   # 渐进演化
│   │   ├── speciation.py   # 物种分化
│   │   └── ...
│   └── simulation/         # 引擎主循环
├── tests/                  # 单元测试
└── pyproject.toml          # 依赖管理
```

## 4. 前端架构 (Frontend Architecture)

前端是一个独立的 React 应用，负责可视化复杂的演化数据。

*   **技术栈**: Vite + React + TypeScript + D3.js
*   **核心目录**:
    *   `components/GenealogyGraphView.tsx`: 使用 D3.js 绘制交互式族谱树。
    *   `components/MapPanel.tsx`: 六边形地图渲染器。
    *   `services/api.ts`: 强类型的 API 客户端，与后端 `API_GUIDE.md` 保持同步。
    *   `hooks/useGameState.ts`: 全局状态管理（当前回合、选中物种等）。

## 5. 数据库管理 (Database Management)

系统使用 **SQLModel (SQLAlchemy + Pydantic)** 作为 ORM。

*   **自动建表**: 系统启动时会自动检查并创建缺失的表 (`backend/app/core/database.py:init_db`)。
*   **无迁移工具**: 目前未集成 Alembic。
    *   ⚠️ **注意**: 如果你修改了 `backend/app/models/` 下的模型定义，必须删除 `data/db/egame.db` 文件，重启后端以触发重建。
    *   或者使用 `scripts/reset_to_initial_species.py` 进行重置。

## 6. 运维与调试工具 (Scripts & Ops)

为了简化开发流程，我们将核心运维工具集成到了前端 UI 的 **"开发者工具 (Admin Panel)"** 中。你可以在游戏设置菜单中找到它。

### 6.1 开发者工具面板 (Admin Panel)
前端面板 (`frontend/src/components/AdminPanel.tsx`) 提供了以下功能：

*   **系统健康 (System Health)**:
    *   实时检查后端 API 连通性。
    *   验证数据库完整性（初始物种是否存在）。
    *   检查关键数据目录 (`data/db`, `data/logs` 等) 是否正常。
*   **重置世界 (Reset World)**:
    *   **一键重置**：清空数据库，删除所有存档，仅保留初始物种。
    *   **选项**：支持保留存档文件 (`keep_saves`) 或地图演化历史 (`keep_map`)。
    *   *对应后端接口*: `POST /api/admin/reset`
*   **地形沙盒 (Terrain Sandbox)**:
    *   独立运行地形演化模拟，不影响主游戏进度。
    *   实时查看 AI 生成的地质事件日志。
    *   *对应后端接口*: `POST /api/admin/simulate-terrain`

### 6.2 命令行脚本 (Legacy Scripts)
虽然推荐使用前端面板，但 `scripts/` 目录下仍保留了对应的 Python 脚本，供 CI/CD 或无头模式下使用：

*   `scripts/health_check.py`: 命令行版的系统健康检查。
*   `scripts/reset_world.py`: 命令行版的重置工具。
*   `scripts/simulate_terrain.py`: 命令行版的地形演化模拟器。

## 7. 开发指南

### 7.1 如何新增一种环境压力？
1.  在 `backend/app/schemas/requests.py` 的 `PressureConfig` 中定义。
2.  在 `backend/app/services/environment_system.py` 中添加解析逻辑。
3.  在 `backend/app/services/mortality_engine.py` 中添加该压力对死亡率的影响公式。

### 7.2 如何调整 AI 的创造力？
*   修改 `backend/app/ai/prompts/` 下的模板。
*   在 `data/settings.json` 中调整 `temperature` 参数。

### 7.3 AI 模型配置 (Model Router)
系统支持多模型路由，可在 `.env` 中配置：
*   `AI_BASE_URL`: 兼容 OpenAI 接口的 API 地址（如本地 vLLM 或第三方服务）。
*   `AI_API_KEY`: 对应的 API Key。
*   **路由逻辑**: `backend/app/ai/model_router.py` 负责将不同任务（如 `narrative`, `speciation`）分发给不同的模型配置。

### 7.4 调试建议
*   **日志**：系统日志输出在 `data/logs/simulation.log`，包含详细的决策过程。
*   **可视化**：使用前端的“族谱树”功能，可以直观地看到一次代码修改对物种演化路径的影响。
