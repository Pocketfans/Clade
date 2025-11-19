# 后端架构与模块参考手册

> **Backend Architecture & Module Reference**

本文档是 EvoSandbox 后端系统的核心技术蓝图。鉴于后端包含 30+ 个服务模块、复杂的混合演化引擎以及 AI 编排系统，本手册旨在帮助开发者理解系统的**分层架构**、**数据流向**以及**各模块的职责边界**。

---

## 1. 系统分层架构 (Layered Architecture)

后端采用经典的领域驱动设计 (DDD) 分层风格，确保规则逻辑与基础设施分离。

```mermaid
graph TD
    Client[前端 Client] --> API[API Layer (FastAPI)]
    
    subgraph Backend Core
        API --> Engine[Simulation Engine (Orchestrator)]
        
        Engine --> Services[Service Layer (Business Logic)]
        Engine --> AI[AI Layer (Model Router)]
        
        Services --> Repos[Repository Layer (Data Access)]
        Services --> AI
        
        Repos --> DB[(SQLite / SQLModel)]
    end
    
    style Engine fill:#f9f,stroke:#333,stroke-width:2px
    style Services fill:#bbf,stroke:#333,stroke-width:2px
```

### 1.1 接口层 (API Layer)
- **位置**: `backend/app/api/`
- **职责**: 处理 HTTP 请求，验证输入 (Pydantic)，将请求转发给 Engine 或 Service，格式化响应。
- **原则**: **不包含业务逻辑**。只做“收发员”。

### 1.2 引擎层 (Engine Layer)
- **位置**: `backend/app/simulation/`
- **核心**: `SimulationEngine`
- **职责**: **时间的主宰**。管理回合循环 (Turn Loop)，按严格顺序调度各个 Service（环境 -> 地形 -> 死亡 -> 繁殖 -> 演化）。它是整个系统的“心脏”。

### 1.3 服务层 (Service Layer) - *最庞大的部分*
- **位置**: `backend/app/services/`
- **职责**: **规则的执行者**。实现了所有硬编码的生态学规律。
- **关键服务**:
    - `MortalityEngine`: 死亡判官（基于压力计算死亡率）。
    - `TrophicLevelCalculator`: 能量金字塔构建者。
    - `TerrainEvolutionService`: 地质变迁模拟器。
    - `SpeciationService`: 物种分化控制器（混合架构的典型代表）。

### 1.4 AI 层 (AI Layer)
- **位置**: `backend/app/ai/`
- **职责**: **创意的源泉**。管理 Prompt 模板，通过 `ModelRouter` 智能分发请求（如将简单的分类任务交给 gpt-4o-mini，将复杂的叙事交给 gpt-4o）。

### 1.5 仓储层 (Repository Layer)
- **位置**: `backend/app/repositories/`
- **职责**: **数据的管家**。封装所有数据库操作，确保 Service 层不直接接触 SQL 语句。

---

## 2. 核心机制详解

### 2.1 混合架构的实现 (The Hybrid Implementation)
我们如何在代码层面落实 "规则约束 AI"？

1.  **前置约束 (Pre-Constraint)**: 
    - 在调用 AI 生成新物种前，`TraitConfig` 服务会计算当前营养级的属性上限（如 T1 物种的总属性点不能超过 30）。这些限制会作为 Prompt 的一部分发送给 AI。
2.  **AI 生成 (Generation)**:
    - `ModelRouter` 调用 LLM，返回 JSON 格式的结构化数据（如 `structural_innovations`）。
3.  **后置校验 (Post-Validation)**:
    - `SpeciationService` 接收 AI 返回的数据，再次运行校验逻辑。如果 AI 生成的数值超标，会被强制修正（Clamping）或拒绝。

### 2.2 演化数据流 (Evolutionary Data Flow)
一个典型的“回合”数据流向：
1.  **Input**: 前端发送 `TurnCommand` (包含压力配置)。
2.  **Environment**: `EnvironmentSystem` 解析压力，更新全局温度/海平面。
3.  **Terrain**: `TerrainEvolutionService` 根据板块阶段修改 `MapTile` 数据。
4.  **Life**: `MortalityEngine` 读取所有 `Species`，计算存活率。
5.  **Narrative**: `ReportBuilder` 收集上述所有事件，投喂给 AI 生成战报。
6.  **Output**: 打包为 `TurnReport` 返回前端，并写入 `data/exports/`。

---

## 3. 模块详细文档索引

为了应对庞大的代码库，我们将详细文档按功能域拆分：

| 模块域 | 说明 | 关键涉及文件 |
| :--- | :--- | :--- |
| **[Simulation (模拟核心)](modules/simulation/README.md)** | 引擎循环、压力队列、回合结算机制 | `engine.py`, `pressure.py` |
| **[Species (物种系统)](modules/species/README.md)** | 物种数据结构、谱系管理、分化逻辑 | `species.py`, `speciation.py` |
| **[Environment (环境系统)](modules/environment/README.md)** | 地图生成、地形演化算法、气候模型 | `map_manager.py`, `terrain_evolution.py` |
| **[Analytics & AI (分析与智能)](modules/analytics-ai/README.md)** | 生态位分析、AI 模型路由、Embedding | `niche.py`, `model_router.py` |
| **[Saves & Ops (运维管理)](modules/saves-ops/README.md)** | 存档管理、数据导出、日志系统 | `save_manager.py`, `exporter.py` |
| **[Config & UI (配置系统)](modules/config-ui/README.md)** | 系统配置、UI 状态同步 | `config.py` |
| **[Frontend Integration (前端集成)](modules/frontend-integration/README.md)** | 前端服务层对接指南 | `api.ts` |

---

## 4. 开发规范

- **新增 Service**: 必须在 `backend/app/services/__init__.py` 导出，并在 `SimulationEngine` 中注册。
- **修改模型**: 若修改 `models/species.py`，需同步更新 `schemas/responses.py` 和前端类型定义。
- **AI Prompt**: 所有 Prompt 必须放在 `backend/app/ai/prompts/`，严禁硬编码在 Service 中。

> **注意**：如果你是前端开发者，请直接查看根目录下的 **[`API_GUIDE.md`](../../API_GUIDE.md)** 获取接口契约。
