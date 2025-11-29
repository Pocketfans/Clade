# Stage 插件开发指南

本文档面向希望为模拟引擎编写自定义 Stage 插件的第三方开发者。

---

## 目录

1. [快速开始](#1-快速开始)
2. [Stage 接口详解](#2-stage-接口详解)
3. [使用 SimulationContext](#3-使用-simulationcontext)
4. [访问服务与仓储](#4-访问服务与仓储)
5. [依赖声明](#5-依赖声明)
6. [注册与配置](#6-注册与配置)
7. [日志规范](#7-日志规范)
8. [测试指南](#8-测试指南)
9. [示例插件](#9-示例插件)
10. [常见问题](#10-常见问题)

---

## 1. 快速开始

### 最小 Stage 示例

```python
from app.simulation.stages import BaseStage, StageDependency
from app.simulation.stage_config import register_stage

@register_stage("my_custom_stage")
class MyCustomStage(BaseStage):
    """自定义阶段示例"""
    
    def __init__(self):
        # order 决定执行顺序，name 用于日志
        super().__init__(order=75, name="我的自定义阶段")
    
    def get_dependency(self) -> StageDependency:
        """声明依赖关系"""
        return StageDependency(
            requires_stages={"获取物种列表"},  # 依赖的前置阶段
            requires_fields={"species_batch"},  # 需要的 Context 字段
            writes_fields={"_plugin_my_result"},  # 本阶段写入的字段
        )
    
    async def execute(self, ctx, engine):
        """执行阶段逻辑"""
        # 从 Context 读取数据
        species = ctx.species_batch
        
        # 处理逻辑
        result = len(species) * 2
        
        # 写入结果（使用 _plugin_ 前缀避免冲突）
        ctx._plugin_data["my_result"] = result
        
        # 发送事件
        ctx.emit_event("info", f"处理了 {len(species)} 个物种", "自定义")
```

### 启用插件

在 `stage_config.yaml` 中添加：

```yaml
modes:
  standard:
    stages:
      # ... 其他阶段 ...
      - name: my_custom_stage
        enabled: true
        order: 75
```

---

## 2. Stage 接口详解

### 必须实现的属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 阶段名称，用于日志和调试 |
| `order` | `int` | 执行顺序，数值越小越先执行 |
| `is_async` | `bool` | 是否为异步阶段（通常为 True） |

### 必须实现的方法

```python
async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
    """执行阶段逻辑
    
    Args:
        ctx: 回合上下文，包含所有共享数据
        engine: 模拟引擎，提供服务和仓储访问
    
    Raises:
        可以抛出异常中断流水线（严重错误时）
    """
    pass
```

### 推荐实现的方法

```python
def get_dependency(self) -> StageDependency:
    """声明依赖关系（强烈建议实现）"""
    return StageDependency(
        requires_stages=set(),    # 依赖的阶段名称
        requires_fields=set(),    # 需要的 Context 字段
        writes_fields=set(),      # 写入的 Context 字段
        optional_stages=set(),    # 可选依赖
    )
```

---

## 3. 使用 SimulationContext

### 读取数据

```python
# 基本信息
turn = ctx.turn_index           # 当前回合
command = ctx.command           # 回合命令

# 环境数据
modifiers = ctx.modifiers       # 压力修饰符
map_state = ctx.current_map_state  # 地图状态

# 物种数据
all_species = ctx.all_species   # 所有物种（含灭绝）
species = ctx.species_batch     # 存活物种
extinct = ctx.extinct_codes     # 灭绝物种代码

# 生态数据
habitats = ctx.all_habitats     # 栖息地列表
tiles = ctx.all_tiles           # 地块列表
niche = ctx.niche_metrics       # 生态位指标
```

### 写入数据

```python
# 使用 _plugin_data 存储插件数据（避免字段冲突）
if not hasattr(ctx, '_plugin_data'):
    ctx._plugin_data = {}

ctx._plugin_data['my_result'] = value

# 或者直接写入已定义的字段（如果符合契约）
ctx.modifiers['my_modifier'] = 1.5
```

### 发送事件

```python
# 阶段开始
ctx.emit_event("stage", f"🔄 {self.name}", "流水线")

# 信息更新
ctx.emit_event("info", "处理完成", "物种")

# 警告
ctx.emit_event("warning", "检测到异常", "警告")

# 自定义事件（带额外数据）
ctx.emit_event("custom", "消息内容", "分类", 
               extra_key="extra_value")
```

---

## 4. 访问服务与仓储

### 通过 Engine 访问

```python
async def execute(self, ctx, engine):
    # 仓储
    from app.repositories.species_repository import species_repository
    from app.repositories.environment_repository import environment_repository
    
    # 通过仓储访问数据库
    species = species_repository.list_species()
    tiles = environment_repository.list_tiles()
    
    # 引擎内置服务
    engine.mortality           # 死亡率计算
    engine.migration_advisor   # 迁徙建议
    engine.reproduction_service  # 繁殖服务
    engine.speciation          # 分化服务
```

### 注意事项

1. **只读访问**：尽量通过 Context 读取数据，避免直接修改仓储
2. **事务边界**：引擎会在回合结束时统一提交更改
3. **缓存**：某些服务有缓存，注意使用 `clear_cache()` 方法

---

## 5. 依赖声明

### StageDependency 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `requires_stages` | `Set[str]` | 必须先执行的阶段名称 |
| `requires_fields` | `Set[str]` | 需要已填充的 Context 字段 |
| `writes_fields` | `Set[str]` | 本阶段写入的 Context 字段 |
| `optional_stages` | `Set[str]` | 可选依赖（存在时才检查顺序） |

### 示例

```python
def get_dependency(self) -> StageDependency:
    return StageDependency(
        requires_stages={"解析环境压力", "获取物种列表"},
        requires_fields={"modifiers", "species_batch"},
        writes_fields={"_plugin_weather_effect"},
        optional_stages={"板块构造运动"},
    )
```

### 验证

流水线构建时会自动验证依赖。debug 模式下会输出依赖图：

```
Stage 依赖关系图:
==================================================
[  0] 回合初始化
      → 输出字段: (无)

[ 10] 解析环境压力
      ← 依赖阶段: 回合初始化
      → 输出字段: pressures, modifiers, major_events

[ 75] 我的自定义阶段
      ← 依赖阶段: 解析环境压力, 获取物种列表
      ← 需要字段: modifiers, species_batch
      → 输出字段: _plugin_my_result
==================================================
```

---

## 6. 注册与配置

### 方法 1：装饰器注册

```python
from app.simulation.stage_config import register_stage

@register_stage("my_stage")
class MyStage(BaseStage):
    ...
```

### 方法 2：手动注册

```python
from app.simulation.stage_config import stage_registry

stage_registry.register("my_stage", MyStage)
```

### 配置启用/禁用

在 `stage_config.yaml` 中：

```yaml
modes:
  standard:
    stages:
      - name: my_stage
        enabled: true   # 启用
        order: 75       # 执行顺序
        params:         # 可选参数
          threshold: 0.5
```

---

## 7. 日志规范

### 使用 StageLogger

```python
from app.simulation.logging_config import get_stage_logger, LogCategory

class MyStage(BaseStage):
    async def execute(self, ctx, engine):
        log = get_stage_logger(self.name, LogCategory.SPECIES)
        
        log.info("开始处理")
        log.debug(f"物种数: {len(ctx.species_batch)}")
        log.warning("检测到异常情况")
        log.error("处理失败")
```

### 日志类别

| 类别 | 用途 |
|------|------|
| `SYSTEM` | 系统级操作 |
| `ENVIRONMENT` | 环境变化 |
| `GEOLOGY` | 地质/板块 |
| `SPECIES` | 物种相关 |
| `MIGRATION` | 迁徙 |
| `MORTALITY` | 死亡率 |
| `REPRODUCTION` | 繁殖 |
| `SPECIATION` | 分化 |
| `AI` | AI 相关 |
| `PERFORMANCE` | 性能统计 |

---

## 8. 测试指南

### 单元测试模板

```python
import pytest
from unittest.mock import MagicMock
from app.simulation.context import SimulationContext

@pytest.fixture
def mock_context():
    ctx = SimulationContext(turn_index=0)
    ctx.species_batch = [MagicMock(lineage_code="SP001")]
    ctx.modifiers = {"temperature": 1.0}
    return ctx

@pytest.fixture
def mock_engine():
    return MagicMock()

@pytest.mark.asyncio
async def test_my_stage(mock_context, mock_engine):
    from my_plugin import MyStage
    
    stage = MyStage()
    await stage.execute(mock_context, mock_engine)
    
    # 验证输出
    assert "_plugin_my_result" in mock_context._plugin_data
```

### 运行测试

```bash
cd backend
pytest app/simulation/tests/test_my_plugin.py -v
```

---

## 9. 示例插件

### 已有示例

项目中已包含以下示例插件供参考：

| 插件 | 文件 | 功能 |
|------|------|------|
| `SimpleWeatherStage` | `plugin_stages.py` | 简单天气扰动 |
| `EcoMetricsStage` | `plugin_stages.py` | 生态健康度计算 |
| `SimpleMortalityStage` | `plugin_stages.py` | 简化死亡率 |
| `StageProfilingStartStage` | `plugin_stages.py` | 性能分析开始 |
| `StageProfilingEndStage` | `plugin_stages.py` | 性能分析结束 |

### 查看源码

```python
# backend/app/simulation/plugin_stages.py

@register_stage("simple_weather")
class SimpleWeatherStage(BaseStage):
    """简单天气扰动阶段
    
    随机对部分地块施加温度扰动，模拟局部天气变化。
    """
    
    def __init__(self, trigger_chance: float = 0.3):
        super().__init__(order=22, name="简单天气扰动")
        self.trigger_chance = trigger_chance
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"地图演化"},
            requires_fields={"current_map_state"},
            writes_fields=set(),
        )
    
    async def execute(self, ctx, engine):
        import random
        if random.random() > self.trigger_chance:
            return
        
        # ... 天气处理逻辑 ...
```

---

## 10. 常见问题

### Q: 如何避免与其他插件冲突？

使用 `_plugin_` 前缀存储数据：

```python
ctx._plugin_data['myplugin_result'] = value
```

### Q: 如何处理可选依赖？

在 `get_dependency()` 中使用 `optional_stages`，然后在 `execute()` 中检查：

```python
if ctx.tectonic_result is not None:
    # 使用板块数据
    pass
```

### Q: 如何在不同模式下有不同行为？

检查模式参数：

```python
params = getattr(engine, '_mode_params', None)
if params and params.log_verbosity >= 2:
    # 详细日志模式
    pass
```

### Q: 如何调试我的插件？

1. 使用 debug 模式：`--mode debug`
2. 使用部分执行：只运行特定阶段
3. 检查 Context diff 输出

```python
from app.simulation.pipeline import PipelineConfig

config = PipelineConfig(
    debug_mode=True,
    only_stage="我的自定义阶段",
)
```

---

## 更多资源

- [Stage 接口契约](./STAGE_CONTRACT.md)
- [架构文档](./ARCHITECTURE.md)
- [API 指南](../../API_GUIDE.md)

---

*文档版本: 1.0 | 最后更新: 2025-11*



