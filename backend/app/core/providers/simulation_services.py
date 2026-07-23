"""
模拟服务提供者 - 模拟引擎及相关服务

提供对模拟服务的缓存访问：
- environment_system: 环境状态管理
- mortality_engine: 规则死亡率计算
- map_evolution: 地图地形演化
- map_manager: 地图状态管理
- pressure_escalation: 压力升级逻辑
- resource_manager: 资源/NPP 管理
- simulation_engine: 主模拟引擎
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..config import Settings
    from ...simulation.environment import EnvironmentSystem
    from ...simulation.species import MortalityEngine
    from ...simulation.engine import SimulationEngine
    from ...services.geo.map_evolution import MapEvolutionService
    from ...services.geo.map_manager import MapStateManager
    from ...services.system.pressure import PressureEscalationService

logger = logging.getLogger(__name__)


class SimulationServiceProvider:
    """Mixin providing simulation-related services"""
    
    settings: 'Settings'
    _overrides: dict[str, Any]
    config_service: Any
    
    # Dependencies from other providers (will be available via multiple inheritance)
    embedding_service: Any
    model_router: Any
    report_builder: Any
    export_service: Any
    niche_analyzer: Any
    speciation_service: Any
    background_manager: Any
    tiering_service: Any
    focus_processor: Any
    critical_analyzer: Any
    migration_advisor: Any
    reproduction_service: Any
    adaptation_service: Any
    gene_flow_service: Any
    embedding_integration: Any
    
    def _get_or_override(self, name: str, factory: Callable[[], Any]) -> Any:
        """Get service instance, preferring override if set"""
        if name in self._overrides:
            return self._overrides[name]
        return factory()
    
    @cached_property
    def environment_system(self) -> 'EnvironmentSystem':
        from ...simulation.environment import EnvironmentSystem
        return self._get_or_override(
            'environment_system',
            lambda: EnvironmentSystem(self.settings.map_width, self.settings.map_height)
        )
    
    @cached_property
    def mortality_engine(self) -> 'MortalityEngine':
        from ...simulation.species import MortalityEngine
        return self._get_or_override(
            'mortality_engine',
            lambda: MortalityEngine(
                batch_limit=self.settings.batch_rule_limit,
                ecology_config=self.config_service.get_ecology_balance(),
            )
        )
    
    @cached_property
    def pressure_escalation(self) -> 'PressureEscalationService':
        from ...services.system.pressure import PressureEscalationService
        return self._get_or_override(
            'pressure_escalation',
            lambda: PressureEscalationService(
                window=self.settings.minor_pressure_window,
                threshold=self.settings.escalation_threshold,
                cooldown=self.settings.high_event_cooldown,
            )
        )
    
    @cached_property
    def map_evolution(self) -> 'MapEvolutionService':
        from ...services.geo.map_evolution import MapEvolutionService
        return self._get_or_override(
            'map_evolution',
            lambda: MapEvolutionService(self.settings.map_width, self.settings.map_height)
        )
    
    @cached_property
    def map_manager(self) -> 'MapStateManager':
        from ...services.geo.map_manager import MapStateManager
        return self._get_or_override(
            'map_manager',
            lambda: MapStateManager(
                self.settings.map_width, 
                self.settings.map_height, 
                primordial_mode=True
            )
        )
    
    @cached_property
    def resource_manager(self):
        """Get resource manager service"""
        from ...services.ecology.resource_manager import ResourceManager
        
        ui_config = self.config_service.get_ui_config()
        resource_config = getattr(ui_config, 'resource_system', None)
        
        return self._get_or_override(
            'resource_manager',
            lambda: ResourceManager(config=resource_config)
        )
    
    def get_engine_configs(self) -> dict:
        """Get configuration dictionary for SimulationEngine
        
        Returns:
            dict: {ecology, mortality, speciation, food_web, 张量系统开关} config objects
        """
        ui_config = self.config_service.get_ui_config()
        speciation_config = self.config_service.get_speciation()
        settings = self.settings
        
        return {
            "ecology": self.config_service.get_ecology_balance(),
            "mortality": self.config_service.get_mortality(),
            "speciation": speciation_config,
            "food_web": getattr(ui_config, 'food_web', None),
            # 【张量系统配置】
            "use_tensor_mortality": getattr(settings, "use_tensor_mortality", True),
            "use_tensor_speciation": getattr(speciation_config, "use_tensor_speciation", 
                                             getattr(settings, "use_tensor_speciation", True)),
            "use_auto_tradeoff": getattr(speciation_config, "use_auto_tradeoff",
                                         getattr(settings, "use_auto_tradeoff", True)),
            "tradeoff_ratio": getattr(speciation_config, "tradeoff_ratio",
                                      getattr(settings, "tradeoff_ratio", 0.7)),
            "tensor_balance_path": getattr(settings, "tensor_balance_path", None),
        }
    
    @cached_property
    def simulation_engine(self) -> 'SimulationEngine':
        from ...simulation.engine import SimulationEngine
        return self._get_or_override(
            'simulation_engine',
            lambda: SimulationEngine(
                environment=self.environment_system,
                mortality=self.mortality_engine,
                embeddings=self.embedding_service,
                router=self.model_router,
                report_builder=self.report_builder,
                exporter=self.export_service,
                niche_analyzer=self.niche_analyzer,
                speciation=self.speciation_service,
                background_manager=self.background_manager,
                species_repository=self.species_repository,
                environment_repository=self.environment_repository,
                tiering=self.tiering_service,
                focus_processor=self.focus_processor,
                critical_analyzer=self.critical_analyzer,
                escalation_service=self.pressure_escalation,
                map_evolution=self.map_evolution,
                migration_advisor=self.migration_advisor,
                map_manager=self.map_manager,
                reproduction_service=self.reproduction_service,
                gene_flow_service=self.gene_flow_service,
                embedding_integration=self.embedding_integration,
                resource_manager=self.resource_manager,
                ecological_realism_service=self.ecological_realism_service,
                configs=self.get_engine_configs(),
            )
        )

