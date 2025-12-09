"""张量化适宜度计算模块 - Taichi GPU 加速

综合实现：
1. 收紧环境容忍度 - 温度/湿度/盐度等
2. 生态位拥挤惩罚 - 同营养级竞争排斥
3. 资源分割因子 - 相似物种分割资源
4. 专化度/泛化度权衡 - 专化高分窄范围，泛化低分宽范围
5. 多维环境约束 - 深度、盐度、光照等
6. 历史适应惩罚 - 新环境降低适宜度

依赖：
- Taichi GPU 内核
- Embedding 引擎缓存
- 现有 NicheTensorCompute
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ..models.species import Species
    from ..models.environment import MapTile
    from ..models.config import SuitabilityConfig

logger = logging.getLogger(__name__)


# ============================================================================
# 配置和数据结构
# ============================================================================

@dataclass
class SuitabilityMetrics:
    """适宜度计算性能指标"""
    total_time_ms: float = 0.0
    env_suitability_time_ms: float = 0.0
    crowding_time_ms: float = 0.0
    resource_split_time_ms: float = 0.0
    niche_similarity_time_ms: float = 0.0
    species_count: int = 0
    tile_count: int = 0
    backend: str = "numpy"
    avg_suitability: float = 0.0
    min_suitability: float = 0.0
    max_suitability: float = 0.0


@dataclass
class EnhancedSuitabilityResult:
    """增强适宜度计算结果"""
    # 最终适宜度矩阵 (S, H, W) 或 (S, T) - 取决于计算模式
    suitability: np.ndarray
    # 各因子分解
    env_suitability: np.ndarray | None = None  # 纯环境适宜度
    crowding_factor: np.ndarray | None = None  # 拥挤惩罚因子
    resource_split_factor: np.ndarray | None = None  # 资源分割因子
    # 物种专化度
    specialization: np.ndarray | None = None
    # 物种间生态位相似度矩阵
    niche_similarity: np.ndarray | None = None
    # 性能指标
    metrics: SuitabilityMetrics = field(default_factory=SuitabilityMetrics)


# ============================================================================
# 核心计算器
# ============================================================================

class TensorSuitabilityCalculator:
    """张量化适宜度计算器 - Taichi GPU 加速
    
    实现完整的生态位分化和竞争排斥机制。
    
    使用方法：
        calc = TensorSuitabilityCalculator(config)
        result = calc.compute_all(species_list, tiles, env_tensor, pop_tensor)
    """
    
    # 特质名称到索引的映射
    TRAIT_INDICES = {
        "耐寒性": 0,
        "耐热性": 1,
        "耐旱性": 2,
        "耐盐性": 3,
        "光照需求": 4,
    }
    
    # 环境通道索引（需要与环境张量格式匹配）
    ENV_CHANNELS = {
        "temperature": 0,
        "humidity": 1,
        "elevation": 2,
        "resources": 3,
        "salinity": 4,
        "light": 5,
        "land": 6,
        "ocean": 7,
        "coastal": 8,
    }
    
    def __init__(self, config: "SuitabilityConfig | None" = None):
        """初始化计算器
        
        Args:
            config: 适宜度配置，如果为 None 使用默认值
        """
        self._config = config
        self._taichi_available = False
        self._kernels = None
        
        # 缓存
        self._species_traits_cache: dict[str, np.ndarray] = {}
        self._niche_similarity_cache: np.ndarray | None = None
        self._niche_similarity_codes: list[str] = []
        self._specialization_cache: dict[str, float] = {}
        self._historical_presence_cache: np.ndarray | None = None
        
        # 尝试加载 Taichi 内核
        self._init_taichi()
    
    def _init_taichi(self) -> None:
        """初始化 Taichi 内核 - GPU-only 模式"""
        from . import taichi_hybrid_kernels as _kernels
        self._taichi_available = True
        self._kernels = _kernels
        logger.debug("[TensorSuitability] Taichi GPU 内核加载成功")
    
    def reload_config(self, config: "SuitabilityConfig") -> None:
        """重新加载配置"""
        self._config = config
    
    def clear_cache(self) -> None:
        """清除缓存"""
        self._species_traits_cache.clear()
        self._niche_similarity_cache = None
        self._niche_similarity_codes = []
        self._specialization_cache.clear()
        self._historical_presence_cache = None
    
    # ========================================================================
    # 栖息地掩码生成 (GPU 兼容)
    # ========================================================================
    
    def compute_habitat_mask(
        self,
        species_list: Sequence["Species"],
        env_tensor: np.ndarray,
    ) -> np.ndarray:
        """基于物种 habitat_type 生成栖息地硬约束掩码
        
        【关键】这是水生/陆生硬约束的 GPU 实现！
        
        Args:
            species_list: 物种列表
            env_tensor: 环境张量 (C, H, W)，需要包含 land/ocean 通道
            
        Returns:
            habitat_mask (S, H, W): 0=不可生存, 1=可生存
        """
        S = len(species_list)
        _, H, W = env_tensor.shape
        
        mask = np.ones((S, H, W), dtype=np.float32)
        
        # 获取环境中的水域/陆地通道
        land_idx = self.ENV_CHANNELS.get("land", 6)
        ocean_idx = self.ENV_CHANNELS.get("ocean", 7)
        
        # 提取水域/陆地层
        if env_tensor.shape[0] > land_idx:
            is_land = env_tensor[land_idx] > 0.5  # (H, W) bool
        else:
            # 后备：使用海拔判断
            elevation_idx = self.ENV_CHANNELS.get("elevation", 2)
            is_land = env_tensor[elevation_idx] > 0  # 海拔>0为陆地
        
        if env_tensor.shape[0] > ocean_idx:
            is_ocean = env_tensor[ocean_idx] > 0.5
        else:
            is_ocean = ~is_land
        
        # 定义栖息地类型到环境约束的映射
        AQUATIC_HABITATS = {"marine", "deep_sea", "freshwater", "coastal", "hydrothermal"}
        TERRESTRIAL_HABITATS = {"terrestrial", "aerial"}
        
        for s, species in enumerate(species_list):
            habitat = (getattr(species, 'habitat_type', '') or '').lower()
            
            if habitat in AQUATIC_HABITATS:
                # 水生物种：只能在水域生存
                # 陆地区域 mask = 0 (完全不可生存)
                mask[s] = np.where(is_land & ~is_ocean, 0.0, 1.0)
                
            elif habitat in TERRESTRIAL_HABITATS:
                # 陆生物种：只能在陆地生存
                # 深水区域 mask = 0
                mask[s] = np.where(is_ocean & ~is_land, 0.0, 1.0)
                
            elif habitat == "amphibious":
                # 两栖：都可以，但有轻微偏好
                # 不设硬约束，保持全1
                pass
            
            # 其他未知类型：保持全1，由环境适宜度自然筛选
        
        return mask
    
    # ========================================================================
    # 主计算接口
    # ========================================================================
    
    def compute_all(
        self,
        species_list: Sequence["Species"],
        env_tensor: np.ndarray,
        pop_tensor: np.ndarray,
        habitat_mask: np.ndarray | None = None,
        historical_presence: np.ndarray | None = None,
        auto_generate_mask: bool = True,
    ) -> EnhancedSuitabilityResult:
        """一次性计算所有物种对所有地块的增强适宜度
        
        Args:
            species_list: 物种列表
            env_tensor: 环境张量 (C, H, W)
            pop_tensor: 种群张量 (S, H, W)
            habitat_mask: 栖息地掩码 (S, H, W)，如果为 None 且 auto_generate_mask=True 则自动生成
            historical_presence: 历史存在记录 (S, H, W)，可选
            auto_generate_mask: 是否自动生成栖息地掩码（基于 habitat_type）
            
        Returns:
            EnhancedSuitabilityResult 包含最终适宜度和各因子分解
        """
        start_time = time.perf_counter()
        metrics = SuitabilityMetrics(
            species_count=len(species_list),
            backend="taichi" if self._taichi_available else "numpy",
        )
        
        S = len(species_list)
        _, H, W = env_tensor.shape
        metrics.tile_count = H * W
        
        if S == 0:
            return EnhancedSuitabilityResult(
                suitability=np.array([], dtype=np.float32),
                metrics=metrics,
            )
        
        # 获取配置参数
        cfg = self._get_config()
        
        # 1. 提取物种特质矩阵
        species_traits = self._extract_species_traits(species_list)
        
        # 2. 计算专化度
        t0 = time.perf_counter()
        specialization = self._compute_specialization(species_traits, S)
        
        # 将专化度添加到 traits 矩阵
        species_traits_ext = np.concatenate([
            species_traits, 
            specialization.reshape(-1, 1)
        ], axis=1).astype(np.float32)
        
        # 3. 获取营养级
        trophic_levels = np.array([
            sp.trophic_level for sp in species_list
        ], dtype=np.float32)
        
        # 4. 计算生态位相似度矩阵
        t1 = time.perf_counter()
        niche_similarity = self._compute_niche_similarity(species_list, species_traits)
        metrics.niche_similarity_time_ms = (time.perf_counter() - t1) * 1000
        
        # 5. 准备 habitat_mask
        # 【关键】自动生成基于 habitat_type 的硬约束掩码
        if habitat_mask is None:
            if auto_generate_mask:
                habitat_mask = self.compute_habitat_mask(species_list, env_tensor)
                logger.debug(f"[TensorSuitability] 自动生成 habitat_mask, 约束数: {np.sum(habitat_mask < 0.5)}")
            else:
                habitat_mask = np.ones((S, H, W), dtype=np.float32)
        
        # 6. 计算适宜度 [GPU-only]
        result = self._compute_taichi(
            env_tensor, species_traits_ext, habitat_mask,
            trophic_levels, pop_tensor, niche_similarity,
            cfg, S, H, W, metrics
        )
        
        # 7. 可选：历史适应惩罚
        if historical_presence is not None:
            result = self._apply_historical_penalty(
                result, historical_presence, cfg
            )
        
        # 统计
        metrics.total_time_ms = (time.perf_counter() - start_time) * 1000
        metrics.avg_suitability = float(np.mean(result))
        metrics.min_suitability = float(np.min(result))
        metrics.max_suitability = float(np.max(result))
        
        logger.info(
            f"[TensorSuitability] S={S}, tiles={H}x{W}, "
            f"avg={metrics.avg_suitability:.3f}, "
            f"range=[{metrics.min_suitability:.3f}, {metrics.max_suitability:.3f}], "
            f"time={metrics.total_time_ms:.1f}ms ({metrics.backend})"
        )
        
        return EnhancedSuitabilityResult(
            suitability=result,
            specialization=specialization,
            niche_similarity=niche_similarity,
            metrics=metrics,
        )
    
    # ========================================================================
    # Taichi GPU 计算
    # ========================================================================
    
    def _compute_taichi(
        self,
        env: np.ndarray,
        species_traits: np.ndarray,
        habitat_mask: np.ndarray,
        trophic_levels: np.ndarray,
        pop: np.ndarray,
        niche_similarity: np.ndarray,
        cfg: dict,
        S: int, H: int, W: int,
        metrics: SuitabilityMetrics,
    ) -> np.ndarray:
        """使用 Taichi GPU 计算适宜度（极端收紧版）"""
        import taichi as ti
        
        result = np.zeros((S, H, W), dtype=np.float32)
        
        # 调用一体化内核
        t0 = time.perf_counter()
        self._kernels.kernel_combined_suitability(
            env.astype(np.float32),
            species_traits.astype(np.float32),
            habitat_mask.astype(np.float32),
            trophic_levels.astype(np.float32),
            pop.astype(np.float32),
            niche_similarity.astype(np.float32),
            result,
            # 环境参数（极端收紧版）
            float(cfg.get("temp_tolerance_coef", 1.0)),
            float(cfg.get("temp_penalty_rate", 0.4)),
            float(cfg.get("humidity_penalty_rate", 4.0)),
            float(cfg.get("salinity_penalty_rate", 5.0)),
            float(cfg.get("light_penalty_rate", 3.0)),
            float(cfg.get("resource_threshold", 0.9)),
            # 竞争参数
            float(cfg.get("crowding_penalty_per_species", 0.25)),
            float(cfg.get("max_crowding_penalty", 0.70)),
            float(cfg.get("trophic_tolerance", 0.3)),
            float(cfg.get("split_coefficient", 0.5)),
            float(cfg.get("min_split_factor", 0.2)),
            # 专化度参数
            float(cfg.get("generalist_threshold", 0.4)),
            float(cfg.get("generalist_penalty_base", 0.60)),
            # 权重
            float(cfg.get("weight_temperature", 0.30)),
            float(cfg.get("weight_humidity", 0.15)),
            float(cfg.get("weight_salinity", 0.15)),
            float(cfg.get("weight_light", 0.10)),
            float(cfg.get("weight_resources", 0.30)),
            # 环境通道索引
            self.ENV_CHANNELS["temperature"],
            self.ENV_CHANNELS["humidity"],
            self.ENV_CHANNELS["resources"],
            self.ENV_CHANNELS["salinity"],
            self.ENV_CHANNELS["light"],
        )
        
        ti.sync()
        metrics.env_suitability_time_ms = (time.perf_counter() - t0) * 1000
        
        return result
    
    
    # ========================================================================
    # 辅助计算
    # ========================================================================
    
    def _extract_species_traits(self, species_list: Sequence["Species"]) -> np.ndarray:
        """提取物种特质矩阵"""
        S = len(species_list)
        traits = np.zeros((S, 5), dtype=np.float32)
        
        for i, sp in enumerate(species_list):
            code = sp.lineage_code
            
            # 检查缓存
            if code in self._species_traits_cache:
                traits[i] = self._species_traits_cache[code]
                continue
            
            # 提取特质
            abs_traits = sp.abstract_traits or {}
            sp_traits = np.array([
                abs_traits.get("耐寒性", 5.0),
                abs_traits.get("耐热性", 5.0),
                abs_traits.get("耐旱性", 5.0),
                abs_traits.get("耐盐性", 5.0),
                abs_traits.get("光照需求", 5.0),
            ], dtype=np.float32)
            
            traits[i] = sp_traits
            self._species_traits_cache[code] = sp_traits
        
        return traits
    
    def _compute_specialization(self, traits: np.ndarray, S: int) -> np.ndarray:
        """计算物种专化度 [GPU-only]"""
        import taichi as ti
        result = np.zeros(S, dtype=np.float32)
        self._kernels.kernel_compute_specialization(
            traits.astype(np.float32), result, 5  # 前5个特质
        )
        ti.sync()
        return result
    
    def _compute_niche_similarity(
        self, 
        species_list: Sequence["Species"],
        traits: np.ndarray,
    ) -> np.ndarray:
        """计算物种间生态位相似度矩阵
        
        利用现有的 embedding 缓存和特征向量
        """
        S = len(species_list)
        codes = [sp.lineage_code for sp in species_list]
        
        # 检查缓存
        if (self._niche_similarity_cache is not None and 
            self._niche_similarity_codes == codes):
            return self._niche_similarity_cache
        
        # 构建特征矩阵（使用特质 + 营养级 + 栖息地类型）
        features = np.zeros((S, 8), dtype=np.float32)
        
        for i, sp in enumerate(species_list):
            # 基本特质（归一化到 0-1）
            features[i, :5] = traits[i] / 10.0
            # 营养级（归一化）
            features[i, 5] = sp.trophic_level / 5.0
            # 栖息地类型编码
            habitat_type = (getattr(sp, 'habitat_type', '') or 'terrestrial').lower()
            habitat_codes = {
                "marine": 0.0, "deep_sea": 0.1, "coastal": 0.3,
                "freshwater": 0.5, "amphibious": 0.6,
                "terrestrial": 0.8, "aerial": 1.0
            }
            features[i, 6] = habitat_codes.get(habitat_type, 0.5)
            # 食性类型
            diet_type = (getattr(sp, 'diet_type', '') or 'herbivore').lower()
            diet_codes = {
                "autotroph": 0.0, "herbivore": 0.3, "omnivore": 0.5,
                "carnivore": 0.8, "detritivore": 0.2
            }
            features[i, 7] = diet_codes.get(diet_type, 0.3)
        
        # 特征权重
        weights = np.array([
            0.10, 0.10, 0.10, 0.10, 0.05,  # 特质权重
            0.25,  # 营养级权重（重要！）
            0.20,  # 栖息地权重
            0.10,  # 食性权重
        ], dtype=np.float32)
        
        # 计算相似度矩阵 [GPU-only]
        import taichi as ti
        similarity = np.zeros((S, S), dtype=np.float32)
        self._kernels.kernel_compute_niche_similarity(
            features, similarity, weights
        )
        ti.sync()
        
        # 缓存
        self._niche_similarity_cache = similarity
        self._niche_similarity_codes = codes
        
        return similarity
    
    def _apply_historical_penalty(
        self,
        suitability: np.ndarray,
        historical_presence: np.ndarray,
        cfg: dict,
    ) -> np.ndarray:
        """应用历史适应惩罚 [GPU-only]"""
        import taichi as ti
        novelty_penalty = cfg.get("novelty_penalty", 0.8)
        adaptation_bonus = cfg.get("adaptation_bonus", 1.1)
        
        result = np.zeros_like(suitability)
        self._kernels.kernel_historical_adaptation_penalty(
            suitability.astype(np.float32),
            historical_presence.astype(np.float32),
            result,
            float(novelty_penalty),
            float(adaptation_bonus),
        )
        ti.sync()
        return result
    
    def _get_config(self) -> dict:
        """获取配置参数
        
        【v2.0 极端收紧版】默认参数设计目标：
        - 温度适应范围：5-10°C（非常狭窄）
        - 同生态位2个物种时适宜度降50%
        - 泛化物种适宜度打6折
        - 新环境适宜度打6.5折
        """
        if self._config is not None:
            return {
                # 环境容忍度
                "temp_tolerance_coef": getattr(self._config, 'temp_tolerance_coef', 1.0),
                "temp_penalty_rate": getattr(self._config, 'temp_penalty_rate', 0.4),
                "humidity_penalty_rate": getattr(self._config, 'humidity_penalty_rate', 4.0),
                "salinity_penalty_rate": getattr(self._config, 'salinity_penalty_rate', 5.0),
                "light_penalty_rate": getattr(self._config, 'light_penalty_rate', 3.0),
                "resource_threshold": getattr(self._config, 'resource_threshold', 0.9),
                # 拥挤惩罚
                "crowding_penalty_per_species": getattr(self._config, 'crowding_penalty_per_species', 0.25),
                "max_crowding_penalty": getattr(self._config, 'max_crowding_penalty', 0.70),
                "trophic_tolerance": getattr(self._config, 'trophic_tolerance', 0.3),
                # 资源分割
                "split_coefficient": getattr(self._config, 'split_coefficient', 0.5),
                "min_split_factor": getattr(self._config, 'min_split_factor', 0.2),
                # 专化度权衡
                "generalist_threshold": getattr(self._config, 'generalist_threshold', 0.4),
                "generalist_penalty_base": getattr(self._config, 'generalist_penalty_base', 0.60),
                # 历史适应
                "novelty_penalty": getattr(self._config, 'novelty_penalty', 0.65),
                "adaptation_bonus": getattr(self._config, 'adaptation_bonus', 1.15),
                # 权重
                "weight_temperature": getattr(self._config, 'weight_temperature', 0.30),
                "weight_humidity": getattr(self._config, 'weight_humidity', 0.15),
                "weight_salinity": getattr(self._config, 'weight_salinity', 0.15),
                "weight_light": getattr(self._config, 'weight_light', 0.10),
                "weight_resources": getattr(self._config, 'weight_resources', 0.30),
                # 开关
                "enable_enhanced_suitability": getattr(self._config, 'enable_enhanced_suitability', True),
                "enable_crowding_penalty": getattr(self._config, 'enable_crowding_penalty', True),
                "enable_resource_split": getattr(self._config, 'enable_resource_split', True),
                "enable_specialization_tradeoff": getattr(self._config, 'enable_specialization_tradeoff', True),
                "enable_historical_adaptation": getattr(self._config, 'enable_historical_adaptation', True),
            }
        
        # 默认配置（极端收紧版）
        return {
            # 环境容忍度（极端收紧）
            "temp_tolerance_coef": 1.0,      # 温度范围5-10°C
            "temp_penalty_rate": 0.4,        # 超出2.5°C归零
            "humidity_penalty_rate": 4.0,    # 湿度差0.25归零
            "salinity_penalty_rate": 5.0,    # 盐度差0.2归零
            "light_penalty_rate": 3.0,       # 光照差0.33归零
            "resource_threshold": 0.9,       # 资源需90%才满分
            # 拥挤惩罚（加强）
            "crowding_penalty_per_species": 0.25,  # 2个竞争者-50%
            "max_crowding_penalty": 0.70,          # 最多-70%
            "trophic_tolerance": 0.3,              # 营养级差0.3视为同级
            # 资源分割（加强）
            "split_coefficient": 0.5,         # 高重叠大幅分割
            "min_split_factor": 0.2,          # 最低保留20%
            # 专化度权衡（加强）
            "generalist_threshold": 0.4,      # 专化度<0.4为泛化
            "generalist_penalty_base": 0.60,  # 泛化打6折
            # 历史适应（加强）
            "novelty_penalty": 0.65,          # 新环境打6.5折
            "adaptation_bonus": 1.15,         # 老环境+15%
            # 权重
            "weight_temperature": 0.30,
            "weight_humidity": 0.15,
            "weight_salinity": 0.15,
            "weight_light": 0.10,
            "weight_resources": 0.30,
            # 开关（默认全开）
            "enable_enhanced_suitability": True,
            "enable_crowding_penalty": True,
            "enable_resource_split": True,
            "enable_specialization_tradeoff": True,
            "enable_historical_adaptation": True,
        }


# ============================================================================
# 便捷函数和单例
# ============================================================================

_tensor_suitability_calculator: TensorSuitabilityCalculator | None = None


def get_tensor_suitability_calculator() -> TensorSuitabilityCalculator:
    """获取张量适宜度计算器单例"""
    global _tensor_suitability_calculator
    if _tensor_suitability_calculator is None:
        _tensor_suitability_calculator = TensorSuitabilityCalculator()
    return _tensor_suitability_calculator


def reset_tensor_suitability_calculator() -> None:
    """重置计算器（用于测试）"""
    global _tensor_suitability_calculator
    if _tensor_suitability_calculator is not None:
        _tensor_suitability_calculator.clear_cache()
    _tensor_suitability_calculator = None


def compute_enhanced_suitability(
    species_list: Sequence["Species"],
    env_tensor: np.ndarray,
    pop_tensor: np.ndarray,
    habitat_mask: np.ndarray | None = None,
    config: "SuitabilityConfig | None" = None,
) -> EnhancedSuitabilityResult:
    """便捷函数：计算增强适宜度
    
    Args:
        species_list: 物种列表
        env_tensor: 环境张量 (C, H, W)
        pop_tensor: 种群张量 (S, H, W)
        habitat_mask: 栖息地掩码 (S, H, W)
        config: 适宜度配置
        
    Returns:
        EnhancedSuitabilityResult
    """
    calc = get_tensor_suitability_calculator()
    if config is not None:
        calc.reload_config(config)
    return calc.compute_all(species_list, env_tensor, pop_tensor, habitat_mask)
