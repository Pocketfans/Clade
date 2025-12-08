"""
Tensor utilities and state containers.

张量计算系统的核心模块，提供：
- TensorState: 统一的张量状态容器
- SpeciationMonitor: 张量分化信号检测器
- SpeciationTrigger: 分化触发信号数据结构
- TradeoffCalculator: 自动代价计算器
- TensorConfig: 张量系统配置
- TensorMetrics: 性能监控指标
- TensorMetricsCollector: 指标收集器
- HybridCompute: NumPy + Taichi 混合计算引擎
- PressureToTensorBridge: 压力→张量桥接器
- MultiFactorMortality: 多因子死亡率计算器
- TensorMigrationEngine: GPU 加速的张量迁徙引擎
- NicheTensorCompute: 张量化生态位重叠计算
- HybridizationTensorCompute: 张量化杂交候选筛选
- TensorSuitabilityCalculator: 【v2.0】增强适宜度计算（生态位分化）

分工策略：
- Taichi: 大规模并行计算（死亡率、扩散、繁殖、竞争、迁徙、适宜度）
- NumPy: 简单操作（聚合、筛选、掩码）
- 批量矩阵: O(n²) 计算（生态位重叠、杂交候选、生态位相似度）

【v2.0 增强适宜度】
TensorSuitabilityCalculator 实现生态位分化和竞争排斥：
- 收紧环境容忍度（温度/湿度/盐度等）
- 生态位拥挤惩罚（同营养级竞争排斥）
- 资源分割因子（相似物种分割资源）
- 专化度/泛化度权衡
"""

from .config import TensorConfig, TensorBalanceConfig, TradeoffConfig
from .metrics import (
    TensorMetrics,
    TensorMetricsCollector,
    get_global_collector,
    reset_global_collector,
)
from .speciation_monitor import SpeciationMonitor, SpeciationTrigger
from .state import TensorState
from .tradeoff import TradeoffCalculator

# 混合计算引擎（NumPy + Taichi）
from .hybrid import HybridCompute, get_compute, reset_compute

# 压力-张量桥接
from .pressure_bridge import (
    PressureChannel,
    PressureTensorOverlay,
    PressureToTensorBridge,
    SpeciesParamsExtractor,
    MultiFactorMortality,
    PressureBridgeConfig,
    get_pressure_bridge,
    get_params_extractor,
    get_multifactor_mortality,
    reset_pressure_bridge,
)

# 张量迁徙引擎
from .migration import (
    TensorMigrationEngine,
    MigrationConfig,
    MigrationMetrics,
    get_migration_engine,
    reset_migration_engine,
    extract_species_preferences,
    extract_habitat_mask,
)

# 张量化生态位计算
from .niche_tensor import (
    NicheTensorCompute,
    NicheTensorMetrics,
    get_niche_tensor_compute,
    reset_niche_tensor_compute,
)

# 张量化杂交候选筛选
from .hybridization_tensor import (
    HybridizationTensorCompute,
    HybridizationTensorMetrics,
    HybridCandidate,
    get_hybridization_tensor_compute,
    reset_hybridization_tensor_compute,
)

# 统一张量生态计算引擎（整合死亡率、扩散、迁徙）
from .ecology import (
    TensorEcologyEngine,
    EcologyConfig,
    EcologyMetrics,
    EcologyResult,
    get_ecology_engine,
    reset_ecology_engine,
    extract_species_params,
    extract_species_prefs,
    extract_trophic_levels,
)

# 张量化竞争计算（Taichi GPU加速）
from .competition import (
    TensorCompetitionCalculator,
    TensorCompetitionResult,
    get_tensor_competition_calculator,
    calculate_competition_tensor,
)

# 张量化适宜度计算（Taichi GPU加速 + 生态位分化）
from .suitability import (
    TensorSuitabilityCalculator,
    EnhancedSuitabilityResult,
    SuitabilityMetrics,
    get_tensor_suitability_calculator,
    reset_tensor_suitability_calculator,
    compute_enhanced_suitability,
)

__all__ = [
    # 核心数据结构
    "TensorState",
    "TensorConfig",
    "TensorBalanceConfig",
    "TradeoffConfig",
    # 物种形成监测
    "SpeciationMonitor",
    "SpeciationTrigger",
    # 权衡计算
    "TradeoffCalculator",
    # 性能监控
    "TensorMetrics",
    "TensorMetricsCollector",
    "get_global_collector",
    "reset_global_collector",
    # 混合计算引擎（推荐使用）
    "HybridCompute",
    "get_compute",
    "reset_compute",
    # 压力-张量桥接
    "PressureChannel",
    "PressureTensorOverlay",
    "PressureToTensorBridge",
    "SpeciesParamsExtractor",
    "MultiFactorMortality",
    "PressureBridgeConfig",
    "get_pressure_bridge",
    "get_params_extractor",
    "get_multifactor_mortality",
    "reset_pressure_bridge",
    # 张量迁徙引擎
    "TensorMigrationEngine",
    "MigrationConfig",
    "MigrationMetrics",
    "get_migration_engine",
    "reset_migration_engine",
    "extract_species_preferences",
    "extract_habitat_mask",
    # 张量化生态位计算
    "NicheTensorCompute",
    "NicheTensorMetrics",
    "get_niche_tensor_compute",
    "reset_niche_tensor_compute",
    # 张量化杂交候选筛选
    "HybridizationTensorCompute",
    "HybridizationTensorMetrics",
    "HybridCandidate",
    "get_hybridization_tensor_compute",
    "reset_hybridization_tensor_compute",
    # 统一张量生态计算引擎
    "TensorEcologyEngine",
    "EcologyConfig",
    "EcologyMetrics",
    "EcologyResult",
    "get_ecology_engine",
    "reset_ecology_engine",
    "extract_species_params",
    "extract_species_prefs",
    "extract_trophic_levels",
    # 张量化竞争计算
    "TensorCompetitionCalculator",
    "TensorCompetitionResult",
    "get_tensor_competition_calculator",
    "calculate_competition_tensor",
    # 张量化适宜度计算
    "TensorSuitabilityCalculator",
    "EnhancedSuitabilityResult",
    "SuitabilityMetrics",
    "get_tensor_suitability_calculator",
    "reset_tensor_suitability_calculator",
    "compute_enhanced_suitability",
]
