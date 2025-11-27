"""Analytics and reporting services."""

from .ecosystem_health import EcosystemHealthService, EcosystemHealthReport
from .taxonomy import TaxonomyService, TaxonomyResult, CladeInfo
from .evolution_predictor import EvolutionPredictor, PressureVectorLibrary, EvolutionPredictionResult
from .narrative_engine import NarrativeEngine, EventRecord, Era, NarrativeResult
from .encyclopedia import EncyclopediaService, SearchResult, QAResponse, EvolutionExplanation, GameHint
from .embedding_integration import EmbeddingIntegrationService

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
]
