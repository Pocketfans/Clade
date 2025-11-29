# SimulationEngine 架构说明

## 概述

`SimulationEngine` 已重构为"瘦中枢"架构，不再承载任何具体业务逻辑。
所有回合业务逻辑已迁移到 **Stage** 和 **Service** 中，
Engine 只负责模式选择和 Pipeline 调度。

**当前代码量：约 320 行**（从原来的 2600+ 行大幅精简）

---

## 核心职责

### 1. 依赖注入
在构造函数中注入各类 service / repository / 配置：

```python
engine = SimulationEngine(
    environment=...,
    mortality=...,
    embeddings=...,
    # ... 其他服务
)
```

### 2. 模式管理
通过 `set_mode()` 切换运行模式：

```python
engine.set_mode("standard")  # 可选: minimal, standard, full, debug
```

### 3. 回合调度
通过 `run_turns_async()` 驱动 Pipeline 执行回合：

```python
reports = await engine.run_turns_async(command)
```

---

## 核心方法列表

| 方法 | 职责 | 说明 |
|------|------|------|
| `__init__()` | 依赖注入 | 接收所有服务和配置 |
| `set_mode(mode)` | 模式切换 | 加载对应模式的 Stage 列表 |
| `run_turns_async(command)` | 回合调度 | 执行多个回合（统一使用 Pipeline）|
| `run_turn_with_pipeline(command)` | 单回合执行 | 使用 Pipeline 执行单个回合 |
| `get_pipeline_metrics()` | 性能指标 | 获取最近一次执行的性能数据 |
| `get_pipeline_dependency_graph()` | 依赖图 | 获取 Stage 依赖关系图 |
| `_emit_event()` | 事件发送 | 发送事件到前端 |
| `update_watchlist()` | 关注列表 | 更新玩家关注的物种列表 |

---

## 服务属性（供 Stage 访问）

Engine 作为服务容器，提供以下属性供 Stage 访问：

| 属性 | 类型 | 用途 |
|------|------|------|
| `trophic_service` | `TrophicInteractionService` | 营养级互动计算 |
| `report_builder` | `ReportBuilder` | 报告叙事生成 |
| `tile_mortality` | `TileBasedMortalityEngine` | 地块死亡率计算 |
| `mortality` | `MortalityEngine` | 传统死亡率计算 |
| `tiering` | `SpeciesTieringService` | 物种分层 |
| `speciation` | `SpeciationService` | 物种分化 |
| `background_manager` | `BackgroundSpeciesManager` | 背景物种管理 |
| `migration_advisor` | `MigrationAdvisor` | 迁徙建议 |
| `niche_analyzer` | `NicheAnalyzer` | 生态位分析 |
| `food_web_manager` | `FoodWebManager` | 食物网维护 |
| `embedding_integration` | `EmbeddingIntegrationService` | Embedding 集成 |

---

## 领域服务（Stage 直接调用）

Stage 现在直接调用这些服务，不再通过 Engine 转发：

| 服务 | 位置 | 职责 | 调用方 Stage |
|------|------|------|-------------|
| `TrophicInteractionService` | `services/species/trophic_interaction.py` | 营养级互动计算 | `PreliminaryMortalityStage` |
| `ExtinctionChecker` | `services/species/extinction_checker.py` | 灭绝条件检测 | `PopulationUpdateStage` |
| `InterventionService` | `services/species/intervention.py` | 干预状态管理 | `HabitatAdjustmentStage` |
| `ReemergenceService` | `services/species/reemergence.py` | 物种重现评估 | `BackgroundManagementStage` |
| `TurnReportService` | `services/analytics/turn_report.py` | 回合报告构建 | `BuildReportStage` |
| `PopulationSnapshotService` | `services/analytics/population_snapshot.py` | 种群快照保存 | `PopulationSnapshotStage` |
| `EcosystemMetricsService` | `services/analytics/ecosystem_metrics.py` | 生态系统指标 | `TurnReportService` |

---

## 遗留实现

旧版"手写回合逻辑"已迁移到独立文件：

```
backend/app/simulation/legacy_engine.py
```

### LegacyTurnRunner 类

⚠️ **已废弃** - 仅用于回归测试和历史对比

```python
from .legacy_engine import LegacyTurnRunner

runner = LegacyTurnRunner(engine)
reports = await runner.run_turns_legacy(command)
```

---

## 废弃字段

| 字段/参数 | 状态 | 说明 |
|-----------|------|------|
| `use_pipeline` | 废弃 | 始终使用 Pipeline，参数保留但无效 |

---

## 扩展指南

### 添加新业务规则

1. **优先以 Stage 形式加入**
   - 参见 `stages.py` 中的 Stage 示例
   - 参见 `PLUGIN_GUIDE.md` 插件开发指南

2. **或以 Service 形式加入**
   - 在 `services/` 目录创建新服务
   - Stage 直接实例化并调用

3. **不应直接在 Engine 中添加业务逻辑**

### 添加新 Stage

```python
from .stages import BaseStage, StageOrder, StageDependency

class MyNewStage(BaseStage):
    def __init__(self):
        super().__init__(StageOrder.CUSTOM.value, "我的新阶段")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"初始化"},
            writes_fields={"my_new_data"}
        )
    
    async def execute(self, ctx, engine):
        # 业务逻辑
        ctx.my_new_data = ...
```

---

## 文件结构

```
simulation/
├── engine.py              # SimulationEngine（瘦中枢，~320行）
├── legacy_engine.py       # LegacyTurnRunner（遗留实现）
├── stages.py              # Stage 定义
├── pipeline.py            # Pipeline 执行器
├── stage_config.py        # Stage 配置
├── context.py             # SimulationContext
├── ENGINE_ARCHITECTURE.md # Engine 架构（本文件）
├── PLUGIN_GUIDE.md        # 插件开发指南
└── STAGE_CONTRACT.md      # Stage 契约

services/species/
├── trophic_interaction.py # 营养级互动服务
├── extinction_checker.py  # 灭绝检测服务
├── genetic_evolution.py   # 遗传演化服务
├── intervention.py        # 玩家干预服务
├── reemergence.py         # 物种重现服务
└── ...                    # 其他服务

services/analytics/
├── ecosystem_metrics.py   # 生态系统指标服务
├── population_snapshot.py # 种群快照服务
├── turn_report.py         # 回合报告服务
├── report_builder.py      # 报告叙事生成器
└── ...                    # 其他服务
```

---

## 版本历史

- **v5.0** (当前): 完全解耦架构
  - Engine 只有 ~320 行代码
  - 所有业务逻辑在 Stage 和 Service 中
  - Stage 直接调用 Service，无需 Engine 转发
  - 新增服务: `TurnReportService`, `PopulationSnapshotService`, `ReemergenceService`, `EcosystemMetricsService`

- **v4.0**: Pipeline-only 架构
  - `run_turns_async` 统一使用 Pipeline
  - 旧版逻辑迁移到 `legacy_engine.py`
  - Engine 职责收敛为调度器

- **v3.x**: Pipeline + Legacy 混合架构
  - `use_pipeline` 参数控制执行路径
  - 两种路径并存

- **v2.x**: 手写回合逻辑
  - 所有业务逻辑在 `run_turns_async` 中
  - 无 Stage/Pipeline 概念
