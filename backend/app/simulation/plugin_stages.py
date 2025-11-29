"""
Plugin Stages - 插件阶段示例

该模块包含用于验证插件系统的示例阶段：
- StageProfilingStartStage: 性能分析开始
- StageProfilingEndStage: 性能分析结束，输出表格
- SimpleWeatherStage: 简单天气扰动
- EcoMetricsStage: 生态健康度计算

这些阶段展示了如何创建新的插件，并验证插件系统的易用性。
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .stages import BaseStage, StageOrder
from .stage_config import register_stage

if TYPE_CHECKING:
    from .context import SimulationContext
    from .engine import SimulationEngine

logger = logging.getLogger(__name__)


# ============================================================================
# 性能分析阶段
# ============================================================================

@register_stage("stage_profiling_start")
class StageProfilingStartStage(BaseStage):
    """性能分析开始阶段
    
    在流水线开始时记录时间戳，用于后续计算总耗时。
    """
    
    def __init__(self, log_level: str = "DEBUG"):
        super().__init__(order=1, name="性能分析开始")
        self.log_level = log_level
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        # 在 context 中存储开始时间
        if not hasattr(ctx, '_profiling_data'):
            ctx._profiling_data = {}
        
        ctx._profiling_data['start_time'] = time.perf_counter()
        ctx._profiling_data['stage_times'] = []
        
        logger.info(f"[Profiling] 开始性能分析，回合 {ctx.turn_index}")


@register_stage("stage_profiling_end")
class StageProfilingEndStage(BaseStage):
    """性能分析结束阶段
    
    在流水线结束时输出性能表格。
    """
    
    def __init__(self, output_format: str = "table"):
        super().__init__(order=179, name="性能分析结束")
        self.output_format = output_format
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        if not hasattr(ctx, '_profiling_data') or 'start_time' not in ctx._profiling_data:
            logger.warning("[Profiling] 未找到分析数据")
            return
        
        total_time = (time.perf_counter() - ctx._profiling_data['start_time']) * 1000
        
        logger.info(f"[Profiling] 回合 {ctx.turn_index} 总耗时: {total_time:.2f}ms")
        
        # 输出关键统计
        if ctx.species_batch:
            logger.info(f"[Profiling] 物种数: {len(ctx.species_batch)}")
        if ctx.combined_results:
            avg_death_rate = sum(r.death_rate for r in ctx.combined_results) / len(ctx.combined_results)
            logger.info(f"[Profiling] 平均死亡率: {avg_death_rate:.2%}")
        if ctx.migration_count:
            logger.info(f"[Profiling] 迁徙次数: {ctx.migration_count}")
        if ctx.branching_events:
            logger.info(f"[Profiling] 分化事件: {len(ctx.branching_events)}")


# ============================================================================
# 简单天气阶段
# ============================================================================

@dataclass
class WeatherEvent:
    """天气事件"""
    event_type: str  # "heat_wave", "cold_snap", "drought", "flood"
    intensity: float  # 0.0 - 1.0
    affected_tiles: list[int] = field(default_factory=list)
    description: str = ""


@register_stage("simple_weather")
class SimpleWeatherStage(BaseStage):
    """简单天气阶段
    
    每回合对部分地块施加随机温度扰动，模拟天气变化。
    这是一个独立的插件示例，不依赖复杂的服务。
    
    配置参数:
        - trigger_chance: 天气事件触发概率 (0.0-1.0)
        - max_temp_delta: 最大温度变化 (°C)
        - max_affected_ratio: 最大影响地块比例 (0.0-1.0)
    """
    
    def __init__(
        self,
        trigger_chance: float = 0.3,
        max_temp_delta: float = 5.0,
        max_affected_ratio: float = 0.2,
    ):
        super().__init__(order=22, name="简单天气")  # 在地图演化之后
        self.trigger_chance = trigger_chance
        self.max_temp_delta = max_temp_delta
        self.max_affected_ratio = max_affected_ratio
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..repositories.environment_repository import environment_repository
        
        # 随机决定是否触发天气事件
        if random.random() > self.trigger_chance:
            logger.debug("[Weather] 本回合无天气事件")
            return
        
        # 获取地块
        tiles = ctx.all_tiles or environment_repository.list_tiles()
        if not tiles:
            return
        
        # 随机选择事件类型
        event_types = [
            ("heat_wave", 1.0),   # 热浪：升温
            ("cold_snap", -1.0),  # 寒流：降温
        ]
        event_type, temp_sign = random.choice(event_types)
        
        # 计算影响范围
        affected_count = max(1, int(len(tiles) * random.random() * self.max_affected_ratio))
        affected_tiles = random.sample(tiles, affected_count)
        
        # 计算温度变化
        temp_delta = random.uniform(1.0, self.max_temp_delta) * temp_sign
        
        # 应用变化
        updated_tiles = []
        for tile in affected_tiles:
            if hasattr(tile, 'temperature'):
                old_temp = tile.temperature
                tile.temperature = max(-50, min(50, old_temp + temp_delta))
                updated_tiles.append(tile)
        
        if updated_tiles:
            environment_repository.upsert_tiles(updated_tiles)
        
        # 记录事件
        event = WeatherEvent(
            event_type=event_type,
            intensity=abs(temp_delta) / self.max_temp_delta,
            affected_tiles=[t.id for t in affected_tiles if hasattr(t, 'id')],
            description=f"{'热浪' if temp_sign > 0 else '寒流'}，温度变化 {temp_delta:+.1f}°C",
        )
        
        # 发送事件
        ctx.emit_event(
            "weather",
            f"🌤️ {event.description}，影响 {len(affected_tiles)} 个地块",
            "天气"
        )
        
        logger.info(f"[Weather] {event.description}，影响 {len(affected_tiles)} 个地块")


# ============================================================================
# 生态健康度计算阶段
# ============================================================================

@dataclass
class EcoMetrics:
    """生态系统健康度指标"""
    shannon_diversity: float = 0.0  # Shannon多样性指数
    evenness: float = 0.0           # 均匀度
    trophic_balance: float = 0.0    # 营养级平衡度
    ecosystem_health: float = 0.0    # 综合健康度
    producer_ratio: float = 0.0      # 生产者比例
    consumer_ratio: float = 0.0      # 消费者比例
    decomposer_ratio: float = 0.0    # 分解者比例


@register_stage("eco_metrics")
class EcoMetricsStage(BaseStage):
    """生态健康度计算阶段
    
    计算本回合的生态系统健康度指标：
    - Shannon多样性指数
    - 营养级均匀度
    - 生态系统稳定性评分
    
    这是一个纯分析性质的阶段，不修改任何数据。
    """
    
    def __init__(self):
        super().__init__(order=88, name="生态健康度")  # 在死亡率计算之后
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        import math
        
        if not ctx.species_batch:
            return
        
        # 收集种群数据
        populations = []
        trophic_levels = []
        
        for sp in ctx.species_batch:
            if sp.status != "alive":
                continue
            pop = sp.morphology_stats.get("population", 0) or 0
            if pop > 0:
                populations.append(pop)
                trophic_levels.append(sp.trophic_level)
        
        if not populations:
            return
        
        total_pop = sum(populations)
        n_species = len(populations)
        
        # 计算 Shannon 多样性指数
        shannon = 0.0
        for pop in populations:
            if pop > 0:
                p = pop / total_pop
                shannon -= p * math.log(p)
        
        # 计算均匀度 (Pielou's J)
        max_shannon = math.log(n_species) if n_species > 1 else 1.0
        evenness = shannon / max_shannon if max_shannon > 0 else 0.0
        
        # 计算营养级分布
        trophic_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for tl in trophic_levels:
            level = min(5, max(1, int(tl)))
            trophic_counts[level] += 1
        
        # 计算营养级平衡度
        # 理想分布: T1 > T2 > T3 > T4 > T5
        expected_ratios = [0.4, 0.3, 0.15, 0.1, 0.05]
        actual_ratios = [trophic_counts[i] / n_species for i in range(1, 6)]
        
        trophic_balance = 1.0 - sum(abs(e - a) for e, a in zip(expected_ratios, actual_ratios)) / 2
        
        # 计算综合健康度
        ecosystem_health = (shannon / 3.0 + evenness + trophic_balance) / 3.0
        ecosystem_health = min(1.0, max(0.0, ecosystem_health))
        
        # 构建指标
        metrics = EcoMetrics(
            shannon_diversity=shannon,
            evenness=evenness,
            trophic_balance=trophic_balance,
            ecosystem_health=ecosystem_health,
            producer_ratio=trophic_counts[1] / n_species if n_species > 0 else 0,
            consumer_ratio=(trophic_counts[2] + trophic_counts[3] + trophic_counts[4]) / n_species if n_species > 0 else 0,
            decomposer_ratio=trophic_counts[5] / n_species if n_species > 0 else 0,
        )
        
        # 存储到 context
        if not hasattr(ctx, '_plugin_data'):
            ctx._plugin_data = {}
        ctx._plugin_data['eco_metrics'] = metrics
        
        # 发送事件
        health_emoji = "🌿" if ecosystem_health > 0.7 else "🍂" if ecosystem_health > 0.4 else "🏜️"
        ctx.emit_event(
            "eco_health",
            f"{health_emoji} 生态健康度: {ecosystem_health:.0%} (多样性: {shannon:.2f}, 均匀度: {evenness:.0%})",
            "生态"
        )
        
        logger.info(
            f"[EcoMetrics] 健康度: {ecosystem_health:.0%}, "
            f"Shannon: {shannon:.2f}, 均匀度: {evenness:.0%}, "
            f"营养平衡: {trophic_balance:.0%}"
        )


# ============================================================================
# 简单死亡率阶段（替代复杂的 tile-based mortality）
# ============================================================================

@register_stage("simple_mortality")
class SimpleMortalityStage(BaseStage):
    """简单死亡率阶段
    
    使用固定比例或线性模型计算死亡率，作为复杂死亡率系统的简化替代。
    适用于快速测试或极简模式。
    
    配置参数:
        - base_rate: 基础死亡率 (0.0-1.0)
        - pressure_sensitivity: 压力敏感度系数
    """
    
    def __init__(
        self,
        base_rate: float = 0.05,
        pressure_sensitivity: float = 0.1,
    ):
        super().__init__(order=80, name="简单死亡率")
        self.base_rate = base_rate
        self.pressure_sensitivity = pressure_sensitivity
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from .species import MortalityResult
        
        if not ctx.species_batch:
            return
        
        # 计算总压力
        total_pressure = sum(abs(v) for v in ctx.modifiers.values()) if ctx.modifiers else 0
        
        # 简单死亡率 = 基础率 + 压力 * 敏感度
        pressure_modifier = min(0.5, total_pressure * self.pressure_sensitivity)
        
        results = []
        for sp in ctx.species_batch:
            if sp.status != "alive":
                continue
            
            initial_pop = int(sp.morphology_stats.get("population", 0) or 0)
            
            # 根据营养级调整死亡率
            trophic_modifier = (sp.trophic_level - 1) * 0.02  # 高营养级更脆弱
            
            death_rate = min(0.9, self.base_rate + pressure_modifier + trophic_modifier)
            death_rate = max(0.01, death_rate)  # 至少1%死亡率
            
            deaths = int(initial_pop * death_rate)
            survivors = initial_pop - deaths
            
            result = MortalityResult(
                species=sp,
                initial_population=initial_pop,
                deaths=deaths,
                survivors=survivors,
                death_rate=death_rate,
                notes=[f"简单死亡率模型, 压力修正: {pressure_modifier:.2f}"],
                niche_overlap=0.0,
                resource_pressure=pressure_modifier,
                is_background=getattr(sp, 'is_background', False),
                tier="simple",
            )
            results.append(result)
        
        # 存储结果
        ctx.combined_results = results
        ctx.critical_results = [r for r in results if r.death_rate > 0.3]
        ctx.focus_results = [r for r in results if 0.1 < r.death_rate <= 0.3]
        ctx.background_results = [r for r in results if r.death_rate <= 0.1]
        
        logger.info(
            f"[SimpleMortality] 计算了 {len(results)} 个物种的死亡率, "
            f"平均死亡率: {sum(r.death_rate for r in results) / len(results):.2%}"
        )

