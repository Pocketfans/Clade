from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ..ai.model_router import ModelConfig, ModelRouter, ProviderPoolConfig
from ..models.config import CapabilityRouteConfig, ProviderConfig, UIConfig

if TYPE_CHECKING:
    from .config import Settings
    from ..services.system.embedding import EmbeddingService

logger = logging.getLogger(__name__)


def _pick_provider_model(provider: Optional[ProviderConfig]) -> Optional[str]:
    if not provider:
        return None
    if provider.selected_models:
        return next((m for m in provider.selected_models if m), None)
    if provider.models:
        return next((m for m in provider.models if m), None)
    return None


def _resolve_final_model(
    capability: str,
    route_config: CapabilityRouteConfig,
    active_provider: Optional[ProviderConfig],
    default_provider: Optional[ProviderConfig],
    current_route: Optional[ModelConfig],
    config: UIConfig,
    settings: 'Settings',
) -> Optional[str]:
    candidates = [
        route_config.model,
        _pick_provider_model(active_provider),
    ]
    if default_provider:
        candidates.append(_pick_provider_model(default_provider))
    candidates.extend([
        config.default_model,
        getattr(current_route, "model", None),
        settings.speciation_model,
    ])
    for candidate in candidates:
        if candidate:
            if candidate != route_config.model:
                logger.debug(f"[配置] {capability} 使用回退模型: {candidate}")
            return candidate
    return None


def configure_model_router(
    config: UIConfig,
    model_router: ModelRouter,
    embedding_service: 'EmbeddingService',
    settings: 'Settings',
) -> UIConfig:
    """Apply UI routing config to the provided ModelRouter instance."""
    if not config:
        return config
    
    model_router.overrides = {}
    
    if config.ai_concurrency_limit > 0:
        model_router.set_concurrency_limit(config.ai_concurrency_limit)
    
    providers = getattr(config, "providers", {}) or {}
    capability_routes = getattr(config, "capability_routes", {}) or {}
    
    default_provider = providers.get(config.default_provider_id) if config.default_provider_id else None
    default_model_name = config.default_model
    
    if default_provider:
        model_router.api_base_url = default_provider.base_url
        model_router.api_key = default_provider.api_key
        if not default_model_name:
            default_model_name = _pick_provider_model(default_provider)
            if default_model_name:
                config.default_model = default_model_name
    
    lb_enabled = getattr(config, 'load_balance_enabled', False)
    lb_strategy = getattr(config, 'load_balance_strategy', 'round_robin')
    model_router.configure_load_balance(lb_enabled, lb_strategy)
    logger.info(f"[AI配置] 负载均衡: enabled={lb_enabled}, strategy={lb_strategy}")
    logger.info(f"[AI配置] 可用服务商: {list(providers.keys())}")
    for pid, prov in providers.items():
        logger.info(f"[AI配置] 服务商 {pid}: selected_models={prov.selected_models}, provider_type={prov.provider_type}")
    logger.info(f"[AI配置] model_router.routes 包含: {list(model_router.routes.keys())}")
    
    for capability, route_config in capability_routes.items():
        if capability not in model_router.routes:
            logger.warning(f"[AI配置] 跳过 {capability}: 不在 model_router.routes 中")
            continue
        
        current_route = model_router.routes.get(capability)
        provider = providers.get(route_config.provider_id)
        selectable_provider_ids = [
            pid for pid in (route_config.provider_ids or []) if pid in providers
        ]
        
        if not provider and selectable_provider_ids and not lb_enabled:
            first_pid = selectable_provider_ids[0]
            provider = providers.get(first_pid)
            if provider:
                logger.debug(f"[AI配置] {capability}: 负载均衡关闭，使用 provider_ids 首选 {first_pid}")
        
        active_provider = provider or default_provider
        
        if lb_enabled and selectable_provider_ids:
            pool_configs = []
            for pid in selectable_provider_ids:
                p = providers.get(pid)
                if p and p.api_key and p.base_url:
                    pool_model = _pick_provider_model(p)
                    if not pool_model:
                        pool_model = _resolve_final_model(
                            capability, route_config, p, default_provider, current_route, config, settings
                        )
                    
                    if not pool_model:
                        logger.warning(f"[AI配置] {capability} 跳过服务商 {pid}: 未找到可用模型")
                        continue
                    
                    logger.info(f"[AI配置] {capability} 添加服务商池: {pid}, model={pool_model}, provider_type={p.provider_type}")
                    pool_configs.append(ProviderPoolConfig(
                        provider_id=pid,
                        base_url=p.base_url,
                        api_key=p.api_key,
                        provider_type=p.provider_type or "openai",
                        model=pool_model,
                    ))
            if pool_configs:
                model_router.set_provider_pool(capability, pool_configs)
                models_info = [(pc.provider_id, pc.model, pc.provider_type) for pc in pool_configs]
                logger.info(f"[AI配置] {capability} 启用负载均衡: {models_info}")
                first_pool_provider = providers.get(pool_configs[0].provider_id)
                if first_pool_provider:
                    active_provider = first_pool_provider
            else:
                logger.info(f"[AI配置] {capability} 启用负载均衡但未选择有效服务商，回退到默认")
        
        if active_provider:
            original_extra_body = current_route.extra_body if current_route else None
            extra_body = dict(original_extra_body) if original_extra_body else {}
            
            if route_config.enable_thinking:
                extra_body["enable_thinking"] = True
                extra_body["thinking_budget"] = 4096
            
            final_model = _resolve_final_model(
                capability, route_config, active_provider, default_provider, current_route, config, settings
            )
            if not final_model and default_model_name:
                final_model = default_model_name
            if not final_model:
                logger.error(f"[AI配置] {capability} 未找到可用模型，请检查 providers/capability_routes 配置")
                continue
            
            model_router.routes[capability] = ModelConfig(
                provider=active_provider.type,
                model=final_model,
                endpoint=model_router.routes[capability].endpoint,
                extra_body=extra_body
            )
            
            model_router.overrides[capability] = {
                "base_url": active_provider.base_url,
                "api_key": active_provider.api_key,
                "timeout": route_config.timeout,
                "model": final_model,
                "extra_body": extra_body,
                "provider_type": active_provider.provider_type or "openai",
            }
            logger.debug(
                f"[AI配置] 已设置 {capability} -> Provider: {active_provider.name}, "
                f"Model: {final_model}, Type: {active_provider.provider_type}, Thinking: {route_config.enable_thinking}"
            )
    
    if default_provider:
        for cap_name, current_config in model_router.routes.items():
            if cap_name not in capability_routes:
                model_to_use = _pick_provider_model(default_provider) or default_model_name
                if not model_to_use:
                    model_to_use = getattr(current_config, "model", None) or settings.speciation_model
                
                model_router.routes[cap_name] = ModelConfig(
                    provider=default_provider.type,
                    model=model_to_use,
                    endpoint=current_config.endpoint,
                    extra_body=current_config.extra_body
                )
                
                model_router.overrides[cap_name] = {
                    "base_url": default_provider.base_url,
                    "api_key": default_provider.api_key,
                    "timeout": 60,
                    "model": model_to_use,
                    "extra_body": current_config.extra_body,
                    "provider_type": default_provider.provider_type or "openai",
                }
                logger.debug(
                    f"[AI配置] 自动应用默认服务商到 {cap_name}: "
                    f"{default_provider.name} (Model: {model_to_use}, Type: {default_provider.provider_type})"
                )
    
    emb_provider = providers.get(config.embedding_provider_id) if config.embedding_provider_id else None
    
    if emb_provider and embedding_service:
        embedding_service.provider = emb_provider.type
        embedding_service.api_base_url = emb_provider.base_url
        embedding_service.api_key = emb_provider.api_key
        embedding_service.model = config.embedding_model
        embedding_service.enabled = True
    elif getattr(config, "embedding_api_key", None) and getattr(config, "embedding_base_url", None):
        if embedding_service:
            embedding_service.provider = settings.embedding_provider
            embedding_service.api_base_url = config.embedding_base_url
            embedding_service.api_key = config.embedding_api_key
            embedding_service.model = config.embedding_model
            embedding_service.enabled = True
    elif embedding_service:
        embedding_service.enabled = False
    
    return config

