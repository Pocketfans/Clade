"""Analytics and reporting services."""

from .ecosystem_health import EcosystemHealthService, EcosystemHealthReport
from .taxonomy import TaxonomyService, TaxonomyResult, CladeInfo
from .evolution_predictor import EvolutionPredictor, PressureVectorLibrary, EvolutionPredictionResult
from .narrative_engine import NarrativeEngine, EventRecord, Era, NarrativeResult
from .encyclopedia import EncyclopediaService, SearchResult, QAResponse, EvolutionExplanation, GameHint
from .embedding_integration import EmbeddingIntegrationService
from .achievements import AchievementService, AchievementDefinition, AchievementProgress, ACHIEVEMENTS
from .game_hints import GameHintsService, GameHint as GameHintModel, HintType, HintPriority
from .report_builder import ReportBuilder
from .report_builder_v2 import ReportBuilderV2

# 新增服务
from .ecosystem_metrics import EcosystemMetricsService, get_ecosystem_metrics_service
from .population_snapshot import PopulationSnapshotService, create_population_snapshot_service
from .turn_report import TurnReportService, create_turn_report_service

__all__ = [
    # 原有服务
    "EcosystemHealthService",
    "EcosystemHealthReport",
    # 分类学服务
    "TaxonomyService",
    "TaxonomyResult",
    "CladeInfo",
    # 演化预测服务
    "EvolutionPredictor",
    "PressureVectorLibrary",
    "EvolutionPredictionResult",
    # 叙事生成服务
    "NarrativeEngine",
    "EventRecord",
    "Era",
    "NarrativeResult",
    # 百科服务
    "EncyclopediaService",
    "SearchResult",
    "QAResponse",
    "EvolutionExplanation",
    "GameHint",
    # 集成服务
    "EmbeddingIntegrationService",
    # 成就系统
    "AchievementService",
    "AchievementDefinition",
    "AchievementProgress",
    "ACHIEVEMENTS",
    # 智能提示
    "GameHintsService",
    "GameHintModel",
    "HintType",
    "HintPriority",
    # 报告生成
    "ReportBuilder",
    "ReportBuilderV2",
    # 生态系统指标
    "EcosystemMetricsService",
    "get_ecosystem_metrics_service",
    # 种群快照
    "PopulationSnapshotService",
    "create_population_snapshot_service",
    # 回合报告
    "TurnReportService",
    "create_turn_report_service",
]
