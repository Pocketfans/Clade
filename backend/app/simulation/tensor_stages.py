"""
张量计算管线阶段

本模块提供使用张量系统的管线阶段：
 - PressureTensorStage: 压力张量化转换（将 ctx.modifiers 转换为张量）
 - TensorEcologyStage: 统一生态计算（整合死亡率、扩散、迁徙、繁殖、竞争）
 - TensorStateSyncStage: 张量状态同步回数据库
 - TensorMetricsStage: 收集和记录张量系统监控指标

【性能优化】
TensorEcologyStage 将原本分散的多个阶段合并为单一阶段：
- 原方案：多个阶段串行执行，每个阶段内有 Python 循环
- 新方案：单一阶段，全物种张量并行，无 Python 循环
- 性能提升：10-50x

张量路径为唯一计算路径。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import numpy as np

from .stages import BaseStage, StageOrder, StageDependency

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
    供后续张量生态计算使用。
    
    执行顺序：在 ParsePressuresStage (10) 之后
    
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
            requires_stages=set(),
            requires_fields=set(),
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
# 张量状态构建阶段
# ============================================================================

class TensorStateInitStage(BaseStage):
    """构建张量状态，供后续统一生态计算使用"""
    
    def __init__(self):
        super().__init__(
            StageOrder.TENSOR_STATE_INIT.value,  # order=49
            "张量状态构建"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages=set(),
            optional_stages={"压力张量化"},
            requires_fields={"species_batch"},
            writes_fields={"tensor_state"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        import numpy as np
        from ..repositories.environment_repository import environment_repository

        species_batch = getattr(ctx, "species_batch", []) or []
        if not species_batch:
            logger.warning("[张量状态构建] 无物种，跳过")
            return
        
        # 获取地图尺寸
        map_state = getattr(ctx, "current_map_state", None)
        all_tiles = getattr(ctx, "all_tiles", []) or []
        
        # 计算地图尺寸
        if map_state:
            H = getattr(map_state, "height", 64)
            W = getattr(map_state, "width", 128)
        elif all_tiles:
            # 从地块推断尺寸（MapTile 使用 x, y 坐标）
            max_y = max((t.y for t in all_tiles), default=40)
            max_x = max((t.x for t in all_tiles), default=128)
            H, W = max_y + 1, max_x + 1
        else:
            H, W = 40, 128  # 默认尺寸
        
        S = len(species_batch)
        
        # 构建环境张量 (7, H, W): [temp, humidity, altitude, resource, land, sea, coast]
        env = np.zeros((7, H, W), dtype=np.float32)
        tile_id_grid = np.full((H, W), -1, dtype=np.int32)

        # 构建 tile_id -> (y, x) 映射
        tile_coords = {}
        coord_to_tile_id = {}

        if all_tiles:
            def _classify_biome(biome: str) -> tuple[float, float, float]:
                b = (biome or "land").lower()
                sea_keywords = ("ocean", "sea", "deep_ocean", "marsh", "lagoon", "bay", "海", "海洋", "深海", "浅海", "大洋")
                freshwater_keywords = ("lake", "river", "freshwater", "wetland", "bog", "pond", "湖", "河", "淡水", "湿地")
                coast_keywords = ("coast", "coastal", "shore", "beach", "岸", "海岸", "沿海")

                is_sea = any(k in b for k in sea_keywords) or any(k in b for k in freshwater_keywords)
                is_coast = any(k in b for k in coast_keywords)

                # 沿岸区域视作陆地+海岸，但保持海洋为0以限制纯水生上岸
                is_land = not is_sea or is_coast or ("land" in b)
                return (
                    1.0 if is_land else 0.0,
                    1.0 if is_sea else 0.0,
                    1.0 if is_coast else 0.0,
                )

            for tile in all_tiles:
                # MapTile 使用 x, y 坐标（y 对应行，x 对应列）
                r, c = tile.y, tile.x
                if 0 <= r < H and 0 <= c < W:
                    env[0, r, c] = getattr(tile, 'temperature', 20.0) / 50.0  # 归一化
                    env[1, r, c] = getattr(tile, 'humidity', 0.5)
                    env[2, r, c] = getattr(tile, 'elevation', 0.0) / 1000.0  # 使用 elevation
                    env[3, r, c] = getattr(tile, 'resources', 100.0) / 100.0  # 使用 resources
                    tile_id_grid[r, c] = tile.id
                    # 地形类型（扩展中英文关键词）
                    biome = getattr(tile, 'biome', 'land')
                    land_flag, sea_flag, coast_flag = _classify_biome(biome)
                    env[4, r, c] = land_flag
                    env[5, r, c] = sea_flag
                    env[6, r, c] = coast_flag
                    tile_coords[tile.id] = (r, c)
                    coord_to_tile_id[(r, c)] = tile.id
        else:
            # 默认环境：温带陆地
            env[0, :, :] = 0.4  # 温度
            env[1, :, :] = 0.5  # 湿度
            env[3, :, :] = 0.8  # 资源
            env[4, :, :] = 1.0  # 陆地
        
        # 构建种群张量 (S, H, W)
        pop = np.zeros((S, H, W), dtype=np.float32)
        species_map = {}
        
        for idx, sp in enumerate(species_batch):
            species_map[sp.lineage_code] = idx
            # 分配种群到地图（从 morphology_stats 获取）
            total_pop = sp.morphology_stats.get("population", 0)
            if total_pop <= 0:
                logger.warning(f"[张量状态构建] {sp.lineage_code}: 总种群为0，跳过分布")
                continue
            
            # 【v3.2 修复】优先从数据库加载地块级别种群分布
            loaded_from_db = False
            species_tiles_used = set()
            if tile_coords:
                try:
                    # 从数据库读取该物种的栖息地分布
                    habitat_pops = environment_repository.get_habitats_by_species_id(
                        species_id=sp.id,
                        latest_only=True
                    )
                    
                    if habitat_pops:
                        for hab in habitat_pops:
                            if hab.tile_id in tile_coords:
                                r, c = tile_coords[hab.tile_id]
                                if 0 <= r < H and 0 <= c < W:
                                    pop[idx, r, c] = float(hab.population)
                        
                        # 验证总数是否匹配
                        loaded_total = pop[idx].sum()
                        if loaded_total > 0:
                            # 按比例调整到当前总种群
                            if abs(loaded_total - total_pop) > 1:
                                pop[idx] *= total_pop / loaded_total
                            loaded_from_db = True
                            logger.debug(
                                f"[张量状态构建] {sp.lineage_code}: "
                                f"从DB加载 {len(habitat_pops)} 个栖息地, "
                                f"映射到 {len(species_tiles_used)} 个地块"
                            )
                except Exception as e:
                    logger.warning(f"[张量状态构建] 从DB加载栖息地失败: {e}")
            # 【回退】如果数据库没有数据，从 habitats 属性加载
            if not loaded_from_db:
                logger.info(f"[张量状态构建] {sp.lineage_code}: 从 habitats 属性分布种群")
                # 获取物种栖息地分布
                habitats = getattr(sp, 'habitats', []) or []
                if habitats and tile_coords:
                    # 按栖息地分配
                    pop_per_habitat = total_pop / len(habitats)
                    for hab in habitats:
                        tile_id = getattr(hab, 'tile_id', None)
                        if tile_id is not None and tile_id in tile_coords:
                            r, c = tile_coords[tile_id]
                            if 0 <= r < H and 0 <= c < W:
                                pop[idx, r, c] += pop_per_habitat
                    loaded_from_db = pop[idx].sum() > 0
                else:
                    logger.warning(f"[张量状态构建] {sp.lineage_code}: 无 habitats 信息，使用默认分布")
                    # 【v2.1修复】没有栖息地信息时，只分布到有限的起始地块
                    # 参考 config.py: terrestrial_top_k = 4, marine_top_k = 3
                    # 不再均匀分布到所有陆地，而是选择少量高资源地块
                    habitat_type = (getattr(sp, 'habitat_type', 'terrestrial') or 'terrestrial').lower()
                    
                    # 根据栖息地类型选择合适的地块
                    if habitat_type in ('marine', 'deep_sea', 'freshwater'):
                        mask = env[5] > 0.5  # 海洋
                    else:
                        mask = env[4] > 0.5  # 陆地
                    
                    if mask.sum() > 0:
                        # 按资源排序，只选择前 4 个最高资源的地块
                        resources = env[3] * mask  # 资源 × 栖息地掩码
                        flat_resources = resources.flatten()
                        top_k = min(4, int(mask.sum()))  # 最多 4 个地块
                        top_indices = np.argpartition(flat_resources, -top_k)[-top_k:]
                        top_indices = top_indices[flat_resources[top_indices] > 0]
                        
                        if len(top_indices) > 0:
                            pop_per_tile = total_pop / len(top_indices)
                            for flat_idx in top_indices:
                                r, c = flat_idx // W, flat_idx % W
                                pop[idx, r, c] = pop_per_tile
                        else:
                            # 实在没有合适地块，放到地图中心
                            pop[idx, H // 2, W // 2] = total_pop
                    else:
                        # 没有合适栖息地类型，放到地图中心
                        pop[idx, H // 2, W // 2] = total_pop
        
        # 构建物种参数 (S, F)
        species_params = np.zeros((S, 4), dtype=np.float32)
        for idx, sp in enumerate(species_batch):
            species_params[idx, 0] = getattr(sp, 'temp_optimal', 20.0)
            species_params[idx, 1] = getattr(sp, 'temp_tolerance', 15.0)
            species_params[idx, 2] = getattr(sp, 'mobility', 1.0)
            species_params[idx, 3] = getattr(sp, 'reproduction_rate', 0.1)
        
        from ..tensor.state import TensorState
        tensor_state = TensorState(
            env=env,
            pop=pop,
            species_params=species_params,
            masks={"tile_ids": tile_id_grid, "coord_to_tile_id": coord_to_tile_id},
            species_map=species_map,
        )
        
        ctx.tensor_state = tensor_state
        total_pop = pop.sum()
        nonzero_tiles = (pop > 0).any(axis=0).sum()
        logger.info(
            f"[张量状态构建] 已构建张量状态：物种数={S}, 维度={H}x{W}, "
            f"总种群={total_pop:.0f}, 有物种地块={nonzero_tiles}"
        )

# ============================================================================
# 统一张量生态计算阶段
# ============================================================================

class TensorEcologyStage(BaseStage):
    """统一张量生态计算阶段
    
    【核心优化】整合死亡率、扩散、迁徙、繁殖、竞争为单一阶段：
    - 单一阶段，全物种张量并行，无 Python 循环
    - 性能提升：10-50x
    
    工作流程（单次调用完成）：
    1. 死亡率计算（多因子张量）
    2. 扩散计算（带适宜度引导）
    3. 迁徙计算（压力驱动+猎物追踪）
    4. 繁殖计算（承载力约束）
    5. 竞争计算（种间竞争）
    """
    
    def __init__(self):
        # 在张量状态构建之后执行（order=51）
        super().__init__(
            StageOrder.PRELIMINARY_MORTALITY.value + 1,  # order=51
            "统一张量生态计算"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            requires_stages={"张量状态构建"},
            requires_fields={"tensor_state", "species_batch"},
            optional_stages={"压力张量化"},  # 可选的前置阶段
            writes_fields={"tensor_state", "tensor_metrics", "combined_results", 
                          "migration_events", "migration_count"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import (
            TensorMetrics,
            get_ecology_engine,
            extract_species_params,
            extract_species_prefs,
            extract_species_traits,
            extract_trophic_levels,
        )
        from ..services.species.habitat_manager import habitat_manager
        
        logger.info("【统一张量生态】开始计算...")
        ctx.emit_event("stage", "🧬 【统一张量生态】死亡率+扩散+迁徙+繁殖+竞争", "生态")
        
        # 检查张量状态
        tensor_state = getattr(ctx, "tensor_state", None)
        if tensor_state is None:
            logger.warning("[统一张量生态] 缺少 tensor_state，跳过")
            return
        
        # 获取生态引擎
        ecology_engine = get_ecology_engine()
        
        # 准备数据
        pop = tensor_state.pop.astype(np.float32)
        env = tensor_state.env.astype(np.float32)
        species_map = tensor_state.species_map
        S = pop.shape[0]
        
        if S == 0:
            logger.debug("[统一张量生态] 无物种，跳过")
            return
        
        # 创建物种索引映射
        species_batch = getattr(ctx, "species_batch", []) or []
        
        # 提取物种参数
        species_params = extract_species_params(species_batch, species_map)
        species_prefs = extract_species_prefs(species_batch, species_map)
        species_traits = extract_species_traits(species_batch, species_map)
        trophic_levels = extract_trophic_levels(species_batch, species_map)
        
        # 获取压力叠加层
        pressure_overlay = None
        if hasattr(ctx, "pressure_overlay") and ctx.pressure_overlay is not None:
            pressure_overlay = ctx.pressure_overlay.overlay.astype(np.float32)
        
        # 构建冷却期掩码
        turn_index = getattr(ctx, "turn_index", 0)
        cooldown_mask = np.ones(S, dtype=bool)
        for lineage, idx in species_map.items():
            if idx < S:
                is_on_cooldown = habitat_manager.is_migration_on_cooldown(
                    lineage, turn_index, cooldown_turns=2
                )
                if is_on_cooldown:
                    cooldown_mask[idx] = False
        
        # 慢性衰退计数：从 ctx 取持久化字典，按物种映射
        decline_map = getattr(ctx, "tensor_decline_streaks", {}) or {}
        decline_streaks = np.zeros(S, dtype=np.int32)
        for lineage, idx in species_map.items():
            decline_streaks[idx] = int(decline_map.get(lineage, 0))
        
        # 构造 external_bonus：压力叠加 + (可选)embedding 热点
        external_bonus = None
        try:
            H, W = pop.shape[1], pop.shape[2]
            bonus_2d = np.zeros((H, W), dtype=np.float32)
            if pressure_overlay is not None:
                # 支持按通道权重叠加（若存在 weights 字段）
                weights = None
                if hasattr(ctx, "pressure_overlay") and hasattr(ctx.pressure_overlay, "weights"):
                    weights = ctx.pressure_overlay.weights
                if weights is not None and len(weights) == pressure_overlay.shape[0]:
                    overlay_sum = (pressure_overlay * np.array(weights)[:, None, None]).sum(axis=0)
                else:
                    overlay_sum = pressure_overlay.sum(axis=0)
                if overlay_sum.max() > 1e-6:
                    overlay_norm = overlay_sum / overlay_sum.max()
                    bonus_2d += overlay_norm.astype(np.float32) * 0.2
            emb_data = getattr(ctx, "embedding_turn_data", {}) or {}
            # 支持多热力图/多权重
            if "heatmaps" in emb_data and isinstance(emb_data["heatmaps"], dict):
                for name, payload in emb_data["heatmaps"].items():
                    weight = 0.1
                    if isinstance(payload, tuple) and len(payload) == 2:
                        arr, w = payload
                        weight = float(w)
                    else:
                        arr = payload
                    if isinstance(arr, np.ndarray) and arr.shape == (H, W):
                        bonus_2d += arr.astype(np.float32) * weight
            # 兼容旧键
            for key in ("tile_heatmap", "tile_scores", "tile_bonus"):
                if key in emb_data:
                    arr = emb_data[key]
                    if isinstance(arr, np.ndarray) and arr.shape == (H, W):
                        bonus_2d += arr.astype(np.float32) * 0.1
                        break
            if bonus_2d.max() > 0:
                external_bonus = np.broadcast_to(bonus_2d, (S, H, W))
        except Exception:
            external_bonus = None
        
        # 【v3.0】获取回合年数（从配置或 ctx）
        from ..core.config import get_settings
        settings = get_settings()
        turn_years = getattr(ctx, "turn_years", None) or settings.turn_years
        
        # 【核心】直接执行 Taichi 计算（CUDA 上下文不能跨线程）
        # 注意：Taichi/CUDA 上下文是线程绑定的，不能用 asyncio.to_thread()
        result = ecology_engine.process_ecology(
            pop=pop,
            env=env,
            species_params=species_params,
            species_prefs=species_prefs,
            species_traits=species_traits,  # 【新】传递精确特质矩阵
            turn_index=turn_index,
            trophic_levels=trophic_levels,
            pressure_overlay=pressure_overlay,
            cooldown_mask=cooldown_mask,
            external_bonus=external_bonus,
            decline_streaks=decline_streaks,
            turn_years=turn_years,  # 【v3.0】传递回合年数用于世代缩放
        )
        
        # 【新增诊断】比较计算前后的地块数
        tiles_before = int((pop > 0).any(axis=0).sum())
        tiles_after = int((result.pop > 0).any(axis=0).sum())
        logger.info(
            f"[统一张量生态] 地块变化: {tiles_before} -> {tiles_after} "
            f"(+{tiles_after - tiles_before})"
        )

        logger.info(
            f"[统一张量生态] 后端={result.metrics.backend}, "
            f"耗时={result.metrics.total_time_ms:.1f}ms"
        )
        
        # 更新张量状态
        tensor_state.pop = result.pop
        ctx.tensor_state = tensor_state
        
        # 同步死亡率到 combined_results
        self._sync_mortality_to_results(ctx, result, species_map)
        
        # 更新迁徙统计
        ctx.migration_count = len(result.migrated_species)
        ctx.migration_events = []
        
        # 更新慢性衰退计数持久化
        decline_map = getattr(ctx, "tensor_decline_streaks", {}) or {}
        pop_before = pop.sum(axis=(1, 2))
        pop_after = result.pop.sum(axis=(1, 2))
        for lineage, idx in species_map.items():
            if idx < result.metrics.species_count:
                # 更严谨的衰退判定：高死亡率且净增长<1
                mortality_slice = result.mortality_rates[idx]
                mask = mortality_slice > 0
                avg_death = float(mortality_slice[mask].mean()) if mask.any() else 0.0
                initial_pop = float(pop_before[idx])
                final_pop = float(pop_after[idx])
                growth = final_pop / max(initial_pop, 1e-6)
                is_declining = (avg_death >= 0.12) and (growth < 1.0)
                if is_declining:
                    decline_map[lineage] = int(decline_map.get(lineage, 0)) + 1
                else:
                    decline_map[lineage] = 0
        ctx.tensor_decline_streaks = decline_map
        
        # 设置迁徙冷却期
        for s_idx in result.migrated_species:
            # 找到对应的 lineage_code
            for lineage, idx in species_map.items():
                if idx == s_idx:
                    habitat_manager.set_migration_cooldown(lineage, turn_index)
                    break
        
        # 更新性能指标
        if ctx.tensor_metrics is None:
            ctx.tensor_metrics = TensorMetrics()
        
        ctx.tensor_metrics.mortality_time_ms = result.metrics.mortality_time_ms
        ctx.tensor_metrics.migration_time_ms = result.metrics.migration_time_ms
        
        logger.info(
            f"【统一张量生态】完成: {S}物种, "
            f"耗时={result.metrics.total_time_ms:.1f}ms, "
            f"后端={result.metrics.backend}, "
            f"平均死亡率={result.metrics.avg_mortality_rate:.1%}, "
            f"迁徙物种={len(result.migrated_species)}"
        )
        
        ctx.emit_event(
            "info", 
            f"🧬 张量生态计算完成: {result.metrics.total_time_ms:.0f}ms, "
            f"平均死亡率 {result.metrics.avg_mortality_rate:.1%}", 
            "生态"
        )
    
    def _sync_mortality_to_results(
        self,
        ctx,
        result,
        species_map: dict,
    ) -> None:
        """将张量死亡率同步到 combined_results
        
        如果 combined_results 不存在或为空，从 species_batch 创建。
        """
        from ..simulation.tile_based_mortality import AggregatedMortalityResult
        
        combined_results = getattr(ctx, "combined_results", None) or []
        species_batch = getattr(ctx, "species_batch", []) or []
        
        # 如果 combined_results 为空，从 species_batch 创建
        if len(combined_results) == 0 and species_batch:
            combined_results = []
            for sp in species_batch:
                pop = sp.morphology_stats.get("population", 0)
                combined_results.append(AggregatedMortalityResult(
                    species=sp,
                    initial_population=pop,
                    deaths=0,
                    survivors=pop,
                    death_rate=0.0,
                ))
            ctx.combined_results = combined_results
            logger.info(f"[张量生态] 创建 combined_results: {len(combined_results)} 个物种")
        
        if not combined_results:
            logger.warning("[张量生态] combined_results 为空，跳过死亡率同步")
            return
        
        sync_count = 0
        for res in combined_results:
            lineage = res.species.lineage_code
            idx = species_map.get(lineage)
            if idx is not None and idx < result.mortality_rates.shape[0]:
                # 取该物种的平均死亡率
                species_mortality = result.mortality_rates[idx]
                mask = species_mortality > 0
                if mask.any():
                    avg_mortality = float(species_mortality[mask].mean())
                    res.death_rate = avg_mortality
                    res.deaths = int(result.death_counts[idx])
                    res.survivors = int(result.survivor_counts[idx])
                    res.final_population = res.survivors
                    sync_count += 1
        
        logger.info(f"[张量生态] 死亡率同步完成: {sync_count}/{len(combined_results)} 个物种")


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
            optional_stages={"统一张量生态计算", "分化"},
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
    4. 【新增】同步到数据库仓库
    5. 【新增】检查灭绝状态
    """
    
    def __init__(self):
        # 在保存快照之前执行
        super().__init__(
            StageOrder.SAVE_POPULATION_SNAPSHOT.value - 1,
            "张量状态同步"
        )
    
    def get_dependency(self) -> StageDependency:
        return StageDependency(
            optional_stages={"统一张量生态计算", "种群更新"},
            requires_fields={"species_batch"},
            writes_fields={"new_populations"},
        )
    
    async def execute(self, ctx: SimulationContext, engine: SimulationEngine) -> None:
        from ..tensor import get_compute
        from ..repositories.species_repository import species_repository
        from ..repositories.environment_repository import environment_repository
        from ..models.environment import HabitatPopulation
        
        tensor_state = getattr(ctx, "tensor_state", None)
        species_batch = getattr(ctx, "species_batch", []) or []
        all_tiles = getattr(ctx, "all_tiles", []) or []
        
        if not species_batch:
            logger.debug("[张量同步] 无物种，跳过")
            return
        
        # 构建 lineage -> species 映射
        species_by_lineage = {sp.lineage_code: sp for sp in species_batch}
        
        # 构建 tile_id -> (y, x) 映射（用于栖息地同步）
        tile_coords = {}
        for tile in all_tiles:
            if hasattr(tile, 'id') and tile.id is not None:
                tile_coords[(tile.y, tile.x)] = tile.id
        
        sync_count = 0
        extinct_count = 0
        habitat_sync_count = 0
        
        # 优先从 tensor_state 获取种群数据
        if tensor_state is not None:
            try:
                compute = get_compute()
                pop = tensor_state.pop
                species_map = tensor_state.species_map
                S, H, W = pop.shape
                
                # 计算每个物种的总种群
                totals = compute.sum_population(pop)
                
                # 【v2.0 新增】同步栖息地分布
                new_habitats = []
                turn_index = getattr(ctx, "turn_index", 0)
                
                for lineage, idx in species_map.items():
                    if idx >= len(totals):
                        continue
                    
                    new_population = max(0, int(totals[idx]))
                    
                    # 更新 new_populations
                    ctx.new_populations[lineage] = new_population
                    
                    # 更新 species_batch 中的物种对象
                    if lineage in species_by_lineage:
                        sp = species_by_lineage[lineage]
                        old_pop = sp.morphology_stats.get("population", 0)
                        sp.morphology_stats["population"] = new_population
                        
                        # 检查灭绝
                        if new_population <= 0 and old_pop > 0:
                            sp.status = "extinct"
                            sp.morphology_stats["extinction_turn"] = turn_index
                            extinct_count += 1
                            logger.info(f"[张量同步] 物种 {lineage} 灭绝")
                        
                        # 【v2.0 新增】同步栖息地分布（按地块）
                        if new_population > 0 and tile_coords:
                            species_pop_2d = pop[idx]  # (H, W)
                            total_pop_in_tensor = species_pop_2d.sum()
                            
                            if total_pop_in_tensor > 0:
                                # 找到有种群的地块
                                for r in range(H):
                                    for c in range(W):
                                        tile_pop = int(species_pop_2d[r, c])
                                        if tile_pop > 0:
                                            tile_id = tile_coords.get((r, c))
                                            if tile_id is not None:
                                                # 计算适宜度（基于种群比例）
                                                suit = min(1.0, tile_pop / (total_pop_in_tensor / 10 + 1))
                                                new_habitats.append(
                                                    HabitatPopulation(
                                                        tile_id=tile_id,
                                                        species_id=sp.id,
                                                        population=tile_pop,
                                                        suitability=suit,
                                                        turn_index=turn_index,
                                                    )
                                                )
                                                habitat_sync_count += 1
                    
                    sync_count += 1
                
                # 批量写入栖息地数据
                if new_habitats:
                    try:
                        environment_repository.write_habitats(new_habitats)
                        logger.info(f"[张量同步] 同步 {len(new_habitats)} 条栖息地记录")
                    except Exception as e:
                        logger.warning(f"[张量同步] 写入栖息地失败: {e}")
                
            except Exception as e:
                logger.warning(f"[张量同步] 从 tensor_state 同步失败: {e}")
        
        # 如果有 new_populations 数据（来自 PopulationUpdateStage），也要同步
        if ctx.new_populations:
            for lineage, new_pop in ctx.new_populations.items():
                if lineage in species_by_lineage:
                    sp = species_by_lineage[lineage]
                    old_pop = sp.morphology_stats.get("population", 0)
                    sp.morphology_stats["population"] = new_pop
                    
                    # 检查灭绝
                    if new_pop <= 0 and old_pop > 0:
                        if sp.status != "extinct":
                            sp.status = "extinct"
                            sp.morphology_stats["extinction_turn"] = ctx.turn_index
                            extinct_count += 1
        
        # 持久化到数据库（使用 upsert 方法）
        persisted_count = 0
        for sp in species_batch:
            try:
                species_repository.upsert(sp)
                persisted_count += 1
            except Exception as e:
                logger.warning(f"[张量同步] 持久化物种 {sp.lineage_code} 失败: {e}")
        
        logger.info(
            f"[张量同步] 完成: 同步={sync_count}, 栖息地={habitat_sync_count}, "
            f"持久化={persisted_count}, 灭绝={extinct_count}"
        )


# ============================================================================
# 获取所有张量阶段
# ============================================================================

def get_tensor_stages() -> list[BaseStage]:
    """获取所有张量计算阶段
    
    返回可以添加到管线中的张量阶段列表。
    使用 TensorEcologyStage 整合全部生态计算。
    
    阶段执行顺序：
    1. PressureTensorStage (order=11): 压力张量化
    2. TensorEcologyStage (order=51): 统一生态计算（整合死亡率+扩散+迁徙+繁殖+竞争）
    3. TensorStateSyncStage (order=159): 状态同步
    4. TensorMetricsStage (order=139): 监控指标
    
    Returns:
        张量阶段列表
    """
    return [
        PressureTensorStage(),     # 压力张量化（在压力解析后立即执行）
        TensorStateInitStage(),    # 张量状态构建
        TensorEcologyStage(),      # 统一生态计算
        TensorStateSyncStage(),    # 状态同步
        TensorMetricsStage(),      # 监控指标
    ]


def get_minimal_tensor_stages() -> list[BaseStage]:
    """获取最小张量阶段集
    
    只包含核心的压力转换、统一生态计算和监控指标收集。
    
    Returns:
        最小张量阶段列表
    """
    return [
        PressureTensorStage(),
        TensorEcologyStage(),
        TensorMetricsStage(),
    ]
