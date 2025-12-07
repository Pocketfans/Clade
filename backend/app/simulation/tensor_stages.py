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
    
    【完全替代旧系统】
    - 位置：order=60（原 MigrationStage 位置）
    - 启用时：跳过旧的 MigrationStage
    - 性能：比旧系统快 10-50x
    
    【性能优化核心】
    - 原方案：逐物种循环，~50ms/物种
    - 新方案：全物种并行，~5ms 总计
    
    工作流程：
    1. 从 ctx.tensor_state 获取种群和环境张量
    2. 从 ctx.preliminary_mortality 获取死亡率数据
    3. 使用 TensorMigrationEngine 批量计算迁徙
    4. 更新 tensor_state.pop
    5. 同步迁徙结果到栖息地数据库
    """
    
    def __init__(self):
        # 【修改】移到 order=60，完全替代旧 MigrationStage
        super().__init__(
            StageOrder.MIGRATION.value,  # order=60
            "张量迁徙计算"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"初步死亡率评估"},  # 在初步死亡率之后执行
            requires_fields={"tensor_state", "preliminary_mortality"},
            optional_fields={"species_batch", "all_habitats"},
            writes_fields={"tensor_state", "tensor_metrics", "migration_events", "migration_count"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import TensorMetrics
        from ..tensor.migration import (
            get_migration_engine,
            extract_species_preferences,
            extract_habitat_mask,
        )
        from ..repositories.environment_repository import environment_repository
        from ..services.species.habitat_manager import habitat_manager
        
        logger.info("【阶段2】张量迁徙计算...")
        ctx.emit_event("stage", "🦅 【阶段2】张量迁徙计算", "生态")
        
        # 初始化迁徙事件列表和共生追随计数
        ctx.migration_events = []
        ctx.migration_count = 0
        ctx.symbiotic_follow_count = getattr(ctx, "symbiotic_follow_count", 0)
        
        # 检查是否启用张量计算
        if not getattr(engine, "_use_tensor_mortality", False):
            logger.debug("[张量迁徙] 张量计算未启用，回退到旧系统")
            # 设置标志让旧系统执行
            ctx._tensor_migration_skipped = True
            return
        
        # 标记张量迁徙已执行，旧系统应跳过
        ctx._tensor_migration_executed = True
        
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            logger.warning("[张量迁徙] 缺少 tensor_state，回退到旧系统")
            ctx._tensor_migration_skipped = True
            return
        
        start_time = time.perf_counter()
        
        # 更新猎物分布缓存（保持与旧系统兼容）
        ctx.all_habitats = environment_repository.latest_habitats()
        habitat_manager.update_prey_distribution_cache(ctx.species_batch, ctx.all_habitats)
        
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
        
        # 创建物种索引 -> 物种对象映射
        species_batch = getattr(ctx, "species_batch", []) or []
        code_to_species = {sp.lineage_code: sp for sp in species_batch}
        idx_to_species = {}
        for lineage, idx in species_map.items():
            sp = code_to_species.get(lineage)
            if sp:
                idx_to_species[idx] = sp
        
        # 从 preliminary_mortality 提取死亡率
        death_rates = np.zeros(S, dtype=np.float32)
        preliminary = getattr(ctx, "preliminary_mortality", []) or []
        for result in preliminary:
            lineage = result.species.lineage_code
            idx = species_map.get(lineage)
            if idx is not None and idx < S:
                death_rates[idx] = result.death_rate
        
        # 【猎物追踪】提取营养级数组
        trophic_levels = np.ones(S, dtype=np.float32)
        for idx, sp in idx_to_species.items():
            if idx < S:
                trophic_levels[idx] = getattr(sp, 'trophic_level', 1.0) or 1.0
        
        # 【冷却期】构建冷却期掩码 (True=允许迁徙, False=冷却中)
        turn_index = getattr(ctx, "turn_index", 0)
        cooldown_mask = np.ones(S, dtype=bool)
        cooldown_species_set = set()
        for idx, sp in idx_to_species.items():
            if idx < S:
                is_on_cooldown = habitat_manager.is_migration_on_cooldown(
                    sp.lineage_code, turn_index, cooldown_turns=2
                )
                if is_on_cooldown:
                    cooldown_mask[idx] = False
                    cooldown_species_set.add(sp.lineage_code)
        
        if cooldown_species_set:
            logger.debug(f"[冷却期] {len(cooldown_species_set)} 个物种处于迁徙冷却期")
        
        # 提取物种偏好
        if species_batch:
            species_prefs = extract_species_preferences(species_batch, species_map)
        else:
            # 默认偏好（全陆生）
            species_prefs = np.zeros((S, 7), dtype=np.float32)
            species_prefs[:, 4] = 1.0  # 陆地
        
        # 生成栖息地掩码
        habitat_mask = extract_habitat_mask(env, species_prefs)
        
        # 记录迁徙前的种群分布
        old_pop = pop.copy()
        
        # 执行迁徙计算（包含猎物追踪和冷却期）
        new_pop, metrics = migration_engine.process_migration(
            pop=pop,
            env=env,
            species_prefs=species_prefs,
            death_rates=death_rates,
            habitat_mask=habitat_mask,
            trophic_levels=trophic_levels,
            cooldown_mask=cooldown_mask,
        )
        
        # 更新张量状态
        tensor_state.pop = new_pop
        ctx.tensor_state = tensor_state
        
        # 计算迁徙变化并同步到栖息地数据库，返回已迁徙的物种列表
        migrating_count, migrated_species = self._sync_migration_to_database(
            old_pop, new_pop, species_map, species_batch, ctx, habitat_manager, turn_index
        )
        
        # 【共生追随】处理共生物种追随迁徙
        symbiotic_count = 0
        if migrated_species:
            symbiotic_count = self._handle_symbiotic_following(
                migrated_species, species_batch, habitat_manager,
                environment_repository, turn_index
            )
            ctx.symbiotic_follow_count = symbiotic_count
        
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # 更新性能指标
        if ctx.tensor_metrics is None:
            ctx.tensor_metrics = TensorMetrics()
        ctx.tensor_metrics.migration_time_ms = duration_ms
        
        ctx.migration_count = migrating_count
        
        log_msg = f"【阶段2】张量迁徙完成: {S}物种, {migrating_count}个有显著迁徙"
        if symbiotic_count > 0:
            log_msg += f", {symbiotic_count}个共生物种追随"
        logger.info(log_msg)
        logger.info(
            f"[张量迁徙] 耗时={duration_ms:.1f}ms, 后端={metrics.backend}"
        )
        
        if migrating_count > 0:
            ctx.emit_event("info", f"🦅 {migrating_count} 个物种完成迁徙扩散", "生态")
        if symbiotic_count > 0:
            ctx.emit_event("info", f"🤝 {symbiotic_count} 个共生物种追随迁徙", "生态")
    
    def _sync_migration_to_database(
        self,
        old_pop: np.ndarray,
        new_pop: np.ndarray,
        species_map: dict,
        species_batch: list,
        ctx,
        habitat_manager,
        turn_index: int,
    ) -> tuple[int, list]:
        """同步迁徙结果到栖息地数据库
        
        检测种群分布变化，更新栖息地记录。
        
        Args:
            old_pop: 迁徙前种群 (S, H, W)
            new_pop: 迁徙后种群 (S, H, W)
            species_map: {lineage_code: index}
            species_batch: 物种列表
            ctx: 上下文
            habitat_manager: 栖息地管理器
            turn_index: 当前回合
        
        Returns:
            (有显著迁徙的物种数, 已迁徙物种列表)
        """
        from ..repositories.environment_repository import environment_repository
        
        migrating_count = 0
        migrated_species = []
        code_to_species = {sp.lineage_code: sp for sp in species_batch}
        
        # 计算每个物种的种群变化
        for lineage_code, idx in species_map.items():
            if idx >= old_pop.shape[0]:
                continue
            
            species = code_to_species.get(lineage_code)
            if not species or not species.id:
                continue
            
            old_dist = old_pop[idx]
            new_dist = new_pop[idx]
            
            # 计算变化量
            diff = np.abs(new_dist - old_dist)
            change_ratio = diff.sum() / (old_dist.sum() + 1e-6)
            
            # 如果变化超过 5%，认为有显著迁徙
            if change_ratio > 0.05:
                migrating_count += 1
                migrated_species.append(species)
                
                # 设置迁徙冷却期
                habitat_manager.set_migration_cooldown(lineage_code, turn_index)
                
                # 更新栖息地记录
                H, W = new_dist.shape
                new_tile_ids = []
                
                for i in range(H):
                    for j in range(W):
                        tile_idx = i * W + j
                        old_val = old_dist[i, j]
                        new_val = new_dist[i, j]
                        
                        # 新增栖息地（从无到有）
                        if old_val < 1 and new_val >= 1:
                            new_tile_ids.append(tile_idx)
                            try:
                                habitat_manager.add_habitat_population(
                                    species_id=species.id,
                                    tile_id=tile_idx,
                                    population=int(new_val),
                                    suitability=0.5,  # 默认适宜度
                                )
                            except Exception:
                                pass  # 忽略已存在的记录
                
                # 记录新迁入的地块（用于共生追随）
                species._new_tile_ids = new_tile_ids
        
        return migrating_count, migrated_species
    
    def _handle_symbiotic_following(
        self,
        migrated_species: list,
        all_species: list,
        habitat_manager,
        environment_repository,
        turn_index: int,
    ) -> int:
        """处理共生物种追随迁徙
        
        当一个物种迁徙后，检查是否有共生依赖物种需要追随。
        
        Args:
            migrated_species: 已迁徙的物种列表
            all_species: 所有物种列表
            habitat_manager: 栖息地管理器
            environment_repository: 环境仓库
            turn_index: 当前回合
        
        Returns:
            追随迁徙的物种数
        """
        symbiotic_count = 0
        tiles = environment_repository.list_tiles()
        
        for leader in migrated_species:
            # 获取领导者的新地块
            new_tile_ids = getattr(leader, '_new_tile_ids', [])
            if not new_tile_ids:
                continue
            
            # 获取应该追随的物种
            followers = habitat_manager.get_symbiotic_followers(leader, all_species)
            
            for follower in followers:
                try:
                    success = habitat_manager.execute_symbiotic_following(
                        leader_species=leader,
                        follower_species=follower,
                        leader_new_tiles=new_tile_ids,
                        all_tiles=tiles,
                        turn_index=turn_index,
                    )
                    if success:
                        symbiotic_count += 1
                        logger.info(
                            f"[共生追随] {follower.common_name} 追随 {leader.common_name} 迁徙"
                        )
                except Exception as e:
                    logger.warning(f"[共生追随] 执行失败: {e}")
        
        return symbiotic_count


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
    2. TensorMigrationStage (order=60): 迁徙计算 [完全替代旧 MigrationStage]
    3. TensorMortalityStage (order=81): 多因子死亡率
    4. TensorDiffusionStage (order=91): 种群扩散
    5. TensorReproductionStage (order=92): 繁殖计算
    6. TensorCompetitionStage (order=93): 种间竞争
    7. TensorMetricsStage (order=139): 监控指标
    8. TensorStateSyncStage (order=159): 状态同步
    
    Returns:
        张量阶段列表
    """
    return [
        PressureTensorStage(),     # 压力张量化（在压力解析后立即执行）
        TensorMigrationStage(),    # 迁徙计算（order=60，替代旧系统）
        TensorMortalityStage(),
        TensorDiffusionStage(),
        TensorReproductionStage(),
        TensorCompetitionStage(),
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

