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
        return self._get_or_override(
            'embedding_service',
            lambda: EmbeddingService(self.settings.embedding_provider)
        )
    
    @cached_property
    def model_router(self) -> 'ModelRouter':
        from ...ai.model_router import ModelConfig, ModelRouter
        from ...ai.prompts import PROMPT_TEMPLATES
        
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
            
            return router
        
        return self._get_or_override('model_router', create_router)
    
    @cached_property
    def save_manager(self) -> 'SaveManager':
        from ...services.system.save_manager import SaveManager
        return self._get_or_override(
            'save_manager',
            lambda: SaveManager(self.settings.saves_dir, embedding_service=self.embedding_service)
        )

