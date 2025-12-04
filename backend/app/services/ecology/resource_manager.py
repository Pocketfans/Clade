"""资源管理服务 (Resource Manager)

基于净初级生产力 (NPP) 的资源模型，统一能量单位。

核心功能：
1. NPP 计算：基于Miami模型（温湿限制）+ 纬度光照限制
2. 资源再生：Logistic 恢复模型
3. 过采惩罚：需求超过供给时的反馈
4. 事件脉冲：火山灰、洪水、干旱等
5. 承载力计算：统一 T1-T5 能量传递

设计原则：
- 所有能量单位统一为 kg 生物量
- 配置驱动，避免硬编码常数
- 支持向量化计算
- 回合级缓存
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.environment import MapTile

from ...core.config import get_settings
from ...models.config import ResourceSystemConfig
# 导入常量以获取地图尺寸用于纬度计算
from ...simulation.constants import LOGIC_RES_Y

logger = logging.getLogger(__name__)
_settings = get_settings()


@dataclass
class TileResourceState:
    """单个地块的资源状态"""
    tile_id: int
    
    # 基础 NPP（由气候/地质决定）
    base_npp: float = 0.0
    
    # 当前 NPP（考虑再生/过采后）
    current_npp: float = 0.0
    
    # 事件修正倍率
    event_multiplier: float = 1.0
    
    # 上回合消耗比例（需求/供给）
    last_consumption_ratio: float = 0.0
    
    # 过采惩罚累积
    overgrazing_penalty: float = 0.0
    
    # T1 承载力（kg 生物量）
    t1_capacity_kg: float = 0.0
    
    # 各营养级承载力（个体数，按平均体重折算）
    trophic_capacities: dict[int, float] = field(default_factory=dict)


@dataclass
class ResourceSnapshot:
    """资源系统快照（用于缓存）"""
    turn_index: int
    tile_states: dict[int, TileResourceState]
    
    # 汇总统计
    total_npp: float = 0.0
    avg_npp: float = 0.0
    overgrazing_tiles: int = 0
    
    # NPP 矩阵（用于向量化）
    npp_vector: np.ndarray | None = None
    t1_capacity_vector: np.ndarray | None = None


class ResourceManager:
    """资源管理服务
    
    提供基于 NPP 的资源模型，统一能量单位和传递效率。
    
    【依赖注入】
    配置必须通过构造函数注入，内部方法不再调用隐式加载。
    如需刷新配置，使用 reload_config() 显式更新。
    """
    
    def __init__(self, config: ResourceSystemConfig | None = None):
        """初始化资源管理器
        
        Args:
            config: 资源系统配置（如未提供则使用默认值并警告）
        """
        self._logger = logging.getLogger(__name__)
        
        # 配置注入 - 如未提供则使用默认值并警告
        if config is None:
            self._logger.warning("[资源管理] config 未注入，使用默认值")
            config = ResourceSystemConfig()
        self._config = config
        
        # 地块资源状态
        self._tile_states: dict[int, TileResourceState] = {}
        
        # 缓存
        self._snapshot: ResourceSnapshot | None = None
        self._last_turn: int = -1
        
        # 事件脉冲队列 {tile_id: [(event_type, multiplier, decay_rate, remaining_turns)]}
        self._event_pulses: dict[int, list[tuple[str, float, float, int]]] = {}
    
    def reload_config(self, config: ResourceSystemConfig | None = None):
        """热更新配置
        
        Args:
            config: 资源系统配置（必须由调用方提供）
            
        注意: 配置应由调用方从容器统一获取后传入。
        """
        if config is not None:
            self._config = config
            self._logger.info("[资源管理] 配置已重新加载")
    
    # ========== NPP 计算 ==========
    
    def calculate_npp(
        self,
        tile: "MapTile",
        temperature: float | None = None,
        humidity: float | None = None,
    ) -> float:
        """计算单个地块的净初级生产力 (NPP)
        
        【改进v8】使用综合生态压力模型：
        1. Miami模型：Liebig最小因子定律，由温度和降水（湿度）的最小值决定
        2. 纬度光照限制：高纬度地区即使温度适宜，光照不足也会限制生长
        3. 致死阈值：极端环境直接归零，取消无条件保底
        
        Args:
            tile: 地块对象
            temperature: 可选的温度覆盖
            humidity: 可选的湿度覆盖
            
        Returns:
            NPP (kg/回合)
        """
        cfg = self._config
        
        # 获取环境参数
        temp = temperature if temperature is not None else getattr(tile, 'temperature', 20)
        hum = humidity if humidity is not None else getattr(tile, 'humidity', 0.5)
        
        # 1. 致死阈值检测（Extreme Environment Cutoff）
        # 如果环境过于恶劣，生命完全无法生存，NPP 强制归零
        if temp < -30.0 or temp > 55.0:
            return 0.0
        if hum < 0.05:  # 极度干旱（沙漠中心）
            return 0.0
            
        # 2. Miami 模型计算气候潜力 NPP (g/m²/yr -> kg/tile/turn)
        # 原模型公式：
        # NPP_temp = 3000 / (1 + exp(1.315 - 0.119 * T))
        # NPP_water = 3000 * (1 - exp(-0.000664 * Rainfall))
        
        # 映射参数
        # 假设湿度 1.0 对应年降雨量 3000mm (热带雨林)
        # 假设湿度 0.5 对应年降雨量 800mm (温带森林/草原)
        # 假设湿度 0.1 对应年降雨量 100mm (荒漠)
        rainfall_mm = hum * 3500.0
        
        try:
            npp_temp = 3000.0 / (1.0 + math.exp(1.315 - 0.119 * temp))
        except OverflowError:
            npp_temp = 0.0
            
        npp_water = 3000.0 * (1.0 - math.exp(-0.000664 * rainfall_mm))
        
        # Liebig最小因子定律
        miami_npp = min(npp_temp, npp_water)
        
        # 转换为游戏单位 (kg/tile/turn)
        # miami_npp 是 g/m²/yr
        # 假设一个 tile 是 100km² = 10^8 m² (仅作比喻，实际用系数调整)
        # 使用 resource_to_npp_factor 作为缩放系数的基础
        # 将 miami_npp (0-3000) 映射到游戏数值范围 (0-100000)
        base_npp = miami_npp * 30.0  # 3000 * 30 = 90,000 max
        
        # 3. 纬度光照限制 (Latitudinal Light Limit)
        # 获取 y 坐标 (0-LOGIC_RES_Y)
        # 假设地图中间 (y=HEIGHT/2) 是赤道，两端是极地
        y_coord = getattr(tile, 'y', 0)
        if hasattr(tile, 'y'):
            # 归一化纬度 0.0(赤道) - 1.0(极地)
            half_height = LOGIC_RES_Y / 2.0
            normalized_lat = abs(y_coord - half_height) / half_height
            normalized_lat = min(1.0, max(0.0, normalized_lat))
            
            # 光照系数：赤道=1.0，极地=0.2 (极夜/光照角度低)
            # 使用平方衰减模拟高纬度的剧烈变化
            light_factor = 1.0 - (normalized_lat ** 2.5) * 0.8
        else:
            light_factor = 1.0
            
        base_npp *= light_factor
        
        # 4. 栖息地/土壤修正 (Edaphic Factors)
        habitat_type = getattr(tile, 'habitat_type', 'terrestrial')
        habitat_multiplier = self._get_habitat_multiplier(habitat_type, cfg)
        base_npp *= habitat_multiplier
        
        # 5. 地质资源加成 (Mineral Nutrients)
        # 原有的 resources 属性代表矿物质/土壤肥力
        tile_resources = getattr(tile, 'resources', 50)
        # 资源影响系数：0.5 (贫瘠) - 1.5 (肥沃)
        soil_fertility = 0.5 + (tile_resources / 1000.0)
        base_npp *= soil_fertility

        # 6. 事件脉冲修正 (Event Pulse)
        event_multiplier = self._get_event_multiplier(tile.id)
        base_npp *= event_multiplier
        
        # 上限截断
        base_npp = min(base_npp, cfg.max_npp_per_tile)
        
        return max(0.0, base_npp)
    
    def _calculate_temp_modifier(self, temp: float, cfg: ResourceSystemConfig) -> float:
        """计算温度对 NPP 的修正 (已集成到 calculate_npp，保留用于兼容)"""
        if cfg.optimal_temp_min <= temp <= cfg.optimal_temp_max:
            return 1.0
        
        if temp < cfg.optimal_temp_min:
            deviation = cfg.optimal_temp_min - temp
        else:
            deviation = temp - cfg.optimal_temp_max
        
        # 指数衰减
        modifier = math.exp(-cfg.temp_deviation_penalty * deviation)
        return max(0.1, modifier)  # 至少 10%
    
    def _calculate_humidity_modifier(self, humidity: float, cfg: ResourceSystemConfig) -> float:
        """计算湿度对 NPP 的修正 (已集成到 calculate_npp，保留用于兼容)"""
        if humidity < cfg.humidity_min_threshold:
            # 极端干旱
            return 0.1 + 0.4 * (humidity / cfg.humidity_min_threshold)
        
        # 湿度越高越好（但有上限）
        base = 0.5 + cfg.humidity_npp_factor * min(humidity, 1.0)
        return min(1.2, base)
    
    def _get_habitat_multiplier(self, habitat_type: str, cfg: ResourceSystemConfig) -> float:
        """获取栖息地类型的 NPP 倍率"""
        multipliers = {
            "marine": cfg.aquatic_npp_multiplier,
            "deep_sea": cfg.deep_sea_npp_multiplier,
            "shallow_sea": cfg.shallow_sea_npp_multiplier,
            "coastal": cfg.shallow_sea_npp_multiplier,
            "freshwater": cfg.aquatic_npp_multiplier * 1.2,
            "desert": cfg.desert_npp_multiplier,  # 沙漠在Miami模型中已受限，此处作为额外修正
            "tundra": cfg.tundra_npp_multiplier,  # 苔原在温度限制下已很低
            "temperate": cfg.temperate_forest_npp_multiplier,
            "tropical": cfg.tropical_forest_npp_multiplier,
            "grassland": 0.8,
            "terrestrial": 1.0,
        }
        return multipliers.get(habitat_type, 1.0)
    
    def _get_event_multiplier(self, tile_id: int) -> float:
        """获取事件脉冲修正倍率"""
        if tile_id not in self._event_pulses:
            return 1.0
        
        total_multiplier = 1.0
        for event_type, multiplier, decay, remaining in self._event_pulses[tile_id]:
            if remaining > 0:
                total_multiplier *= multiplier
        
        return total_multiplier
    
    # ========== 资源再生与过采 ==========
    
    def update_resource_dynamics(
        self,
        tiles: Sequence["MapTile"],
        consumption_by_tile: dict[int, float],
        turn_index: int,
    ):
        """更新资源动态（每回合调用）
        
        Args:
            tiles: 所有地块
            consumption_by_tile: 各地块的消耗量 {tile_id: kg}
            turn_index: 当前回合
        """
        cfg = self._config
        
        if not cfg.enable_resource_dynamics:
            return
        
        for tile in tiles:
            tid = tile.id
            
            # 获取或创建状态
            if tid not in self._tile_states:
                self._tile_states[tid] = TileResourceState(tile_id=tid)
            
            state = self._tile_states[tid]
            
            # 计算基础 NPP
            state.base_npp = self.calculate_npp(tile)
            
            # 计算消耗比例
            consumption = consumption_by_tile.get(tid, 0.0)
            supply = state.current_npp * cfg.harvestable_fraction if state.current_npp > 0 else state.base_npp * cfg.harvestable_fraction
            
            if supply > 0:
                state.last_consumption_ratio = consumption / supply
            else:
                state.last_consumption_ratio = 0.0
            
            # 过采惩罚
            if state.last_consumption_ratio > cfg.overgrazing_threshold:
                excess = state.last_consumption_ratio - cfg.overgrazing_threshold
                state.overgrazing_penalty = min(0.5, excess * cfg.overgrazing_penalty)
            else:
                # 恢复
                state.overgrazing_penalty = max(0, state.overgrazing_penalty - 0.05)
            
            # Logistic 恢复
            capacity = state.base_npp * cfg.resource_capacity_multiplier
            if state.current_npp == 0:
                state.current_npp = state.base_npp
            
            # dN/dt = r * N * (1 - N/K) - penalty
            r = cfg.resource_recovery_rate
            n = state.current_npp
            k = capacity
            
            growth = r * n * (1 - n / k) if k > 0 else 0
            penalty_loss = state.overgrazing_penalty * n
            
            state.current_npp = max(0.1 * state.base_npp, n + growth - penalty_loss)
            
            # 季节波动
            if cfg.resource_fluctuation_amplitude > 0:
                fluctuation = 1.0 + cfg.resource_fluctuation_amplitude * math.sin(turn_index * 0.5)
                state.current_npp *= fluctuation
            
            # 计算 T1 承载力
            state.t1_capacity_kg = state.current_npp * cfg.npp_to_capacity_factor
        
        # 处理事件脉冲衰减
        self._decay_event_pulses()
        
        self._last_turn = turn_index
        self._snapshot = None  # 失效缓存
    
    def _decay_event_pulses(self):
        """衰减事件脉冲"""
        cfg = self._config
        
        for tile_id in list(self._event_pulses.keys()):
            updated = []
            for event_type, multiplier, decay, remaining in self._event_pulses[tile_id]:
                if remaining > 1:
                    # 衰减
                    new_mult = 1.0 + (multiplier - 1.0) * (1 - decay)
                    updated.append((event_type, new_mult, decay, remaining - 1))
            
            if updated:
                self._event_pulses[tile_id] = updated
            else:
                del self._event_pulses[tile_id]
    
    # ========== 承载力计算 ==========
    
    def get_trophic_capacity(
        self,
        tile_id: int,
        trophic_level: int,
        avg_body_weight_kg: float = 1.0,
    ) -> float:
        """获取指定营养级的承载力（个体数）
        
        Args:
            tile_id: 地块 ID
            trophic_level: 营养级 (1-5)
            avg_body_weight_kg: 平均体重 (kg)
            
        Returns:
            承载力（个体数）
        """
        cfg = self._config
        
        state = self._tile_states.get(tile_id)
        if not state:
            return 0.0
        
        # T1 承载力 (kg)
        t1_capacity = state.t1_capacity_kg
        
        if trophic_level == 1:
            # 生产者
            if avg_body_weight_kg > 0:
                return t1_capacity / avg_body_weight_kg
            return t1_capacity
        
        # 向上营养级用生态效率衰减
        capacity_kg = t1_capacity
        for level in range(2, trophic_level + 1):
            efficiency = self._get_efficiency(level - 1, level, cfg)
            capacity_kg *= efficiency
        
        if avg_body_weight_kg > 0:
            return capacity_kg / avg_body_weight_kg
        return capacity_kg
    
    def _get_efficiency(self, from_level: int, to_level: int, cfg: ResourceSystemConfig) -> float:
        """获取营养级间的能量传递效率"""
        if from_level == 1 and to_level == 2:
            return cfg.efficiency_t1_to_t2
        elif from_level == 2 and to_level == 3:
            return cfg.efficiency_t2_to_t3
        elif from_level == 3 and to_level == 4:
            return cfg.efficiency_t3_to_t4
        elif from_level == 4 and to_level == 5:
            return cfg.efficiency_t4_to_t5
        else:
            return cfg.default_ecological_efficiency
    
    def get_ecological_efficiency(self, from_level: int, to_level: int) -> float:
        """获取生态效率（供外部使用）"""
        return self._get_efficiency(from_level, to_level, self._config)
    
    def get_species_assimilation_efficiency(
        self,
        species_code: str,
        default: float = 0.10,
    ) -> float:
        """获取物种的同化效率（从生态拟真数据）
        
        同化效率由 EcologicalRealismService 基于语义匹配计算：
        - 草食动物: ~12%
        - 肉食动物: ~25%
        - 腐食动物: ~20%
        - 滤食动物: ~15%
        
        Args:
            species_code: 物种代码
            default: 默认效率值
            
        Returns:
            同化效率 (0.05-0.35)
        """
        # 尝试从生态拟真数据获取
        eco_data = getattr(self, '_ecological_realism_data', None)
        if eco_data:
            efficiencies = eco_data.get("assimilation_efficiencies", {})
            if species_code in efficiencies:
                return efficiencies[species_code]
        
        return default
    
    # ========== 资源压力计算 ==========
    
    def calculate_resource_pressure(
        self,
        tile_id: int,
        population: int,
        body_weight_kg: float,
        trophic_level: int,
    ) -> float:
        """计算物种在地块上的资源压力
        
        Args:
            tile_id: 地块 ID
            population: 种群数量
            body_weight_kg: 体重 (kg)
            trophic_level: 营养级
            
        Returns:
            资源压力 (0-1)
        """
        cfg = self._config
        
        state = self._tile_states.get(tile_id)
        if not state or state.current_npp <= 0:
            return cfg.resource_pressure_cap
        
        # 计算代谢需求
        # 使用异速生长：需求 ∝ 体重^0.75
        individual_demand = cfg.metabolic_rate_coefficient * (body_weight_kg ** cfg.metabolic_weight_exponent)
        total_demand = individual_demand * population
        
        # 计算可用供给
        capacity = self.get_trophic_capacity(tile_id, trophic_level, body_weight_kg)
        available_supply = capacity * body_weight_kg * cfg.harvestable_fraction
        
        if available_supply <= 0:
            return cfg.resource_pressure_cap
        
        # 压力 = 需求 / 供给
        pressure_ratio = total_demand / available_supply
        
        # 使用 sigmoid 平滑
        # pressure_ratio = 1.0 → pressure ≈ 0.3
        # pressure_ratio = 2.0 → pressure ≈ 0.5
        # pressure_ratio = 5.0 → pressure ≈ 0.6
        pressure = cfg.resource_pressure_cap * (1 - math.exp(-pressure_ratio))
        
        return max(cfg.resource_pressure_floor, min(cfg.resource_pressure_cap, pressure))
    
    # ========== 事件脉冲 ==========
    
    def apply_event_pulse(
        self,
        tile_id: int,
        event_type: str,
        duration_turns: int = 3,
    ):
        """应用事件脉冲
        
        Args:
            tile_id: 地块 ID
            event_type: 事件类型 (volcanic_ash, flood, drought, etc.)
            duration_turns: 持续回合数
        """
        cfg = self._config
        
        if tile_id not in self._event_pulses:
            self._event_pulses[tile_id] = []
        
        if event_type == "volcanic_ash":
            multiplier = cfg.volcanic_ash_boost
            decay = cfg.volcanic_ash_decay
        elif event_type == "flood":
            # 先损失后提升
            multiplier = 1 - cfg.flood_initial_loss
            decay = -cfg.flood_fertility_boost / duration_turns  # 负衰减=增长
        elif event_type == "drought":
            multiplier = cfg.drought_resource_penalty
            decay = 0.1  # 慢恢复
        else:
            multiplier = 1.0
            decay = 0.2
        
        self._event_pulses[tile_id].append((event_type, multiplier, decay, duration_turns))
        
        # 立即更新状态
        if tile_id in self._tile_states:
            self._tile_states[tile_id].event_multiplier = self._get_event_multiplier(tile_id)
        
        self._logger.info(
            f"[资源事件] 地块{tile_id}: {event_type}, 倍率={multiplier:.2f}, 持续{duration_turns}回合"
        )
    
    # ========== 快照与缓存 ==========
    
    def get_snapshot(self, turn_index: int) -> ResourceSnapshot:
        """获取资源系统快照"""
        if self._snapshot is not None and self._last_turn == turn_index:
            return self._snapshot
        
        # 构建快照
        total_npp = sum(s.current_npp for s in self._tile_states.values())
        avg_npp = total_npp / len(self._tile_states) if self._tile_states else 0
        overgrazing_tiles = sum(
            1 for s in self._tile_states.values()
            if s.last_consumption_ratio > self._config.overgrazing_threshold
        )
        
        # 构建向量
        tile_ids = sorted(self._tile_states.keys())
        npp_vector = np.array([self._tile_states[tid].current_npp for tid in tile_ids])
        t1_capacity_vector = np.array([self._tile_states[tid].t1_capacity_kg for tid in tile_ids])
        
        self._snapshot = ResourceSnapshot(
            turn_index=turn_index,
            tile_states=self._tile_states.copy(),
            total_npp=total_npp,
            avg_npp=avg_npp,
            overgrazing_tiles=overgrazing_tiles,
            npp_vector=npp_vector,
            t1_capacity_vector=t1_capacity_vector,
        )
        
        return self._snapshot
    
    def get_tile_state(self, tile_id: int) -> TileResourceState | None:
        """获取单个地块的资源状态"""
        return self._tile_states.get(tile_id)
    
    def initialize_tiles(self, tiles: Sequence["MapTile"]):
        """初始化所有地块的资源状态"""
        for tile in tiles:
            tid = tile.id
            if tid not in self._tile_states:
                self._tile_states[tid] = TileResourceState(tile_id=tid)
            
            state = self._tile_states[tid]
            state.base_npp = self.calculate_npp(tile)
            state.current_npp = state.base_npp
            state.t1_capacity_kg = state.current_npp * self._config.npp_to_capacity_factor
        
        self._logger.info(f"[资源管理] 初始化 {len(tiles)} 个地块的资源状态")
    
    def clear_cache(self):
        """清除缓存"""
        self._snapshot = None
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        if not self._tile_states:
            return {
                "total_tiles": 0,
                "total_npp": 0,
                "avg_npp": 0,
                "overgrazing_tiles": 0,
                "event_affected_tiles": len(self._event_pulses),
            }
        
        snapshot = self.get_snapshot(self._last_turn)
        return {
            "total_tiles": len(self._tile_states),
            "total_npp": round(snapshot.total_npp, 2),
            "avg_npp": round(snapshot.avg_npp, 2),
            "overgrazing_tiles": snapshot.overgrazing_tiles,
            "event_affected_tiles": len(self._event_pulses),
        }


import warnings

_resource_manager_warned: bool = False


def get_resource_manager() -> ResourceManager:
    """Get resource manager instance
    
    .. deprecated::
        Use ``Depends(get_resource_manager)`` from ``api.dependencies`` instead.
        This function uses the deprecated global container singleton.
    
    Raises:
        RuntimeError: If container not initialized
    """
    global _resource_manager_warned
    
    if not _resource_manager_warned:
        warnings.warn(
            "get_resource_manager() is deprecated. Use Depends(get_resource_manager) "
            "from api.dependencies which accesses app.state.container.resource_manager.",
            DeprecationWarning,
            stacklevel=2
        )
        _resource_manager_warned = True
    
    from ...core.container import get_container
    
    container = get_container()
    if container is None:
        raise RuntimeError(
            "ResourceManager requires container access, but container not initialized. "
            "Use Depends(get_resource_manager) for proper injection."
        )
    return container.resource_manager
