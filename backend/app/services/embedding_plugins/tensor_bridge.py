"""张量-Embedding桥接模块

提供TensorState到Embedding插件数据格式的转换。
统一数据访问接口，避免重复计算。

设计原则：
1. 优先从TensorState获取种群分布数据（已计算）
2. 提供高效的批量数据转换
3. 保持与原有数据格式的兼容性
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np

if TYPE_CHECKING:
    from ...tensor.state import TensorState
    from ...tensor.speciation_monitor import SpeciationMonitor, SpeciationTrigger
    from ...simulation.context import SimulationContext
    from ...models.species import Species

logger = logging.getLogger(__name__)


@dataclass
class TensorSpeciesDistribution:
    """物种分布数据（从张量提取）"""
    lineage_code: str
    total_population: int
    tile_populations: Dict[str, int]  # {tile_id: population}
    occupied_tiles: List[str]
    max_population_tile: Optional[str] = None
    distribution_entropy: float = 0.0  # 分布均匀度


@dataclass
class TensorEnvironmentProfile:
    """环境剖面数据（从张量提取）"""
    tile_id: str
    temperature: float
    precipitation: float
    elevation: float
    vegetation: float
    species_count: int


@dataclass
class TensorSpeciationSignal:
    """分化信号数据（从张量检测）"""
    lineage_code: str
    signal_type: str  # geographic_isolation | ecological_divergence
    strength: float
    region_count: int = 0
    divergence_score: float = 0.0


class TensorEmbeddingBridge:
    """张量-Embedding桥接器
    
    将TensorState中的numpy数组数据转换为embedding插件友好的格式。
    提供统一的数据访问接口，支持：
    - 种群分布提取
    - 环境数据获取
    - 分化信号传递
    
    使用方式:
    ```python
    bridge = TensorEmbeddingBridge()
    bridge.sync_from_context(ctx)
    
    # 获取物种分布
    dist = bridge.get_species_distribution("SP001")
    
    # 获取分化信号
    signals = bridge.get_speciation_signals(threshold=0.5)
    ```
    """
    
    def __init__(self):
        self._tensor_state: Optional['TensorState'] = None
        self._speciation_monitor: Optional['SpeciationMonitor'] = None
        self._tile_id_map: Dict[int, str] = {}  # tile_idx -> tile_id
        self._species_distributions: Dict[str, TensorSpeciesDistribution] = {}
        self._environment_profiles: Dict[str, TensorEnvironmentProfile] = {}
        self._speciation_signals: List[TensorSpeciationSignal] = []
        self._synced = False
    
    def sync_from_context(
        self, 
        ctx: 'SimulationContext',
        tile_id_map: Optional[Dict[int, str]] = None
    ) -> bool:
        """从SimulationContext同步数据
        
        Args:
            ctx: 模拟上下文
            tile_id_map: 地块索引到ID的映射（可选，自动推断）
            
        Returns:
            是否成功同步
        """
        tensor_state = getattr(ctx, 'tensor_state', None)
        if tensor_state is None:
            logger.debug("[TensorBridge] tensor_state不可用，使用空数据")
            self._synced = False
            return False
        
        self._tensor_state = tensor_state
        
        # 构建地块ID映射
        if tile_id_map:
            self._tile_id_map = tile_id_map
        else:
            self._tile_id_map = self._infer_tile_id_map(ctx)
        
        # 提取种群分布
        self._extract_species_distributions()
        
        # 提取环境数据
        self._extract_environment_profiles(ctx)
        
        # 提取分化信号
        self._extract_speciation_signals(ctx)
        
        self._synced = True
        logger.debug(
            f"[TensorBridge] 同步完成: "
            f"{len(self._species_distributions)}物种, "
            f"{len(self._environment_profiles)}地块, "
            f"{len(self._speciation_signals)}分化信号"
        )
        return True
    
    def _infer_tile_id_map(self, ctx: 'SimulationContext') -> Dict[int, str]:
        """从上下文推断地块ID映射"""
        result = {}
        tiles = getattr(ctx, 'all_tiles', []) or []
        for idx, tile in enumerate(tiles):
            if isinstance(tile, dict):
                tile_id = str(tile.get("id", tile.get("tile_id", idx)))
            else:
                tile_id = str(getattr(tile, 'id', getattr(tile, 'tile_id', idx)))
            result[idx] = tile_id
        return result
    
    def _extract_species_distributions(self) -> None:
        """从TensorState提取种群分布"""
        self._species_distributions.clear()
        
        if self._tensor_state is None:
            return
        
        pop = self._tensor_state.pop  # (S, H, W) 或 (S, 1, T)
        species_map = self._tensor_state.species_map
        
        for lineage_code, species_idx in species_map.items():
            if species_idx >= pop.shape[0]:
                continue
            
            species_pop = pop[species_idx]  # (H, W) 或 (1, T)
            
            # 处理不同维度的张量
            if species_pop.ndim == 2:
                if species_pop.shape[0] == 1:
                    # (1, T) 格式 - 线性化地块
                    flat_pop = species_pop[0]
                else:
                    # (H, W) 格式 - 需要展平
                    flat_pop = species_pop.flatten()
            else:
                flat_pop = species_pop
            
            tile_populations = {}
            occupied_tiles = []
            
            for tile_idx, tile_pop in enumerate(flat_pop):
                if tile_pop > 0:
                    tile_id = self._tile_id_map.get(tile_idx, str(tile_idx))
                    tile_populations[tile_id] = int(tile_pop)
                    occupied_tiles.append(tile_id)
            
            total_population = int(np.sum(flat_pop))
            
            # 计算分布均匀度（熵）
            if len(tile_populations) > 1 and total_population > 0:
                probs = np.array(list(tile_populations.values())) / total_population
                entropy = float(-np.sum(probs * np.log(probs + 1e-10)))
                max_entropy = np.log(len(tile_populations))
                distribution_entropy = entropy / max_entropy if max_entropy > 0 else 0
            else:
                distribution_entropy = 0.0
            
            # 找最大种群地块
            max_tile = None
            if tile_populations:
                max_tile = max(tile_populations, key=tile_populations.get)
            
            self._species_distributions[lineage_code] = TensorSpeciesDistribution(
                lineage_code=lineage_code,
                total_population=total_population,
                tile_populations=tile_populations,
                occupied_tiles=occupied_tiles,
                max_population_tile=max_tile,
                distribution_entropy=distribution_entropy,
            )
    
    def _extract_environment_profiles(self, ctx: 'SimulationContext') -> None:
        """从TensorState提取环境数据"""
        self._environment_profiles.clear()
        
        if self._tensor_state is None:
            return
        
        env = self._tensor_state.env  # (C, H, W) 或 (C, 1, T)
        
        # 环境通道索引（根据张量配置）
        # 默认: 0=海拔, 1=温度, 2=降水, 3=纬度, 4=植被
        ELEV_IDX = 0
        TEMP_IDX = 1
        PRECIP_IDX = 2
        VEG_IDX = 4 if env.shape[0] > 4 else 2
        
        # 处理不同维度
        if env.ndim == 3 and env.shape[1] == 1:
            # (C, 1, T) 格式
            num_tiles = env.shape[2]
            for tile_idx in range(num_tiles):
                tile_id = self._tile_id_map.get(tile_idx, str(tile_idx))
                
                # 计算该地块的物种数
                species_count = 0
                for dist in self._species_distributions.values():
                    if tile_id in dist.tile_populations:
                        species_count += 1
                
                self._environment_profiles[tile_id] = TensorEnvironmentProfile(
                    tile_id=tile_id,
                    temperature=float(env[TEMP_IDX, 0, tile_idx]) if env.shape[0] > TEMP_IDX else 20.0,
                    precipitation=float(env[PRECIP_IDX, 0, tile_idx]) if env.shape[0] > PRECIP_IDX else 500.0,
                    elevation=float(env[ELEV_IDX, 0, tile_idx]) if env.shape[0] > ELEV_IDX else 0.0,
                    vegetation=float(env[VEG_IDX, 0, tile_idx]) if env.shape[0] > VEG_IDX else 0.5,
                    species_count=species_count,
                )
    
    def _extract_speciation_signals(self, ctx: 'SimulationContext') -> None:
        """从TensorState提取分化信号"""
        self._speciation_signals.clear()
        
        # 优先使用ctx中已计算的分化触发
        tensor_trigger_codes = getattr(ctx, 'tensor_trigger_codes', set())
        if tensor_trigger_codes:
            for code in tensor_trigger_codes:
                self._speciation_signals.append(TensorSpeciationSignal(
                    lineage_code=code,
                    signal_type="tensor_triggered",
                    strength=1.0,
                ))
        
        # 如果有SpeciationMonitor，使用它进行更详细的检测
        if self._tensor_state is None:
            return
        
        try:
            from ...tensor import SpeciationMonitor
            
            monitor = SpeciationMonitor(self._tensor_state.species_map)
            triggers = monitor.get_speciation_triggers(
                self._tensor_state,
                threshold=0.5
            )
            
            for trigger in triggers:
                signal = TensorSpeciationSignal(
                    lineage_code=trigger.lineage_code,
                    signal_type=trigger.type,
                    strength=1.0,
                    region_count=trigger.num_regions or 0,
                    divergence_score=trigger.divergence_score or 0.0,
                )
                # 避免重复添加
                if signal.lineage_code not in [s.lineage_code for s in self._speciation_signals]:
                    self._speciation_signals.append(signal)
                    
        except Exception as e:
            logger.debug(f"[TensorBridge] SpeciationMonitor检测失败: {e}")
    
    # ==================== 数据访问接口 ====================
    
    @property
    def is_synced(self) -> bool:
        """是否已同步张量数据"""
        return self._synced
    
    def get_species_distribution(
        self, 
        lineage_code: str
    ) -> Optional[TensorSpeciesDistribution]:
        """获取物种分布数据"""
        return self._species_distributions.get(lineage_code)
    
    def get_all_distributions(self) -> Dict[str, TensorSpeciesDistribution]:
        """获取所有物种分布"""
        return self._species_distributions.copy()
    
    def get_tile_species_codes(self, tile_id: str) -> List[str]:
        """获取指定地块上的物种编码列表"""
        result = []
        for code, dist in self._species_distributions.items():
            if tile_id in dist.tile_populations and dist.tile_populations[tile_id] > 0:
                result.append(code)
        return result
    
    def get_tile_population(self, tile_id: str) -> Dict[str, int]:
        """获取指定地块的种群数据"""
        result = {}
        for code, dist in self._species_distributions.items():
            if tile_id in dist.tile_populations:
                result[code] = dist.tile_populations[tile_id]
        return result
    
    def get_environment_profile(
        self, 
        tile_id: str
    ) -> Optional[TensorEnvironmentProfile]:
        """获取地块环境数据"""
        return self._environment_profiles.get(tile_id)
    
    def get_speciation_signals(
        self, 
        min_strength: float = 0.0
    ) -> List[TensorSpeciationSignal]:
        """获取分化信号"""
        return [s for s in self._speciation_signals if s.strength >= min_strength]
    
    def has_speciation_signal(self, lineage_code: str) -> bool:
        """检查物种是否有分化信号"""
        return any(s.lineage_code == lineage_code for s in self._speciation_signals)
    
    def get_species_isolation_regions(
        self, 
        lineage_code: str
    ) -> int:
        """获取物种的隔离区域数量"""
        for signal in self._speciation_signals:
            if signal.lineage_code == lineage_code and signal.signal_type == "geographic_isolation":
                return signal.region_count
        return 0
    
    def get_species_divergence_score(
        self, 
        lineage_code: str
    ) -> float:
        """获取物种的生态分化得分"""
        for signal in self._speciation_signals:
            if signal.lineage_code == lineage_code and signal.signal_type == "ecological_divergence":
                return signal.divergence_score
        return 0.0
    
    # ==================== 兼容性接口 ====================
    
    def to_legacy_species_distribution(
        self
    ) -> Dict[str, List[str]]:
        """转换为旧格式的物种分布
        
        Returns:
            {tile_id: [species_codes]}
        """
        result: Dict[str, List[str]] = {}
        for code, dist in self._species_distributions.items():
            for tile_id in dist.occupied_tiles:
                if tile_id not in result:
                    result[tile_id] = []
                result[tile_id].append(code)
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """获取桥接器状态摘要"""
        return {
            "synced": self._synced,
            "species_count": len(self._species_distributions),
            "tile_count": len(self._environment_profiles),
            "speciation_signals": len(self._speciation_signals),
            "total_population": sum(
                d.total_population for d in self._species_distributions.values()
            ),
        }


# 全局桥接器实例（可选使用）
_global_bridge: Optional[TensorEmbeddingBridge] = None


def get_tensor_bridge() -> TensorEmbeddingBridge:
    """获取全局桥接器实例"""
    global _global_bridge
    if _global_bridge is None:
        _global_bridge = TensorEmbeddingBridge()
    return _global_bridge


def reset_tensor_bridge() -> None:
    """重置全局桥接器"""
    global _global_bridge
    _global_bridge = TensorEmbeddingBridge()





