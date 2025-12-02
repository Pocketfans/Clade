"""
物种服务提供者 - 物种相关服务

提供对物种服务的缓存访问：
- niche_analyzer: 生态位分析
- speciation_service: 物种分化
- background_manager: 背景物种管理
- tiering_service: 物种分层
- reproduction_service: 繁殖计算
- adaptation_service: 适应逻辑
- hybridization_service: 物种杂交
- gene_flow_service: 种群间基因流动
- genetic_distance_calculator: 遗传距离计算
- migration_advisor: 迁徙建议
- species_generator: AI 物种生成
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..config import Settings
    from ...services.species.niche import NicheAnalyzer
    from ...services.species.speciation import SpeciationService
    from ...services.species.background import BackgroundSpeciesManager
    from ...services.species.tiering import SpeciesTieringService
    from ...services.species.reproduction import ReproductionService
    from ...services.species.adaptation import AdaptationService
    from ...services.species.hybridization import HybridizationService
    from ...services.species.gene_flow import GeneFlowService
    from ...services.species.genetic_distance import GeneticDistanceCalculator
    from ...services.species.migration import MigrationAdvisor
    from ...services.species.species_generator import SpeciesGenerator
    from ...ai.model_router import ModelRouter
    from ...services.system.embedding import EmbeddingService


class SpeciesServiceProvider:
    """Mixin providing species-related services"""
    
    settings: 'Settings'
    _overrides: dict[str, Any]
    embedding_service: 'EmbeddingService'
    model_router: 'ModelRouter'
    config_service: Any
    
    def _get_or_override(self, name: str, factory: Callable[[], Any]) -> Any:
        """Get service instance, preferring override if set"""
        if name in self._overrides:
            return self._overrides[name]
        return factory()
    
    @cached_property
    def niche_analyzer(self) -> 'NicheAnalyzer':
        from ...services.species.niche import NicheAnalyzer
        return self._get_or_override(
            'niche_analyzer',
            lambda: NicheAnalyzer(self.embedding_service, self.settings.global_carrying_capacity)
        )
    
    @cached_property
    def speciation_service(self) -> 'SpeciationService':
        from ...services.species.speciation import SpeciationService
        return self._get_or_override(
            'speciation_service',
            lambda: SpeciationService(
                self.model_router,
                config=self.config_service.get_speciation()
            )
        )
    
    @cached_property
    def background_manager(self) -> 'BackgroundSpeciesManager':
        from ...services.species.background import BackgroundConfig, BackgroundSpeciesManager
        return self._get_or_override(
            'background_manager',
            lambda: BackgroundSpeciesManager(
                BackgroundConfig(
                    population_threshold=self.settings.background_population_threshold,
                    mass_extinction_threshold=self.settings.mass_extinction_threshold,
                    promotion_quota=self.settings.background_promotion_quota,
                )
            )
        )
    
    @cached_property
    def tiering_service(self) -> 'SpeciesTieringService':
        from ...services.species.tiering import SpeciesTieringService, TieringConfig
        return self._get_or_override(
            'tiering_service',
            lambda: SpeciesTieringService(
                TieringConfig(
                    critical_limit=self.settings.critical_species_limit,
                    focus_batch_size=self.settings.focus_batch_size,
                    focus_batch_limit=self.settings.focus_batch_limit,
                    background_threshold=self.settings.background_population_threshold,
                )
            )
        )
    
    @cached_property
    def reproduction_service(self) -> 'ReproductionService':
        from ...services.species.reproduction import ReproductionService
        return self._get_or_override(
            'reproduction_service',
            lambda: ReproductionService(
                global_carrying_capacity=self.settings.global_carrying_capacity,
                turn_years=500_000,
            )
        )
    
    @cached_property
    def adaptation_service(self) -> 'AdaptationService':
        from ...services.species.adaptation import AdaptationService
        return self._get_or_override(
            'adaptation_service',
            lambda: AdaptationService(self.model_router)
        )
    
    @cached_property
    def genetic_distance_calculator(self) -> 'GeneticDistanceCalculator':
        from ...services.species.genetic_distance import GeneticDistanceCalculator
        return self._get_or_override(
            'genetic_distance_calculator',
            lambda: GeneticDistanceCalculator(embedding_service=self.embedding_service)
        )
    
    @cached_property
    def hybridization_service(self) -> 'HybridizationService':
        from ...services.species.hybridization import HybridizationService
        return self._get_or_override(
            'hybridization_service',
            lambda: HybridizationService(
                self.genetic_distance_calculator, 
                router=self.model_router
            )
        )
    
    @cached_property
    def gene_flow_service(self) -> 'GeneFlowService':
        from ...services.species.gene_flow import GeneFlowService
        return self._get_or_override(
            'gene_flow_service',
            lambda: GeneFlowService()
        )
    
    @cached_property
    def migration_advisor(self) -> 'MigrationAdvisor':
        from ...services.species.migration import MigrationAdvisor
        return self._get_or_override(
            'migration_advisor',
            lambda: MigrationAdvisor(pressure_migration_threshold=0.45, min_population=500)
        )
    
    @cached_property
    def species_generator(self) -> 'SpeciesGenerator':
        from ...services.species.species_generator import SpeciesGenerator
        return self._get_or_override(
            'species_generator',
            lambda: SpeciesGenerator(self.model_router)
        )

