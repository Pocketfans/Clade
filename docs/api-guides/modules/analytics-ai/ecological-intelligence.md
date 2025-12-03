# 生态智能体（Ecological Intelligence）

> 统一的 AI 评估系统，负责物种分档、LLM 评估和数值修正应用。

## 概述

生态智能体是 Clade 的核心 AI 模块，每回合自动对物种进行评估并应用数值修正。设计原则：
- **Embedding 广覆盖**：快速预测，全局适用
- **LLM 局部深度**：仅对高优先级物种调用 LLM
- **统一修正入口**：所有数值调整通过 `ModifierApplicator` 完成

## 架构图

```
Turn Execution
     ↓
┌────────────────────────────────────────────────────────────┐
│              EcologicalIntelligenceStage                   │
├────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐    ┌─────────────────────────────┐  │
│  │EcologicalIntelligence│ │      LLMOrchestrator        │  │
│  │                  │    │                             │  │
│  │ • calculate_risk │    │ • build_prompt_a/b          │  │
│  │ • calculate_impact│   │ • call_llm_batch (parallel) │  │
│  │ • calculate_potential│ │ • parse_llm_response        │  │
│  │ • partition_species│  │                             │  │
│  └──────────────────┘    └─────────────────────────────┘  │
│              ↓                        ↓                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              BiologicalAssessment                    │  │
│  │  • mortality_modifier  • r_adjust  • k_adjust        │  │
│  │  • migration_bias  • speciation_signal               │  │
│  │  • ecological_fate  • narrative  • headline          │  │
│  └─────────────────────────────────────────────────────┘  │
│                          ↓                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              ModifierApplicator                      │  │
│  │  apply(species_id, base_value, adjustment_type)      │  │
│  │  → 统一数值修正入口，自动 clamp 到安全范围            │  │
│  └─────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
                          ↓
              存入 SimulationContext
              供后续 Stage 使用
```

## 分档策略

物种按 **risk × 0.4 + impact × 0.3 + potential × 0.3** 计算优先级后分档：

| 档次 | 数量限制 | 模型 | Prompt | 输出 |
|------|---------|------|--------|------|
| **A档** | Top 5 | 大模型 (GPT-4/Claude) | 详细（含生态位、历史、叙事要求） | 完整评估 + 叙事 |
| **B档** | 6-20 | 小模型 (GPT-3.5) | 精简（仅物种列表） | 数值修正 |
| **C档** | 其余 | 无 | 无 | 使用默认值 |

### 评分维度

| 维度 | 权重 | 输入因子 | 说明 |
|------|------|---------|------|
| **Risk** | 0.4 | 死亡率、种群规模、适配度 | 越高越危险 |
| **Impact** | 0.3 | 生物量占比、营养级、食物网中心度 | 灭绝影响范围 |
| **Potential** | 0.3 | 遗传多样性、生态位独特性、种群规模 | 演化潜力 |

## BiologicalAssessment 结构

LLM 输出解析后的统一结构，所有字段有默认值和安全范围：

```python
@dataclass
class BiologicalAssessment:
    species_id: int
    lineage_code: str
    
    # 核心修正因子
    mortality_modifier: float = 1.0      # [0.3, 1.8]
    r_adjust: float = 0.0                # [-0.3, 0.3]
    k_adjust: float = 0.0                # [-0.5, 0.5]
    
    # 行为修正
    migration_bias: float = 0.0          # [-1, 1]
    
    # 演化信号
    speciation_signal: float = 0.0       # [0, 1]
    ecological_fate: str = "stable"      # thriving/stable/declining/endangered
    evolution_direction: List[str] = []
    
    # 叙事（仅 A 档）
    narrative: str = ""
    headline: str = ""
    mood: str = "neutral"                # positive/neutral/negative/critical
    
    # 元数据
    tier: AssessmentTier = AssessmentTier.C
    confidence: float = 0.5              # [0, 1]
```

## ModifierApplicator 使用方式

业务 Stage 不直接读取 `BiologicalAssessment`，而是通过 `ModifierApplicator` 获取修正后的值：

```python
# 在任意 Stage 中
class PopulationUpdateStage(BaseStage):
    async def execute(self, ctx: SimulationContext, engine) -> None:
        modifier = ctx.modifier_applicator
        
        for species in ctx.species_batch:
            code = species.lineage_code
            
            # 获取修正后的值
            adjusted_r = modifier.apply(code, base_r, "reproduction_r")
            adjusted_k = modifier.apply(code, base_k, "carrying_capacity")
            adjusted_mortality = modifier.apply(code, base_mort, "mortality")
            
            # 查询生态命运
            fate = modifier.get_ecological_fate(code)
            
            # 判断是否应该分化
            if modifier.should_speciate(code, threshold=0.7):
                # 触发物种分化逻辑
                pass
```

### 支持的修正类型

| 类型 | 枚举值 | 公式 | 说明 |
|------|--------|------|------|
| 死亡率 | `mortality` | `base × modifier` | 乘数 [0.3, 1.8] |
| 繁殖率 | `reproduction_r` | `base + adjust` | 加法 [-0.3, 0.3] |
| 承载力 | `carrying_capacity` | `base × (1 + adjust)` | 比例 [-0.5, 0.5] |
| 迁徙 | `migration` | `base × (1 + bias × 0.5)` | 概率调整 |
| 分化 | `speciation` | `base + signal × 0.1` | 概率加成 |
| 气候耐受 | `climate_tolerance` | `base + bandwidth` | 带宽调整 |
| 捕食脆弱性 | `predation` | `base × (1 + vuln × 0.3)` | 被捕食概率 |

## 监控与降级

`IntelligenceMonitor` 提供流水线监控和降级策略：

```python
from app.services.intelligence import get_monitor

monitor = get_monitor()

# 开始回合
monitor.start_turn(turn_index=10, total_species=50)

# 记录 LLM 调用
monitor.record_llm_call(success=True, tokens=150)
monitor.record_llm_call(success=False, error="Timeout")

# 检查是否应降级
if monitor.should_fallback():
    # 使用默认评估，跳过 LLM 调用
    assessments = orchestrator.create_default_assessments(codes)

# 获取统计
stats = monitor.get_summary()
# {
#   "health_status": "healthy",
#   "total_turns": 10,
#   "total_llm_calls": 50,
#   "recent_avg_llm_success_rate": 0.95,
#   "should_fallback": false
# }
```

### 健康状态

| 状态 | 条件 | 行为 |
|------|------|------|
| `HEALTHY` | 正常运行 | 完整 LLM 调用 |
| `DEGRADED` | LLM 失败率 > 50% 或最近有失败 | 警告日志，继续运行 |
| `UNHEALTHY` | 连续 3 次失败 或 最近 10 回合多次异常 | 自动降级，跳过 LLM |

## 配置参数

在 `intelligence/config.py` 中配置：

```python
@dataclass
class IntelligenceConfig:
    # 分档数量
    top_a_count: int = 5
    top_b_count: int = 15
    
    # 评分权重
    risk_weight: float = 0.4
    impact_weight: float = 0.3
    potential_weight: float = 0.3
    
    # 阈值
    priority_threshold: float = 0.3
    death_rate_critical_threshold: float = 0.5
    death_rate_warning_threshold: float = 0.3
    population_critical_threshold: int = 100
    
    # LLM 设置
    enable_llm_calls: bool = True
    llm_timeout_seconds: float = 30.0
    use_parallel_batches: bool = True
    
    # 修正范围
    mortality_mod_range: tuple = (0.3, 1.8)
    r_adjust_range: tuple = (-0.3, 0.3)
    k_adjust_range: tuple = (-0.5, 0.5)
    migration_bias_range: tuple = (-1.0, 1.0)
    
    # 降级默认值
    fallback_mortality_modifier: float = 1.0
    fallback_r_adjust: float = 0.0
    fallback_k_adjust: float = 0.0
```

## Stage 配置

在 `stage_config.yaml` 中启用：

```yaml
stages:
  ecological_intelligence:
    order: 82
    enabled: true
    class: "EcologicalIntelligenceStage"
    params:
      enable_llm_calls: true
      top_a_count: 5
      top_b_count: 15

# 禁用旧的 AI 阶段（避免双改）
  ai_status_eval:
    enabled: false
  ai_parallel_tasks:
    enabled: false
  adaptation:
    enabled: false
  speciation:
    enabled: false
```

## 测试

```bash
cd backend
pytest app/services/intelligence/tests -v

# 输出
# 57 passed
# - test_scoring.py (17 tests)
# - test_partition.py (9 tests)
# - test_assessment.py (10 tests)
# - test_modifier.py (14 tests)
# - test_integration.py (7 tests)
```

## 扩展指南

### 新增修正类型

1. 在 `AdjustmentType` 枚举中添加新类型
2. 在 `ModifierApplicator.apply()` 中添加处理逻辑
3. 在 `BiologicalAssessment` 中添加对应字段
4. 更新 LLM Prompt 模板
5. 添加单元测试

### 调整分档策略

1. 修改 `IntelligenceConfig` 的 `risk_weight`/`impact_weight`/`potential_weight`
2. 调整 `top_a_count`/`top_b_count`
3. 修改 `calculate_risk()`/`calculate_impact()`/`calculate_potential()` 的权重

### 自定义 Prompt

编辑 `llm_orchestrator.py` 中的：
- `SYSTEM_PROMPT_A` / `SYSTEM_PROMPT_B`
- `USER_PROMPT_TEMPLATE_A` / `USER_PROMPT_TEMPLATE_B`

## 相关文档

- [AI 路由](./ai-routing.md) - ModelRouter 配置
- [生态位分析](./niche-compare.md) - Embedding 相似度
- [开发文档](../../../../DEV_DOC.md) - 整体架构








