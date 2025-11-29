# 第三阶段完成报告

**Pipeline 流水线系统实现**

---

## 1. 当前流水线结构

### 1.1 Stage 列表（完整）

| 顺序 | Stage 名称 | 配置键名 | 说明 |
|------|-----------|----------|------|
| 0 | 回合初始化 | `init` | 清理缓存，准备上下文 |
| 10 | 解析环境压力 | `parse_pressures` | 解析压力配置 |
| 20 | 地图演化 | `map_evolution` | 温度/海平面变化 |
| 25 | 板块构造运动 | `tectonic_movement` | 板块移动与地形变化 |
| 30 | 获取物种列表 | `fetch_species` | 加载物种数据 |
| 35 | 食物网维护 | `food_web` | 更新捕食关系 |
| 40 | 物种分层与生态位 | `tiering_and_niche` | 分类为 Critical/Focus/Background |
| 50 | 初步死亡率评估 | `preliminary_mortality` | 迁徙前死亡率计算 |
| 55 | 猎物分布更新 | `prey_distribution` | 更新猎物密度缓存 |
| 60 | 迁徙执行 | `migration` | 规划并执行迁徙 |
| 65 | 被动扩散 | `dispersal` | 物种自然扩散 |
| 66 | 饥饿迁徙 | `hunger_migration` | 消费者追踪猎物 |
| 70 | 后迁徙生态位 | `post_migration_niche` | 重新分析生态位 |
| 80 | 最终死亡率评估 | `final_mortality` | 迁徙后死亡率计算 |
| 85 | AI状态评估 | `ai_status_eval` | AI 评估物种状态 |
| 86 | 分化数据传递 | `speciation_data_transfer` | 传递数据给分化服务 |
| 90 | 种群更新 | `population_update` | 应用死亡和繁殖 |
| 95 | 基因激活 | `gene_activation` | 激活潜在基因 |
| 100 | 基因流动 | `gene_flow` | 种群间基因交流 |
| 105 | 遗传漂变 | `genetic_drift` | 小种群随机漂变 |
| 110 | 自动杂交 | `auto_hybridization` | 同域物种杂交 |
| 115 | 亚种晋升 | `subspecies_promotion` | 亚种晋升为物种 |
| 120 | AI并行任务 | `ai_parallel_tasks` | 叙事生成、适应、分化 |
| 130 | 背景物种管理 | `background_management` | 大灭绝检测与重现 |
| 140 | 构建报告 | `build_report` | 生成回合报告 |
| 150 | 保存地图快照 | `save_map_snapshot` | 保存栖息地分布 |
| 155 | 植被覆盖更新 | `vegetation_cover` | 更新地块植被 |
| 160 | 保存种群快照 | `save_population_snapshot` | 保存种群数据 |
| 165 | Embedding集成 | `embedding_hooks` | 分类学更新 |
| 170 | 保存历史记录 | `save_history` | 保存回合历史 |
| 175 | 导出数据 | `export_data` | 导出 CSV/JSON |
| 180 | 最终化 | `finalize` | 更新回合计数器 |

### 1.2 依赖关系图示例

```
Stage 依赖关系图:
==================================================

[  0] 回合初始化
      → 输出字段: (无)

[ 10] 解析环境压力
      ← 依赖阶段: 回合初始化
      → 输出字段: pressures, modifiers, major_events

[ 20] 地图演化
      ← 依赖阶段: 解析环境压力
      → 输出字段: current_map_state, map_changes, temp_delta, sea_delta

[ 30] 获取物种列表
      ← 依赖阶段: 地图演化
      → 输出字段: all_species, species_batch, extinct_codes

... (更多阶段) ...

[180] 最终化
      ← 依赖阶段: 导出数据
==================================================
```

---

## 2. 已有模式列表

### 2.1 minimal（极简模式）

- **描述**: 仅保留最基础生态循环
- **适用场景**: 快速测试、性能基准
- **启用阶段**: 14 个核心阶段
- **禁用功能**: AI、Embedding、板块、杂交、遗传漂变

**参数配置**:
- 回合时长: 0.5s
- 压力缩放: 0.8
- 物种上限: 100
- 分化上限/回合: 2

### 2.2 standard（标准模式）

- **描述**: 推荐的日常使用模式
- **适用场景**: 正常游戏、演示
- **启用阶段**: 22 个阶段
- **禁用功能**: AI状态评估、Embedding、自动杂交

**参数配置**:
- 回合时长: 1.0s
- 压力缩放: 1.0
- 物种上限: 300
- 分化上限/回合: 5

### 2.3 full（全功能模式）

- **描述**: 所有功能启用
- **适用场景**: 完整体验、研究分析
- **启用阶段**: 全部 30+ 阶段
- **禁用功能**: 无

**参数配置**:
- 回合时长: 2.0s
- 压力缩放: 1.0
- 物种上限: 500
- 分化上限/回合: 10
- 自动快照: 每 50 回合

### 2.4 debug（调试模式）

- **描述**: 开发调试专用
- **适用场景**: 问题排查、性能分析
- **启用阶段**: 全部阶段 + 性能分析阶段
- **特殊功能**: 
  - 详细日志输出
  - Context 变化追踪
  - 性能表格输出

**参数配置**:
- 回合时长: 0.5s
- 日志详细度: 3 (DEBUG)
- 性能分析: 启用
- 自动快照: 每 10 回合

---

## 3. 回归测试结果摘要

### 3.1 测试框架

- **RegressionTestRunner**: 对比新旧引擎输出
- **QuickConsistencyChecker**: 快速一致性检查
- **generate_regression_report()**: 生成详细报告

### 3.2 验证指标

| 指标 | 阈值 | 说明 |
|------|------|------|
| 种群差异 | ≤ 5% | 同一物种种群数量差异 |
| 生物量差异 | ≤ 5% | 总生物量差异 |
| 灭绝事件匹配 | 100% | 灭绝物种必须完全一致 |
| 分化事件匹配 | 100% | 分化事件必须完全一致 |

### 3.3 测试方法

```python
# 运行回归测试
from app.simulation.regression_test import RegressionTestRunner

runner = RegressionTestRunner(seed=42)
# 1. 运行旧版引擎
old_snapshots = await runner.run_engine_with_snapshots(old_engine, command)
# 2. 运行新版引擎（Pipeline 模式）
new_snapshots = await runner.run_engine_with_snapshots(new_engine, command)
# 3. 对比结果
result = runner.compare_snapshots(old_snapshots, new_snapshots)
print(generate_regression_report([result]))
```

### 3.4 当前状态

- ✅ Pipeline 架构实现完成
- ✅ 所有 Stage 实现就位
- ✅ 依赖验证通过
- ⏳ 完整回归测试待运行（需要数据库环境）

---

## 4. 调试工具和局部执行能力

### 4.1 局部执行

```python
from app.simulation.pipeline import Pipeline, PipelineConfig

# 只执行单个阶段
config = PipelineConfig(
    only_stage="迁徙执行",
    debug_mode=True,
)

# 指定起止阶段
config = PipelineConfig(
    start_stage="物种分层与生态位",
    stop_stage="最终死亡率评估",
    debug_mode=True,
)
```

### 4.2 Debug 模式功能

- **Context 变化追踪**: 每个阶段执行前后对比 Context 字段变化
- **性能表格**: 按耗时排序的阶段性能表
- **依赖图输出**: 启动时打印完整依赖关系图

### 4.3 日志过滤

```python
from app.simulation.logging_config import configure_log_filter, LogCategory

# 只看迁徙相关日志
configure_log_filter(
    allowed_categories={LogCategory.MIGRATION},
    min_level="INFO",
)

# 排除 AI 阶段日志
configure_log_filter(
    excluded_stages={"AI状态评估", "AI叙事生成"},
)
```

---

## 5. 插件开发指南位置

文档位置: `backend/app/simulation/PLUGIN_GUIDE.md`

### 5.1 主要内容

1. **快速开始**: 最小 Stage 模板
2. **接口详解**: Stage 协议、依赖声明
3. **Context 使用**: 读取/写入数据
4. **注册与配置**: 装饰器注册、YAML 配置
5. **日志规范**: StageLogger 使用
6. **测试指南**: 单元测试模板

### 5.2 最小模板

```python
@register_stage("my_custom_stage")
class MyCustomStage(BaseStage):
    def __init__(self):
        super().__init__(order=75, name="我的自定义阶段")
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"获取物种列表"},
            writes_fields={"_plugin_my_result"},
        )
    
    async def execute(self, ctx, engine):
        result = len(ctx.species_batch) * 2
        ctx._plugin_data["my_result"] = result
```

---

## 6. 文件结构

```
backend/app/simulation/
├── __init__.py          # 模块导出
├── engine.py            # 引擎主类（含 Pipeline 集成）
├── context.py           # SimulationContext
├── stages.py            # 所有 Stage 实现 (1800+ 行)
├── pipeline.py          # Pipeline 执行器
├── stage_config.py      # StageLoader + 配置系统
├── stage_config.yaml    # 模式配置
├── plugin_stages.py     # 示例插件
├── regression_test.py   # 回归测试
├── snapshot.py          # 快照系统
├── logging_config.py    # 日志配置
├── cli.py               # 命令行接口
├── ARCHITECTURE.md      # 架构文档
├── PLUGIN_GUIDE.md      # 插件开发指南
├── STAGE_CONTRACT.md    # Stage 接口契约
└── tests/
    ├── conftest.py      # 测试夹具
    ├── test_pipeline.py # Pipeline 测试
    ├── test_ai_stages.py
    ├── test_ecology_stages.py
    └── test_environment_stages.py
```

---

## 7. 下阶段建议方向

### 7.1 性能优化

1. **并行阶段执行**: 识别无依赖的阶段组，并行执行
2. **增量计算**: 只对变化的物种重新计算
3. **缓存优化**: 跨回合缓存静态数据

### 7.2 可观察性增强

1. **实时仪表盘**: Web UI 展示流水线状态
2. **指标导出**: Prometheus/Grafana 集成
3. **分布式追踪**: OpenTelemetry 支持

### 7.3 场景系统

1. **预设场景**: 灭绝事件、物种入侵、气候变化
2. **场景序列化**: 保存和分享实验配置
3. **A/B 测试**: 并行运行不同配置进行对比

### 7.4 API 完善

1. **REST API 扩展**: 暴露更多控制接口
2. **WebSocket 增强**: 更细粒度的事件推送
3. **GraphQL**: 灵活的数据查询

---

## 8. 使用示例

### 8.1 使用 Pipeline 模式运行

```python
from app.simulation.engine import SimulationEngine
from app.schemas.requests import TurnCommand

# 创建引擎
engine = SimulationEngine(...)

# 使用 Pipeline 模式运行 10 回合
command = TurnCommand(pressures=[], rounds=10)
reports = await engine.run_turns_async(
    command,
    use_pipeline=True,
    mode="standard"
)

# 获取性能指标
metrics = engine.get_pipeline_metrics()
print(metrics.get_performance_table())
```

### 8.2 切换模式

```python
# 切换到 debug 模式
engine.set_mode("debug")

# 运行单个回合并查看详细日志
report = await engine.run_turn_with_pipeline(command, mode="debug")

# 获取依赖关系图
print(engine.get_pipeline_dependency_graph())
```

### 8.3 CLI 使用

```bash
# 运行标准模式 10 回合
python -m app.simulation.cli --mode standard --turns 10

# 调试模式，固定种子
python -m app.simulation.cli --mode debug --turns 5 --seed 42

# 列出所有可用模式
python -m app.simulation.cli --list-modes

# 列出已注册阶段
python -m app.simulation.cli --list-stages
```

---

**报告生成时间**: 2025-11

**状态**: ✅ 第三阶段完成

