"""
张量计算管线阶段

本模块提供使用张量系统的管线阶段：
 - PressureTensorStage: 压力张量化转换（将 ctx.modifiers 转换为张量）
 - TensorMortalityStage: 使用多因子模型计算死亡率
 - TensorDiffusionStage: 使用 HybridCompute 计算种群扩散
 - TensorReproductionStage: 张量繁殖计算
 - TensorCompetitionStage: 张量种间竞争
 - TensorStateSyncStage: 张量状态同步回数据库
 - TensorMetricsStage: 收集和记录张量系统监控指标

张量路径为唯一计算路径，不再回退到旧逻辑。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from .stages import BaseStage, StageOrder, StageDependency
from .constants import get_time_config

if TYPE_CHECKING:
    from .context import SimulationContext
    from .engine import SimulationEngine

logger = logging.getLogger(__name__)


# ============================================================================
# 压力张量化阶段
# ============================================================================

class PressureTensorStage(BaseStage):
    """压力张量化阶段
    
    将 ctx.modifiers 和 ctx.pressures 转换为张量格式的压力叠加层，
    供后续张量死亡率计算使用。
    
    执行顺序：在 ParsePressuresStage (10) 之后，TensorMortalityStage (81) 之前
    
    工作流程：
    1. 从 ctx.modifiers 读取压力修改器
    2. 从 ctx.pressures 读取区域性压力配置
    3. 使用 PressureToTensorBridge 转换为空间张量
    4. 存入 ctx.pressure_overlay
    """
    
    def __init__(self):
        super().__init__(
            StageOrder.PARSE_PRESSURES.value + 1,  # order=11
            "压力张量化"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"解析环境压力"},
            requires_fields={"modifiers", "pressures"},
            writes_fields={"pressure_overlay"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import get_pressure_bridge
        
        bridge = get_pressure_bridge()
        
        # 获取地图尺寸
        map_state = getattr(ctx, "current_map_state", None)
        if map_state is not None:
            H = getattr(map_state, "height", 64)
            W = getattr(map_state, "width", 64)
            map_width = getattr(map_state, "width", 8)
            map_height = getattr(map_state, "height", 8)
        else:
            # 默认尺寸
            H, W = 64, 64
            map_width, map_height = 8, 8
        
        # 获取压力数据
        modifiers = getattr(ctx, "modifiers", {}) or {}
        pressures = getattr(ctx, "pressures", []) or []
        
        # 转换为张量
        overlay = bridge.convert(
            modifiers=modifiers,
            pressures=pressures,
            map_shape=(H, W),
            map_width=map_width,
            map_height=map_height,
        )
        
        # 存入上下文
        ctx.pressure_overlay = overlay
        
        active_str = ", ".join(overlay.active_pressures[:5])
        if len(overlay.active_pressures) > 5:
            active_str += f" 等{len(overlay.active_pressures)}种"
        
        logger.info(
            f"[压力张量化] 完成: {len(overlay.active_pressures)} 种压力, "
            f"总强度={overlay.total_intensity:.1f}, "
            f"激活: {active_str}"
        )


# ============================================================================
# 张量死亡率计算阶段
# ============================================================================

class TensorMortalityStage(BaseStage):
    """张量死亡率计算阶段（多因子版）
    
    使用 MultiFactorMortality 进行多因子死亡率计算，
    综合温度、干旱、毒性、缺氧、直接死亡等多个压力因子。
    
    张量路径为唯一来源，不使用旧回退逻辑。
    
    工作流程：
    1. 从 ctx.tensor_state 获取种群和环境张量
    2. 从 ctx.pressure_overlay 获取压力叠加层
    3. 使用 MultiFactorMortality 计算多因子死亡率
    4. 使用 HybridCompute.apply_mortality() 应用死亡率
    5. 更新 ctx.combined_results 中的死亡率数据
    """
    
    def __init__(self):
        # 在 FinalMortalityStage 之后执行
        super().__init__(
            StageOrder.FINAL_MORTALITY.value + 1,
            "张量死亡率计算"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"最终死亡率评估"},
            requires_fields={"combined_results", "tensor_state"},
            optional_fields={"pressure_overlay"},
            writes_fields={"tensor_state", "tensor_metrics"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import (
            TensorMetrics, 
            get_compute, 
            get_global_collector,
            get_multifactor_mortality,
            PressureChannel,
        )
        
        if not getattr(engine, "_use_tensor_mortality", False):
            raise RuntimeError("张量死亡率被禁用，演化链路无法继续（请启用 use_tensor_mortality）。")
        
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            raise RuntimeError("缺少 tensor_state，张量死亡率无法执行。")
        
        start_time = time.perf_counter()
        balance = engine.tensor_config.balance
        compute = get_compute()
        collector = get_global_collector()
        
        with collector.track_mortality():
            pop = tensor_state.pop.astype(np.float32)
            env = tensor_state.env.astype(np.float32)
            params = tensor_state.species_params.astype(np.float32)
            
            # 获取压力叠加层
            pressure_overlay = getattr(ctx, "pressure_overlay", None)
            if pressure_overlay is not None:
                pressure = pressure_overlay.overlay.astype(np.float32)
                use_multifactor = True
            else:
                # 无压力叠加层时，创建空张量
                S, H, W = pop.shape
                pressure = np.zeros((PressureChannel.NUM_CHANNELS, H, W), dtype=np.float32)
                use_multifactor = False
            
            # 使用多因子死亡率计算
            if use_multifactor and pressure.sum() > 0.1:
                # 有压力时使用多因子模型
                # 从 UI 配置中读取压力桥接参数
                from ..tensor.pressure_bridge import PressureBridgeConfig
                ui_config = getattr(ctx, "ui_config", None)
                if ui_config is not None:
                    bridge_config = PressureBridgeConfig.from_ui_config(ui_config)
                    mortality_calc = get_multifactor_mortality(bridge_config)
                else:
                    mortality_calc = get_multifactor_mortality()
                
                mortality = mortality_calc.compute(
                    pop=pop,
                    env=env,
                    pressure=pressure,
                    params=params,
                    balance_config=balance,
                )
                logger.debug(f"[张量死亡率] 使用多因子模型，压力强度={pressure.sum():.2f}")
            else:
                # 无压力或压力很小时，使用简单温度模型（回退）
                turn_index = getattr(ctx, "turn_index", 0)
                era_factor = max(0.0, turn_index / 100.0)
                
                mortality = compute.mortality(
                    pop, env, params,
                    temp_idx=balance.temp_channel_idx,
                    temp_opt=balance.temp_optimal + balance.temp_optimal_shift_per_100_turns * era_factor,
                    temp_tol=balance.temp_tolerance + balance.temp_tolerance_shift_per_100_turns * era_factor,
                )
                logger.debug("[张量死亡率] 使用简单温度模型（无压力叠加）")
            
            new_pop = compute.apply_mortality(pop, mortality)
            
            tensor_state.pop = new_pop
            ctx.tensor_state = tensor_state
            
            self._sync_mortality_to_results(ctx, mortality, tensor_state)
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(f"[张量死亡率] 完成，耗时 {duration_ms:.1f}ms，后端={compute.backend}")
        
        if ctx.tensor_metrics is None:
            ctx.tensor_metrics = TensorMetrics()
        ctx.tensor_metrics.mortality_time_ms = duration_ms
    
    def _sync_mortality_to_results(
        self,
        ctx: SimulationContext,
        mortality: np.ndarray,
        tensor_state
    ) -> None:
        """将张量死亡率同步到 combined_results"""
        species_map = tensor_state.species_map
        combined_results = getattr(ctx, "combined_results", None) or []
        
        for result in combined_results:
            lineage = result.species.lineage_code
            idx = species_map.get(lineage)
            if idx is not None and idx < mortality.shape[0]:
                # 取该物种的平均死亡率
                species_mortality = mortality[idx]
                mask = species_mortality > 0
                if mask.any():
                    avg_mortality = float(species_mortality[mask].mean())
                    result.death_rate = avg_mortality


# ============================================================================
# 张量种群扩散阶段
# ============================================================================

class TensorDiffusionStage(BaseStage):
    """张量种群扩散阶段
    
    使用 HybridCompute.diffusion() 计算种群的空间扩散。
    模拟物种的自然迁徙和扩张行为。
    
    工作流程：
    1. 从 ctx.tensor_state 获取种群张量
    2. 使用 HybridCompute.diffusion() 计算扩散
    3. 更新 tensor_state.pop
    """
    
    def __init__(self):
        # 在种群更新之后执行
        super().__init__(
            StageOrder.POPULATION_UPDATE.value + 1,
            "张量种群扩散"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"种群更新"},
            requires_fields={"tensor_state"},
            writes_fields={"tensor_state"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import get_compute
        
        # 检查是否启用张量计算
        if not getattr(engine, "_use_tensor_mortality", False):
            raise RuntimeError("张量扩散被禁用，演化链路无法继续。")
        
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            raise RuntimeError("缺少 tensor_state，张量扩散无法执行。")
        
        compute = get_compute()
        
        pop = tensor_state.pop.astype(np.float32)
        balance = engine.tensor_config.balance
        turn_index = getattr(ctx, "turn_index", 0)
        era_factor = max(0.0, turn_index / 100.0)
        
        # 获取时代缩放因子（太古宙=40x, 元古宙=100x, 古生代=2x, 中生代=1x, 新生代=0.5x）
        time_config = get_time_config(turn_index)
        time_scaling = time_config["scaling_factor"]
        
        # 基础扩散率 + 回合增长
        base_diffusion = balance.diffusion_rate + balance.diffusion_rate_growth_per_100_turns * era_factor
        
        # 应用时代缩放：早期时代（太古宙/元古宙）扩散极快
        # 使用平方根缓和极端值，但保持显著差异
        # 太古宙: sqrt(40) ≈ 6.3x, 元古宙: sqrt(100) = 10x
        effective_scaling = max(1.0, time_scaling ** 0.5)
        diffusion_rate = base_diffusion * effective_scaling
        
        # 设置合理上限，避免数值不稳定（最大扩散率 0.8）
        diffusion_rate = min(0.8, max(0.0, diffusion_rate))
        
        new_pop = compute.diffusion(pop, rate=diffusion_rate)
        
        tensor_state.pop = new_pop
        ctx.tensor_state = tensor_state
        
        if time_scaling > 1.5:
            logger.info(f"[张量扩散] {time_config['era_name']}，时代缩放={time_scaling:.1f}x，有效扩散率={diffusion_rate:.3f}")
        else:
            logger.debug(f"[张量扩散] 完成，扩散率={diffusion_rate:.3f}")


# ============================================================================
# 张量繁殖计算阶段
# ============================================================================

class TensorReproductionStage(BaseStage):
    """张量繁殖计算阶段
    
    使用 HybridCompute.reproduction() 计算种群繁殖。
    考虑适应度和承载力约束。
    
    工作流程：
    1. 从 ctx.tensor_state 获取种群和环境张量
    2. 计算适应度张量
    3. 使用 HybridCompute.reproduction() 计算繁殖
    4. 更新 tensor_state.pop
    """
    
    def __init__(self):
        # 在张量扩散之后执行
        super().__init__(
            StageOrder.POPULATION_UPDATE.value + 2,
            "张量繁殖计算"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"张量种群扩散"},
            requires_fields={"tensor_state"},
            writes_fields={"tensor_state"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import get_compute
        
        if not getattr(engine, "_use_tensor_mortality", False):
            raise RuntimeError("张量繁殖被禁用，演化链路无法继续。")
        
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            raise RuntimeError("缺少 tensor_state，张量繁殖无法执行。")
        
        compute = get_compute()
        
        pop = tensor_state.pop.astype(np.float32)
        env = tensor_state.env.astype(np.float32)
        
        S, H, W = pop.shape
        balance = engine.tensor_config.balance
        turn_index = getattr(ctx, "turn_index", 0)
        era_factor = max(0.0, turn_index / 100.0)
        
        # 获取时代缩放因子（太古宙=40x, 元古宙=100x, 古生代=2x, 中生代=1x, 新生代=0.5x）
        time_config = get_time_config(turn_index)
        time_scaling = time_config["scaling_factor"]
        
        temp = env[balance.temp_channel_idx] if env.shape[0] > balance.temp_channel_idx else np.full((H, W), 20.0, dtype=np.float32)
        temp_opt = balance.temp_optimal + balance.temp_optimal_shift_per_100_turns * era_factor
        temp_tol = balance.temp_tolerance + balance.temp_tolerance_shift_per_100_turns * era_factor
        deviation = np.abs(temp - temp_opt)
        base_fitness = np.exp(-deviation / max(1e-5, temp_tol))
        fitness = np.broadcast_to(base_fitness, pop.shape).astype(np.float32)
        
        vegetation = env[4] if env.shape[0] > 4 else np.ones((H, W), dtype=np.float32) * 0.5
        veg_mean = float(vegetation.mean())
        
        # 承载力也随时代缩放：早期时代环境更"空旷"，承载力相对更大
        cap_scaling = max(1.0, time_scaling ** 0.3)  # 缓和缩放，太古宙约3.2x
        cap_multiplier = balance.capacity_multiplier * (1 + balance.veg_capacity_sensitivity * (veg_mean - 0.5)) * cap_scaling
        capacity = (vegetation * cap_multiplier).astype(np.float32)
        
        # 基础出生率 + 回合增长
        base_birth = balance.birth_rate + balance.birth_rate_growth_per_100_turns * era_factor
        
        # 应用时代缩放：早期时代（太古宙/元古宙）繁殖极快
        # 单细胞生物繁殖周期极短，几千万年内可以繁衍天文数字的代数
        # 使用平方根缓和极端值：太古宙 sqrt(40)≈6.3x, 元古宙 sqrt(100)=10x
        effective_scaling = max(1.0, time_scaling ** 0.5)
        birth_rate = base_birth * effective_scaling
        
        # 设置合理上限，避免数值爆炸（最大出生率 2.0）
        birth_rate = min(2.0, max(0.0, birth_rate))
        
        new_pop = compute.reproduction(pop, fitness, capacity, birth_rate)
        
        tensor_state.pop = new_pop
        ctx.tensor_state = tensor_state
        
        if time_scaling > 1.5:
            logger.info(f"[张量繁殖] {time_config['era_name']}，时代缩放={time_scaling:.1f}x，有效出生率={birth_rate:.3f}，承载力缩放={cap_scaling:.2f}x")
        else:
            logger.debug(f"[张量繁殖] 完成，出生率={birth_rate:.3f}")


# ============================================================================
# 张量种间竞争阶段
# ============================================================================

class TensorCompetitionStage(BaseStage):
    """张量种间竞争阶段
    
    使用 HybridCompute.competition() 计算种间竞争效应。
    
    工作流程：
    1. 从 ctx.tensor_state 获取种群张量
    2. 计算适应度
    3. 使用 HybridCompute.competition() 计算竞争
    4. 更新 tensor_state.pop
    """
    
    def __init__(self):
        # 在张量繁殖之后执行
        super().__init__(
            StageOrder.POPULATION_UPDATE.value + 3,
            "张量种间竞争"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"张量繁殖计算"},
            requires_fields={"tensor_state"},
            writes_fields={"tensor_state"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import get_compute
        
        if not getattr(engine, "_use_tensor_mortality", False):
            raise RuntimeError("张量竞争被禁用，演化链路无法继续。")
        
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            raise RuntimeError("缺少 tensor_state，张量竞争无法执行。")
        
        compute = get_compute()
        
        pop = tensor_state.pop.astype(np.float32)
        balance = engine.tensor_config.balance
        turn_index = getattr(ctx, "turn_index", 0)
        era_factor = max(0.0, turn_index / 100.0)
        
        fitness = np.ones_like(pop, dtype=np.float32)
        
        competition_strength = balance.competition_strength - balance.competition_decay_per_100_turns * era_factor
        competition_strength = max(0.0, competition_strength)
        
        new_pop = compute.competition(pop, fitness, strength=competition_strength)
        
        tensor_state.pop = new_pop
        ctx.tensor_state = tensor_state
        
        logger.debug(f"[张量竞争] 完成，竞争强度={competition_strength}")


# ============================================================================
# 张量迁徙计算阶段
# ============================================================================

class TensorMigrationStage(BaseStage):
    """张量迁徙计算阶段
    
    使用 GPU 加速的张量引擎批量计算所有物种的迁徙。
    
    【性能优化核心】
    - 原方案：逐物种循环，~50ms/物种
    - 新方案：全物种并行，~5ms 总计
    - 加速比：10-50x
    
    工作流程：
    1. 从 ctx.tensor_state 获取种群和环境张量
    2. 从 ctx.combined_results 获取死亡率数据
    3. 使用 TensorMigrationEngine 批量计算迁徙
    4. 更新 tensor_state.pop
    """
    
    def __init__(self):
        # 在张量竞争之后执行
        super().__init__(
            StageOrder.POPULATION_UPDATE.value + 4,
            "张量迁徙计算"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"张量种间竞争"},
            requires_fields={"tensor_state", "combined_results"},
            optional_fields={"species_batch"},
            writes_fields={"tensor_state", "tensor_metrics"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import TensorMetrics
        from ..tensor.migration import (
            get_migration_engine,
            extract_species_preferences,
            extract_habitat_mask,
        )
        
        # 检查是否启用张量计算
        if not getattr(engine, "_use_tensor_mortality", False):
            logger.debug("[张量迁徙] 张量计算未启用，跳过")
            return
        
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            logger.warning("[张量迁徙] 缺少 tensor_state，跳过")
            return
        
        start_time = time.perf_counter()
        
        # 获取迁徙引擎
        migration_engine = get_migration_engine()
        
        # 准备数据
        pop = tensor_state.pop.astype(np.float32)
        env = tensor_state.env.astype(np.float32)
        species_map = tensor_state.species_map
        
        S = pop.shape[0]
        if S == 0:
            logger.debug("[张量迁徙] 无物种，跳过")
            return
        
        # 提取死亡率
        death_rates = np.zeros(S, dtype=np.float32)
        combined_results = getattr(ctx, "combined_results", []) or []
        for result in combined_results:
            lineage = result.species.lineage_code
            idx = species_map.get(lineage)
            if idx is not None and idx < S:
                death_rates[idx] = result.death_rate
        
        # 提取物种偏好
        species_batch = getattr(ctx, "species_batch", []) or []
        if species_batch:
            species_prefs = extract_species_preferences(species_batch, species_map)
        else:
            # 默认偏好（全陆生）
            species_prefs = np.zeros((S, 7), dtype=np.float32)
            species_prefs[:, 4] = 1.0  # 陆地
        
        # 生成栖息地掩码
        habitat_mask = extract_habitat_mask(env, species_prefs)
        
        # 执行迁徙计算
        new_pop, metrics = migration_engine.process_migration(
            pop=pop,
            env=env,
            species_prefs=species_prefs,
            death_rates=death_rates,
            habitat_mask=habitat_mask,
        )
        
        # 更新张量状态
        tensor_state.pop = new_pop
        ctx.tensor_state = tensor_state
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # 更新性能指标
        if ctx.tensor_metrics is None:
            ctx.tensor_metrics = TensorMetrics()
        ctx.tensor_metrics.migration_time_ms = duration_ms
        
        logger.info(
            f"[张量迁徙] 完成: {S}物种, {metrics.migrating_species}迁徙, "
            f"耗时={duration_ms:.1f}ms, 后端={metrics.backend}"
        )


# ============================================================================
# 张量监控指标收集阶段
# ============================================================================

class TensorMetricsStage(BaseStage):
    """张量监控指标收集阶段
    
    在回合结束时收集张量系统的性能指标，并记录到全局收集器。
    
    工作流程：
    1. 从 ctx.tensor_metrics 获取本回合指标
    2. 更新全局 TensorMetricsCollector
    3. 输出性能摘要日志
    """
    
    def __init__(self):
        # 在报告生成之前执行
        super().__init__(
            StageOrder.BUILD_REPORT.value - 1,
            "张量监控指标收集"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            optional_stages={"张量种间竞争", "分化"},
            writes_fields={"tensor_metrics"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import get_global_collector, TensorMetrics
        
        collector = get_global_collector()
        
        # 统计张量触发的分化数
        tensor_triggers = len(getattr(ctx, "tensor_trigger_codes", set()))
        collector.record_tensor_trigger(tensor_triggers)
        
        # 记录隔离检测和分歧检测
        if tensor_triggers > 0:
            collector.record_isolation_detection(tensor_triggers)
        
        # 结束本回合，保存指标
        metrics = collector.end_turn(ctx.turn_index)
        ctx.tensor_metrics = metrics
        
        # 输出统计信息
        stats = collector.get_statistics()
        if stats["total_turns"] > 0:
            logger.info(
                f"[张量监控] 累计回合={stats['total_turns']}, "
                f"平均耗时={stats['avg_time_ms']:.1f}ms, "
                f"张量触发占比={stats['tensor_vs_ai_ratio']:.1%}"
            )


# ============================================================================
# 张量状态同步阶段
# ============================================================================

class TensorStateSyncStage(BaseStage):
    """张量状态同步阶段
    
    将张量状态同步回数据库对象（Species 的 population 等）。
    确保张量计算结果能够持久化。
    
    工作流程：
    1. 从 ctx.tensor_state 获取最终种群数据
    2. 更新 ctx.species_batch 中各物种的 population
    3. 更新 ctx.new_populations
    """
    
    def __init__(self):
        # 在张量竞争之后、保存快照之前执行
        super().__init__(
            StageOrder.SAVE_POPULATION_SNAPSHOT.value - 1,
            "张量状态同步"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            optional_stages={"张量种间竞争"},
            requires_fields={"tensor_state", "species_batch"},
            writes_fields={"new_populations"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import get_compute
        
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            return
        
        compute = get_compute()
        
        try:
            pop = tensor_state.pop
            species_map = tensor_state.species_map
            
            # 计算每个物种的总种群
            totals = compute.sum_population(pop)
            
            sync_count = 0
            for lineage, idx in species_map.items():
                if idx < len(totals):
                    new_population = max(0, int(totals[idx]))
                    
                    # 更新 new_populations
                    if lineage in ctx.new_populations:
                        # 与现有值混合（避免突变）
                        old_val = ctx.new_populations[lineage]
                        ctx.new_populations[lineage] = int(
                            0.5 * old_val + 0.5 * new_population
                        )
                    else:
                        ctx.new_populations[lineage] = new_population
                    
                    sync_count += 1
            
            logger.debug(f"[张量同步] 已同步 {sync_count} 个物种的种群数据")
            
        except Exception as e:
            logger.warning(f"[张量同步] 同步失败: {e}")


# ============================================================================
# 获取所有张量阶段
# ============================================================================

def get_tensor_stages() -> list[BaseStage]:
    """获取所有张量计算阶段
    
    返回可以添加到管线中的张量阶段列表。
    这些阶段会根据配置开关自动启用或跳过。
    
    阶段执行顺序：
    1. PressureTensorStage (order=11): 压力张量化
    2. TensorMortalityStage (order=81): 多因子死亡率
    3. TensorDiffusionStage (order=91): 种群扩散
    4. TensorReproductionStage (order=92): 繁殖计算
    5. TensorCompetitionStage (order=93): 种间竞争
    6. TensorMigrationStage (order=94): 迁徙计算 [新增 - GPU 加速]
    7. TensorStateSyncStage (order=159): 状态同步
    8. TensorMetricsStage (order=139): 监控指标
    
    Returns:
        张量阶段列表
    """
    return [
        PressureTensorStage(),   # 压力张量化（在压力解析后立即执行）
        TensorMortalityStage(),
        TensorDiffusionStage(),
        TensorReproductionStage(),
        TensorCompetitionStage(),
        TensorMigrationStage(),   # 迁徙计算（GPU 加速）
        TensorStateSyncStage(),
        TensorMetricsStage(),
    ]


def get_minimal_tensor_stages() -> list[BaseStage]:
    """获取最小张量阶段集
    
    只包含核心的压力转换、死亡率计算和监控指标收集。
    适合在保守模式下使用。
    
    Returns:
        最小张量阶段列表
    """
    return [
        PressureTensorStage(),
        TensorMortalityStage(),
        TensorMetricsStage(),
    ]

