"""
Simulation Package - 模拟引擎核心模块

该包包含模拟引擎的核心组件：
- engine: SimulationEngine 主调度器（瘦中枢架构）
- legacy_engine: LegacyTurnRunner 遗留实现（仅用于回归测试）
- context: SimulationContext 回合上下文
- stages: 流水线阶段定义
- pipeline: 流水线执行器
- stage_config: 阶段配置和注册表
- plugin_stages: 插件阶段示例
- regression_test: 回归测试框架
- snapshot: 快照与回滚系统
- logging_config: 日志配置与标签化
- cli: 命令行接口
- species: 死亡率引擎
- tile_based_mortality: 地块级死亡率引擎
- environment: 环境系统

架构说明：
- SimulationEngine 统一使用 Pipeline 执行回合逻辑
- 旧版手写逻辑已迁移到 LegacyTurnRunner（仅用于回归测试）
- 新业务应以 Stage 或 Service 形式加入
"""

from .context import SimulationContext
from .engine import SimulationEngine
from .legacy_engine import LegacyTurnRunner
from .pipeline import (
    Pipeline,
    PipelineBuilder,
    PipelineConfig,
    PipelineResult,
    PipelineMetrics,
    StageMetrics,
)
from .stage_config import (
    StageConfig,
    PipelineStageConfig,
    StageRegistry,
    stage_registry,
    register_stage,
    create_stage_config_from_engine_flags,
    load_stage_config_from_yaml,
    get_mode_description,
    get_mode_parameters,
    load_mode_with_parameters,
    ModeParameters,
    AVAILABLE_MODES,
    StageLoader,
)
from .stages import (
    Stage,
    BaseStage,
    StageOrder,
    StageResult,
    StageDependency,
    StageDependencyValidator,
    DependencyError,
    get_default_stages,
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
    AIStatusEvalStage,
    AINarrativeStage,
    AdaptationStage,
    SpeciationStage,
    # 后处理阶段
    BackgroundManagementStage,
    BuildReportStage,
    SaveMapSnapshotStage,
    VegetationCoverStage,
    SavePopulationSnapshotStage,
    EmbeddingStage,
    SaveHistoryStage,
    ExportDataStage,
    FinalizeStage,
)
from .regression_test import (
    RegressionTestRunner,
    RegressionResult,
    QuickConsistencyChecker,
    generate_regression_report,
    run_quick_consistency_check,
)
from .snapshot import (
    SnapshotManager,
    WorldSnapshot,
    SnapshotMetadata,
    create_snapshot,
    list_snapshots,
    restore_from_snapshot,
    get_snapshot_manager,
)
from .logging_config import (
    LogCategory,
    StageLogger,
    StageSummary,
    LogFilter,
    SimulationLogManager,
    get_log_manager,
    get_stage_logger,
    configure_log_filter,
    enable_debug_logging,
    disable_debug_logging,
)

# 导入插件阶段（自动注册）
from . import plugin_stages

__all__ = [
    # 核心类
    "SimulationEngine",
    "SimulationContext",
    "LegacyTurnRunner",  # 仅用于回归测试
    # 流水线
    "Pipeline",
    "PipelineBuilder",
    "PipelineConfig",
    "PipelineResult",
    "PipelineMetrics",
    "StageMetrics",
    # 阶段
    "Stage",
    "BaseStage",
    "StageOrder",
    "StageResult",
    "StageDependency",
    "StageDependencyValidator",
    "DependencyError",
    "get_default_stages",
    # 配置与模式
    "StageConfig",
    "PipelineStageConfig",
    "StageRegistry",
    "stage_registry",
    "register_stage",
    "create_stage_config_from_engine_flags",
    "load_stage_config_from_yaml",
    "get_mode_description",
    "get_mode_parameters",
    "load_mode_with_parameters",
    "ModeParameters",
    "AVAILABLE_MODES",
    "StageLoader",
    # 回归测试
    "RegressionTestRunner",
    "RegressionResult",
    "QuickConsistencyChecker",
    "generate_regression_report",
    "run_quick_consistency_check",
    # 快照
    "SnapshotManager",
    "WorldSnapshot",
    "SnapshotMetadata",
    "create_snapshot",
    "list_snapshots",
    "restore_from_snapshot",
    "get_snapshot_manager",
    # 日志
    "LogCategory",
    "StageLogger",
    "StageSummary",
    "LogFilter",
    "SimulationLogManager",
    "get_log_manager",
    "get_stage_logger",
    "configure_log_filter",
    "enable_debug_logging",
    "disable_debug_logging",
]
