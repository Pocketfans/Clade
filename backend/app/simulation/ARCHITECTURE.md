# 插件化模拟引擎架构文档

## 目录

1. [整体架构概览](#整体架构概览)
2. [四层架构详解](#四层架构详解)
3. [流水线阶段说明](#流水线阶段说明)
4. [如何添加新的 Stage](#如何添加新的-stage)
5. [配置系统](#配置系统)
6. [模式系统](#模式系统)
7. [调试与性能分析](#调试与性能分析)
8. [插件开发指南](#插件开发指南)

---

## 整体架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Layer (FastAPI)                       │
│                     routes.py / admin_routes.py                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                           │
│  ┌─────────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ SimulationEngine │──│   Pipeline  │──│ SimulationContext   │  │
│  └─────────────────┘  └─────────────┘  └─────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                     Stage Pipeline                           ││
│  │  [Init]→[Pressures]→[Map]→[Tectonic]→[Species]→[FoodWeb]→...││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Domain Services Layer                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ Environment  │ │   Species    │ │         AI/ML            │ │
│  │  Services    │ │  Services    │ │       Services           │ │
│  │              │ │              │ │                          │ │
│  │ • MapEvol    │ │ • Mortality  │ │ • AIPressureResponse    │ │
│  │ • Tectonic   │ │ • Migration  │ │ • EmbeddingIntegration  │ │
│  │ • Vegetation │ │ • Speciation │ │ • ModelRouter           │ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Repository Layer                             │
│  ┌───────────────────┐ ┌───────────────────┐ ┌─────────────────┐│
│  │ environment_repo  │ │   species_repo    │ │  history_repo   ││
│  └───────────────────┘ └───────────────────┘ └─────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Model Layer                                 │
│    Species, Tile, Habitat, MapState, TurnReport, ...            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四层架构详解

### 1. 接口与调度层 (Orchestration Layer)

| 组件 | 文件 | 职责 |
|------|------|------|
| `SimulationEngine` | `engine.py` | 核心调度器，持有所有服务引用 |
| `SimulationContext` | `context.py` | 回合内数据共享上下文 |
| `Pipeline` | `pipeline.py` | 流水线执行器 |
| `Stage` | `stages.py` | 阶段基类和具体实现 |

### 2. 领域服务层 (Domain Services)

#### 环境/地图服务
- `MapEvolutionService`: 地图阶段演进
- `TectonicIntegration`: 板块构造系统
- `vegetation_cover_service`: 植被覆盖更新

#### 物种服务
- `MortalityEngine`: 死亡率计算
- `TileBasedMortalityEngine`: 地块级死亡率
- `MigrationAdvisor`: 迁徙规划
- `SpeciationService`: 物种分化
- `FoodWebManager`: 食物网维护

#### AI/ML 服务
- `AIPressureResponseService`: AI 压力评估
- `EmbeddingIntegrationService`: 向量嵌入集成

### 3. 数据访问层 (Repository Layer)

| 仓储 | 职责 |
|------|------|
| `environment_repository` | 地图、地块、栖息地存取 |
| `species_repository` | 物种 CRUD |
| `history_repository` | 历史记录 |
| `genus_repository` | 属级操作 |

### 4. 领域模型层 (Model Layer)

- `Species`: 物种实体
- `Tile`: 地块
- `Habitat`: 栖息地
- `MapState`: 地图状态
- `TurnReport`: 回合报告

---

## 流水线阶段说明

### 阶段执行顺序

| 顺序 | 名称 | 输入 | 输出 | 说明 |
|------|------|------|------|------|
| 0 | `init` | - | - | 清理服务缓存 |
| 10 | `parse_pressures` | `command.pressures` | `ctx.pressures`, `ctx.modifiers` | 解析环境压力 |
| 20 | `map_evolution` | `ctx.modifiers` | `ctx.map_changes`, `ctx.current_map_state` | 地图演化 |
| 25 | `tectonic_movement` | `ctx.modifiers` | `ctx.tectonic_result` | 板块运动 |
| 30 | `fetch_species` | - | `ctx.species_batch`, `ctx.all_species` | 获取物种 |
| 35 | `food_web` | `ctx.all_species` | `ctx.food_web_analysis` | 食物网维护 |
| 40 | `tiering_and_niche` | `ctx.species_batch` | `ctx.tiered`, `ctx.niche_metrics` | 分层分析 |
| 50 | `preliminary_mortality` | `ctx.tiered` | `ctx.preliminary_mortality` | 初步死亡率 |
| 60 | `migration` | `ctx.preliminary_mortality` | `ctx.migration_events`, `ctx.migration_count` | 迁徙执行 |
| 80 | `final_mortality` | `ctx.species_batch` | `ctx.combined_results` | 最终死亡率 |
| 85 | `ai_status_eval` | `ctx.combined_results` | `ctx.ai_status_evals` | AI 评估 |
| 90 | `population_update` | `ctx.combined_results` | `ctx.new_populations` | 种群更新 |
| 120 | `ai_parallel_tasks` | - | `ctx.adaptation_events`, `ctx.branching_events` | AI 并行任务 |
| 140 | `build_report` | all | `ctx.report` | 构建报告 |
| 170 | `save_history` | `ctx.report` | - | 保存历史 |

---

## 如何添加新的 Stage

### 步骤 1: 创建 Stage 类

```python
from app.simulation.stages import BaseStage
from app.simulation.stage_config import register_stage

@register_stage("my_custom_stage")
class MyCustomStage(BaseStage):
    """我的自定义阶段"""
    
    def __init__(self, my_param: float = 1.0):
        # order 决定执行顺序
        super().__init__(order=75, name="自定义阶段")
        self.my_param = my_param
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        # 1. 从 ctx 读取输入
        species = ctx.species_batch
        
        # 2. 执行逻辑
        for sp in species:
            # ... 处理逻辑
            pass
        
        # 3. 写回 ctx
        ctx._plugin_data['my_result'] = result
        
        # 4. 发送事件（可选）
        ctx.emit_event("my_event", "处理完成", "自定义")
```

### 步骤 2: 注册到配置

在 `stage_config.yaml` 中添加：

```yaml
- name: my_custom_stage
  enabled: true
  order: 75
  params:
    my_param: 2.0
```

### 步骤 3: 导入模块

确保在 `__init__.py` 或启动时导入模块：

```python
import app.simulation.plugin_stages  # 自动注册
```

---

## 配置系统

### YAML 配置文件结构

```yaml
# stage_config.yaml

# 当前模式
mode: standard

# 模式定义
modes:
  minimal:
    description: "极简模式"
    stages:
      - name: init
        enabled: true
        order: 0
      # ...
  
  standard:
    description: "标准模式"
    stages:
      # ...
```

### 编程式配置

```python
from app.simulation.stage_config import (
    load_stage_config_from_yaml,
    create_stage_config_from_engine_flags,
)

# 从 YAML 加载
configs = load_stage_config_from_yaml(mode="standard")

# 从开关创建
config = create_stage_config_from_engine_flags(
    use_tectonic=True,
    use_ai_pressure=False,
)
```

---

## 模式系统

### 可用模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `minimal` | 仅核心功能 | 快速测试、性能基准 |
| `standard` | 推荐设置 | 日常使用 |
| `full` | 全功能 | 完整体验 |
| `debug` | 调试模式 | 开发、问题排查 |

### 切换模式

**方法 1: 修改配置文件**

```yaml
mode: debug
```

**方法 2: 代码指定**

```python
configs = load_stage_config_from_yaml(mode="debug")
```

---

## 调试与性能分析

### 启用性能分析

1. 使用 `debug` 模式
2. 查看日志中的性能表格

```
┌────────────────────────────────────────┬────────────┬────────┐
│ Stage                                  │ Time (ms)  │ Status │
├────────────────────────────────────────┼────────────┼────────┤
│ ai_parallel_tasks                      │    1234.56 │   ✅   │
│ final_mortality                        │     456.78 │   ✅   │
│ ...                                    │            │        │
├────────────────────────────────────────┼────────────┼────────┤
│ TOTAL                                  │    2345.67 │        │
└────────────────────────────────────────┴────────────┴────────┘
```

### 单阶段调试

可以只启用特定阶段进行调试：

```yaml
stages:
  - name: init
    enabled: true
  - name: fetch_species
    enabled: true
  - name: my_debug_target
    enabled: true
  # 其他全部禁用
```

---

## 插件开发指南

### Stage 接口契约

#### 必须遵守的规则

1. **只通过 ctx 通信**：禁止使用全局变量或模块级状态
2. **只读取需要的字段**：不要访问不相关的 ctx 字段
3. **明确写回字段**：修改后的数据必须写回 ctx
4. **不修改 engine 状态**：engine 只用于访问服务

#### 输入/输出字段

```python
# ✅ 正确：从 ctx 读取输入
species = ctx.species_batch

# ✅ 正确：写回 ctx
ctx.my_result = result

# ❌ 错误：修改 engine
engine.some_counter += 1

# ❌ 错误：使用全局变量
global_state['key'] = value
```

#### 异常处理

```python
async def execute(self, ctx, engine):
    try:
        # 主逻辑
        pass
    except SomeExpectedException as e:
        # 记录日志，继续流水线
        logger.warning(f"Expected error: {e}")
    except CriticalException as e:
        # 重新抛出，中断流水线
        logger.error(f"Critical error: {e}")
        raise
```

### 最佳实践

1. **保持阶段独立**：一个阶段只做一件事
2. **合理设置 order**：考虑依赖关系
3. **使用日志**：方便调试
4. **发送事件**：让前端知道进度
5. **写测试**：验证行为正确性

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2024-11 | 初始插件化架构 |

---

*文档最后更新：自动生成*



