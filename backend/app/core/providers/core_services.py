"""
核心服务提供者 - 基础设施服务

提供对核心服务的缓存访问：
- config_service: 配置管理
- embedding_service: 向量嵌入
- model_router: AI 模型路由
- save_manager: 游戏存档管理
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..config import Settings
    from ..config_service import ConfigService
    from ...ai.model_router import ModelRouter
    from ...services.system.embedding import EmbeddingService
    from ...services.system.save_manager import SaveManager
    from ...services.ecology.semantic_anchors import SemanticAnchorService
    from ...services.ecology.ecological_realism import EcologicalRealismService

logger = logging.getLogger(__name__)


class CoreServiceProvider:
    """Mixin providing core infrastructure services"""
    
    settings: 'Settings'
    _overrides: dict[str, Any]
    
    def _get_or_override(self, name: str, factory: Callable[[], Any]) -> Any:
        """Get service instance, preferring override if set"""
        if name in self._overrides:
            return self._overrides[name]
        return factory()
    
    @cached_property
    def config_service(self) -> 'ConfigService':
        from ..config_service import ConfigService
        return self._get_or_override('config_service', lambda: ConfigService(self.settings))
    
    @cached_property
    def embedding_service(self) -> 'EmbeddingService':
        from ...services.system.embedding import EmbeddingService
        
        def create_embedding_service():
            # 1. 默认使用环境变量配置
            provider = self.settings.embedding_provider
            base_url = self.settings.ai_base_url
            api_key = self.settings.ai_api_key
            model = None
            enabled = False
            concurrency_enabled = False
            concurrency_limit = 1
            
            # 2. 尝试从 UI 配置加载 (settings.json)
            try:
                ui_config = self.config_service.get_ui_config()
                concurrency_enabled = getattr(ui_config, "embedding_concurrency_enabled", False)
                concurrency_limit = max(1, getattr(ui_config, "embedding_concurrency_limit", 1) or 1)

                # 如果 UI 中指定了 Embedding Provider
                if ui_config.embedding_provider_id:
                    provider_id = ui_config.embedding_provider_id
                    
                    # 在 providers 列表中查找详细配置
                    if provider_id in ui_config.providers:
                        prov_config = ui_config.providers[provider_id]
                        provider = prov_config.provider_type
                        
                        # 优先使用 provider 特定的配置
                        if prov_config.base_url:
                            base_url = prov_config.base_url
                        if prov_config.api_key:
                            api_key = prov_config.api_key
                            
                        # 标记为启用
                        enabled = True
                    
                # 如果 UI 中指定了模型
                if ui_config.embedding_model:
                    model = ui_config.embedding_model
                    
            except Exception as e:
                logger.warning(f"[核心服务] 从 UI 配置加载 Embedding 设置失败: {e}")
            
            # 如果配置了必要参数，则启用
            if base_url and api_key and model:
                enabled = True
                
            logger.info(f"[Embedding] 初始化: provider={provider}, model={model}, base_url={base_url}, enabled={enabled}")
            
            return EmbeddingService(
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                model=model,
                enabled=enabled,
                timeout=self.settings.ai_request_timeout,
                allow_fake_embeddings=self.settings.allow_fake_embeddings,
                max_parallel_requests=concurrency_limit,
                enable_concurrency=concurrency_enabled,
            )

        return self._get_or_override('embedding_service', create_embedding_service)
    
    @cached_property
    def model_router(self) -> 'ModelRouter':
        from ...ai.model_router import ModelConfig, ModelRouter
        from ...ai.prompts import PROMPT_TEMPLATES
        from ..ai_router_config import configure_model_router
        
        def create_router():
            router = ModelRouter(
                {
                    # Core reasoning capabilities
                    "turn_report": ModelConfig(provider="local", model="template-narrator"),
                    "focus_batch": ModelConfig(
                        provider="local", 
                        model="focus-template",
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "critical_detail": ModelConfig(provider="local", model="critical-template"),
                    
                    # Speciation capabilities
                    "speciation": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "speciation_batch": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "plant_speciation": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "plant_speciation_batch": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    
                    # Species generation and narrative
                    "species_generation": ModelConfig(
                        provider="openai", 
                        model=self.settings.species_gen_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "species_narrative": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "narrative": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    
                    # Pressure adaptation and status evaluation
                    "pressure_adaptation": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "species_status_eval": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    
                    # Hybridization capabilities
                    "hybridization": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "forced_hybridization": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    
                    # Ecological intelligence assessment
                    "biological_assessment_a": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "biological_assessment_b": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    
                    # Auxiliary capabilities (optional LLM enhancement)
                    "migration": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "pressure_escalation": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                    "reemergence": ModelConfig(
                        provider="openai", 
                        model=self.settings.speciation_model,
                        extra_body={"response_format": {"type": "json_object"}}
                    ),
                },
                base_url=self.settings.ai_base_url,
                api_key=self.settings.ai_api_key,
                timeout=self.settings.ai_request_timeout,
            )
            
            # Register prompt templates
            for capability, prompt in PROMPT_TEMPLATES.items():
                try:
                    router.set_prompt(capability, prompt)
                except KeyError:
                    pass
            
            try:
                ui_config = self.config_service.get_ui_config()
                configure_model_router(ui_config, router, self.embedding_service, self.settings)
                logger.info("[核心服务] 已根据 UI 配置初始化 ModelRouter")
            except Exception as e:
                logger.warning(f"[核心服务] 初始化 ModelRouter 配置失败: {e}")
            
            return router
        
        return self._get_or_override('model_router', create_router)
    
    @cached_property
    def save_manager(self) -> 'SaveManager':
        from ...services.system.save_manager import SaveManager
        return self._get_or_override(
            'save_manager',
            lambda: SaveManager(self.settings.saves_dir, embedding_service=self.embedding_service)
        )
    
    @cached_property
    def semantic_anchor_service(self) -> 'SemanticAnchorService':
        """语义锚点服务 - 提供基于 embedding 的语义匹配
        
        用于生态拟真系统中的生态学判断。
        """
        from ...services.ecology.semantic_anchors import SemanticAnchorService
        
        def create_service():
            service = SemanticAnchorService(self.embedding_service)
            service.initialize()
            logger.info("[核心服务] 语义锚点服务初始化完成")
            return service
        
        return self._get_or_override('semantic_anchor_service', create_service)
    
    @cached_property
    def ecological_realism_service(self) -> 'EcologicalRealismService':
        """生态拟真服务 - 提供高级生态学机制
        
        包含 Allee 效应、密度依赖疾病、环境波动、空间捕食等模块。
        """
        from ...services.ecology.ecological_realism import (
            EcologicalRealismService,
            EcologicalRealismConfig,
        )
        
        def create_service():
            # 尝试从 UI 配置加载生态拟真配置
            try:
                ui_config = self.config_service.get_ui_config()
                eco_config = ui_config.ecological_realism
                config = EcologicalRealismConfig(
                    enable_allee_effect=eco_config.enable_allee_effect,
                    allee_critical_ratio=eco_config.allee_critical_ratio,
                    allee_max_penalty=eco_config.allee_max_penalty,
                    allee_steepness=eco_config.allee_steepness,
                    enable_density_disease=eco_config.enable_density_disease,
                    disease_density_threshold=eco_config.disease_density_threshold,
                    disease_base_mortality=eco_config.disease_base_mortality,
                    disease_social_factor=eco_config.disease_social_factor,
                    disease_resistance_factor=eco_config.disease_resistance_factor,
                    enable_env_fluctuation=eco_config.enable_env_fluctuation,
                    fluctuation_period_turns=eco_config.fluctuation_period_turns,
                    fluctuation_amplitude=eco_config.fluctuation_amplitude,
                    latitude_sensitivity=eco_config.latitude_sensitivity,
                    specialist_sensitivity=eco_config.specialist_sensitivity,
                    enable_spatial_predation=eco_config.enable_spatial_predation,
                    min_overlap_for_predation=eco_config.min_overlap_for_predation,
                    overlap_efficiency_factor=eco_config.overlap_efficiency_factor,
                    enable_dynamic_assimilation=eco_config.enable_dynamic_assimilation,
                    herbivore_base_efficiency=eco_config.herbivore_base_efficiency,
                    carnivore_base_efficiency=eco_config.carnivore_base_efficiency,
                    detritivore_base_efficiency=eco_config.detritivore_base_efficiency,
                    filter_feeder_efficiency=eco_config.filter_feeder_efficiency,
                    endotherm_penalty=eco_config.endotherm_penalty,
                    enable_vertical_niche=eco_config.enable_vertical_niche,
                    same_layer_competition=eco_config.same_layer_competition,
                    adjacent_layer_competition=eco_config.adjacent_layer_competition,
                    distant_layer_competition=eco_config.distant_layer_competition,
                    enable_adaptation_lag=eco_config.enable_adaptation_lag,
                    env_change_tracking_window=eco_config.env_change_tracking_window,
                    max_adaptation_penalty=eco_config.max_adaptation_penalty,
                    plasticity_protection=eco_config.plasticity_protection,
                    generation_time_factor=eco_config.generation_time_factor,
                    enable_mutualism=eco_config.enable_mutualism,
                    mutualism_threshold=eco_config.mutualism_threshold,
                    mutualism_benefit=eco_config.mutualism_benefit,
                    mutualism_penalty=eco_config.mutualism_penalty,
                )
            except Exception as e:
                logger.warning(f"[核心服务] 加载生态拟真配置失败，使用默认值: {e}")
                config = EcologicalRealismConfig()
            
            service = EcologicalRealismService(
                self.semantic_anchor_service,
                config,
            )
            logger.info("[核心服务] 生态拟真服务初始化完成")
            return service
        
        return self._get_or_override('ecological_realism_service', create_service)

