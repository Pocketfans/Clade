"""
Stage Configuration - 阶段配置

该模块定义了流水线中各阶段的配置，包括：
- 阶段是否启用
- 阶段顺序
- 阶段参数
- 多种模拟模式（minimal/standard/full/debug）
- 模式参数（默认回合时长、压力缩放系数等）

支持从 YAML 配置文件或代码配置。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Type, Dict

if TYPE_CHECKING:
    from .stages import BaseStage

logger = logging.getLogger(__name__)


# 支持的模式名称
AVAILABLE_MODES = ["minimal", "standard", "full", "debug"]


# ============================================================================
# 模式参数
# ============================================================================

@dataclass
class ModeParameters:
    """模式参数配置
    
    不同模式可以指定不同的默认参数值，
    这些参数会在引擎加载模式时应用到 SimulationContext 或全局配置。
    """
    
    # 默认回合时长（秒）
    default_turn_duration: float = 1.0
    
    # 默认压力强度缩放系数
    pressure_scale: float = 1.0
    
    # 默认物种数量上限
    max_species_count: int = 500
    
    # 分化频率限制（每回合最多分化次数）
    max_speciations_per_turn: int = 5
    
    # 日志详细程度（0=最少, 1=正常, 2=详细, 3=调试）
    log_verbosity: int = 1
    
    # AI 调用超时（秒）
    ai_timeout: float = 30.0
    
    # 是否启用性能统计
    enable_profiling: bool = False
    
    # 是否启用快照自动保存
    auto_snapshot: bool = False
    
    # 自动快照间隔（回合数，0=禁用）
    snapshot_interval: int = 0
    
    # 随机种子（0=不固定）
    random_seed: int = 0
    
    # 额外的自定义参数
    custom_params: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def for_minimal(cls) -> "ModeParameters":
        """minimal 模式的默认参数"""
        return cls(
            default_turn_duration=0.5,
            pressure_scale=0.8,
            max_species_count=100,
            max_speciations_per_turn=2,
            log_verbosity=0,
            ai_timeout=10.0,
            enable_profiling=False,
            auto_snapshot=False,
        )
    
    @classmethod
    def for_standard(cls) -> "ModeParameters":
        """standard 模式的默认参数"""
        return cls(
            default_turn_duration=1.0,
            pressure_scale=1.0,
            max_species_count=300,
            max_speciations_per_turn=5,
            log_verbosity=1,
            ai_timeout=30.0,
            enable_profiling=False,
            auto_snapshot=False,
        )
    
    @classmethod
    def for_full(cls) -> "ModeParameters":
        """full 模式的默认参数"""
        return cls(
            default_turn_duration=2.0,
            pressure_scale=1.0,
            max_species_count=500,
            max_speciations_per_turn=10,
            log_verbosity=2,
            ai_timeout=60.0,
            enable_profiling=False,
            auto_snapshot=True,
            snapshot_interval=50,
        )
    
    @classmethod
    def for_debug(cls) -> "ModeParameters":
        """debug 模式的默认参数"""
        return cls(
            default_turn_duration=0.5,
            pressure_scale=1.0,
            max_species_count=200,
            max_speciations_per_turn=3,
            log_verbosity=3,
            ai_timeout=15.0,
            enable_profiling=True,
            auto_snapshot=True,
            snapshot_interval=10,
        )
    
    @classmethod
    def for_mode(cls, mode: str) -> "ModeParameters":
        """根据模式名称获取默认参数"""
        factories = {
            "minimal": cls.for_minimal,
            "standard": cls.for_standard,
            "full": cls.for_full,
            "debug": cls.for_debug,
        }
        factory = factories.get(mode, cls.for_standard)
        return factory()
    
    def merge(self, overrides: Dict[str, Any]) -> "ModeParameters":
        """合并自定义覆盖参数"""
        import copy
        new_params = copy.copy(self)
        for key, value in overrides.items():
            if hasattr(new_params, key):
                setattr(new_params, key, value)
            else:
                new_params.custom_params[key] = value
        return new_params
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "default_turn_duration": self.default_turn_duration,
            "pressure_scale": self.pressure_scale,
            "max_species_count": self.max_species_count,
            "max_speciations_per_turn": self.max_speciations_per_turn,
            "log_verbosity": self.log_verbosity,
            "ai_timeout": self.ai_timeout,
            "enable_profiling": self.enable_profiling,
            "auto_snapshot": self.auto_snapshot,
            "snapshot_interval": self.snapshot_interval,
            "random_seed": self.random_seed,
            **self.custom_params,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModeParameters":
        """从字典创建"""
        known_keys = {
            "default_turn_duration", "pressure_scale", "max_species_count",
            "max_speciations_per_turn", "log_verbosity", "ai_timeout",
            "enable_profiling", "auto_snapshot", "snapshot_interval", "random_seed",
        }
        kwargs = {k: v for k, v in data.items() if k in known_keys}
        custom = {k: v for k, v in data.items() if k not in known_keys}
        params = cls(**kwargs)
        params.custom_params = custom
        return params


@dataclass
class StageConfig:
    """单个阶段的配置"""
    name: str
    enabled: bool = True
    order: int = 0
    params: dict[str, Any] = field(default_factory=dict)
    
    # 可选：阶段类（用于动态实例化）
    stage_class: Type[BaseStage] | None = None
    # 可选：阶段工厂函数（用于复杂的实例化逻辑）
    factory: Callable[..., BaseStage] | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> "StageConfig":
        """从字典创建配置"""
        return cls(
            name=data["name"],
            enabled=data.get("enabled", True),
            order=data.get("order", 0),
            params=data.get("params", {}),
        )


@dataclass 
class PipelineStageConfig:
    """流水线阶段配置集合"""
    
    # 核心阶段（总是启用）
    init: StageConfig = field(default_factory=lambda: StageConfig(
        name="init", enabled=True, order=0
    ))
    parse_pressures: StageConfig = field(default_factory=lambda: StageConfig(
        name="parse_pressures", enabled=True, order=10
    ))
    map_evolution: StageConfig = field(default_factory=lambda: StageConfig(
        name="map_evolution", enabled=True, order=20
    ))
    fetch_species: StageConfig = field(default_factory=lambda: StageConfig(
        name="fetch_species", enabled=True, order=30
    ))
    tiering_and_niche: StageConfig = field(default_factory=lambda: StageConfig(
        name="tiering_and_niche", enabled=True, order=40
    ))
    preliminary_mortality: StageConfig = field(default_factory=lambda: StageConfig(
        name="preliminary_mortality", enabled=True, order=50
    ))
    migration: StageConfig = field(default_factory=lambda: StageConfig(
        name="migration", enabled=True, order=60
    ))
    final_mortality: StageConfig = field(default_factory=lambda: StageConfig(
        name="final_mortality", enabled=True, order=80
    ))
    population_update: StageConfig = field(default_factory=lambda: StageConfig(
        name="population_update", enabled=True, order=90
    ))
    
    # 可选阶段（可通过配置禁用）
    tectonic_movement: StageConfig = field(default_factory=lambda: StageConfig(
        name="tectonic_movement", enabled=True, order=25
    ))
    food_web: StageConfig = field(default_factory=lambda: StageConfig(
        name="food_web", enabled=True, order=35
    ))
    gene_activation: StageConfig = field(default_factory=lambda: StageConfig(
        name="gene_activation", enabled=True, order=95
    ))
    gene_flow: StageConfig = field(default_factory=lambda: StageConfig(
        name="gene_flow", enabled=True, order=100
    ))
    genetic_drift: StageConfig = field(default_factory=lambda: StageConfig(
        name="genetic_drift", enabled=True, order=105
    ))
    auto_hybridization: StageConfig = field(default_factory=lambda: StageConfig(
        name="auto_hybridization", enabled=True, order=110
    ))
    subspecies_promotion: StageConfig = field(default_factory=lambda: StageConfig(
        name="subspecies_promotion", enabled=True, order=115
    ))
    background_management: StageConfig = field(default_factory=lambda: StageConfig(
        name="background_management", enabled=True, order=130
    ))
    build_report: StageConfig = field(default_factory=lambda: StageConfig(
        name="build_report", enabled=True, order=140
    ))
    save_map_snapshot: StageConfig = field(default_factory=lambda: StageConfig(
        name="save_map_snapshot", enabled=True, order=150
    ))
    vegetation_cover: StageConfig = field(default_factory=lambda: StageConfig(
        name="vegetation_cover", enabled=True, order=155
    ))
    save_population_snapshot: StageConfig = field(default_factory=lambda: StageConfig(
        name="save_population_snapshot", enabled=True, order=160
    ))
    embedding_hooks: StageConfig = field(default_factory=lambda: StageConfig(
        name="embedding_hooks", enabled=True, order=165
    ))
    save_history: StageConfig = field(default_factory=lambda: StageConfig(
        name="save_history", enabled=True, order=170
    ))
    export_data: StageConfig = field(default_factory=lambda: StageConfig(
        name="export_data", enabled=True, order=175
    ))
    
    def get_enabled_stages(self) -> list[StageConfig]:
        """获取所有启用的阶段配置（按顺序）"""
        all_configs = [
            self.init,
            self.parse_pressures,
            self.map_evolution,
            self.tectonic_movement,
            self.fetch_species,
            self.food_web,
            self.tiering_and_niche,
            self.preliminary_mortality,
            self.migration,
            self.final_mortality,
            self.population_update,
            self.gene_activation,
            self.gene_flow,
            self.genetic_drift,
            self.auto_hybridization,
            self.subspecies_promotion,
            self.background_management,
            self.build_report,
            self.save_map_snapshot,
            self.vegetation_cover,
            self.save_population_snapshot,
            self.embedding_hooks,
            self.save_history,
            self.export_data,
        ]
        return sorted(
            [c for c in all_configs if c.enabled],
            key=lambda c: c.order
        )
    
    def disable_stage(self, name: str) -> None:
        """禁用指定阶段"""
        if hasattr(self, name):
            getattr(self, name).enabled = False
    
    def enable_stage(self, name: str) -> None:
        """启用指定阶段"""
        if hasattr(self, name):
            getattr(self, name).enabled = True


# 默认配置实例
DEFAULT_STAGE_CONFIG = PipelineStageConfig()


def create_stage_config_from_engine_flags(
    use_tectonic: bool = True,
    use_embedding: bool = True,
    use_tile_mortality: bool = True,
) -> PipelineStageConfig:
    """从引擎功能开关创建阶段配置
    
    Args:
        use_tectonic: 是否启用板块系统
        use_embedding: 是否启用 Embedding 集成
        use_tile_mortality: 是否启用地块死亡率
    
    Returns:
        配置好的 PipelineStageConfig
    """
    config = PipelineStageConfig()
    
    # 根据功能开关禁用相应阶段
    if not use_tectonic:
        config.disable_stage("tectonic_movement")
    
    if not use_embedding:
        config.disable_stage("embedding_hooks")
    
    return config


# ============================================================================
# YAML 配置加载
# ============================================================================

def load_stage_config_from_yaml(
    yaml_path: str | Path | None = None,
    mode: str = "standard",
) -> list[StageConfig]:
    """从 YAML 文件加载阶段配置
    
    Args:
        yaml_path: YAML 配置文件路径，为 None 时使用默认路径
        mode: 使用的模式名称 (minimal/standard/full/debug)
    
    Returns:
        启用的阶段配置列表（按顺序排列）
    """
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed, using default config")
        return [StageConfig.from_dict({"name": s.name, "enabled": s.enabled, "order": s.order})
                for s in DEFAULT_STAGE_CONFIG.get_enabled_stages()]
    
    if yaml_path is None:
        yaml_path = Path(__file__).parent / "stage_config.yaml"
    else:
        yaml_path = Path(yaml_path)
    
    if not yaml_path.exists():
        logger.warning(f"Config file not found: {yaml_path}, using default")
        return [StageConfig.from_dict({"name": s.name, "enabled": s.enabled, "order": s.order})
                for s in DEFAULT_STAGE_CONFIG.get_enabled_stages()]
    
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return [StageConfig.from_dict({"name": s.name, "enabled": s.enabled, "order": s.order})
                for s in DEFAULT_STAGE_CONFIG.get_enabled_stages()]
    
    # 获取当前模式
    current_mode = config_data.get("mode", mode)
    if current_mode not in AVAILABLE_MODES:
        logger.warning(f"Unknown mode '{current_mode}', using 'standard'")
        current_mode = "standard"
    
    # 获取模式配置
    modes = config_data.get("modes", {})
    mode_config = modes.get(current_mode, {})
    stages_data = mode_config.get("stages", [])
    
    if not stages_data:
        logger.warning(f"No stages defined for mode '{current_mode}'")
        return []
    
    # 构建配置列表
    configs = []
    for stage_data in stages_data:
        if stage_data.get("enabled", True):
            configs.append(StageConfig.from_dict(stage_data))
    
    # 按顺序排序
    configs.sort(key=lambda c: c.order)
    
    logger.info(f"Loaded {len(configs)} stages for mode '{current_mode}'")
    return configs


def get_mode_description(mode: str) -> str:
    """获取模式描述"""
    descriptions = {
        "minimal": "极简模式：仅保留压力、简单死亡率、繁殖",
        "standard": "标准模式：保留主流程，禁用最重的AI阶段",
        "full": "全功能模式：所有Stage启用",
        "debug": "调试模式：专用调试Stage，打印更多日志",
    }
    return descriptions.get(mode, f"未知模式: {mode}")


def get_mode_parameters(mode: str, overrides: Dict[str, Any] | None = None) -> ModeParameters:
    """获取模式参数
    
    Args:
        mode: 模式名称
        overrides: 覆盖的参数
    
    Returns:
        模式参数对象
    """
    params = ModeParameters.for_mode(mode)
    if overrides:
        params = params.merge(overrides)
    return params


def load_mode_with_parameters(
    mode: str,
    yaml_path: str | Path | None = None,
    param_overrides: Dict[str, Any] | None = None,
) -> tuple[list[StageConfig], ModeParameters]:
    """加载模式配置和参数
    
    Args:
        mode: 模式名称
        yaml_path: YAML 配置文件路径
        param_overrides: 参数覆盖
    
    Returns:
        (阶段配置列表, 模式参数)
    """
    stages = load_stage_config_from_yaml(yaml_path, mode)
    params = get_mode_parameters(mode, param_overrides)
    
    logger.info(f"加载模式 '{mode}':")
    logger.info(f"  阶段数: {len(stages)}")
    logger.info(f"  压力缩放: {params.pressure_scale}")
    logger.info(f"  物种上限: {params.max_species_count}")
    logger.info(f"  日志详细度: {params.log_verbosity}")
    
    return stages, params


def format_mode_info(mode: str, params: ModeParameters | None = None) -> str:
    """格式化模式信息为可读文本"""
    if params is None:
        params = get_mode_parameters(mode)
    
    lines = [
        f"模式: {mode}",
        f"描述: {get_mode_description(mode)}",
        "",
        "参数:",
        f"  回合时长: {params.default_turn_duration}s",
        f"  压力缩放: {params.pressure_scale}",
        f"  物种上限: {params.max_species_count}",
        f"  分化上限/回合: {params.max_speciations_per_turn}",
        f"  日志详细度: {params.log_verbosity}",
        f"  AI 超时: {params.ai_timeout}s",
        f"  性能分析: {'启用' if params.enable_profiling else '禁用'}",
        f"  自动快照: {'启用' if params.auto_snapshot else '禁用'}",
    ]
    
    if params.auto_snapshot and params.snapshot_interval > 0:
        lines.append(f"  快照间隔: 每 {params.snapshot_interval} 回合")
    
    if params.random_seed > 0:
        lines.append(f"  随机种子: {params.random_seed}")
    
    if params.custom_params:
        lines.append("")
        lines.append("自定义参数:")
        for key, value in params.custom_params.items():
            lines.append(f"  {key}: {value}")
    
    return "\n".join(lines)


# ============================================================================
# 阶段注册表 - 用于插件系统
# ============================================================================

class StageRegistry:
    """阶段注册表
    
    用于集中管理所有可用的阶段类型，支持：
    - 按名称查找阶段类
    - 动态注册新阶段
    - 阶段依赖检查
    """
    
    _instance: "StageRegistry | None" = None
    
    def __new__(cls) -> "StageRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._stages = {}
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._stages: dict[str, Type[BaseStage]] = {}
            self._initialized = True
    
    def register(self, name: str, stage_class: Type[BaseStage]) -> None:
        """注册阶段类
        
        Args:
            name: 阶段名称
            stage_class: 阶段类
        """
        self._stages[name] = stage_class
    
    def get(self, name: str) -> Type[BaseStage] | None:
        """获取阶段类
        
        Args:
            name: 阶段名称
        
        Returns:
            阶段类，如果不存在则返回 None
        """
        return self._stages.get(name)
    
    def list_stages(self) -> list[str]:
        """列出所有已注册的阶段名称"""
        return list(self._stages.keys())
    
    def create_stage(self, name: str, **kwargs) -> BaseStage | None:
        """创建阶段实例
        
        Args:
            name: 阶段名称
            **kwargs: 传递给阶段构造函数的参数
        
        Returns:
            阶段实例，如果不存在则返回 None
        """
        stage_class = self.get(name)
        if stage_class:
            return stage_class(**kwargs)
        return None


# 全局注册表实例
stage_registry = StageRegistry()


def register_stage(name: str):
    """阶段注册装饰器
    
    使用方式：
    ```python
    @register_stage("my_custom_stage")
    class MyCustomStage(BaseStage):
        ...
    ```
    """
    def decorator(cls: Type[BaseStage]) -> Type[BaseStage]:
        stage_registry.register(name, cls)
        return cls
    return decorator


# ============================================================================
# StageLoader - 阶段加载器
# ============================================================================

class StageLoader:
    """阶段加载器
    
    根据配置文件加载并构建 Stage 实例列表。
    负责:
    - 从配置创建 Stage 实例
    - 验证依赖关系
    - 排序阶段
    """
    
    def __init__(
        self,
        registry: StageRegistry | None = None,
        yaml_path: str | Path | None = None,
    ):
        """初始化 StageLoader
        
        Args:
            registry: 阶段注册表（默认使用全局注册表）
            yaml_path: YAML 配置文件路径
        """
        self.registry = registry or stage_registry
        self.yaml_path = yaml_path
        self._validation_errors: list[str] = []
        self._validation_warnings: list[str] = []
    
    def load_stages_for_mode(
        self,
        mode: str = "standard",
        validate: bool = True,
    ) -> list[BaseStage]:
        """根据模式加载阶段列表
        
        Args:
            mode: 模式名称 (minimal/standard/full/debug)
            validate: 是否验证依赖关系
        
        Returns:
            排序好的 Stage 实例列表
        
        Raises:
            DependencyError: 依赖验证失败时
        """
        from .stages import StageDependencyValidator, DependencyError
        
        # 加载配置
        stage_configs = load_stage_config_from_yaml(self.yaml_path, mode)
        
        if not stage_configs:
            logger.warning(f"模式 '{mode}' 没有定义任何阶段，使用默认阶段")
            from .stages import get_default_stages
            return get_default_stages()
        
        # 构建阶段实例
        stages = []
        for config in stage_configs:
            if not config.enabled:
                continue
            
            stage = self._create_stage(config)
            if stage:
                stages.append(stage)
            else:
                self._validation_warnings.append(
                    f"⚠️ 阶段 '{config.name}' 未注册，已跳过"
                )
        
        # 按 order 排序
        stages.sort(key=lambda s: s.order)
        
        # 验证依赖
        if validate and stages:
            validator = StageDependencyValidator(stages)
            result = validator.validate()
            
            self._validation_errors = result.errors
            self._validation_warnings.extend(result.warnings)
            
            if not result.valid:
                error_msg = (
                    f"模式 '{mode}' 依赖验证失败:\n" +
                    "\n".join(result.errors)
                )
                logger.error(error_msg)
                raise DependencyError(error_msg)
            
            logger.info(f"[StageLoader] 模式 '{mode}' 加载了 {len(stages)} 个阶段")
            if result.warnings:
                for warn in result.warnings:
                    logger.warning(warn)
        
        return stages
    
    def _create_stage(self, config: StageConfig) -> BaseStage | None:
        """从配置创建阶段实例
        
        Args:
            config: 阶段配置
        
        Returns:
            Stage 实例，如果未注册则返回 None
        """
        stage_class = self.registry.get(config.name)
        if not stage_class:
            return None
        
        try:
            # 如果有参数，尝试传递
            if config.params:
                return stage_class(**config.params)
            else:
                return stage_class()
        except Exception as e:
            logger.warning(f"创建阶段 '{config.name}' 失败: {e}")
            return None
    
    def get_validation_errors(self) -> list[str]:
        """获取验证错误"""
        return self._validation_errors.copy()
    
    def get_validation_warnings(self) -> list[str]:
        """获取验证警告"""
        return self._validation_warnings.copy()
    
    def list_available_stages(self) -> list[str]:
        """列出所有可用的阶段名称"""
        return self.registry.list_stages()
    
    def get_dependency_graph(self, mode: str = "standard") -> str:
        """获取依赖关系图
        
        Args:
            mode: 模式名称
        
        Returns:
            文本形式的依赖图
        """
        from .stages import StageDependencyValidator
        
        try:
            stages = self.load_stages_for_mode(mode, validate=False)
            validator = StageDependencyValidator(stages)
            result = validator.validate()
            return result.dependency_graph
        except Exception as e:
            return f"无法生成依赖图: {e}"


# ============================================================================
# 初始化默认阶段注册
# ============================================================================

def _register_default_stages() -> None:
    """注册默认阶段到注册表"""
    from .stages import (
        # 核心阶段
        InitStage,
        ParsePressuresStage,
        MapEvolutionStage,
        TectonicMovementStage,
        FetchSpeciesStage,
        FoodWebStage,
        TieringAndNicheStage,
        PreliminaryMortalityStage,
        PreyDistributionStage,
        MigrationStage,
        DispersalStage,
        HungerMigrationStage,
        PostMigrationNicheStage,
        FinalMortalityStage,
        PopulationUpdateStage,
        # 遗传与演化阶段
        SpeciationDataTransferStage,
        GeneActivationStage,
        GeneFlowStage,
        GeneticDriftStage,
        AutoHybridizationStage,
        SubspeciesPromotionStage,
        # AI 阶段
        SpeciationStage,
        # 后处理阶段
        BackgroundManagementStage,
        BuildReportStage,
        SaveMapSnapshotStage,
        VegetationCoverStage,
        SavePopulationSnapshotStage,
        EmbeddingStage,
        EmbeddingPluginsStage,
        SaveHistoryStage,
        ExportDataStage,
        FinalizeStage,
    )
    
    # 导入生态拟真阶段
    from .ecological_realism_stage import EcologicalRealismStage
    
    # 核心阶段
    stage_registry.register("init", InitStage)
    stage_registry.register("parse_pressures", ParsePressuresStage)
    stage_registry.register("map_evolution", MapEvolutionStage)
    stage_registry.register("tectonic_movement", TectonicMovementStage)
    stage_registry.register("fetch_species", FetchSpeciesStage)
    stage_registry.register("food_web", FoodWebStage)
    stage_registry.register("tiering_and_niche", TieringAndNicheStage)
    stage_registry.register("ecological_realism", EcologicalRealismStage)  # 生态拟真
    stage_registry.register("preliminary_mortality", PreliminaryMortalityStage)
    stage_registry.register("prey_distribution", PreyDistributionStage)
    stage_registry.register("migration", MigrationStage)
    stage_registry.register("dispersal", DispersalStage)
    stage_registry.register("hunger_migration", HungerMigrationStage)
    stage_registry.register("post_migration_niche", PostMigrationNicheStage)
    stage_registry.register("final_mortality", FinalMortalityStage)
    # ecological_intelligence 已被张量系统替代，不再注册
    stage_registry.register("population_update", PopulationUpdateStage)
    
    # 遗传与演化阶段
    stage_registry.register("speciation_data_transfer", SpeciationDataTransferStage)
    stage_registry.register("gene_activation", GeneActivationStage)
    stage_registry.register("gene_flow", GeneFlowStage)
    stage_registry.register("genetic_drift", GeneticDriftStage)
    stage_registry.register("auto_hybridization", AutoHybridizationStage)
    stage_registry.register("subspecies_promotion", SubspeciesPromotionStage)
    
    # AI 阶段
    stage_registry.register("speciation", SpeciationStage)
    
    # 后处理阶段
    stage_registry.register("background_management", BackgroundManagementStage)
    stage_registry.register("build_report", BuildReportStage)
    stage_registry.register("save_map_snapshot", SaveMapSnapshotStage)
    stage_registry.register("vegetation_cover", VegetationCoverStage)
    stage_registry.register("save_population_snapshot", SavePopulationSnapshotStage)
    stage_registry.register("embedding_hooks", EmbeddingStage)
    stage_registry.register("embedding_plugins", EmbeddingPluginsStage)
    stage_registry.register("save_history", SaveHistoryStage)
    stage_registry.register("export_data", ExportDataStage)
    stage_registry.register("finalize", FinalizeStage)
    
    logger.debug(f"[StageRegistry] 注册了 {len(stage_registry.list_stages())} 个阶段")


# 自动注册默认阶段
_register_default_stages()

