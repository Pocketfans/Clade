# Stage 接口契约说明

本文档定义了 Stage 系统的输入/输出契约，确保所有阶段行为一致、可预测。

---

## 1. Stage 协议定义

每个 Stage 必须满足以下协议：

```python
class Stage(Protocol):
    @property
    def name(self) -> str:
        """阶段名称（用于日志和调试）"""
        ...
    
    @property
    def order(self) -> int:
        """阶段顺序（数值越小越先执行）"""
        ...
    
    @property
    def is_async(self) -> bool:
        """是否为异步阶段"""
        ...
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        """执行阶段逻辑"""
        ...
```

---

## 2. SimulationContext 字段规范

### 2.1 只读字段（不应修改）

| 字段 | 类型 | 说明 |
|------|------|------|
| `turn_index` | `int` | 当前回合索引 |
| `command` | `TurnCommand` | 回合命令 |
| `event_callback` | `Callable` | 事件回调（使用 `emit_event` 方法） |

### 2.2 阶段输入/输出映射

#### 压力解析阶段 (`parse_pressures`)
```
输入: ctx.command.pressures
输出: ctx.pressures       (list[PressureConfig])
      ctx.modifiers       (dict[str, float])
      ctx.major_events    (list[MajorPressureEvent])
```

#### 地图演化阶段 (`map_evolution`)
```
输入: ctx.modifiers, ctx.major_events
输出: ctx.current_map_state  (MapState)
      ctx.map_changes        (list[MapChange])
      ctx.temp_delta         (float)
      ctx.sea_delta          (float)
```

#### 板块运动阶段 (`tectonic_movement`)
```
输入: ctx.modifiers, ctx.current_map_state
输出: ctx.tectonic_result   (TectonicStepResult | None)
      ctx.modifiers         (更新压力反馈)
```

#### 获取物种阶段 (`fetch_species`)
```
输入: -
输出: ctx.all_species    (list[Species])
      ctx.species_batch  (list[Species]) - 仅存活物种
      ctx.extinct_codes  (set[str])
```

#### 食物网阶段 (`food_web`)
```
输入: ctx.all_species
输出: ctx.food_web_analysis  (FoodWebAnalysis)
      ctx.species_batch      (可能更新)
```

#### 分层与生态位阶段 (`tiering_and_niche`)
```
输入: ctx.species_batch
输出: ctx.tiered        (TieringResult)
      ctx.all_habitats  (list[Habitat])
      ctx.all_tiles     (list[Tile])
      ctx.niche_metrics (dict[str, NicheMetrics])
```

#### 初步死亡率阶段 (`preliminary_mortality`)
```
输入: ctx.tiered, ctx.modifiers, ctx.niche_metrics
输出: ctx.trophic_interactions  (dict[str, float])
      ctx.preliminary_mortality (list[MortalityResult])
```

#### 迁徙阶段 (`migration`)
```
输入: ctx.preliminary_mortality, ctx.modifiers, ctx.major_events
输出: ctx.migration_events        (list[MigrationEvent])
      ctx.migration_count         (int)
      ctx.symbiotic_follow_count  (int)
      ctx.cooldown_species        (set[str])
```

#### 最终死亡率阶段 (`final_mortality`)
```
输入: ctx.species_batch, ctx.modifiers, ctx.niche_metrics
输出: ctx.critical_results    (list[MortalityResult])
      ctx.focus_results       (list[MortalityResult])
      ctx.background_results  (list[MortalityResult])
      ctx.combined_results    (list[MortalityResult])
```

#### AI 状态评估阶段 (`ai_status_eval`)
```
输入: ctx.combined_results, ctx.modifiers
输出: ctx.ai_status_evals      (dict[str, SpeciesStatusEval])
      ctx.emergency_responses  (list[dict])
      ctx.pressure_context     (str)
```

#### 种群更新阶段 (`population_update`)
```
输入: ctx.combined_results, ctx.niche_metrics
输出: ctx.new_populations       (dict[str, int])
      ctx.reproduction_results  (dict[str, int])
```

#### AI 并行任务阶段 (`ai_parallel_tasks`)
```
输入: ctx.critical_results, ctx.focus_results, ctx.modifiers
输出: ctx.narrative_results   (list[NarrativeResult])
      ctx.adaptation_events   (list[dict])
      ctx.branching_events    (list[BranchingEvent])
```

#### 背景物种管理阶段 (`background_management`)
```
输入: ctx.background_results, ctx.combined_results
输出: ctx.background_summary    (list[BackgroundSummary])
      ctx.mass_extinction       (bool)
      ctx.reemergence_events    (list[ReemergenceEvent])
```

#### 构建报告阶段 (`build_report`)
```
输入: 所有上述字段
输出: ctx.report              (TurnReport)
      ctx.species_snapshots   (list[SpeciesSnapshot])
      ctx.ecosystem_metrics   (EcosystemMetrics)
```

---

## 3. 禁止的行为

### ❌ 禁止使用全局变量通信

```python
# 错误示例
GLOBAL_STATE = {}

class BadStage(BaseStage):
    async def execute(self, ctx, engine):
        GLOBAL_STATE['key'] = value  # ❌ 禁止
```

### ❌ 禁止修改 engine 状态

```python
class BadStage(BaseStage):
    async def execute(self, ctx, engine):
        engine.turn_counter += 1  # ❌ 禁止
        engine._some_flag = True  # ❌ 禁止
```

### ❌ 禁止直接调用其他阶段

```python
class BadStage(BaseStage):
    async def execute(self, ctx, engine):
        other_stage = SomeOtherStage()
        await other_stage.execute(ctx, engine)  # ❌ 禁止
```

### ❌ 禁止修改不属于自己的字段

```python
class MortalityStage(BaseStage):
    async def execute(self, ctx, engine):
        ctx.migration_events = []  # ❌ 不属于死亡率阶段
```

---

## 4. 异常处理规范

### 4.1 可恢复异常（记录并继续）

```python
async def execute(self, ctx, engine):
    try:
        result = some_operation()
    except ValueError as e:
        logger.warning(f"[{self.name}] 可恢复错误: {e}")
        # 使用默认值或跳过
        result = default_value
```

### 4.2 严重异常（中断流水线）

```python
async def execute(self, ctx, engine):
    if not ctx.species_batch:
        raise RuntimeError("没有物种数据，无法继续")
```

### 4.3 超时处理

```python
async def execute(self, ctx, engine):
    try:
        result = await asyncio.wait_for(
            long_running_task(),
            timeout=60
        )
    except asyncio.TimeoutError:
        logger.error(f"[{self.name}] 超时")
        # 使用 fallback 或标记失败
```

---

## 5. 日志规范

### 使用模块 logger

```python
logger = logging.getLogger(__name__)

class MyStage(BaseStage):
    async def execute(self, ctx, engine):
        logger.info(f"[{self.name}] 开始处理")
        logger.debug(f"[{self.name}] 详细信息: {data}")
        logger.warning(f"[{self.name}] 警告: {issue}")
        logger.error(f"[{self.name}] 错误: {error}")
```

### 日志级别

| 级别 | 用途 |
|------|------|
| `DEBUG` | 详细调试信息 |
| `INFO` | 正常操作记录 |
| `WARNING` | 可恢复的问题 |
| `ERROR` | 错误但不中断 |

---

## 6. 事件发送规范

### 使用 `ctx.emit_event()`

```python
async def execute(self, ctx, engine):
    # 阶段开始
    ctx.emit_event("stage", f"🔄 {self.name}", "流水线")
    
    # 进度更新
    ctx.emit_event("info", f"处理了 {count} 个物种", "物种")
    
    # 警告
    ctx.emit_event("warning", "检测到异常情况", "警告")
    
    # 自定义事件
    ctx.emit_event("my_event", "自定义消息", "自定义分类",
                   extra_data=value)
```

---

## 7. 第三方插件约束

### 7.1 注册方式

```python
from app.simulation.stage_config import register_stage

@register_stage("my_plugin_stage")
class MyPluginStage(BaseStage):
    ...
```

### 7.2 命名规范

- 使用 `snake_case`
- 添加前缀避免冲突: `myplugin_feature`

### 7.3 依赖声明

在文档字符串中声明依赖：

```python
class MyStage(BaseStage):
    """我的阶段
    
    依赖:
        - 必须在 fetch_species 之后运行
        - 需要 ctx.species_batch 已填充
    
    输出:
        - ctx._plugin_data['my_result']
    """
```

### 7.4 版本兼容性

```python
class MyStage(BaseStage):
    # 声明最低 API 版本
    MIN_API_VERSION = "1.0"
    
    async def execute(self, ctx, engine):
        # 检查兼容性
        if not hasattr(ctx, 'required_field'):
            raise RuntimeError("需要更新 SimulationContext")
```

---

## 8. 测试要求

每个 Stage 应有对应的单元测试：

```python
import pytest
from app.simulation.context import SimulationContext
from app.simulation.stages import MyStage

@pytest.fixture
def mock_context():
    ctx = SimulationContext(turn_index=0)
    ctx.species_batch = [...]
    return ctx

@pytest.fixture
def mock_engine():
    # 创建模拟 engine
    ...

@pytest.mark.asyncio
async def test_my_stage(mock_context, mock_engine):
    stage = MyStage()
    await stage.execute(mock_context, mock_engine)
    
    # 验证输出
    assert mock_context.some_field is not None
```

---

## 版本

- **契约版本**: 1.0
- **最后更新**: 2025-11

