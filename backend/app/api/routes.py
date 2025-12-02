"""
⚠️⚠️⚠️ 已弃用 - Legacy API Routes ⚠️⚠️⚠️

此文件为历史遗留的巨型路由模块，已被拆分到以下领域模块：
- api/simulation.py: 回合推演、存档管理、压力队列
- api/species.py: 物种管理、干预控制、系谱树
- api/divine.py: 能量、成就、提示、杂交、神格系统
- api/ecosystem.py: 食物网、生态健康分析
- api/analytics.py: 导出、地图、配置、系统诊断

┌─────────────────────────────────────────────────────────────┐
│  ❌ 禁止向此文件添加新代码 ❌                                │
│  所有新功能必须在 api/*.py 领域模块中实现                   │
└─────────────────────────────────────────────────────────────┘

退场计划与时间线：
==================
阶段 1（当前 - v1.5）：
  - USE_LEGACY_ROUTES=true 时仍可启用（默认 false）
  - 仅用于紧急回退和回归测试
  - 不接受新功能 PR

阶段 2（v1.5 - v2.0）：
  - 移除 USE_LEGACY_ROUTES 开关
  - 此文件仅作为参考保留在 docs/ 目录
  - 新路由完全替代

阶段 3（v2.0+）：
  - 彻底删除此文件

兼容性保证：
-----------
- 所有端点签名在新路由中保持一致
- 响应格式不变
- 迁移后前端无需修改

迁移指南：
---------
- 所有新开发应使用 api/*.py 的领域模块
- 通过 Depends() 注入服务，不使用模块级单例
- 使用 SessionManager 进行状态管理和并发控制
- 使用 ConfigService 获取配置

最后更新：2025-01 (重构后保留作为兼容层)
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
import uuid
import json
import httpx
import asyncio
from queue import Queue

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Query
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

# 发出弃用警告（仅在首次导入时）
warnings.warn(
    "api/routes.py 已弃用，请使用新的领域路由模块 (api/simulation.py, api/species.py 等)。"
    "设置 USE_LEGACY_ROUTES=false 以使用新路由（默认）。",
    DeprecationWarning,
    stacklevel=2
)
from sqlmodel import select

from ..core.config import get_settings
from ..ai.prompts import PROMPT_TEMPLATES
from ..models.config import UIConfig, ProviderConfig, CapabilityRouteConfig
from ..repositories.genus_repository import genus_repository
from ..repositories.history_repository import history_repository
from ..repositories.environment_repository import environment_repository
from ..repositories.species_repository import species_repository
from ..schemas.requests import (
    PressureConfig, 
    QueueRequest, 
    SpeciesEditRequest, 
    TurnCommand, 
    WatchlistRequest,
    CreateSaveRequest,
    SaveGameRequest,
    LoadGameRequest,
    GenerateSpeciesRequest,
    GenerateSpeciesAdvancedRequest,
    NicheCompareRequest,
    ProtectSpeciesRequest,
    SuppressSpeciesRequest,
    IntroduceSpeciesRequest,
    SetSymbiosisRequest,
)
from ..schemas.responses import (
    ActionQueueStatus,
    ExportRecord,
    MapOverview,
    PressureTemplate,
    LineageNode,
    LineageTree,
    SpeciesDetail,
    TurnReport,
    NicheCompareResult,
    SpeciesList,
    SpeciesListItem,
    EcosystemHealthResponse,
    TrophicDistributionItem,
    ExtinctionRiskItem,
    InterventionResponse,
)
from ..services.species.adaptation import AdaptationService
from ..services.species.background import BackgroundConfig, BackgroundSpeciesManager
from ..services.species.gene_flow import GeneFlowService
from ..services.species.genetic_distance import GeneticDistanceCalculator
from ..services.species.hybridization import HybridizationService
from ..services.analytics.critical_analyzer import CriticalAnalyzer
from ..services.analytics.exporter import ExportService
from ..services.system.embedding import EmbeddingService
from ..services.system.divine_progression import divine_progression_service
from ..services.analytics.focus_processor import FocusBatchProcessor
from ..services.geo.map_evolution import MapEvolutionService
from ..services.geo.map_manager import MapStateManager
from ..services.species.migration import MigrationAdvisor
from ..services.species.reproduction import ReproductionService
from ..services.species.habitat_manager import habitat_manager
from ..services.species.dispersal_engine import dispersal_engine  # 矩阵化扩散引擎
from ..ai.model_router import ModelConfig, ModelRouter
from ..services.species.niche import NicheAnalyzer
from ..services.system.pressure import PressureEscalationService
from ..services.analytics.report_builder import ReportBuilder
from ..services.analytics.report_builder_v2 import ReportBuilderV2
from ..services.species.speciation import SpeciationService
from ..services.species.tiering import SpeciesTieringService, TieringConfig
from ..services.system.save_manager import SaveManager
from ..services.species.species_generator import SpeciesGenerator
from ..services.analytics.ecosystem_health import EcosystemHealthService
from ..services.species.predation import PredationService
from ..services.analytics.embedding_integration import EmbeddingIntegrationService
from ..simulation.engine import SimulationEngine
from ..simulation.environment import EnvironmentSystem
from ..simulation.species import MortalityEngine


def _infer_ecological_role(species) -> str:
    """根据物种营养级推断生态角色
    
    营养级划分规则：
    - T < 1.5: 纯生产者 (producer) - 纯自养生物
    - 1.5 ≤ T < 2.0: 混合营养 (mixotroph) - 既能自养又能摄食
    - 2.0 ≤ T < 2.8: 草食者 (herbivore) - 以生产者为食
    - 2.8 ≤ T < 3.5: 杂食者 (omnivore) - 植物和动物都吃
    - T ≥ 3.5: 肉食者 (carnivore) - 以其他动物为食
    
    特殊情况：腐食者(detritivore)通过 diet_type 识别
    """
    diet_type = getattr(species, 'diet_type', None)
    
    # 特殊处理：腐食者（分解者）
    if diet_type == "detritivore":
        return "decomposer"
    
    # 【修复】优先使用 diet_type 来推断生态角色（更可靠）
    if diet_type == "autotroph":
        return "producer"
    elif diet_type == "herbivore":
        return "herbivore"
    elif diet_type == "carnivore":
        return "carnivore"
    elif diet_type == "omnivore":
        return "omnivore"
    
    # 回退方案：基于营养级判断
    trophic = getattr(species, 'trophic_level', None)
    # 【修复】确保 trophic 是有效的数字
    if trophic is None or not isinstance(trophic, (int, float)):
        trophic = 2.0  # 默认为初级消费者
    
    if trophic < 1.5:
        return "producer"
    elif trophic < 2.0:
        return "mixotroph"
    elif trophic < 2.8:
        return "herbivore"
    elif trophic < 3.5:
        return "omnivore"
    else:
        return "carnivore"


router = APIRouter(prefix="", tags=["simulation"])

settings = get_settings()
environment_system = EnvironmentSystem(settings.map_width, settings.map_height)
mortality_engine = MortalityEngine(settings.batch_rule_limit)
embedding_service = EmbeddingService(settings.embedding_provider)
model_router = ModelRouter(
    {
        # ========== 核心推演能力（高优先级）==========
        "turn_report": ModelConfig(provider="local", model="template-narrator"),
        "focus_batch": ModelConfig(
            provider="local", 
            model="focus-template",
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "critical_detail": ModelConfig(provider="local", model="critical-template"),
        
        # ========== 物种分化能力 ==========
        "speciation": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "speciation_batch": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "plant_speciation": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "plant_speciation_batch": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        
        # ========== 物种生成与叙事 ==========
        "species_generation": ModelConfig(
            provider="openai", 
            model=settings.species_gen_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "species_narrative": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "narrative": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        
        # ========== 压力适应与状态评估 ==========
        "pressure_adaptation": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "species_status_eval": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        
        # ========== 杂交能力 ==========
        "hybridization": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "forced_hybridization": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        
        # ========== 生态智能体评估 ==========
        "biological_assessment_a": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        "biological_assessment_b": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        
        # ========== 已移除的规则型能力（不使用LLM）==========
        # migration: 迁徙计算完全基于规则，不调用LLM
        # pressure_escalation: 压力升级完全基于规则，不调用LLM  
        # reemergence: 物种重现完全基于规则，不调用LLM
    },
    base_url=settings.ai_base_url,
    api_key=settings.ai_api_key,
    timeout=settings.ai_request_timeout,
)
for capability, prompt in PROMPT_TEMPLATES.items():
    try:
        model_router.set_prompt(capability, prompt)
    except KeyError:
        # Prompt for capabilities not yet registered; skip
        pass
# 【优化】使用并行化报告生成器V2，提升大规模物种场景下的性能
# 可通过环境变量 USE_REPORT_V2=false 回退到旧版本
_use_report_v2 = settings.use_report_v2 if hasattr(settings, 'use_report_v2') else True
if _use_report_v2:
    report_builder = ReportBuilderV2(model_router, batch_size=settings.focus_batch_size)
    logger.info("[报告生成] 使用并行化报告生成器 V2")
else:
    report_builder = ReportBuilder(model_router)
    logger.info("[报告生成] 使用传统报告生成器 V1")
export_service = ExportService(settings.reports_dir, settings.exports_dir)
niche_analyzer = NicheAnalyzer(embedding_service, settings.global_carrying_capacity)
speciation_service = SpeciationService(model_router)
background_manager = BackgroundSpeciesManager(
    BackgroundConfig(
        population_threshold=settings.background_population_threshold,
        mass_extinction_threshold=settings.mass_extinction_threshold,
        promotion_quota=settings.background_promotion_quota,
    )
)
tiering_service = SpeciesTieringService(
    TieringConfig(
        critical_limit=settings.critical_species_limit,
        focus_batch_size=settings.focus_batch_size,
        focus_batch_limit=settings.focus_batch_limit,
        background_threshold=settings.background_population_threshold,
    )
)
focus_processor = FocusBatchProcessor(model_router, settings.focus_batch_size)
critical_analyzer = CriticalAnalyzer(model_router)
pressure_escalation = PressureEscalationService(
    window=settings.minor_pressure_window,
    threshold=settings.escalation_threshold,
    cooldown=settings.high_event_cooldown,
)
map_evolution = MapEvolutionService(settings.map_width, settings.map_height)
migration_advisor = MigrationAdvisor(pressure_migration_threshold=0.45, min_population=500)  # 使用默认参数
# primordial_mode=True 表示28亿年前的原始地质状态，地表无植被覆盖
# 植被会随着植物物种的繁衍而动态更新
map_manager = MapStateManager(settings.map_width, settings.map_height, primordial_mode=True)
reproduction_service = ReproductionService(
    global_carrying_capacity=settings.global_carrying_capacity,  # 从配置读取
    turn_years=500_000,  # 每回合50万年
)
adaptation_service = AdaptationService(model_router)
# 传入embedding_service以支持描述语义距离计算
genetic_distance_calculator = GeneticDistanceCalculator(embedding_service=embedding_service)
hybridization_service = HybridizationService(genetic_distance_calculator, router=model_router)
gene_flow_service = GeneFlowService()
save_manager = SaveManager(settings.saves_dir, embedding_service=embedding_service)
species_generator = SpeciesGenerator(model_router)
ui_config_path = Path(settings.ui_config_path)
pressure_templates: list[PressureTemplate] = [
    # 【零消耗】自然演化 - 在能量不足时仍可推进回合
    PressureTemplate(kind="natural_evolution", label="🌱 自然演化", description="让生态系统自然发展，不施加任何神力干预。物种按照自身特性与环境互动，遵循自然选择规律。消耗 0 神力能量。"),
    PressureTemplate(kind="glacial_period", label="冰河时期", description="气温下降，冰川扩张，环境转向寒冷。对耐寒性弱的物种形成压力，生物需要发展保温结构、提高代谢效率或通过迁移适应新环境。"),
    PressureTemplate(kind="greenhouse_earth", label="温室地球", description="气温上升，极地冰层减少，海平面变化影响沿海栖息地。物种需要改进散热能力、调整分布区域或适应更潮湿的环境形态。"),
    PressureTemplate(kind="pluvial_period", label="洪积期", description="降水增多，形成湿地、湖泊等水域环境。陆生栖息地减少，水生与两栖类获得更多生存空间。物种可能需要增强对水域的适应性。"),
    PressureTemplate(kind="drought_period", label="干旱期", description="降水减少，植被减少，水源变得紧缺。物种需要提升水分保存能力、减少蒸散，或通过休眠、迁移等方式维持生存。"),
    PressureTemplate(kind="monsoon_shift", label="季风变动", description="风带格局发生变化，一些地区从湿润转向干燥，另一些从干燥转向湿润。物种需调整分布区域或适应新的气候组合。"),
    PressureTemplate(kind="fog_period", label="浓雾时期", description="大气湿度提升，持续雾霾削弱光照。光合作用受到限制，生物可能需降低能量需求或依赖替代能量来源。"),
    PressureTemplate(kind="volcanic_eruption", label="火山喷发期", description="火山活动影响大气光照、气温与水体化学条件。物种需适应光照减少、温度变化或受污染的环境。"),
    PressureTemplate(kind="orogeny", label="造山期", description="地壳抬升形成新的山地屏障，改变水汽流动并隔离生境。生物分布被分割，适应高海拔或低氧环境的物种具备优势。"),
    PressureTemplate(kind="subsidence", label="陆架沉降", description="陆地区域下降并被海水覆盖，沿海和浅海环境扩张。物种可能需向内陆迁移，或向半水生与水生方向发展。"),
    PressureTemplate(kind="land_degradation", label="土地退化", description="表层土壤流失，植被生长受限，生态系统的基础生产力下降。物种可能转向耐贫瘠策略或改变食性以维持生存。"),
    PressureTemplate(kind="ocean_current_shift", label="洋流变迁", description="海洋环流改变沿海气候，使部分地区变暖或变冷。依赖稳定环境的物种需要调整分布或适应新的温度条件。"),
    PressureTemplate(kind="resource_abundance", label="资源繁盛期", description="环境资源充裕、生态位开放，生物演化与分化速度提高，产生更多独特的形态和生态策略。"),
    PressureTemplate(kind="productivity_decline", label="生产力衰退", description="基础生产者数量减少，食物链低层受到影响，草食与肉食物种的生存压力增加。物种需降低能耗、改变食性或发展耐逆策略。"),
    PressureTemplate(kind="predator_rise", label="捕食者兴起", description="新型捕食者出现，使捕食压力上升。其他物种需发展更有效的防御、隐蔽或逃避能力。"),
    PressureTemplate(kind="species_invasion", label="物种入侵", description="外来物种进入生态系统，以竞争力或繁殖速度影响本地物种。原生物种可能被迫迁移或演化新策略以避免竞争。"),
    PressureTemplate(kind="ocean_acidification", label="海洋酸化", description="海水化学成分变化，使依赖钙质结构的生物更难形成硬壳或骨骼。生态结构偏向对酸性环境更适应的生物类群。"),
    PressureTemplate(kind="oxygen_increase", label="氧气增多", description="大气含氧量提高，使生物具备发展更大体型、更高代谢能力或更强运动能力的可能性。"),
    PressureTemplate(kind="anoxic_event", label="缺氧事件", description="水体中可利用氧减少，部分海域变成低氧环境。依赖溶氧的生物面临压力，而能耐低氧或使用替代代谢方式的物种更为适应。"),
]
pressure_queue: list[list[PressureConfig]] = []
# 事件队列：用于实时推送演化日志到前端
simulation_events: Queue = Queue()
simulation_running = False

# 自动保存相关
current_save_name: str | None = None  # 当前存档名称
autosave_counter: int = 0  # 自动保存回合计数器


def _serialize_species_detail(species) -> SpeciesDetail:
    """构建统一的 SpeciesDetail 响应，供多个端点复用"""
    morphology_stats = {
        k: v for k, v in (species.morphology_stats or {}).items()
        if isinstance(v, (int, float))
    }
    return SpeciesDetail(
        lineage_code=species.lineage_code,
        latin_name=species.latin_name,
        common_name=species.common_name,
        description=species.description,
        morphology_stats=morphology_stats,
        abstract_traits=species.abstract_traits,
        hidden_traits=species.hidden_traits,
        status=species.status,
        organs=species.organs,
        capabilities=species.capabilities,
        genus_code=species.genus_code,
        taxonomic_rank=species.taxonomic_rank,
        trophic_level=species.trophic_level,
        hybrid_parent_codes=species.hybrid_parent_codes,
        hybrid_fertility=species.hybrid_fertility,
        parent_code=species.parent_code,
        created_turn=species.created_turn,
        dormant_genes=species.dormant_genes,
        stress_exposure=species.stress_exposure,
    )


def apply_ui_config(config: UIConfig) -> UIConfig:
    """应用 UI 配置到运行时服务，包含旧配置迁移逻辑"""
    
    # --- 1. 数据迁移：旧配置 -> 新多服务商配置 ---
    has_legacy_config = config.ai_api_key and not config.providers
    if has_legacy_config:
        logger.debug("[配置] 检测到旧版配置，正在迁移到多服务商结构...")
        default_provider_id = str(uuid.uuid4())[:8]
        provider = ProviderConfig(
            id=default_provider_id,
            name="Default Provider",
            type=config.ai_provider or "openai",
            base_url=config.ai_base_url,
            api_key=config.ai_api_key,
        )
        config.providers[default_provider_id] = provider
        config.default_provider_id = default_provider_id
        config.default_model = config.ai_model
        
        # 迁移旧的 capability_configs
        if config.capability_configs and isinstance(config.capability_configs, dict):
            first_val = next(iter(config.capability_configs.values()), None)
            if first_val and isinstance(first_val, dict) and "api_key" in first_val:
                for cap, old_conf in config.capability_configs.items():
                    if old_conf.get("api_key") or old_conf.get("base_url"):
                        custom_pid = f"custom_{cap}"
                        custom_provider = ProviderConfig(
                            id=custom_pid,
                            name=f"Custom for {cap}",
                            type=old_conf.get("provider", "openai"),
                            base_url=old_conf.get("base_url") or config.ai_base_url,
                            api_key=old_conf.get("api_key") or config.ai_api_key
                        )
                        config.providers[custom_pid] = custom_provider
                        config.capability_routes[cap] = CapabilityRouteConfig(
                            provider_id=custom_pid,
                            model=old_conf.get("model"),
                            timeout=old_conf.get("timeout", 60)
                        )
                    else:
                        config.capability_routes[cap] = CapabilityRouteConfig(
                            provider_id=default_provider_id,
                            model=old_conf.get("model"),
                            timeout=old_conf.get("timeout", 60)
                        )
    
    # 2. 应用配置到 ModelRouter ---
    model_router.overrides = {}
    
    # 设置并发限制
    if config.ai_concurrency_limit > 0:
        model_router.set_concurrency_limit(config.ai_concurrency_limit)
    
    # 2.1 设置默认值
    default_provider = config.providers.get(config.default_provider_id) if config.default_provider_id else None
    
    if default_provider:
        model_router.api_base_url = default_provider.base_url
        model_router.api_key = default_provider.api_key
    
    # 2.2 配置负载均衡
    from ..ai.model_router import ProviderPoolConfig
    lb_enabled = getattr(config, 'load_balance_enabled', False)
    lb_strategy = getattr(config, 'load_balance_strategy', 'round_robin')
    model_router.configure_load_balance(lb_enabled, lb_strategy)
    
    # 2.3 应用 Capability Routes
    for capability, route_config in config.capability_routes.items():
        if capability not in model_router.routes:
            continue
            
        provider = config.providers.get(route_config.provider_id)
        active_provider = provider or default_provider
        
        # 【负载均衡】如果配置了多服务商池
        provider_ids = getattr(route_config, 'provider_ids', None) or []
        if lb_enabled and provider_ids and len(provider_ids) > 1:
            pool_configs = []
            for pid in provider_ids:
                p = config.providers.get(pid)
                if p and p.api_key and p.base_url:
                    # 【修复】如果 route_config.model 为空，使用服务商的 selected_models
                    pool_model = route_config.model
                    if not pool_model and p.selected_models:
                        pool_model = p.selected_models[0]
                    pool_configs.append(ProviderPoolConfig(
                        provider_id=pid,
                        base_url=p.base_url,
                        api_key=p.api_key,
                        provider_type=p.provider_type or "openai",
                        model=pool_model,
                    ))
            if pool_configs:
                model_router.set_provider_pool(capability, pool_configs)
                logger.info(f"[配置] {capability} 启用负载均衡: {len(pool_configs)} 个服务商")
        
        if active_provider:
            # 【修复】保留原始的 extra_body（如 response_format），同时支持 enable_thinking
            original_extra_body = model_router.routes.get(capability)
            original_extra_body = original_extra_body.extra_body if original_extra_body else None
            extra_body = dict(original_extra_body) if original_extra_body else {}
            
            if route_config.enable_thinking:
                extra_body["enable_thinking"] = True
                extra_body["thinking_budget"] = 4096

            # 更新路由配置
            model_router.routes[capability] = ModelConfig(
                provider=active_provider.type,
                model=route_config.model or config.default_model or "gpt-3.5-turbo",
                endpoint=model_router.routes[capability].endpoint,
                extra_body=extra_body
            )
            
            # 设置 override
            model_router.overrides[capability] = {
                "base_url": active_provider.base_url,
                "api_key": active_provider.api_key,
                "timeout": route_config.timeout,
                "model": route_config.model,
                "extra_body": extra_body,
                "provider_type": active_provider.provider_type or "openai",  # 关键：传递服务商API类型
            }
            logger.debug(f"[配置] 已设置 {capability} -> Provider: {active_provider.name}, Model: {route_config.model}, Type: {active_provider.provider_type}, Thinking: {route_config.enable_thinking}")

    # 2.3 (New) 自动应用默认服务商到未配置的路由
    if default_provider:
        for cap_name, current_config in model_router.routes.items():
            if cap_name not in config.capability_routes:
                # 使用默认模型（如果配置了default_model，否则用服务商的第一个模型，否则GPT-3.5）
                model_to_use = config.default_model or (default_provider.models[0] if default_provider.models else "gpt-3.5-turbo")
                
                model_router.routes[cap_name] = ModelConfig(
                    provider=default_provider.type,
                    model=model_to_use,
                    endpoint=current_config.endpoint,
                    extra_body=current_config.extra_body # 保留原始的 extra_body (如 response_format)
                )
                
                model_router.overrides[cap_name] = {
                    "base_url": default_provider.base_url,
                    "api_key": default_provider.api_key,
                    "timeout": 60,
                    "model": model_to_use,
                    "extra_body": current_config.extra_body,
                    "provider_type": default_provider.provider_type or "openai",  # 关键：传递服务商API类型
                }
                logger.debug(f"[配置] 自动应用默认服务商到 {cap_name}: {default_provider.name} (Model: {model_to_use}, Type: {default_provider.provider_type})")

    # --- 3. Embedding 配置 ---
    emb_provider = config.providers.get(config.embedding_provider_id)
    
    if emb_provider:
        embedding_service.provider = emb_provider.type
        embedding_service.api_base_url = emb_provider.base_url
        embedding_service.api_key = emb_provider.api_key
        embedding_service.model = config.embedding_model
        embedding_service.enabled = True
    elif config.embedding_api_key and config.embedding_base_url:
        # 旧配置回退
        embedding_service.provider = settings.embedding_provider
        embedding_service.api_base_url = config.embedding_base_url
        embedding_service.api_key = config.embedding_api_key
        embedding_service.model = config.embedding_model
        embedding_service.enabled = True
    else:
        embedding_service.enabled = False

    return config


ui_config = apply_ui_config(environment_repository.load_ui_config(ui_config_path))

# 【新增】Embedding 集成服务 - 管理分类学、演化预测、叙事生成等扩展功能
embedding_integration = EmbeddingIntegrationService(embedding_service, model_router)

simulation_engine = SimulationEngine(
    environment=environment_system,
    mortality=mortality_engine,
    embeddings=embedding_service,
    router=model_router,
    report_builder=report_builder,
    exporter=export_service,
    niche_analyzer=niche_analyzer,
    speciation=speciation_service,
    background_manager=background_manager,
    tiering=tiering_service,
    focus_processor=focus_processor,
    critical_analyzer=critical_analyzer,
    escalation_service=pressure_escalation,
    map_evolution=map_evolution,
    migration_advisor=migration_advisor,
    map_manager=map_manager,
    reproduction_service=reproduction_service,
    adaptation_service=adaptation_service,
    gene_flow_service=gene_flow_service,
    embedding_integration=embedding_integration,  # 【新增】Embedding集成服务
)
watchlist: set[str] = set()
action_queue = {"queued_rounds": 0, "running": False}

# 后端会话ID：每次后端启动时生成新的UUID
# 用于让前端检测后端是否重启，实现"后端重启回主菜单"的逻辑
# 【迁移说明】这些全局变量将逐步迁移到 core/session.py 的 SimulationSessionManager
_backend_session_id: str = ""


def set_backend_session_id(session_id: str) -> None:
    """设置后端会话ID（由 main.py 在启动时调用）
    
    【迁移说明】此函数保留用于向后兼容。
    新代码应使用 core/session.py 的 get_session_manager().generate_session_id()
    """
    global _backend_session_id
    _backend_session_id = session_id
    # 【桥接】同时设置到新的 SessionManager
    try:
        from ..core.session import get_session_manager
        session = get_session_manager()
        session._session_id = session_id  # 直接设置以保持同步
    except Exception:
        pass  # 初始化阶段可能失败，忽略


def get_backend_session_id() -> str:
    """获取后端会话ID
    
    【迁移说明】此函数保留用于向后兼容。
    新代码应使用 core/session.py 的 get_session_manager().session_id
    """
    return _backend_session_id


def initialize_environment() -> None:
    """启动时的环境初始化：确保数据库结构完整，恢复回合计数器"""
    try:
        logger.info("[环境初始化] 开始检查数据库结构...")
        # 确保数据库列完整
        environment_repository.ensure_map_state_columns()
        environment_repository.ensure_tile_columns()
        
        # 检查地图是否存在（但不自动生成）
        tiles = environment_repository.list_tiles(limit=10)
        if len(tiles) > 0:
            logger.info(f"[环境初始化] 发现现有地图，地块数量: {len(tiles)}")
            logger.debug(f"[环境初始化] 示例地块: x={tiles[0].x}, y={tiles[0].y}, biome={tiles[0].biome}")
        else:
            logger.info(f"[环境初始化] 未发现地图数据，等待创建存档时生成")
        
        # 【关键修复】恢复回合计数器：优先从 MapState，其次从历史记录
        try:
            # 方法1：从 MapState 恢复（最可靠）
            map_state = environment_repository.get_state()
            if map_state and map_state.turn_index > 0:
                simulation_engine.turn_counter = map_state.turn_index + 1
                logger.info(f"[环境初始化] 从 MapState 恢复回合计数器: {simulation_engine.turn_counter}")
            else:
                # 方法2：从历史记录恢复
                logs = history_repository.list_turns(limit=1)
                if logs:
                    last_turn = logs[0].turn_index
                    simulation_engine.turn_counter = last_turn + 1  # 下一个回合
                    logger.info(f"[环境初始化] 从历史记录恢复回合计数器: {simulation_engine.turn_counter}")
                else:
                    logger.info(f"[环境初始化] 未发现历史记录，回合计数器保持为 0")
        except Exception as e:
            logger.warning(f"[环境初始化] 恢复回合计数器失败: {e}")
            
    except Exception as e:
        logger.error(f"[环境初始化错误] {str(e)}")
        import traceback
        logger.error(traceback.format_exc())


def push_simulation_event(event_type: str, message: str, category: str = "其他", force: bool = False, **extra):
    """推送演化事件到前端
    
    Args:
        event_type: 事件类型 (start, complete, error, stage, etc.)
        message: 事件消息
        category: 事件分类
        force: 是否强制推送（即使 simulation_running=False）
        **extra: 额外参数
        
    【迁移说明】此函数保留用于向后兼容。
    新代码应使用 core/session.py 的 get_session_manager().push_event()
    """
    global simulation_events, simulation_running
    # 允许在 simulation_running=False 时也能推送关键事件（如 complete, error）
    if simulation_running or force or event_type in ("complete", "error", "turn_complete"):
        try:
            event = {
                "type": event_type,
                "message": message,
                "category": category,
                "timestamp": __import__("time").time()
            }
            # 添加额外参数（如AI进度信息）
            event.update(extra)
            simulation_events.put(event)
            # 对于关键事件，打印日志确认
            if event_type in ("complete", "error", "turn_complete"):
                logger.debug(f"[SSE事件] 已推送 {event_type}: {message}")
        except Exception as e:
            logger.warning(f"[事件推送错误] {str(e)}")


@router.get("/events/stream")
async def stream_simulation_events():
    """Server-Sent Events 端点，实时推送演化事件"""
    async def event_generator():
        global simulation_events
        
        # 发送连接确认
        yield f"data: {json.dumps({'type': 'connected', 'message': '已连接到事件流'})}\n\n"
        
        idle_count = 0
        while True:
            try:
                # 批量获取所有待发送事件（提高吞吐量）
                events_sent = 0
                while not simulation_events.empty() and events_sent < 20:
                    event = simulation_events.get_nowait()
                    yield f"data: {json.dumps(event)}\n\n"
                    events_sent += 1
                    idle_count = 0
                
                if events_sent == 0:
                    idle_count += 1
                    # 空闲时发送 SSE 心跳保持连接
                    if idle_count >= 50:  # 每5秒发一次心跳
                        yield f": keepalive\n\n"
                        idle_count = 0
                    await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"[SSE错误] {str(e)}")
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


def _perform_autosave(turn_index: int) -> bool:
    """执行自动保存
    
    Returns:
        bool: 是否成功保存
    """
    global current_save_name, autosave_counter
    
    if not current_save_name:
        logger.debug("[自动保存] 跳过: 没有当前存档")
        return False
    
    # 读取配置
    config = environment_repository.load_ui_config(ui_config_path)
    
    if not config.autosave_enabled:
        return False
    
    autosave_counter += 1
    
    # 检查是否达到保存间隔
    if autosave_counter < config.autosave_interval:
        logger.debug(f"[自动保存] 跳过: 计数 {autosave_counter}/{config.autosave_interval}")
        return False
    
    # 重置计数器
    autosave_counter = 0
    
    try:
        # 生成自动保存存档名称
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        autosave_name = f"autosave_{current_save_name}_{timestamp}"
        
        logger.info(f"[自动保存] 开始保存: {autosave_name}, 回合={turn_index}")
        push_simulation_event("autosave", f"💾 自动保存中...", "系统")
        
        # 创建自动保存
        save_manager.create_save(autosave_name, f"自动保存 - T{turn_index}")
        save_manager.save_game(autosave_name, turn_index)
        
        # 清理旧的自动保存（保留最新的N个）
        _cleanup_old_autosaves(current_save_name, config.autosave_max_slots)
        
        logger.info(f"[自动保存] 完成: {autosave_name}")
        push_simulation_event("autosave_complete", f"✅ 自动保存完成 (T{turn_index})", "系统")
        return True
    except Exception as e:
        logger.error(f"[自动保存] 失败: {str(e)}")
        push_simulation_event("autosave_error", f"⚠️ 自动保存失败: {str(e)}", "错误")
        return False


def _cleanup_old_autosaves(base_save_name: str, max_slots: int) -> None:
    """清理旧的自动保存，只保留最新的N个"""
    try:
        all_saves = save_manager.list_saves()
        
        # 筛选出属于当前存档的自动保存
        autosaves = [
            s for s in all_saves 
            if s.get("name", "").startswith(f"autosave_{base_save_name}_")
        ]
        
        # 按时间戳排序（从新到旧）
        autosaves.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
        
        # 删除超出限制的旧存档
        for old_save in autosaves[max_slots:]:
            save_name = old_save.get("name")
            if save_name:
                logger.info(f"[自动保存] 清理旧存档: {save_name}")
                save_manager.delete_save(save_name)
    except Exception as e:
        logger.warning(f"[自动保存] 清理旧存档失败: {str(e)}")


@router.post("/turns/run")  # 移除 response_model，避免 Pydantic 验证阻塞
async def run_turns(command: TurnCommand, background_tasks: BackgroundTasks):
    import traceback
    import time as time_module
    global simulation_running, autosave_counter
    
    start_time = time_module.time()
    
    try:
        logger.info(f"[推演开始] 回合数: {command.rounds}, 压力数: {len(command.pressures)}")
        
        # 清空事件队列
        while not simulation_events.empty():
            simulation_events.get_nowait()
        
        simulation_running = True
        action_queue["running"] = True
        
        push_simulation_event("start", f"开始推演 {command.rounds} 回合", "系统")
        
        simulation_engine.update_watchlist(watchlist)
        pressures = list(command.pressures)
        if not pressures and pressure_queue:
            pressures = pressure_queue.pop(0)
            action_queue["queued_rounds"] = max(action_queue["queued_rounds"] - 1, 0)
        command.pressures = pressures
        logger.info(f"[推演执行] 应用压力: {[p.kind for p in pressures]}")
        
        current_turn = simulation_engine.turn_counter
        
        # 【能量系统】检查压力消耗
        if pressures and energy_service.enabled:
            pressure_dicts = [{"kind": p.kind, "intensity": p.intensity} for p in pressures]
            total_cost = energy_service.get_pressure_cost(pressure_dicts)
            current_energy = energy_service.get_state().current
            
            if current_energy < total_cost:
                action_queue["running"] = False
                simulation_running = False
                raise HTTPException(
                    status_code=400, 
                    detail=f"能量不足！施加压力需要 {total_cost} 能量，当前只有 {current_energy}"
                )
            
            # 消耗能量
            success, msg = energy_service.spend(
                "pressure", 
                current_turn,
                details=f"压力: {', '.join([p.kind for p in pressures])}",
                intensity=sum(p.intensity for p in pressures) / len(pressures) if pressures else 0
            )
            if success:
                push_simulation_event("energy", f"⚡ 消耗 {total_cost} 能量（环境压力）", "系统")
        
        push_simulation_event("pressure", f"应用压力: {', '.join([p.kind for p in pressures]) if pressures else '自然演化'}", "环境")
        
        # 将推送函数传递给引擎
        simulation_engine._event_callback = push_simulation_event
        
        # 【超时配置】从 UIConfig 读取并应用到 AI 服务
        current_config = environment_repository.load_ui_config(ui_config_path)
        simulation_engine.ai_pressure_service.set_timeout_config(
            species_eval_timeout=current_config.ai_species_eval_timeout,
            batch_eval_timeout=current_config.ai_batch_eval_timeout,
            narrative_timeout=current_config.ai_narrative_timeout,
        )
        
        # 【流式心跳】将事件回调传递给 AI 服务，启用流式心跳监测
        simulation_engine.ai_pressure_service.set_event_callback(push_simulation_event)
        
        reports = await simulation_engine.run_turns_async(command)
        
        elapsed = time_module.time() - start_time
        logger.info(f"[推演完成] 生成了 {len(reports)} 个报告, 耗时 {elapsed:.1f}秒")
        
        # 【诊断日志】记录响应数据量，帮助排查卡顿问题
        if reports:
            total_species = sum(len(r.species) for r in reports)
            logger.info(f"[响应准备] 返回 {len(reports)} 个报告, 共 {total_species} 个物种快照")
        
        # 【能量系统】回合结束后恢复能量
        final_turn = simulation_engine.turn_counter
        regen = energy_service.regenerate(final_turn)
        if regen > 0:
            push_simulation_event("energy", f"⚡ 神力恢复 +{regen}", "系统")
        
        # 【关键】先发送完成事件，让前端知道推演已完成
        push_simulation_event("complete", f"推演完成！生成了 {len(reports)} 个报告", "系统")
        push_simulation_event("turn_complete", f"回合推演完成", "系统")
        
        action_queue["running"] = False
        action_queue["queued_rounds"] = max(action_queue["queued_rounds"] - command.rounds, 0)
        simulation_running = False
        
        # 【关键修复】使用 BackgroundTasks 执行自动保存
        # 这会在响应完全发送后才执行，避免响应被阻塞
        latest_turn = reports[-1].turn_index if reports else 0
        
        def do_autosave():
            """在后台执行自动保存"""
            try:
                _perform_autosave(latest_turn)
            except Exception as e:
                logger.warning(f"[后台任务] 自动保存失败: {e}")
        
        # 添加到 BackgroundTasks，会在响应发送后执行
        background_tasks.add_task(do_autosave)
        
        # 【性能优化】直接使用 json.dumps 序列化，完全绕过 FastAPI/Pydantic
        logger.info(f"[HTTP响应] 开始序列化响应...")
        try:
            # 使用 model_dump 转换为 dict
            response_data = [r.model_dump(mode="json") for r in reports]
            # 使用标准 json 模块序列化
            json_str = json.dumps(response_data, ensure_ascii=False, default=str)
            logger.info(f"[HTTP响应] 序列化完成，数据大小: {len(json_str)} 字节，正在返回...")
            # 使用最原始的 Response 返回
            from starlette.responses import Response
            return Response(
                content=json_str,
                media_type="application/json",
                headers={"Content-Length": str(len(json_str.encode('utf-8')))}
            )
        except Exception as e:
            logger.error(f"[HTTP响应] 序列化失败: {e}")
            import traceback as tb
            logger.error(tb.format_exc())
            # 降级：返回简化的响应
            return JSONResponse(content={"error": str(e), "reports_count": len(reports)})
        
    except Exception as e:
        elapsed = time_module.time() - start_time
        logger.error(f"[推演错误] {str(e)}, 耗时 {elapsed:.1f}秒")
        logger.error(traceback.format_exc())
        
        # 【关键修复】先发送 error 事件，再设置 simulation_running=False
        # 使用 force=True 确保事件一定能发送
        push_simulation_event("error", f"推演失败: {str(e)}", "错误", force=True)
        
        action_queue["running"] = False
        simulation_running = False
        
        raise HTTPException(status_code=500, detail=f"推演执行失败: {str(e)}")


@router.post("/species/edit", response_model=SpeciesDetail)
def edit_species(request: SpeciesEditRequest) -> SpeciesDetail:
    species = species_repository.get_by_lineage(request.lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail="Species not found")
    if request.description:
        species.description = request.description
    if request.trait_overrides:
        species.morphology_stats.update(request.trait_overrides)
    if request.abstract_overrides:
        species.abstract_traits.update(request.abstract_overrides)
    if request.open_new_lineage:
        species.status = "split"
    species_repository.upsert(species)
    # 返回最新的物种详情，与 `/species/{code}` 保持一致
    return _serialize_species_detail(species)


@router.get("/watchlist")
def get_watchlist() -> dict[str, list[str]]:
    """获取当前玩家关注的物种列表（Critical 层）"""
    return {"watching": sorted(watchlist)}


@router.post("/watchlist")
def update_watchlist(request: WatchlistRequest) -> dict[str, list[str]]:
    """更新玩家关注的物种列表（Critical 层）"""
    watchlist.clear()
    watchlist.update(request.lineage_codes)
    simulation_engine.update_watchlist(watchlist)
    return {"watching": sorted(watchlist)}


import hashlib
import time

# 族谱缓存（简单内存缓存）
_lineage_cache: dict[str, tuple[LineageTree, str, float]] = {}  # key -> (data, etag, timestamp)
_lineage_cache_ttl = 30  # 缓存有效期（秒）

def _invalidate_lineage_cache():
    """在物种变化时调用以清除缓存"""
    _lineage_cache.clear()

@router.get("/lineage")
def get_lineage_tree(
    request: Request,
    status: str | None = None,
    prefix: str | None = None,
    include_genetic_distances: bool = False,
    limit: int | None = None,
    offset: int = 0
):
    """
    获取族谱树数据
    
    Args:
        status: 可选，筛选状态 ("alive", "extinct")
        prefix: 可选，按lineage_code前缀筛选（如 "A1" 获取A1及其后代）
        include_genetic_distances: 是否包含遗传距离数据（默认False，减少响应体积）
        limit: 可选，返回数量限制（用于分页）
        offset: 分页偏移量
        
    支持 ETag 条件请求，减少重复传输。
    """
    # 构建缓存键
    cache_key = f"{status}:{prefix}:{include_genetic_distances}:{limit}:{offset}"
    current_time = time.time()
    
    # 检查缓存
    if cache_key in _lineage_cache:
        cached_data, cached_etag, cached_time = _lineage_cache[cache_key]
        
        # 检查缓存是否过期
        if current_time - cached_time < _lineage_cache_ttl:
            # 检查 If-None-Match 头
            if_none_match = request.headers.get("if-none-match")
            if if_none_match == cached_etag:
                return JSONResponse(status_code=304, content=None, headers={"ETag": cached_etag})
            
            # 返回缓存数据
            response = JSONResponse(content=cached_data.model_dump())
            response.headers["ETag"] = cached_etag
            response.headers["Cache-Control"] = f"max-age={_lineage_cache_ttl}"
            return response
    
    nodes: list[LineageNode] = []
    
    # 获取物种列表（支持过滤和分页）
    all_species = species_repository.list_species(
        status=status,
        prefix=prefix,
        limit=limit,
        offset=offset
    )
    
    if not all_species:
        return LineageTree(nodes=[], total_count=0)
    
    # 获取总数（用于分页）
    total_count = species_repository.count_species(status=status, prefix=prefix)
    
    # 批量获取人口统计信息（单次查询替代 O(N) 次查询）
    species_ids = [s.id for s in all_species]
    population_stats = species_repository.get_population_stats_batch(species_ids)
    
    # 只在需要时加载遗传距离数据
    genus_distances = {}
    if include_genetic_distances:
        all_genera = genus_repository.list_all()
        for genus in all_genera:
            genus_distances[genus.code] = genus.genetic_distances
    
    # 计算后代数量（内存计算，O(N)）
    descendant_map: dict[str, int] = {}
    for species in all_species:
        if species.parent_code:
            descendant_map[species.parent_code] = descendant_map.get(species.parent_code, 0) + 1
    
    # 构建节点（无数据库查询）
    for species in all_species:
        # 当前种群从 morphology_stats 获取
        current_pop = int(species.morphology_stats.get("population", 0) or 0)
        
        # 从批量查询结果获取峰值人口和最后回合
        stats = population_stats.get(species.id, {})
        historical_peak = stats.get("peak_population", 0)
        peak_pop = max(int(historical_peak), current_pop)
        
        # 灭绝回合
        extinction_turn = None
        if species.status == "extinct":
            extinction_turn = stats.get("last_turn", 0)
        
        # 推断生态角色
        ecological_role = _infer_ecological_role(species)
        
        # 推断tier
        tier = "background" if species.is_background else None
        
        # 遗传距离（按需加载）
        genetic_distances_to_siblings = {}
        if include_genetic_distances and species.genus_code and species.genus_code in genus_distances:
            for key, distance in genus_distances[species.genus_code].items():
                if species.lineage_code in key:
                    other_code = key.replace(f"{species.lineage_code}-", "").replace(f"-{species.lineage_code}", "")
                    if other_code != species.lineage_code:
                        genetic_distances_to_siblings[other_code] = distance
        
        # 获取营养级
        trophic_level = getattr(species, 'trophic_level', 1.0)
        if trophic_level is None or not isinstance(trophic_level, (int, float)):
            trophic_level = 1.0
        
        nodes.append(
            LineageNode(
                lineage_code=species.lineage_code,
                parent_code=species.parent_code,
                latin_name=species.latin_name,
                common_name=species.common_name,
                state=species.status,
                population_share=1.0,
                major_events=[],
                birth_turn=species.created_turn,
                extinction_turn=extinction_turn,
                ecological_role=ecological_role,
                tier=tier,
                trophic_level=float(trophic_level),
                speciation_type="normal",
                current_population=current_pop,
                peak_population=int(peak_pop),
                descendant_count=descendant_map.get(species.lineage_code, 0),
                taxonomic_rank=species.taxonomic_rank,
                genus_code=species.genus_code,
                hybrid_parent_codes=species.hybrid_parent_codes,
                hybrid_fertility=species.hybrid_fertility,
                genetic_distances=genetic_distances_to_siblings,
            )
        )
    
    result = LineageTree(nodes=nodes, total_count=total_count)
    
    # 生成 ETag（基于内容哈希）
    content_str = result.model_dump_json()
    etag = f'"{hashlib.md5(content_str.encode()).hexdigest()}"'
    
    # 缓存结果
    _lineage_cache[cache_key] = (result, etag, current_time)
    
    # 返回带 ETag 的响应
    response = JSONResponse(content=result.model_dump())
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = f"max-age={_lineage_cache_ttl}"
    return response


@router.get("/queue", response_model=ActionQueueStatus)
def get_queue_status() -> ActionQueueStatus:
    preview = []
    for batch in pressure_queue:
        if not batch:
            preview.append("自然演化")
        else:
            kinds = [p.kind for p in batch]
            preview.append("+".join(kinds))
    
    return ActionQueueStatus(
        queued_rounds=action_queue["queued_rounds"], 
        running=action_queue["running"],
        queue_preview=preview
    )


@router.get("/history", response_model=list[TurnReport])
def list_history(limit: int = 10) -> list[TurnReport]:
    logs = history_repository.list_turns(limit=limit)
    return [TurnReport.model_validate(log.record_data) for log in logs]


@router.get("/exports", response_model=list[ExportRecord])
def list_exports() -> list[ExportRecord]:
    records = export_service.list_records()
    return [ExportRecord(**record) for record in records]


@router.get("/map", response_model=MapOverview)
def get_map_overview(
    limit_tiles: int = 0, 
    limit_habitats: int = 0,
    view_mode: str = "terrain",
    species_code: str | None = None,
) -> MapOverview:
    try:
        tile_limit = None if limit_tiles <= 0 else limit_tiles
        habitat_limit = None if limit_habitats <= 0 else limit_habitats
        logger.debug(f"[地图查询] 限制地块: {tile_limit or "all"}, 栖息地: {habitat_limit or "all"}, 模式: {view_mode}, 物种: {species_code}")
        
        species_id = None
        if species_code:
            species = species_repository.get_by_lineage(species_code)
            if species:
                species_id = species.id
        
        overview = map_manager.get_overview(
            tile_limit=tile_limit, 
            habitat_limit=habitat_limit,
            view_mode=view_mode,  # type: ignore
            species_id=species_id,
        )
        logger.debug(f"[地图查询] 返回地块数: {len(overview.tiles)}, 栖息地数: {len(overview.habitats)}")
        return overview
    except Exception as e:
        logger.error(f"[地图查询错误] {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"地图查询失败: {str(e)}")


@router.get("/config/ui", response_model=UIConfig)
def get_ui_config() -> UIConfig:
    config = environment_repository.load_ui_config(ui_config_path)
    return apply_ui_config(config)


@router.post("/config/ui", response_model=UIConfig)
def update_ui_config(config: UIConfig) -> UIConfig:
    saved = environment_repository.save_ui_config(ui_config_path, config)
    return apply_ui_config(saved)


@router.get("/pressures/templates", response_model=list[PressureTemplate])
def list_pressure_templates() -> list[PressureTemplate]:
    return pressure_templates


@router.post("/queue/add", response_model=ActionQueueStatus)
def add_to_queue(request: QueueRequest) -> ActionQueueStatus:
    for _ in range(request.rounds):
        configs = [PressureConfig(**p.model_dump()) for p in request.pressures]
        pressure_queue.append(configs)
    action_queue["queued_rounds"] += request.rounds
    
    # 同样生成 preview
    preview = []
    for batch in pressure_queue:
        if not batch:
            preview.append("自然演化")
        else:
            kinds = [p.kind for p in batch]
            preview.append("+".join(kinds))
            
    return ActionQueueStatus(
        queued_rounds=action_queue["queued_rounds"],
        running=action_queue["running"],
        queue_preview=preview,
    )


@router.post("/queue/clear", response_model=ActionQueueStatus)
def clear_queue() -> ActionQueueStatus:
    pressure_queue.clear()
    action_queue["queued_rounds"] = 0
    return ActionQueueStatus(
        queued_rounds=0,
        running=action_queue["running"],
        queue_preview=[],
    )


@router.get("/species/list", response_model=SpeciesList)
def list_all_species() -> SpeciesList:
    """获取所有物种的简要列表"""
    all_species = species_repository.list_species()
    
    items = []
    for species in all_species:
        # 推断生态角色：优先使用 diet_type 字段
        ecological_role = _infer_ecological_role(species)
        
        # 【修复】确保种群数量在JavaScript安全整数范围内
        raw_population = species.morphology_stats.get("population", 0) or 0
        MAX_SAFE_POPULATION = 9_007_199_254_740_991  # JavaScript安全整数上限
        population = max(0, min(int(raw_population), MAX_SAFE_POPULATION))
        
        items.append(SpeciesListItem(
            lineage_code=species.lineage_code,
            latin_name=species.latin_name,
            common_name=species.common_name,
            population=population,
            status=species.status,
            ecological_role=ecological_role
        ))
    
    return SpeciesList(species=items)


@router.get("/species/{lineage_code}", response_model=SpeciesDetail)
def get_species_detail(lineage_code: str) -> SpeciesDetail:
    species = species_repository.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail="Species not found")
    return _serialize_species_detail(species)


@router.get("/saves/list")
def list_saves() -> list[dict]:
    """列出所有存档"""
    try:
        saves = save_manager.list_saves()
        logger.debug(f"[存档API] 查询到 {len(saves)} 个存档")
        return saves
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"列出存档失败: {str(e)}")


@router.post("/saves/create")
async def create_save(request: CreateSaveRequest) -> dict:
    """创建新存档"""
    global current_save_name, autosave_counter
    try:
        logger.info(f"[存档API] 创建存档: {request.save_name}, 剧本: {request.scenario}")
        
        # 【关键修复】重置回合计数器
        simulation_engine.turn_counter = 0
        logger.debug(f"[存档API] 回合计数器已重置为 0")
        
        # 【重置游戏服务状态】
        energy_service.reset()
        divine_progression_service.reset()
        achievement_service.reset()
        game_hints_service.clear_cooldown()
        logger.debug(f"[存档API] 游戏服务状态已重置")
        
        # 设置当前存档名称（用于自动保存）
        current_save_name = request.save_name
        autosave_counter = 0
        logger.debug(f"[存档API] 当前存档名称设置为: {current_save_name}")
        
        # 1. 清空当前数据库（确保新存档从干净状态开始）
        logger.info(f"[存档API] 清空当前数据...")
        from ..core.database import session_scope
        from ..models.species import Species
        from ..models.environment import MapTile, MapState, HabitatPopulation
        from ..models.history import TurnLog
        from ..models.genus import Genus
        
        with session_scope() as session:
            # 删除所有物种
            for sp in session.exec(select(Species)).all():
                session.delete(sp)
            # 删除所有地图数据
            for tile in session.exec(select(MapTile)).all():
                session.delete(tile)
            for state in session.exec(select(MapState)).all():
                session.delete(state)
            for hab in session.exec(select(HabitatPopulation)).all():
                session.delete(hab)
            # 删除历史记录
            for log in session.exec(select(TurnLog)).all():
                session.delete(log)
            # 删除所有属数据
            for genus in session.exec(select(Genus)).all():
                session.delete(genus)
        
        logger.info(f"[存档API] 数据清空完成")
        
        # 1.5 清除服务内部缓存和全局状态（确保数据隔离）
        logger.debug(f"[存档API] 清除服务缓存和全局状态...")
        migration_advisor.clear_all_caches()
        habitat_manager.clear_all_caches()
        dispersal_engine.clear_caches()  # 清空扩散引擎缓存
        pressure_queue.clear()
        watchlist.clear()
        
        # 【新增】清空AI压力响应服务的缓存（连续危险回合数等）
        if simulation_engine.ai_pressure_service:
            simulation_engine.ai_pressure_service.clear_all_caches()
        
        # 【新增】清空分化服务的缓存（延迟请求等）
        simulation_engine.speciation.clear_all_caches()
        
        # 【新增】尽早清空 embedding 缓存（在初始化物种之前）
        embedding_integration.clear_all_caches()
        
        logger.debug(f"[存档API] 服务缓存和全局状态已清除")
        
        # 2. 初始化地图
        logger.info(f"[存档API] 初始化地图，种子: {request.map_seed if request.map_seed else '随机'}")
        map_manager.ensure_initialized(map_seed=request.map_seed)
        
        # 3. 初始化物种
        if request.scenario == "空白剧本" and request.species_prompts:
            logger.info(f"[存档API] 空白剧本，生成 {len(request.species_prompts)} 个物种")
            # 动态分配 lineage_code，避免冲突
            base_codes = ["A", "B", "C", "D", "E", "F", "G", "H"]
            existing_species = species_repository.list_species()
            used_codes = {sp.lineage_code[:1] for sp in existing_species}  # 已使用的字母前缀
            
            available_codes = [code for code in base_codes if code not in used_codes]
            if len(available_codes) < len(request.species_prompts):
                raise HTTPException(
                    status_code=400, 
                    detail=f"物种数量过多，最多支持 {len(available_codes)} 个初始物种"
                )
            
            for i, prompt in enumerate(request.species_prompts):
                lineage_code = f"{available_codes[i]}1"
                species = species_generator.generate_from_prompt(prompt, lineage_code)
                species_repository.upsert(species)
                logger.debug(f"[存档API] 生成物种: {species.lineage_code} - {species.common_name}")
        else:
            # 原初大陆：使用默认物种
            logger.info(f"[存档API] 原初大陆，加载默认物种...")
            from ..core.seed import seed_defaults
            seed_defaults()
        
        # 3.5 初始化物种栖息地分布（关键！）
        logger.info(f"[存档API] 初始化物种栖息地分布...")
        all_species = species_repository.list_species()
        if all_species:
            map_manager.snapshot_habitats(all_species, turn_index=0, force_recalculate=True)
            logger.info(f"[存档API] 栖息地分布初始化完成，{len(all_species)} 个物种已分布到地图")
        else:
            logger.warning(f"[存档API警告] 没有物种需要分布")
        
        # 3.6 创建初始人口快照（修复bug：系谱树需要这个数据）
        logger.info(f"[存档API] 创建初始人口快照...")
        from ..models.species import PopulationSnapshot
        MAX_SAFE_POPULATION = 9_007_199_254_740_991  # JavaScript安全整数上限
        if all_species:
            snapshots = []
            for species in all_species:
                # 【修复】确保种群数量在安全范围内
                raw_pop = species.morphology_stats.get("population", 0) or 0
                population = max(0, min(int(raw_pop), MAX_SAFE_POPULATION))
                if population > 0:
                    snapshots.append(PopulationSnapshot(
                        species_id=species.id or 0,
                        turn_index=0,
                        region_id=0,
                        count=population,
                        death_count=0,
                        survivor_count=population,
                        population_share=1.0 / len(all_species),
                        ecological_pressure={}
                    ))
            if snapshots:
                species_repository.add_population_snapshots(snapshots)
                logger.debug(f"[存档API] 初始人口快照创建完成，{len(snapshots)} 条记录")
        
        # 3.7 创建初始回合报告（修复bug：前端需要显示物种数量）
        logger.info(f"[存档API] 创建初始回合报告...")
        if all_species:
            from ..schemas.responses import SpeciesSnapshot
            initial_species = []
            # 计算总人口用于计算population_share
            # 【修复】确保种群数量在安全范围内（防止32位整数溢出）
            def safe_population(sp):
                raw = sp.morphology_stats.get("population", 0) or 0
                return max(0, min(int(raw), MAX_SAFE_POPULATION))
            total_population = sum(safe_population(sp) for sp in all_species)
            for species in all_species:
                population = safe_population(species)
                population_share = (population / total_population) if total_population > 0 else 0.0
                
                # 推断生态角色：优先使用 diet_type 字段
                ecological_role = _infer_ecological_role(species)
                
                initial_species.append(SpeciesSnapshot(
                    lineage_code=species.lineage_code,
                    latin_name=species.latin_name,
                    common_name=species.common_name,
                    population=population,
                    population_share=population_share,
                    deaths=0,
                    death_rate=0.0,
                    niche_overlap=0.0,
                    tier="T1.0",
                    notes=[f"初始物种，投放到{request.scenario}"],
                    status=species.status,
                    ecological_role=ecological_role,
                    # 初始状态的地块分布（默认值）
                    total_tiles=0,
                    healthy_tiles=0,
                    warning_tiles=0,
                    critical_tiles=0,
                    best_tile_rate=0.0,
                    worst_tile_rate=0.0,
                    has_refuge=True,
                    distribution_status="初始",
                ))
            
            # 获取地图状态
            map_state = environment_repository.get_state()
            
            initial_report = TurnReport(
                turn_index=0,
                pressures_summary="初始状态，无环境压力",
                narrative=f"世界诞生！{len(all_species)}个物种在{request.scenario}开始了它们的演化之旅。",
                species=initial_species,
                branching_events=[],
                background_summary=[],
                reemergence_events=[],
                major_events=[],
                map_changes=[],
                migration_events=[],
                sea_level=map_state.sea_level if map_state else 0.0,
                global_temperature=map_state.global_avg_temperature if map_state else 15.0,
                tectonic_stage=map_state.stage_name if map_state else "稳定期"
            )
            
            history_repository.log_turn(
                TurnLog(
                    turn_index=0,
                    pressures_summary=initial_report.pressures_summary,
                    narrative=initial_report.narrative,
                    record_data=initial_report.model_dump(mode="json")
                )
            )
            logger.debug(f"[存档API] 初始回合报告创建完成")
        
        # 4. 创建存档元数据
        metadata = save_manager.create_save(request.save_name, request.scenario)
        
        # 4.5 【重要】切换到存档专属的向量索引目录
        save_dir = save_manager.get_save_dir(request.save_name)
        if save_dir:
            context_stats = embedding_integration.switch_to_save_context(save_dir)
            logger.debug(f"[存档API] 已切换到存档向量目录: {context_stats}")
        else:
            logger.warning(f"[存档API警告] 未找到存档目录，使用全局向量索引")
        
        # 5. 立即保存游戏状态到存档文件
        logger.info(f"[存档API] 保存初始游戏状态到存档文件...")
        save_manager.save_game(request.save_name, turn_index=0)
        
        # 6. 更新物种数量
        species_count = len(species_repository.list_species())
        metadata["species_count"] = species_count
        logger.info(f"[存档API] 存档创建完成，物种数: {species_count}")
        
        return metadata
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"创建存档失败: {str(e)}")


@router.post("/saves/save")
async def save_game(request: SaveGameRequest) -> dict:
    """保存当前游戏状态"""
    try:
        # 获取当前回合数
        from ..repositories.history_repository import history_repository
        logs = history_repository.list_turns(limit=1)
        turn_index = logs[0].turn_index if logs else 0
        
        # 【新增】获取 Embedding 集成数据
        taxonomy_data = None
        event_embeddings = None
        try:
            integration_data = embedding_integration.export_for_save()
            taxonomy_data = integration_data.get("taxonomy")
            event_embeddings = integration_data.get("narrative")
        except Exception as e:
            logger.warning(f"[存档API] 获取Embedding集成数据失败（非致命）: {e}")
        
        save_dir = save_manager.save_game(
            request.save_name, 
            turn_index,
            taxonomy_data=taxonomy_data,
            event_embeddings=event_embeddings
        )
        return {"success": True, "save_dir": str(save_dir), "turn_index": turn_index}
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存游戏失败: {str(e)}")


@router.post("/saves/load")
async def load_game(request: LoadGameRequest) -> dict:
    """加载游戏存档"""
    global current_save_name, autosave_counter
    try:
        # 清除服务内部缓存和全局状态（确保数据隔离）
        logger.info(f"[存档加载] 清除服务缓存和全局状态...")
        migration_advisor.clear_all_caches()
        habitat_manager.clear_all_caches()
        dispersal_engine.clear_caches()  # 清空扩散引擎缓存
        pressure_queue.clear()
        watchlist.clear()
        
        # 【新增】清空AI压力响应服务的缓存（连续危险回合数等）
        if simulation_engine.ai_pressure_service:
            simulation_engine.ai_pressure_service.clear_all_caches()
        
        # 【新增】清空分化服务的缓存（延迟请求等）
        simulation_engine.speciation.clear_all_caches()
        
        logger.debug(f"[存档加载] 服务缓存和全局状态已清除")
        
        # 【重要】切换到存档专属的向量索引目录（同时清空所有缓存）
        save_dir = save_manager.get_save_dir(request.save_name)
        if save_dir:
            context_stats = embedding_integration.switch_to_save_context(save_dir)
            logger.debug(f"[存档加载] 已切换到存档向量目录: {context_stats}")
        else:
            # 存档目录不存在时仍需清空缓存
            embedding_integration.clear_all_caches()
            logger.warning(f"[存档加载警告] 未找到存档目录，使用全局向量索引")
        
        save_data = save_manager.load_game(request.save_name)
        turn_index = save_data.get("turn_index", 0)
        
        # 【关键修复】更新 simulation_engine 的回合计数器
        simulation_engine.turn_counter = turn_index
        logger.info(f"[存档加载] 已恢复回合计数器: {turn_index}")
        
        # 【新增】恢复 Embedding 集成数据
        try:
            integration_restore_data = {}
            if save_data.get("taxonomy"):
                integration_restore_data["taxonomy"] = save_data["taxonomy"]
            if save_data.get("event_embeddings"):
                integration_restore_data["narrative"] = save_data["event_embeddings"]
            if integration_restore_data:
                embedding_integration.import_from_save(integration_restore_data)
                logger.debug(f"[存档加载] Embedding集成数据已恢复")
        except Exception as e:
            logger.warning(f"[存档加载] 恢复Embedding集成数据失败（非致命）: {e}")
        
        # 设置当前存档名称（用于自动保存）
        # 如果加载的是自动保存，提取原始存档名
        if request.save_name.startswith("autosave_"):
            # 格式: autosave_{原存档名}_{时间戳}
            parts = request.save_name.split("_")
            if len(parts) >= 3:
                # 重建原始存档名（可能包含下划线）
                current_save_name = "_".join(parts[1:-2]) if len(parts) > 3 else parts[1]
            else:
                current_save_name = request.save_name
        else:
            current_save_name = request.save_name
        autosave_counter = 0
        logger.info(f"[存档加载] 当前存档名称设置为: {current_save_name}")
        
        # 【新增】存档恢复时重建食物网（可选）
        try:
            from ..repositories.environment_repository import environment_repository
            from pathlib import Path
            ui_config = environment_repository.load_ui_config(Path(settings.ui_config_path))
            
            if ui_config.food_web.rebuild_food_web_on_load:
                from ..repositories.species_repository import species_repository
                all_species = species_repository.list_species()
                
                rebuild_count = simulation_engine.food_web_manager.rebuild_food_web(
                    all_species, species_repository,
                    preserve_valid_links=ui_config.food_web.preserve_valid_links_on_rebuild
                )
                
                if rebuild_count > 0:
                    logger.info(f"[存档加载] 食物网重建完成，更新了 {rebuild_count} 个物种")
        except Exception as e:
            logger.warning(f"[存档加载] 食物网重建失败（非致命）: {e}")
        
        return {"success": True, "turn_index": turn_index}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"加载游戏失败: {str(e)}")


@router.delete("/saves/{save_name}")
def delete_save(save_name: str) -> dict:
    """删除存档"""
    try:
        success = save_manager.delete_save(save_name)
        if not success:
            raise HTTPException(status_code=404, detail="存档不存在")
        return {"success": True}
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除存档失败: {str(e)}")


@router.post("/species/generate")
def generate_species(request: GenerateSpeciesRequest) -> dict:
    """使用AI生成物种
    
    消耗能量点。
    """
    current_turn = simulation_engine.turn_counter
    
    # 【能量系统】检查能量
    can_afford, cost = energy_service.can_afford("create_species")
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！创造物种需要 {cost} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    try:
        # 先消耗能量
        success, msg = energy_service.spend(
            "create_species",
            current_turn,
            details=f"创造物种: {request.prompt[:30]}..."
        )
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        
        species = species_generator.generate_from_prompt(request.prompt, request.lineage_code)
        species_repository.upsert(species)
        
        # 记录成就
        achievement_service.record_species_creation(current_turn)
        
        return {
            "success": True,
            "species": {
                "lineage_code": species.lineage_code,
                "latin_name": species.latin_name,
                "common_name": species.common_name,
                "description": species.description,
            },
            "energy_spent": cost,
            "energy_remaining": energy_service.get_state().current,
        }
    except HTTPException:
        raise
    except Exception as e:
        # 生成失败，退还能量
        energy_service.add_energy(cost, "创造物种失败退还")
        logger.error(f"[物种生成API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成物种失败: {str(e)}")


@router.post("/species/generate/advanced")
def generate_species_advanced(request: GenerateSpeciesAdvancedRequest) -> dict:
    """增强版物种生成 - 支持完整参数
    
    支持预设栖息地、食性、猎物、父代物种（神启分化）等参数。
    消耗能量点。
    """
    current_turn = simulation_engine.turn_counter
    
    # 自动生成lineage_code如果未提供
    lineage_code = request.lineage_code
    if not lineage_code:
        existing_species = species_repository.get_all()
        used_codes = {s.lineage_code for s in existing_species}
        prefix = "S"
        index = 1
        while f"{prefix}{index}" in used_codes:
            index += 1
        lineage_code = f"{prefix}{index}"
    
    # 【能量系统】检查能量
    can_afford, cost = energy_service.can_afford("create_species")
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！创造物种需要 {cost} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    try:
        # 先消耗能量
        success, msg = energy_service.spend(
            "create_species",
            current_turn,
            details=f"创造物种(增强版): {request.prompt[:30]}..."
        )
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        
        # 获取现有物种列表
        existing_species = species_repository.get_all()
        
        # 使用增强版生成方法
        species = species_generator.generate_advanced(
            prompt=request.prompt,
            lineage_code=lineage_code,
            existing_species=existing_species,
            habitat_type=request.habitat_type,
            diet_type=request.diet_type,
            prey_species=request.prey_species,
            parent_code=request.parent_code,
            is_plant=request.is_plant,
            plant_stage=request.plant_stage,
        )
        species_repository.upsert(species)
        
        # 记录成就
        achievement_service.record_species_creation(current_turn)
        
        return {
            "success": True,
            "species": {
                "lineage_code": species.lineage_code,
                "latin_name": species.latin_name,
                "common_name": species.common_name,
                "description": species.description,
                "habitat_type": species.habitat_type,
                "diet_type": species.diet_type,
                "trophic_level": species.trophic_level,
                "parent_code": species.parent_code,
            },
            "energy_spent": cost,
            "energy_remaining": energy_service.get_state().current,
        }
    except HTTPException:
        raise
    except Exception as e:
        # 生成失败，退还能量
        energy_service.add_energy(cost, "创造物种失败退还")
        logger.error(f"[物种生成API(增强版)错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成物种失败: {str(e)}")


@router.post("/config/test-api")
def test_api_connection(request: dict) -> dict:
    """测试 API 连接是否有效，支持 OpenAI/Claude/Gemini 多种API格式"""
    
    api_type = request.get("type", "chat")  # chat 或 embedding
    base_url = request.get("base_url", "").rstrip("/")
    api_key = request.get("api_key", "")
    model = request.get("model", "")
    provider_type = request.get("provider_type", "openai")  # openai, anthropic, google
    
    if not base_url or not api_key:
        return {"success": False, "message": "请提供 API Base URL 和 API Key"}
    
    try:
        if api_type == "embedding":
            # 测试 embedding API (仅支持 OpenAI 兼容格式)
            url = f"{base_url}/embeddings"
            body = {
                "model": model or "Qwen/Qwen3-Embedding-4B",
                "input": "test"
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"[测试 Embedding] URL: {url}")
            logger.debug(f"[测试 Embedding] Model: {model}")
            
            response = httpx.post(url, json=body, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            if "data" in data and len(data["data"]) > 0:
                embedding_dim = len(data["data"][0].get("embedding", []))
                return {
                    "success": True,
                    "message": f"✅ 向量模型连接成功！",
                    "details": f"模型：{model or 'default'} | 向量维度：{embedding_dim}"
                }
            else:
                return {
                    "success": False,
                    "message": "API 响应格式不正确",
                    "details": f"响应：{str(data)[:100]}"
                }
        
        # ========== Chat API 测试 ==========
        
        if provider_type == "anthropic":
            # Claude 原生 API
            url = f"{base_url}/messages"
            body = {
                "model": model or "claude-3-5-sonnet-20241022",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "hi"}]
            }
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"[测试 Claude] URL: {url} | Model: {model}")
            
            response = httpx.post(url, json=body, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            if "content" in data and len(data.get("content", [])) > 0:
                return {
                    "success": True,
                    "message": f"✅ Claude API 连接成功！",
                    "details": f"模型：{data.get('model', model)} | 响应时间：{response.elapsed.total_seconds():.2f}s"
                }
            else:
                return {
                    "success": False,
                    "message": "API 响应格式不正确",
                    "details": f"响应：{str(data)[:100]}"
                }
                
        elif provider_type == "google":
            # Gemini 原生 API
            url = f"{base_url}/models/{model or 'gemini-2.0-flash'}:generateContent?key={api_key}"
            body = {
                "contents": [{"role": "user", "parts": [{"text": "hi"}]}]
            }
            headers = {"Content-Type": "application/json"}
            
            logger.debug(f"[测试 Gemini] URL: {url}")
            
            response = httpx.post(url, json=body, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            candidates = data.get("candidates", [])
            if candidates and candidates[0].get("content", {}).get("parts"):
                return {
                    "success": True,
                    "message": f"✅ Gemini API 连接成功！",
                    "details": f"模型：{model or 'gemini-2.0-flash'} | 响应时间：{response.elapsed.total_seconds():.2f}s"
                }
            else:
                return {
                    "success": False,
                    "message": "API 响应格式不正确",
                    "details": f"响应：{str(data)[:100]}"
                }
        
        else:
            # OpenAI 兼容格式（默认）
            # URL 构建优化：自动适配不同的 API Base 风格
            if base_url.endswith("/v1"):
                url = f"{base_url}/chat/completions"
            elif "/v1" in base_url:
                if "chat/completions" not in base_url:
                    url = f"{base_url}/chat/completions" if base_url.endswith("/") else f"{base_url}/chat/completions"
                else:
                    url = base_url
            elif "openai.azure.com" in base_url:
                 url = f"{base_url}/chat/completions"
            elif "chat/completions" in base_url:
                url = base_url
            else:
                url = f"{base_url}/v1/chat/completions"

            # 根据 URL 自动选择默认测试模型
            if not model:
                if "openai.com" in base_url:
                    model = "gpt-4o-mini"
                elif "deepseek.com" in base_url:
                    model = "deepseek-chat"
                elif "siliconflow" in base_url:
                    model = "deepseek-ai/DeepSeek-V3"
                elif "openrouter" in base_url:
                    model = "openai/gpt-4o-mini"
                else:
                    model = "gpt-3.5-turbo"
            
            logger.debug(f"[测试 Chat] URL: {url} | Model: {model}")

            body = {
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            response = httpx.post(url, json=body, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            if "choices" in data and len(data["choices"]) > 0:
                return {
                    "success": True,
                    "message": f"✅ API 连接成功！",
                    "details": f"模型：{model or 'default'} | 响应时间：{response.elapsed.total_seconds():.2f}s"
                }
            else:
                return {
                    "success": False,
                    "message": "API 响应格式不正确",
                    "details": f"响应：{str(data)[:100]}"
                }
                
    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        try:
            error_json = json.loads(error_text)
            # 不同 API 的错误格式
            if provider_type == "anthropic":
                error_msg = error_json.get("error", {}).get("message", error_text[:200])
            elif provider_type == "google":
                error_msg = error_json.get("error", {}).get("message", error_text[:200])
            else:
                error_msg = error_json.get("error", {}).get("message", error_text[:200])
        except:
            error_msg = error_text[:200]
        
        # 如果是 400 错误，可能是模型名称不对
        hint = ""
        if e.response.status_code == 400:
            hint = f"\n💡 测试模型: {model} - 请确认该模型名称正确"
        
        return {
            "success": False,
            "message": f"❌ HTTP 错误 {e.response.status_code}",
            "details": f"{error_msg}{hint}"
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "message": "❌ 连接超时",
            "details": "请检查网络连接或 API 地址是否正确"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"❌ 连接失败",
            "details": str(e)
        }


@router.post("/config/fetch-models")
def fetch_models(request: dict) -> dict:
    """获取服务商的可用模型列表
    
    支持 OpenAI 兼容格式、Claude 原生 API、Gemini 原生 API
    """
    base_url = request.get("base_url", "").rstrip("/")
    api_key = request.get("api_key", "")
    provider_type = request.get("provider_type", "openai")
    
    if not base_url or not api_key:
        return {"success": False, "message": "请提供 API Base URL 和 API Key", "models": []}
    
    try:
        models = []
        
        if provider_type == "anthropic":
            # Claude API - 使用固定的模型列表（Anthropic 暂不提供 /models 端点的公开访问）
            # 但可以尝试调用看看
            url = f"{base_url}/models"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            
            try:
                response = httpx.get(url, headers=headers, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    # Anthropic 返回格式: {"data": [{"id": "claude-xxx", ...}]}
                    for model in data.get("data", []):
                        model_id = model.get("id", "")
                        if model_id:
                            models.append({
                                "id": model_id,
                                "name": model_id,
                                "description": model.get("display_name", ""),
                                "context_window": model.get("context_window"),
                            })
            except:
                pass
            
            # 如果 API 获取失败，使用已知的 Claude 模型列表
            if not models:
                models = [
                    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "最新的 Claude 4 模型", "context_window": 200000},
                    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "description": "强大且快速的模型", "context_window": 200000},
                    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "description": "快速且经济的模型", "context_window": 200000},
                    {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "description": "最强大的 Claude 3 模型", "context_window": 200000},
                    {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet", "description": "平衡性能和速度", "context_window": 200000},
                    {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "description": "最快速的模型", "context_window": 200000},
                ]
                
        elif provider_type == "google":
            # Gemini API
            url = f"{base_url}/models?key={api_key}"
            headers = {"Content-Type": "application/json"}
            
            logger.debug(f"[获取模型] Gemini URL: {url}")
            
            response = httpx.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            # Gemini 返回格式: {"models": [{"name": "models/gemini-xxx", "displayName": "...", ...}]}
            for model in data.get("models", []):
                model_name = model.get("name", "")
                # 移除 "models/" 前缀
                model_id = model_name.replace("models/", "") if model_name.startswith("models/") else model_name
                
                # 只保留 generateContent 方法可用的模型
                supported_methods = model.get("supportedGenerationMethods", [])
                if "generateContent" not in supported_methods:
                    continue
                    
                if model_id:
                    models.append({
                        "id": model_id,
                        "name": model.get("displayName", model_id),
                        "description": model.get("description", ""),
                        "context_window": model.get("inputTokenLimit"),
                    })
                    
        else:
            # OpenAI 兼容格式
            # 构建 URL
            if base_url.endswith("/v1"):
                url = f"{base_url}/models"
            elif "/v1" in base_url:
                url = f"{base_url}/models"
            else:
                url = f"{base_url}/v1/models"
                
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"[获取模型] OpenAI 兼容 URL: {url}")
            
            response = httpx.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            # OpenAI 返回格式: {"data": [{"id": "gpt-4", "object": "model", ...}]}
            for model in data.get("data", []):
                model_id = model.get("id", "")
                if model_id:
                    # 过滤掉一些非聊天模型（如 embedding、whisper 等）
                    skip_prefixes = ("text-embedding", "whisper", "tts", "dall-e", "davinci", "babbage", "ada", "curie")
                    if any(model_id.lower().startswith(p) for p in skip_prefixes):
                        continue
                        
                    models.append({
                        "id": model_id,
                        "name": model_id,
                        "description": model.get("owned_by", ""),
                        "context_window": None,
                    })
        
        # 按名称排序
        models.sort(key=lambda m: m.get("name", "").lower())
        
        return {
            "success": True,
            "message": f"获取到 {len(models)} 个模型",
            "models": models
        }
        
    except httpx.HTTPStatusError as e:
        error_text = e.response.text
        try:
            error_json = json.loads(error_text)
            error_msg = error_json.get("error", {}).get("message", error_text[:200])
        except:
            error_msg = error_text[:200]
        
        return {
            "success": False,
            "message": f"HTTP 错误 {e.response.status_code}: {error_msg}",
            "models": []
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "message": "连接超时，请检查网络",
            "models": []
        }
    except Exception as e:
        logger.error(f"[获取模型] 错误: {e}")
        return {
            "success": False,
            "message": f"获取失败: {str(e)}",
            "models": []
        }


@router.post("/niche/compare", response_model=NicheCompareResult)
def compare_niche(request: NicheCompareRequest) -> NicheCompareResult:
    """对比两个物种的生态位（优化版）
    
    三个指标有明确不同的生态学含义：
    - similarity: 特征描述的语义相似程度
    - overlap: 资源利用、栖息地、生态功能的实际重叠
    - competition_intensity: 考虑种群压力和资源稀缺的真实竞争
    """
    import numpy as np
    from ..services.species.niche_compare import compute_niche_metrics
    
    # 获取两个物种
    species_a = species_repository.get_by_lineage(request.species_a)
    species_b = species_repository.get_by_lineage(request.species_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_b} 不存在")
    
    logger.debug(f"[生态位对比] 对比物种: {species_a.common_name} vs {species_b.common_name}")
    
    # 获取embedding相似度（用于相似度计算）
    embedding_similarity = None
    try:
        vectors = embedding_service.embed(
            [species_a.description, species_b.description], 
            require_real=True
        )
        vec_a = np.array(vectors[0], dtype=float)
        vec_b = np.array(vectors[1], dtype=float)
        
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        
        if norm_a > 0 and norm_b > 0:
            embedding_similarity = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
            embedding_similarity = max(0.0, min(1.0, embedding_similarity))
            logger.debug(f"[生态位对比] 使用embedding向量, 相似度={embedding_similarity:.3f}")
    except (RuntimeError, Exception) as e:
        logger.debug(f"[生态位对比] Embedding服务不可用，使用属性计算: {str(e)}")
    
    # 使用新的向量化生态位计算模块
    niche_result = compute_niche_metrics(
        species_a, species_b,
        embedding_similarity=embedding_similarity
    )
    
    similarity = niche_result.similarity
    overlap = niche_result.overlap
    competition_intensity = niche_result.competition
    
    logger.debug(f"[生态位对比] 结果: 相似度={similarity:.1%}, 重叠度={overlap:.1%}, 竞争强度={competition_intensity:.1%}")
    logger.debug(f"[生态位对比] 重叠度分解: {niche_result.details.get('overlap_breakdown', {})}")
    
    # 保留原有变量用于后续逻辑
    pop_a = float(species_a.morphology_stats.get("population", 0) or 0)
    pop_b = float(species_b.morphology_stats.get("population", 0) or 0)
    
    # 提取关键维度对比
    niche_dimensions = {
        "种群数量": {
            "species_a": pop_a,
            "species_b": pop_b
        },
        "体长(cm)": {
            "species_a": float(species_a.morphology_stats.get("body_length_cm", 0)),
            "species_b": float(species_b.morphology_stats.get("body_length_cm", 0))
        },
        "体重(g)": {
            "species_a": float(species_a.morphology_stats.get("body_weight_g", 0)),
            "species_b": float(species_b.morphology_stats.get("body_weight_g", 0))
        },
        "寿命(天)": {
            "species_a": float(species_a.morphology_stats.get("lifespan_days", 0)),
            "species_b": float(species_b.morphology_stats.get("lifespan_days", 0))
        },
        "代谢率": {
            "species_a": float(species_a.morphology_stats.get("metabolic_rate", 0)),
            "species_b": float(species_b.morphology_stats.get("metabolic_rate", 0))
        },
        "繁殖速度": {
            "species_a": float(species_a.abstract_traits.get("繁殖速度", 0)),
            "species_b": float(species_b.abstract_traits.get("繁殖速度", 0))
        },
        "运动能力": {
            "species_a": float(species_a.abstract_traits.get("运动能力", 0)),
            "species_b": float(species_b.abstract_traits.get("运动能力", 0))
        },
        "社会性": {
            "species_a": float(species_a.abstract_traits.get("社会性", 0)),
            "species_b": float(species_b.abstract_traits.get("社会性", 0))
        }
    }
    
    # 添加环境适应性对比
    env_traits = ["耐寒性", "耐热性", "耐旱性", "耐盐性", "光照需求", "氧气需求"]
    for trait in env_traits:
        if trait in species_a.abstract_traits or trait in species_b.abstract_traits:
            niche_dimensions[trait] = {
                "species_a": float(species_a.abstract_traits.get(trait, 0)),
                "species_b": float(species_b.abstract_traits.get(trait, 0))
            }
    
    return NicheCompareResult(
        species_a=SpeciesDetail(
            lineage_code=species_a.lineage_code,
            latin_name=species_a.latin_name,
            common_name=species_a.common_name,
            description=species_a.description,
            morphology_stats=species_a.morphology_stats,
            abstract_traits=species_a.abstract_traits,
            hidden_traits=species_a.hidden_traits,
            status=species_a.status,
            organs=species_a.organs,
            capabilities=species_a.capabilities,
            genus_code=species_a.genus_code,
            taxonomic_rank=species_a.taxonomic_rank,
            trophic_level=species_a.trophic_level,
            hybrid_parent_codes=species_a.hybrid_parent_codes,
            hybrid_fertility=species_a.hybrid_fertility,
            parent_code=species_a.parent_code,
            created_turn=species_a.created_turn,
            dormant_genes=species_a.dormant_genes,
            stress_exposure=species_a.stress_exposure,
        ),
        species_b=SpeciesDetail(
            lineage_code=species_b.lineage_code,
            latin_name=species_b.latin_name,
            common_name=species_b.common_name,
            description=species_b.description,
            morphology_stats=species_b.morphology_stats,
            abstract_traits=species_b.abstract_traits,
            hidden_traits=species_b.hidden_traits,
            status=species_b.status,
            organs=species_b.organs,
            capabilities=species_b.capabilities,
            genus_code=species_b.genus_code,
            taxonomic_rank=species_b.taxonomic_rank,
            trophic_level=species_b.trophic_level,
            hybrid_parent_codes=species_b.hybrid_parent_codes,
            hybrid_fertility=species_b.hybrid_fertility,
            parent_code=species_b.parent_code,
            created_turn=species_b.created_turn,
            dormant_genes=species_b.dormant_genes,
            stress_exposure=species_b.stress_exposure,
        ),
        similarity=similarity,
        overlap=overlap,
        competition_intensity=competition_intensity,
        niche_dimensions=niche_dimensions
    )


@router.get("/species/{code1}/can_hybridize/{code2}", tags=["species"])
def check_hybridization(code1: str, code2: str) -> dict:
    """检查两个物种能否杂交"""
    species_a = species_repository.get_by_code(code1)
    species_b = species_repository.get_by_code(code2)
    
    if not species_a or not species_b:
        raise HTTPException(status_code=404, detail="物种不存在")
    
    genus = genus_repository.get_by_code(species_a.genus_code)
    distance_key = f"{min(code1, code2)}-{max(code1, code2)}"
    genetic_distance = genus.genetic_distances.get(distance_key, 0.5) if genus else 0.5
    
    can_hybrid, fertility = hybridization_service.can_hybridize(species_a, species_b, genetic_distance)
    
    if not can_hybrid:
        if species_a.genus_code != species_b.genus_code:
            reason = "不同属物种无法杂交"
        elif genetic_distance >= 0.5:
            reason = f"遗传距离过大({genetic_distance:.2f})，无法杂交"
        else:
            reason = "不满足杂交条件"
    else:
        reason = f"近缘物种，遗传距离{genetic_distance:.2f}，可杂交"
    
    return {
        "can_hybridize": can_hybrid,
        "fertility": round(fertility, 3),
        "genetic_distance": round(genetic_distance, 3),
        "reason": reason
    }


@router.get("/genus/{code}/relationships", tags=["species"])
def get_genetic_relationships(code: str) -> dict:
    """获取属内遗传关系"""
    genus = genus_repository.get_by_code(code)
    if not genus:
        raise HTTPException(status_code=404, detail="属不存在")
    
    all_species = species_repository.list_species()
    genus_species = [sp for sp in all_species if sp.genus_code == code and sp.status == "alive"]
    
    species_codes = [sp.lineage_code for sp in genus_species]
    
    can_hybridize_pairs = []
    for sp_a in genus_species:
        for sp_b in genus_species:
            if sp_a.lineage_code >= sp_b.lineage_code:
                continue
            
            distance_key = f"{sp_a.lineage_code}-{sp_b.lineage_code}"
            distance = genus.genetic_distances.get(distance_key, 0.5)
            
            if distance < 0.5:
                can_hybridize_pairs.append({
                    "pair": [sp_a.lineage_code, sp_b.lineage_code],
                    "distance": round(distance, 3)
                })
    
    return {
        "genus_code": genus.code,
        "genus_name": genus.name_common,
        "species": species_codes,
        "genetic_distances": {k: round(v, 3) for k, v in genus.genetic_distances.items()},
        "can_hybridize_pairs": can_hybridize_pairs
    }


@router.get("/system/logs")
def get_system_logs(lines: int = 200) -> dict:
    """获取系统日志"""
    log_file = Path(settings.log_dir) / "simulation.log"
    if not log_file.exists():
        return {"logs": []}
    
    try:
        # Read last N lines
        # Simple implementation: read all and slice (assuming log file isn't huge for this demo)
        # For production, use seek/tail approach
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            recent = all_lines[-lines:]
            return {"logs": [line.strip() for line in recent]}
    except Exception as e:
        return {"logs": [], "error": str(e)}


@router.get("/system/ai-diagnostics", tags=["system"])
def get_ai_diagnostics() -> dict:
    """获取 AI 模型调用诊断信息
    
    返回并发状态、超时统计等信息，用于诊断 AI 调用问题。
    """
    diagnostics = model_router.get_diagnostics()
    
    # 添加判断建议
    advice = []
    if diagnostics["active_requests"] >= diagnostics["concurrency_limit"] * 0.8:
        advice.append("⚠️ 并发接近上限，建议增加 concurrency_limit 或减少同时请求数")
    if diagnostics["total_timeouts"] > 0:
        timeout_rate = diagnostics["total_timeouts"] / max(diagnostics["total_requests"], 1)
        if timeout_rate > 0.3:
            advice.append("⚠️ 超时率过高 (>30%)，建议增加 timeout 时间或检查 API 服务状态")
        elif timeout_rate > 0.1:
            advice.append("⚡ 存在一些超时 (10-30%)，可能是 API 响应慢或网络问题")
    if diagnostics["queued_requests"] > 5:
        advice.append("⏳ 有较多请求在排队，可能是并发限制过低")
    
    if not advice:
        advice.append("✅ AI 调用状态正常")
    
    return {
        **diagnostics,
        "advice": advice,
    }


@router.post("/system/ai-diagnostics/reset", tags=["system"])
def reset_ai_diagnostics() -> dict:
    """重置 AI 诊断统计"""
    model_router._active_requests = 0
    model_router._queued_requests = 0
    model_router._total_requests = 0
    model_router._total_timeouts = 0
    model_router._request_stats = {}
    return {"success": True, "message": "诊断统计已重置"}


# ========== 生态系统健康指标 API ==========

# 游戏状态 API
@router.get("/game/state", tags=["game"])
def get_game_state() -> dict:
    """获取当前游戏状态，包含回合数等关键信息
    
    前端刷新页面时应调用此 API 获取正确的回合数。
    
    返回的 turn_index 是 0-based 索引：
    - turn_index = 0 表示准备执行第 0 回合（前端显示"第 1 回合"）
    - turn_index = 1 表示第 0 回合已完成，准备执行第 1 回合（前端显示"第 2 回合"）
    
    返回的 backend_session_id 是后端本次启动的唯一ID：
    - 每次后端重启都会生成新的 session_id
    - 前端可以对比存储的 session_id 来检测后端是否重启
    - 如果 session_id 不匹配，说明后端重启了，前端应回到主菜单
    """
    map_state = environment_repository.get_state()
    
    # 直接使用 turn_counter（在 initialize_environment 中已经恢复过了）
    # turn_counter 表示"下一个要执行的回合索引"
    current_turn = simulation_engine.turn_counter
    
    species_list = species_repository.list_species()
    alive_species = [sp for sp in species_list if sp.status == "alive"]
    
    return {
        "turn_index": current_turn,
        "species_count": len(alive_species),
        "total_species_count": len(species_list),
        "sea_level": map_state.sea_level if map_state else 0.0,
        "global_temperature": map_state.global_avg_temperature if map_state else 15.0,
        "tectonic_stage": map_state.stage_name if map_state else "稳定期",
        "backend_session_id": get_backend_session_id(),  # 用于前端检测后端重启
    }


# 初始化生态健康服务
ecosystem_health_service = EcosystemHealthService()


@router.get("/ecosystem/health", response_model=EcosystemHealthResponse, tags=["ecosystem"])
def get_ecosystem_health() -> EcosystemHealthResponse:
    """获取生态系统健康报告
    
    返回包括：
    - 多样性指数（Shannon、Simpson）
    - 营养级分布
    - 灭绝风险评估
    - 共生网络统计
    - 整体健康评分
    """
    all_species = species_repository.list_species()
    
    # 获取已灭绝物种代码
    extinct_codes = {sp.lineage_code for sp in all_species if sp.status == "extinct"}
    
    # 分析生态系统健康
    report = ecosystem_health_service.analyze(all_species, extinct_codes)
    
    # 转换为响应格式
    return EcosystemHealthResponse(
        shannon_index=report.shannon_index,
        simpson_index=report.simpson_index,
        species_richness=report.species_richness,
        evenness=report.evenness,
        trophic_distribution=[
            TrophicDistributionItem(
                level=td.level,
                species_count=td.species_count,
                total_population=td.total_population,
                total_biomass=td.total_biomass,
                percentage=td.percentage
            ) for td in report.trophic_distribution
        ],
        trophic_balance_score=report.trophic_balance_score,
        extinction_risks=[
            ExtinctionRiskItem(
                lineage_code=er.lineage_code,
                common_name=er.common_name,
                risk_level=er.risk_level,
                risk_score=er.risk_score,
                reasons=er.reasons
            ) for er in report.extinction_risks
        ],
        critical_count=report.critical_count,
        endangered_count=report.endangered_count,
        symbiotic_connections=report.symbiotic_connections,
        network_connectivity=report.network_connectivity,
        overall_health_score=report.overall_health_score,
        health_grade=report.health_grade,
        health_summary=report.health_summary,
    )


# 初始化捕食网服务
predation_service = PredationService()

# 初始化食物网管理服务
from ..services.species.food_web_manager import FoodWebManager
food_web_manager = FoodWebManager(predation_service)


@router.get("/ecosystem/food-web", tags=["ecosystem"])
def get_food_web(
    max_nodes: int = Query(500, ge=1, le=1000, description="最大节点数"),
    max_links: int = Query(2000, ge=1, le=5000, description="最大链接数"),
    offset: int = Query(0, ge=0, description="节点偏移量"),
    trophic_levels: str | None = Query(None, description="营养级过滤，逗号分隔，如 '1,2,3'"),
    detail_level: str = Query("full", description="详细程度: simple, standard, full"),
    include_preferences: bool = Query(True, description="是否包含猎物偏好"),
    sort_by: str = Query("trophic_level", description="排序字段: trophic_level, population, name"),
    use_cache: bool = Query(True, description="是否使用缓存"),
    legacy_format: bool = Query(True, description="使用原有响应格式（向后兼容）"),
):
    """获取真实的食物网数据（支持分页/裁剪）
    
    返回基于物种prey_species字段的真实捕食关系，用于前端可视化。
    
    【性能优化】
    - 支持分页：max_nodes, offset 控制节点数量
    - 支持过滤：trophic_levels 按营养级过滤
    - 支持缓存：use_cache=True 时优先读取缓存
    - legacy_format=True: 返回原有格式（默认，向后兼容）
    """
    # 【向后兼容】默认使用原有的 build_food_web 方法
    if legacy_format:
        all_species = species_repository.list_species()
        return predation_service.build_food_web(all_species)
    
    # 新的缓存+分页模式
    from ..services.species.food_web_cache import get_food_web_cache, FoodWebQueryOptions
    
    cache_service = get_food_web_cache()
    
    # 解析营养级过滤
    levels = None
    if trophic_levels:
        try:
            levels = [int(x.strip()) for x in trophic_levels.split(",")]
        except ValueError:
            levels = None
    
    # 构建查询选项
    options = FoodWebQueryOptions(
        max_nodes=max_nodes,
        max_links=max_links,
        offset=offset,
        trophic_levels=levels,
        detail_level=detail_level,
        include_preferences=include_preferences,
        sort_by=sort_by,
    )
    
    # 尝试使用缓存
    if use_cache and cache_service.is_valid:
        result = cache_service.query(options)
        return {
            "nodes": result.nodes,
            "links": result.links,
            "total_nodes": result.total_nodes,
            "total_links": result.total_links,
            "has_more_nodes": result.has_more_nodes,
            "has_more_links": result.has_more_links,
            "cache_hit": True,
            "cache_age_seconds": round(result.cache_age_seconds, 1),
        }
    
    # 缓存未命中，重建缓存
    all_species = species_repository.list_species()
    cache_service.build_cache(all_species, simulation_engine.turn_counter)
    
    result = cache_service.query(options)
    return {
        "nodes": result.nodes,
        "links": result.links,
        "total_nodes": result.total_nodes,
        "total_links": result.total_links,
        "has_more_nodes": result.has_more_nodes,
        "has_more_links": result.has_more_links,
        "cache_hit": False,
        "cache_age_seconds": 0,
    }


@router.get("/ecosystem/food-web/summary", tags=["ecosystem"])
def get_food_web_summary():
    """获取食物网简版摘要（用于仪表盘，优先读缓存）
    
    返回轻量级的食物网统计，适合频繁刷新的仪表盘。
    """
    from ..services.species.food_web_cache import get_food_web_cache
    
    cache_service = get_food_web_cache()
    return cache_service.get_simple_summary()


@router.get("/ecosystem/food-web/cache-stats", tags=["ecosystem"])
def get_food_web_cache_stats():
    """获取食物网缓存统计（调试用）
    
    返回缓存命中率、内存占用等性能指标。
    """
    from ..services.species.food_web_cache import get_food_web_cache
    from ..services.species.matrix_cache import get_matrix_cache
    
    food_web_cache = get_food_web_cache()
    matrix_cache = get_matrix_cache()
    
    return {
        "food_web_cache": food_web_cache.get_simple_summary(),
        "matrix_cache": matrix_cache.stats,
    }


@router.get("/ecosystem/food-web/analysis", tags=["ecosystem"])
def get_food_web_analysis(
    detail_level: str = Query("full", description="详细程度: simple, full"),
):
    """获取食物网健康状况分析
    
    返回食物网的详细分析结果，包括：
    - health_score: 食物网健康度 (0-1)
    - total_species: 存活物种总数
    - total_links: 捕食关系总数
    - orphaned_consumers: 没有猎物的消费者列表
    - starving_species: 猎物全部灭绝的物种列表
    - keystone_species: 关键物种列表（被3+物种依赖）
    - isolated_species: 既无猎物也无捕食者的物种
    - avg_prey_per_consumer: 每个消费者的平均猎物种类数
    - food_web_density: 食物网连接密度
    - bottleneck_warnings: 瓶颈警告列表
    
    【性能优化】
    - detail_level=simple: 只返回统计数字，不返回物种列表
    """
    all_species = species_repository.list_species()
    analysis = food_web_manager.analyze_food_web(all_species)
    
    if detail_level == "simple":
        return {
            "health_score": analysis.health_score,
            "total_species": analysis.total_species,
            "total_links": analysis.total_links,
            "orphaned_count": len(analysis.orphaned_consumers),
            "starving_count": len(analysis.starving_species),
            "keystone_count": len(analysis.keystone_species),
            "isolated_count": len(analysis.isolated_species),
            "avg_prey_per_consumer": analysis.avg_prey_per_consumer,
            "food_web_density": analysis.food_web_density,
            "warning_count": len(analysis.bottleneck_warnings),
        }
    
    return {
        "health_score": analysis.health_score,
        "total_species": analysis.total_species,
        "total_links": analysis.total_links,
        "orphaned_consumers": analysis.orphaned_consumers,
        "starving_species": analysis.starving_species,
        "keystone_species": analysis.keystone_species,
        "isolated_species": analysis.isolated_species,
        "avg_prey_per_consumer": analysis.avg_prey_per_consumer,
        "food_web_density": analysis.food_web_density,
        "bottleneck_warnings": analysis.bottleneck_warnings,
    }


@router.post("/ecosystem/food-web/repair", tags=["ecosystem"])
def repair_food_web():
    """修复食物网缺陷
    
    自动为缺少猎物的消费者分配猎物，修复食物链断裂问题。
    
    返回：
    - repaired_count: 修复的物种数量
    - changes: 变更详情列表
    """
    all_species = species_repository.list_species()
    
    # 执行修复
    analysis = food_web_manager.maintain_food_web(
        all_species, species_repository, turn_index=0
    )
    changes = food_web_manager.get_changes()
    
    return {
        "repaired_count": len(changes),
        "changes": [
            {
                "species_code": c.species_code,
                "species_name": c.species_name,
                "change_type": c.change_type,
                "details": c.details,
                "old_prey": c.old_prey,
                "new_prey": c.new_prey,
            }
            for c in changes
        ],
        "analysis_after": {
            "health_score": analysis.health_score,
            "orphaned_consumers": len(analysis.orphaned_consumers),
            "starving_species": len(analysis.starving_species),
        }
    }


@router.get("/ecosystem/food-web/{lineage_code}", tags=["ecosystem"])
def get_species_food_chain(lineage_code: str):
    """获取特定物种的食物链
    
    返回该物种的上下游食物关系：
    - prey_chain: 该物种的猎物及猎物的猎物（向下追溯）
    - predator_chain: 捕食该物种的捕食者及其捕食者（向上追溯）
    - food_dependency: 食物依赖满足度 (0-1)
    - predation_pressure: 被捕食压力 (0-1)
    """
    species = species_repository.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    all_species = species_repository.list_species()
    return predation_service.get_species_food_chain(species, all_species)


@router.get("/ecosystem/food-web/{lineage_code}/neighborhood", tags=["ecosystem"])
def get_species_neighborhood(
    lineage_code: str,
    k_hop: int = Query(2, ge=1, le=5, description="邻域跳数 (1-5)"),
    max_nodes: int = Query(50, ge=1, le=200, description="最大节点数"),
    detail_level: str = Query("standard", description="详细程度: simple, standard, full"),
):
    """获取特定物种的 k-hop 邻域（新 API，用于优化的局部视图）
    
    返回：
    - neighborhood: k-hop 邻域内的节点和链接
    - food_chain: 完整的食物链信息
    """
    from ..services.species.food_web_cache import get_food_web_cache, FoodWebQueryOptions
    
    species = species_repository.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    all_species = species_repository.list_species()
    
    # 尝试使用缓存获取邻域
    cache_service = get_food_web_cache()
    
    # 确保缓存已构建
    if not cache_service.is_valid:
        cache_service.build_cache(all_species, simulation_engine.turn_counter)
    
    options = FoodWebQueryOptions(
        max_nodes=max_nodes,
        max_links=max_nodes * 3,
        center_species=lineage_code,
        k_hop=k_hop,
        detail_level=detail_level,
    )
    result = cache_service.query(options)
    
    # 获取完整的食物链信息
    food_chain = predation_service.get_species_food_chain(species, all_species)
    
    return {
        "neighborhood": {
            "nodes": result.nodes,
            "links": result.links,
            "total_nodes": result.total_nodes,
            "total_links": result.total_links,
        },
        "food_chain": food_chain,
        "cache_hit": result.cache_hit,
    }


@router.get("/ecosystem/extinction-impact/{lineage_code}", tags=["ecosystem"])
def analyze_extinction_impact(lineage_code: str):
    """分析物种灭绝的影响
    
    预测如果该物种灭绝会对生态系统造成什么影响：
    - directly_affected: 直接受影响的捕食者（以该物种为食）
    - indirectly_affected: 间接受影响的物种（二级以上）
    - food_chain_collapse_risk: 食物链崩溃风险 (0-1)
    - affected_biomass_percentage: 受影响生物量百分比
    """
    species = species_repository.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    all_species = species_repository.list_species()
    impact = predation_service.analyze_extinction_impact(species, all_species)
    
    return {
        "extinct_species": impact.extinct_species,
        "directly_affected": impact.directly_affected,
        "indirectly_affected": impact.indirectly_affected,
        "food_chain_collapse_risk": impact.food_chain_collapse_risk,
        "affected_biomass_percentage": impact.affected_biomass_percentage,
    }


# ========== 玩家干预 API ==========

@router.post("/intervention/protect", response_model=InterventionResponse, tags=["intervention"])
def protect_species(request: ProtectSpeciesRequest) -> InterventionResponse:
    """保护指定物种
    
    保护效果：
    - 死亡率降低50%
    - 持续指定回合数
    
    消耗能量点。
    """
    species = species_repository.get_by_lineage(request.lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.lineage_code} 不存在")
    
    if species.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {request.lineage_code} 已灭绝，无法保护")
    
    # 【能量系统】检查能量
    current_turn = simulation_engine.turn_counter
    can_afford, cost = energy_service.can_afford("protect")
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！保护物种需要 {cost} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    # 消耗能量
    energy_service.spend("protect", current_turn, details=f"保护 {species.common_name}")
    
    # 设置保护状态
    species.is_protected = True
    species.protection_turns = request.turns
    species_repository.upsert(species)
    
    return InterventionResponse(
        success=True,
        message=f"已对 {species.common_name} ({request.lineage_code}) 实施保护，持续 {request.turns} 回合（消耗 {cost} 能量）",
        species_code=request.lineage_code,
        effect_duration=request.turns
    )


@router.post("/intervention/suppress", response_model=InterventionResponse, tags=["intervention"])
def suppress_species(request: SuppressSpeciesRequest) -> InterventionResponse:
    """压制指定物种
    
    压制效果：
    - 死亡率增加30%
    - 持续指定回合数
    
    消耗能量点。
    """
    species = species_repository.get_by_lineage(request.lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.lineage_code} 不存在")
    
    if species.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {request.lineage_code} 已灭绝，无需压制")
    
    # 【能量系统】检查能量
    current_turn = simulation_engine.turn_counter
    can_afford, cost = energy_service.can_afford("suppress")
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！压制物种需要 {cost} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    # 消耗能量
    energy_service.spend("suppress", current_turn, details=f"压制 {species.common_name}")
    
    # 设置压制状态
    species.is_suppressed = True
    species.suppression_turns = request.turns
    species_repository.upsert(species)
    
    return InterventionResponse(
        success=True,
        message=f"已对 {species.common_name} ({request.lineage_code}) 实施压制，持续 {request.turns} 回合（消耗 {cost} 能量）",
        species_code=request.lineage_code,
        effect_duration=request.turns
    )


@router.post("/intervention/cancel/{lineage_code}", response_model=InterventionResponse, tags=["intervention"])
def cancel_intervention(lineage_code: str) -> InterventionResponse:
    """取消对指定物种的所有干预"""
    species = species_repository.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    # 取消所有干预
    species.is_protected = False
    species.protection_turns = 0
    species.is_suppressed = False
    species.suppression_turns = 0
    species_repository.upsert(species)
    
    return InterventionResponse(
        success=True,
        message=f"已取消对 {species.common_name} ({lineage_code}) 的所有干预",
        species_code=lineage_code,
        effect_duration=0
    )


@router.post("/intervention/introduce", response_model=InterventionResponse, tags=["intervention"])
async def introduce_species(request: IntroduceSpeciesRequest) -> InterventionResponse:
    """引入新物种
    
    通过AI生成新物种并引入到生态系统中。
    """
    try:
        # 生成唯一的lineage_code
        existing_species = species_repository.list_species()
        used_prefixes = {sp.lineage_code[:1] for sp in existing_species}
        
        available_prefixes = [chr(i) for i in range(ord('A'), ord('Z')+1) if chr(i) not in used_prefixes]
        if not available_prefixes:
            # 如果字母用完，使用数字后缀
            max_num = max((int(sp.lineage_code[1:]) for sp in existing_species if sp.lineage_code[1:].isdigit()), default=0)
            new_code = f"X{max_num + 1}"
        else:
            new_code = f"{available_prefixes[0]}1"
        
        # 生成物种
        new_species = species_generator.generate_from_prompt(request.prompt, new_code)
        
        # 设置初始种群
        new_species.morphology_stats["population"] = request.initial_population
        
        # 保存物种
        species_repository.upsert(new_species)
        
        # 初始化栖息地（如果指定了目标区域）
        if request.target_region:
            # 找到目标地块
            tiles = environment_repository.list_tiles()
            target_x, target_y = request.target_region
            target_tile = next((t for t in tiles if t.x == target_x and t.y == target_y), None)
            
            if target_tile:
                # 分配到目标地块（habitat_manager 已在模块级别导入）
                habitat_manager.assign_initial_habitat(new_species, [target_tile], simulation_engine.turn_counter)
        
        return InterventionResponse(
            success=True,
            message=f"成功引入新物种: {new_species.common_name} ({new_code})，初始种群 {request.initial_population:,}",
            species_code=new_code,
            effect_duration=None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"引入物种失败: {str(e)}")


@router.post("/intervention/symbiosis", response_model=InterventionResponse, tags=["intervention"])
def set_symbiosis(request: SetSymbiosisRequest) -> InterventionResponse:
    """设置物种间的共生关系
    
    可以建立互利共生、偏利共生或寄生关系。
    """
    species = species_repository.get_by_lineage(request.species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code} 不存在")
    
    # 验证依赖物种存在
    if request.depends_on:
        all_species = species_repository.list_species()
        all_codes = {sp.lineage_code for sp in all_species}
        invalid_codes = [code for code in request.depends_on if code not in all_codes]
        if invalid_codes:
            raise HTTPException(
                status_code=400, 
                detail=f"以下物种代码不存在: {', '.join(invalid_codes)}"
            )
    
    # 设置共生关系
    species.symbiotic_dependencies = request.depends_on
    species.dependency_strength = request.strength
    species.symbiosis_type = request.symbiosis_type
    species_repository.upsert(species)
    
    if request.depends_on:
        return InterventionResponse(
            success=True,
            message=f"已设置 {species.common_name} 与 {', '.join(request.depends_on)} 的{request.symbiosis_type}关系，依赖强度 {request.strength}",
            species_code=request.species_code,
            effect_duration=None
        )
    else:
        return InterventionResponse(
            success=True,
            message=f"已清除 {species.common_name} 的共生关系",
            species_code=request.species_code,
            effect_duration=None
        )


@router.get("/intervention/status", tags=["intervention"])
def get_intervention_status() -> dict:
    """获取所有干预状态"""
    all_species = species_repository.list_species()
    
    protected = []
    suppressed = []
    symbiotic = []
    
    for sp in all_species:
        if sp.status != "alive":
            continue
        
        is_protected = getattr(sp, 'is_protected', False) or False
        protection_turns = getattr(sp, 'protection_turns', 0) or 0
        is_suppressed = getattr(sp, 'is_suppressed', False) or False
        suppression_turns = getattr(sp, 'suppression_turns', 0) or 0
        dependencies = getattr(sp, 'symbiotic_dependencies', []) or []
        
        if is_protected and protection_turns > 0:
            protected.append({
                "lineage_code": sp.lineage_code,
                "common_name": sp.common_name,
                "remaining_turns": protection_turns
            })
        
        if is_suppressed and suppression_turns > 0:
            suppressed.append({
                "lineage_code": sp.lineage_code,
                "common_name": sp.common_name,
                "remaining_turns": suppression_turns
            })
        
        if dependencies:
            symbiotic.append({
                "lineage_code": sp.lineage_code,
                "common_name": sp.common_name,
                "depends_on": dependencies,
                "strength": getattr(sp, 'dependency_strength', 0.0) or 0.0,
                "type": getattr(sp, 'symbiosis_type', 'none') or 'none'
            })
    
    return {
        "protected_species": protected,
        "suppressed_species": suppressed,
        "symbiotic_relations": symbiotic,
        "total_protected": len(protected),
        "total_suppressed": len(suppressed),
        "total_symbiotic": len(symbiotic)
    }


# ================== 任务中断 API ==================

@router.post("/tasks/abort", tags=["system"])
async def abort_current_tasks() -> dict:
    """重置 AI 连接，解除卡住状态
    
    当 AI 调用卡住时，可以调用此 API：
    - 关闭当前的 HTTP 客户端连接
    - 不清空队列和计数器（让任务自然恢复）
    - 卡住的请求会因连接关闭而抛出异常，然后自动重试或返回
    
    这类似于后端的 shutdown，可以让卡住的任务继续
    """
    from ..main import get_simulation_engine
    
    try:
        engine = get_simulation_engine()
        router = engine.router
        
        # 获取当前诊断信息
        diagnostics_before = router.get_diagnostics()
        
        # 只关闭客户端连接，不清空计数器
        old_client = router._client_session
        router._client_session = None  # 先置空
        
        if old_client and not old_client.is_closed:
            try:
                await old_client.aclose()
                logger.info("[任务恢复] 已关闭旧的 HTTP 客户端连接")
            except Exception as e:
                logger.warning(f"[任务恢复] 关闭连接时出错: {e}")
        
        logger.warning(f"[任务恢复] 连接已重置，活跃请求: {diagnostics_before['active_requests']}，排队: {diagnostics_before['queued_requests']}")
        
        return {
            "success": True,
            "message": "连接已重置，卡住的任务将自动恢复",
            "active_requests": diagnostics_before['active_requests'],
            "queued_requests": diagnostics_before['queued_requests']
        }
    except Exception as e:
        logger.error(f"[任务恢复] 重置失败: {e}")
        return {
            "success": False,
            "message": f"重置失败: {str(e)}"
        }


@router.post("/tasks/skip-ai-step", tags=["system"])
async def skip_current_ai_step() -> dict:
    """跳过当前AI步骤，使用fallback规则
    
    当AI步骤卡住太久时，可以调用此API：
    - 设置跳过标志
    - 强制关闭当前连接
    - 触发超时异常，让代码使用fallback逻辑
    
    这会让当前的AI步骤（如报告生成、物种分化）立即使用规则fallback完成
    """
    from ..main import get_simulation_engine
    
    try:
        engine = get_simulation_engine()
        router = engine.router
        
        # 设置跳过标志（如果引擎支持）
        if hasattr(engine, '_skip_current_ai_step'):
            engine._skip_current_ai_step = True
        
        # 获取诊断信息
        diagnostics = router.get_diagnostics()
        
        # 强制关闭客户端连接，触发超时
        old_client = router._client_session
        router._client_session = None
        
        if old_client and not old_client.is_closed:
            try:
                await old_client.aclose()
                logger.info("[跳过AI] 已关闭HTTP连接，触发fallback")
            except Exception as e:
                logger.warning(f"[跳过AI] 关闭连接时出错: {e}")
        
        # 发送跳过事件通知前端
        push_simulation_event("ai_skip", "⏭️ 已跳过当前AI步骤，使用规则fallback", "系统")
        
        logger.warning(f"[跳过AI] 用户请求跳过，活跃请求: {diagnostics['active_requests']}")
        
        return {
            "success": True,
            "message": "已触发跳过，当前AI步骤将使用fallback完成",
            "active_requests": diagnostics['active_requests'],
            "skipped_at": "current_stage"
        }
    except Exception as e:
        logger.error(f"[跳过AI] 跳过失败: {e}")
        return {
            "success": False,
            "message": f"跳过失败: {str(e)}"
        }


@router.get("/tasks/diagnostics", tags=["system"])
def get_task_diagnostics() -> dict:
    """获取当前 AI 任务的诊断信息
    
    返回：
    - 并发限制
    - 活跃请求数
    - 排队请求数
    - 超时统计
    """
    from ..main import get_simulation_engine
    
    try:
        engine = get_simulation_engine()
        router = engine.router
        return {
            "success": True,
            **router.get_diagnostics()
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ================== 成就系统 API ==================

from ..services.analytics.achievements import AchievementService
from ..services.analytics.game_hints import GameHintsService

# 初始化服务
achievement_service = AchievementService(settings.data_dir)
game_hints_service = GameHintsService(max_hints=5)


@router.get("/achievements", tags=["achievements"])
def get_achievements() -> dict:
    """获取所有成就及其解锁状态
    
    返回：
    - achievements: 成就列表
    - stats: 统计信息
    """
    return {
        "achievements": achievement_service.get_all_achievements(),
        "stats": achievement_service.get_stats(),
    }


@router.get("/achievements/unlocked", tags=["achievements"])
def get_unlocked_achievements() -> dict:
    """获取已解锁的成就"""
    return {
        "achievements": achievement_service.get_unlocked_achievements(),
    }


@router.get("/achievements/pending", tags=["achievements"])
def get_pending_achievement_unlocks() -> dict:
    """获取待通知的成就解锁事件（获取后清空）
    
    用于前端显示成就解锁弹窗。
    """
    events = achievement_service.get_pending_unlocks()
    return {
        "events": [
            {
                "achievement": {
                    "id": e.achievement.id,
                    "name": e.achievement.name,
                    "description": e.achievement.description,
                    "icon": e.achievement.icon,
                    "rarity": e.achievement.rarity.value,
                    "category": e.achievement.category.value,
                },
                "turn_index": e.turn_index,
                "timestamp": e.timestamp,
            }
            for e in events
        ]
    }


@router.post("/achievements/exploration/{feature}", tags=["achievements"])
def record_exploration(feature: str) -> dict:
    """记录玩家探索功能（用于解锁探索者成就）
    
    Args:
        feature: 功能名称 (genealogy, foodweb, niche)
    """
    # 获取当前回合
    current_turn = simulation_engine.turn_counter
    
    event = achievement_service.record_exploration(feature, current_turn)
    if event:
        return {
            "success": True,
            "unlocked": {
                "id": event.achievement.id,
                "name": event.achievement.name,
                "icon": event.achievement.icon,
            }
        }
    return {"success": True, "unlocked": None}


@router.post("/achievements/reset", tags=["achievements"])
def reset_achievements() -> dict:
    """重置所有成就进度（新存档时调用）"""
    achievement_service.reset()
    return {"success": True, "message": "成就进度已重置"}


# ================== 智能提示 API ==================

@router.get("/hints", tags=["hints"])
def get_game_hints() -> dict:
    """获取当前游戏状态的智能提示
    
    返回：
    - hints: 提示列表（按优先级排序）
    """
    all_species = species_repository.list_species()
    current_turn = simulation_engine.turn_counter
    
    # 获取最近的报告
    logs = history_repository.list_turns(limit=2)
    recent_report = None
    previous_report = None
    
    if logs:
        recent_report = TurnReport.model_validate(logs[0].record_data)
        if len(logs) > 1:
            previous_report = TurnReport.model_validate(logs[1].record_data)
    
    hints = game_hints_service.generate_hints(
        all_species=all_species,
        current_turn=current_turn,
        recent_report=recent_report,
        previous_report=previous_report,
    )
    
    return {
        "hints": [h.to_dict() for h in hints],
        "turn": current_turn,
    }


@router.post("/hints/clear", tags=["hints"])
def clear_hints_cooldown() -> dict:
    """清除提示冷却（新存档时调用）"""
    game_hints_service.clear_cooldown()
    return {"success": True, "message": "提示冷却已清除"}


# 在创建存档时重置成就和提示
def _reset_game_services():
    """重置游戏服务状态（创建/加载存档时调用）"""
    achievement_service.reset()
    game_hints_service.clear_cooldown()
    energy_service.reset()


# ================== 能量点系统 API ==================

from ..services.system.divine_energy import DivineEnergyService

# 初始化能量服务
energy_service = DivineEnergyService(settings.data_dir)

# 【关键】将能量服务注入存档管理器，确保能量状态随存档保存/加载
save_manager.set_energy_service(energy_service)


@router.get("/energy", tags=["energy"])
def get_energy_status() -> dict:
    """获取能量状态
    
    返回：
    - enabled: 系统是否启用
    - current: 当前能量
    - maximum: 最大能量
    - regen_per_turn: 每回合回复
    - percentage: 百分比
    """
    return energy_service.get_status()


@router.get("/energy/costs", tags=["energy"])
def get_energy_costs() -> dict:
    """获取所有操作的能量消耗定义"""
    return {
        "costs": energy_service.get_all_costs(),
    }


@router.get("/energy/history", tags=["energy"])
def get_energy_history(limit: int = 20) -> dict:
    """获取能量交易历史"""
    return {
        "history": energy_service.get_history(limit),
    }


@router.post("/energy/calculate", tags=["energy"])
def calculate_energy_cost(request: dict) -> dict:
    """计算操作的能量消耗
    
    Body:
    - action: 操作类型
    - pressures: 压力列表（可选，用于压力消耗计算）
    - intensity: 强度（可选）
    """
    action = request.get("action", "")
    
    if action == "pressure" and "pressures" in request:
        cost = energy_service.get_pressure_cost(request["pressures"])
    else:
        cost = energy_service.get_cost(action, **request)
    
    can_afford, _ = energy_service.can_afford(action, **request)
    
    return {
        "action": action,
        "cost": cost,
        "can_afford": can_afford,
        "current_energy": energy_service.get_state().current,
    }


@router.post("/energy/toggle", tags=["energy"])
def toggle_energy_system(request: dict) -> dict:
    """启用/禁用能量系统
    
    Body:
    - enabled: bool
    """
    energy_service.enabled = request.get("enabled", True)
    return {
        "success": True,
        "enabled": energy_service.enabled,
    }


@router.post("/energy/set", tags=["energy"])
def set_energy(request: dict) -> dict:
    """设置能量参数（GM模式）
    
    Body:
    - current: 当前能量（可选）
    - maximum: 最大能量（可选）
    - regen: 每回合回复（可选）
    """
    energy_service.set_energy(
        current=request.get("current"),
        maximum=request.get("maximum"),
        regen=request.get("regen"),
    )
    return energy_service.get_status()


# ================== 杂交控制 API ==================

@router.get("/hybridization/candidates", tags=["hybridization"])
def get_hybridization_candidates() -> dict:
    """获取可杂交的物种对
    
    返回所有满足杂交条件的物种组合。
    """
    all_species = species_repository.list_species()
    alive_species = [sp for sp in all_species if sp.status == "alive"]
    
    candidates = []
    checked_pairs = set()
    
    for sp1 in alive_species:
        for sp2 in alive_species:
            if sp1.lineage_code >= sp2.lineage_code:
                continue
            
            pair_key = f"{sp1.lineage_code}-{sp2.lineage_code}"
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            
            can_hybrid, fertility = hybridization_service.can_hybridize(sp1, sp2)
            if can_hybrid:
                candidates.append({
                    "species_a": {
                        "lineage_code": sp1.lineage_code,
                        "common_name": sp1.common_name,
                        "latin_name": sp1.latin_name,
                        "genus_code": sp1.genus_code,
                    },
                    "species_b": {
                        "lineage_code": sp2.lineage_code,
                        "common_name": sp2.common_name,
                        "latin_name": sp2.latin_name,
                        "genus_code": sp2.genus_code,
                    },
                    "fertility": round(fertility, 3),
                    "genus": sp1.genus_code,
                })
    
    return {
        "candidates": candidates,
        "total": len(candidates),
    }


@router.post("/hybridization/execute", tags=["hybridization"])
async def execute_hybridization(request: dict) -> dict:
    """执行杂交（使用AI生成杂交物种）
    
    Body:
    - species_a: 物种A的lineage_code
    - species_b: 物种B的lineage_code
    
    消耗能量点。使用LLM生成杂交物种的名称、描述和属性。
    """
    code_a = request.get("species_a", "")
    code_b = request.get("species_b", "")
    
    if not code_a or not code_b:
        raise HTTPException(status_code=400, detail="请提供两个物种代码")
    
    # 获取物种
    species_a = species_repository.get_by_lineage(code_a)
    species_b = species_repository.get_by_lineage(code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {code_b} 不存在")
    
    if species_a.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {code_a} 已灭绝")
    if species_b.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {code_b} 已灭绝")
    
    # 检查杂交可行性
    can_hybrid, fertility = hybridization_service.can_hybridize(species_a, species_b)
    if not can_hybrid:
        raise HTTPException(status_code=400, detail="这两个物种无法杂交")
    
    # 检查能量
    current_turn = simulation_engine.turn_counter
    can_afford, cost = energy_service.can_afford("hybridize")
    if not can_afford:
        raise HTTPException(
            status_code=400, 
            detail=f"能量不足！杂交需要 {cost} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    # 消耗能量
    success, msg = energy_service.spend(
        "hybridize", 
        current_turn,
        details=f"杂交 {species_a.common_name} × {species_b.common_name}"
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    # 收集现有编码（用于杂交种编码生成）
    all_species = species_repository.list_species()
    existing_codes = {sp.lineage_code for sp in all_species}
    
    # 执行杂交（使用异步AI调用）
    hybrid = await hybridization_service.create_hybrid_async(
        species_a, species_b, current_turn, 
        existing_codes=existing_codes
    )
    if not hybrid:
        # 退还能量（杂交失败）
        energy_service.add_energy(cost, "杂交失败退还")
        raise HTTPException(status_code=500, detail="杂交失败")
    
    # 保存杂交种
    species_repository.upsert(hybrid)
    
    # 记录成就
    achievement_service._unlock("hybrid_creator", current_turn)
    
    return {
        "success": True,
        "hybrid": {
            "lineage_code": hybrid.lineage_code,
            "latin_name": hybrid.latin_name,
            "common_name": hybrid.common_name,
            "description": hybrid.description,
            "fertility": hybrid.hybrid_fertility,
            "parent_codes": hybrid.hybrid_parent_codes,
        },
        "energy_spent": cost,
        "energy_remaining": energy_service.get_state().current,
    }


@router.get("/hybridization/preview", tags=["hybridization"])
def preview_hybridization(species_a: str, species_b: str) -> dict:
    """预览杂交结果
    
    不消耗能量，只显示预期结果。
    """
    sp_a = species_repository.get_by_lineage(species_a)
    sp_b = species_repository.get_by_lineage(species_b)
    
    if not sp_a:
        raise HTTPException(status_code=404, detail=f"物种 {species_a} 不存在")
    if not sp_b:
        raise HTTPException(status_code=404, detail=f"物种 {species_b} 不存在")
    
    can_hybrid, fertility = hybridization_service.can_hybridize(sp_a, sp_b)
    
    if not can_hybrid:
        # 分析为什么不能杂交
        if sp_a.genus_code != sp_b.genus_code:
            reason = "不同属的物种无法杂交"
        elif sp_a.lineage_code == sp_b.lineage_code:
            reason = "同一物种无法杂交"
        else:
            distance = genetic_distance_calculator.calculate_distance(sp_a, sp_b)
            reason = f"遗传距离过大 ({distance:.2f} >= 0.5)"
        
        return {
            "can_hybridize": False,
            "reason": reason,
            "fertility": 0,
            "energy_cost": energy_service.get_cost("hybridize"),
        }
    
    # 预览杂交结果
    hybrid_code = f"{sp_a.lineage_code}×{sp_b.lineage_code}"
    hybrid_name = f"{sp_a.common_name}×{sp_b.common_name}杂交种"
    
    # 预测特征
    predicted_trophic = max(sp_a.trophic_level, sp_b.trophic_level)
    combined_capabilities = list(set(sp_a.capabilities + sp_b.capabilities))
    
    return {
        "can_hybridize": True,
        "fertility": round(fertility, 3),
        "energy_cost": energy_service.get_cost("hybridize"),
        "can_afford": energy_service.can_afford("hybridize")[0],
        "preview": {
            "lineage_code": hybrid_code,
            "common_name": hybrid_name,
            "predicted_trophic_level": predicted_trophic,
            "combined_capabilities": combined_capabilities,
            "parent_traits_merged": True,
        },
    }


# ==================== 强行杂交（跨属/幻想杂交）API ====================

FORCED_HYBRIDIZATION_COST = 50  # 强行杂交消耗的能量（普通杂交的5倍）


@router.get("/hybridization/force/preview", tags=["hybridization"])
def preview_forced_hybridization(species_a: str, species_b: str) -> dict:
    """预览强行杂交结果
    
    强行杂交可以跨越正常杂交限制，将任意两个物种融合成嵌合体。
    - 消耗能量：50点（普通杂交的5倍）
    - 产物：嵌合体（Chimera）
    - 可育性：极低或不育
    - 风险：基因不稳定
    """
    sp_a = species_repository.get_by_lineage(species_a)
    sp_b = species_repository.get_by_lineage(species_b)
    
    if not sp_a:
        raise HTTPException(status_code=404, detail=f"物种 {species_a} 不存在")
    if not sp_b:
        raise HTTPException(status_code=404, detail=f"物种 {species_b} 不存在")
    
    # 检查是否可以强行杂交
    can_force, reason = hybridization_service.can_force_hybridize(sp_a, sp_b)
    
    # 检查是否可以正常杂交
    can_normal, normal_fertility = hybridization_service.can_hybridize(sp_a, sp_b)
    
    # 预估嵌合体特征
    trophic_diff = abs(sp_a.trophic_level - sp_b.trophic_level)
    estimated_fertility = max(0.0, 0.15 - trophic_diff * 0.03)
    if sp_a.genus_code != sp_b.genus_code:
        estimated_fertility *= 0.3
    
    # 稳定性预估
    if sp_a.genus_code == sp_b.genus_code:
        stability = "unstable"
    elif trophic_diff <= 1.0:
        stability = "unstable"
    else:
        stability = "volatile"
    
    return {
        "can_force_hybridize": can_force,
        "reason": reason,
        "can_normal_hybridize": can_normal,
        "normal_fertility": round(normal_fertility, 3) if can_normal else 0,
        "energy_cost": FORCED_HYBRIDIZATION_COST,
        "can_afford": energy_service.get_state().current >= FORCED_HYBRIDIZATION_COST,
        "current_energy": energy_service.get_state().current,
        "preview": {
            "type": "chimera",
            "estimated_fertility": round(estimated_fertility, 3),
            "stability": stability,
            "parent_a": {
                "code": sp_a.lineage_code,
                "name": sp_a.common_name,
                "trophic": sp_a.trophic_level,
            },
            "parent_b": {
                "code": sp_b.lineage_code,
                "name": sp_b.common_name,
                "trophic": sp_b.trophic_level,
            },
            "warnings": [
                "嵌合体通常不育或极低可育性",
                "基因不稳定可能导致寿命缩短",
                "可能出现意想不到的能力或缺陷",
            ] if can_force else [],
        },
    }


@router.post("/hybridization/force/execute", tags=["hybridization"])
async def execute_forced_hybridization(request: dict) -> dict:
    """执行强行杂交（创造嵌合体）
    
    Body:
    - species_a: 物种A的lineage_code
    - species_b: 物种B的lineage_code
    
    消耗50能量点，将任意两个物种强行融合成嵌合体（Chimera）。
    
    ⚠️ 警告：
    - 嵌合体通常不育或极低可育性
    - 基因不稳定可能导致意外变异
    - 这是违背自然规律的实验
    """
    code_a = request.get("species_a", "")
    code_b = request.get("species_b", "")
    
    if not code_a or not code_b:
        raise HTTPException(status_code=400, detail="请提供两个物种代码")
    
    # 获取物种
    species_a = species_repository.get_by_lineage(code_a)
    species_b = species_repository.get_by_lineage(code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {code_b} 不存在")
    
    # 检查是否可以强行杂交
    can_force, reason = hybridization_service.can_force_hybridize(species_a, species_b)
    if not can_force:
        raise HTTPException(status_code=400, detail=reason)
    
    # 获取当前回合
    current_turn = simulation_engine.turn_counter
    
    # 使用 energy_service.spend() 方法消耗能量
    success, message = energy_service.spend(
        action="forced_hybridize",
        turn=current_turn,
        details=f"强行杂交 {species_a.common_name} × {species_b.common_name}"
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # 收集现有编码
    all_species = species_repository.list_species()
    existing_codes = {sp.lineage_code for sp in all_species}
    
    # 执行强行杂交
    chimera = await hybridization_service.force_hybridize_async(
        species_a, species_b, current_turn, existing_codes
    )
    
    if not chimera:
        # 退还能量 - 直接添加回去
        energy_service.add_energy(FORCED_HYBRIDIZATION_COST, "强行杂交失败，能量退还")
        raise HTTPException(status_code=500, detail="强行杂交实验失败")
    
    # 保存嵌合体
    species_repository.upsert(chimera)
    
    # 记录成就
    achievement_service._unlock("chimera_creator", current_turn)
    achievement_service._unlock("mad_scientist", current_turn)
    
    return {
        "success": True,
        "chimera": {
            "lineage_code": chimera.lineage_code,
            "latin_name": chimera.latin_name,
            "common_name": chimera.common_name,
            "description": chimera.description,
            "fertility": chimera.hybrid_fertility,
            "parent_codes": chimera.hybrid_parent_codes,
            "taxonomic_rank": chimera.taxonomic_rank,
            "stability": chimera.hidden_traits.get("genetic_stability", 0.5),
        },
        "energy_spent": FORCED_HYBRIDIZATION_COST,
        "energy_remaining": energy_service.get_state().current,
        "warnings": [
            f"嵌合体可育性仅为 {chimera.hybrid_fertility:.1%}",
            "基因不稳定可能导致后代变异或寿命缩短",
        ],
    }


# ==================== 神力进阶系统 API ====================

from ..services.system.divine_progression import (
    DivinePath,
    DIVINE_SKILLS,
    MIRACLES,
    WagerType,
    WAGER_TYPES,
)
# divine_progression_service 已在文件顶部导入

# 【关键】将神力进阶服务注入存档管理器
save_manager.set_progression_service(divine_progression_service)


@router.get("/divine/status", tags=["divine"])
def get_divine_status() -> dict:
    """获取神力进阶系统完整状态
    
    包括：神格、信仰、神迹、预言四大子系统。
    """
    return divine_progression_service.get_full_status()


@router.get("/divine/paths", tags=["divine"])
def get_available_paths() -> dict:
    """获取可选择的神格路线"""
    return {
        "paths": divine_progression_service.get_available_paths(),
        "current_path": divine_progression_service.get_path_info(),
    }


@router.post("/divine/path/choose", tags=["divine"])
def choose_divine_path(request: dict) -> dict:
    """选择神格路线
    
    Body:
    - path: 神格路线 (creator/guardian/chaos/ecology)
    
    注意：主神格选择后不可更改，4级后可选副神格。
    """
    path_str = request.get("path", "")
    logger.info(f"[神格] 收到选择请求: {path_str}")
    
    try:
        path = DivinePath(path_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知的神格路线: {path_str}")
    
    if path == DivinePath.NONE:
        raise HTTPException(status_code=400, detail="请选择一个有效的神格")
    
    success, message = divine_progression_service.choose_path(path)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    logger.info(f"[神格] 选择成功: {path.value}, 解锁技能: {divine_progression_service.get_state().path_progress.unlocked_skills}")
    
    return {
        "success": True,
        "message": message,
        "path_info": divine_progression_service.get_path_info(),
    }


@router.get("/divine/skills", tags=["divine"])
def get_divine_skills() -> dict:
    """获取所有神力技能信息"""
    path_info = divine_progression_service.get_path_info()
    current_path = path_info["path"] if path_info else None
    
    all_skills = []
    for skill_id, skill in DIVINE_SKILLS.items():
        info = divine_progression_service.get_skill_info(skill_id)
        info["is_current_path"] = skill.path.value == current_path
        all_skills.append(info)
    
    return {
        "skills": all_skills,
        "current_path": current_path,
    }


@router.post("/divine/skill/use", tags=["divine"])
async def use_divine_skill(request: dict) -> dict:
    """使用神力技能
    
    Body:
    - skill_id: 技能ID
    - target: 目标（物种代码或坐标，取决于技能）
    """
    skill_id = request.get("skill_id", "")
    target = request.get("target")
    
    logger.info(f"[技能] 尝试使用: {skill_id}, 目标: {target}")
    
    if skill_id not in DIVINE_SKILLS:
        raise HTTPException(status_code=400, detail=f"未知的技能: {skill_id}")
    
    skill = DIVINE_SKILLS[skill_id]
    skill_info = divine_progression_service.get_skill_info(skill_id)
    
    # 检查是否已选择神格
    path_info = divine_progression_service.get_path_info()
    if not path_info:
        raise HTTPException(status_code=400, detail="请先选择一个神格路线")
    
    if not skill_info["unlocked"]:
        raise HTTPException(status_code=400, detail=f"技能「{skill.name}」尚未解锁（需要等级 {skill.unlock_level}）")
    
    # 检查能量
    current_turn = simulation_engine.turn_counter
    can_afford, cost = energy_service.can_afford("pressure", intensity=skill.cost // 3)
    actual_cost = skill.cost
    
    if energy_service.get_state().current < actual_cost:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！{skill.name}需要 {actual_cost} 能量"
        )
    
    # 消耗能量
    success, msg = energy_service.spend_fixed(actual_cost, current_turn, details=f"技能: {skill.name}")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    logger.info(f"[技能] 消耗能量成功: {actual_cost}, 技能: {skill.name}")
    
    # 增加经验
    divine_progression_service.add_experience(actual_cost)
    
    # 记录技能使用
    state = divine_progression_service.get_state()
    state.path_progress.skills_used[skill_id] = state.path_progress.skills_used.get(skill_id, 0) + 1
    state.total_skills_used += 1
    
    # 执行技能效果（根据技能类型）
    result = {"effect": "executed", "details": f"技能「{skill.name}」已释放"}
    
    # 特定技能的额外效果
    if skill_id == "ancestor_blessing" and target:
        species = species_repository.get_by_lineage(target)
        if species:
            species.can_open_lineage = True
            species_repository.upsert(species)
            result["details"] = f"已赐予「{species.common_name}」始祖标记"
    
    elif skill_id == "life_shelter" and target:
        species = species_repository.get_by_lineage(target)
        if species:
            species.is_protected = True
            species.protection_turns = 999  # 永久保护（一次性）
            species_repository.upsert(species)
            result["details"] = f"「{species.common_name}」获得生命庇护"
    
    elif skill_id == "mass_extinction":
        all_species = species_repository.list_species()
        culled = 0
        
        def calculate_fitness(sp):
            """计算物种适应度（0-1范围）"""
            traits = sp.abstract_traits or {}
            adaptability = traits.get("适应性", 5) / 10.0
            morph = sp.morphology_stats or {}
            morph_avg = sum(morph.values()) / max(1, len(morph)) if morph else 0.5
            return (adaptability + morph_avg) / 2
        
        for sp in all_species:
            if sp.status == "alive":
                fitness = calculate_fitness(sp)
                if fitness < 0.25:
                    sp.status = "extinct"
                    sp.extinction_turn = current_turn
                    sp.extinction_cause = "divine_judgement"
                    species_repository.upsert(sp)
                    culled += 1
        result["details"] = f"大灭绝清除了 {culled} 个低适应力物种"
    
    elif skill_id == "life_spark":
        # 生命火种：使用AI创造一个基础生产者物种
        try:
            # 自动生成lineage_code
            existing_species = species_repository.get_all()
            used_codes = {s.lineage_code for s in existing_species}
            prefix = "P"  # Plant prefix
            index = 1
            while f"{prefix}{index}" in used_codes:
                index += 1
            new_code = f"{prefix}{index}"
            
            # 使用AI生成物种
            new_species = species_generator.generate_advanced(
                prompt="一种能够在当前环境中自给自足的基础光合生物，作为生态系统的初级生产者",
                lineage_code=new_code,
                existing_species=existing_species,
                is_plant=True,
                diet_type="autotroph",
            )
            species_repository.upsert(new_species)
            result["details"] = f"生命火种诞生了「{new_species.common_name}」({new_code})"
            result["new_species"] = {
                "lineage_code": new_species.lineage_code,
                "common_name": new_species.common_name,
                "latin_name": new_species.latin_name,
            }
        except Exception as e:
            logger.error(f"[生命火种] 创造物种失败: {e}")
            result["details"] = f"生命火种创造失败: {str(e)}"
            result["error"] = True
    
    elif skill_id == "revival_light":
        # 复苏之光：复活最近灭绝的物种
        all_species = species_repository.list_species()
        extinct_species = [
            sp for sp in all_species 
            if sp.status == "extinct" and sp.extinction_turn is not None
        ]
        
        if not extinct_species:
            result["details"] = "没有可复活的已灭绝物种"
            result["error"] = True
        else:
            # 找到最近灭绝的物种
            extinct_species.sort(key=lambda x: x.extinction_turn or 0, reverse=True)
            target = extinct_species[0]
            
            # 获取灭绝前的种群快照
            from ..models.species import PopulationSnapshot
            from ..core.database import session_scope
            
            last_population = 100000  # 默认值
            try:
                with session_scope() as session:
                    # 查找该物种灭绝前最后一个种群快照
                    snapshots = session.exec(
                        select(PopulationSnapshot)
                        .where(PopulationSnapshot.species_id == target.id)
                        .order_by(PopulationSnapshot.turn_index.desc())
                    ).all()
                    if snapshots:
                        # 取最后一个快照的种群总数
                        total_pop = sum(s.count for s in snapshots if s.turn_index == snapshots[0].turn_index)
                        if total_pop > 0:
                            last_population = total_pop
            except Exception as e:
                logger.warning(f"[复苏之光] 获取种群快照失败: {e}")
            
            # 恢复物种
            target.status = "alive"
            target.extinction_turn = None
            target.extinction_cause = None
            # 设置初始种群为灭绝前的50%（存储在 morphology_stats 中）
            restored_population = max(1000, int(last_population * 0.5))
            if not target.morphology_stats:
                target.morphology_stats = {}
            target.morphology_stats["population"] = restored_population
            # 记录历史
            if not target.history_highlights:
                target.history_highlights = []
            target.history_highlights.append(f"回合{current_turn}: 被复苏之光复活")
            species_repository.upsert(target)
            
            result["details"] = f"复苏之光复活了「{target.common_name}」，种群恢复至 {restored_population:,}"
            result["revived_species"] = {
                "lineage_code": target.lineage_code,
                "common_name": target.common_name,
                "restored_population": restored_population,
            }
    
    elif skill_id == "divine_speciation":
        # 神启分化：强制物种立即产生分化
        if not target:
            result["details"] = "请指定目标物种"
            result["error"] = True
        else:
            species = species_repository.get_by_lineage(target)
            if not species:
                result["details"] = f"物种 {target} 不存在"
                result["error"] = True
            elif species.status != "alive":
                result["details"] = f"物种 {target} 已灭绝，无法分化"
                result["error"] = True
            else:
                try:
                    # 生成分化后代
                    existing_species = species_repository.get_all()
                    used_codes = {s.lineage_code for s in existing_species}
                    
                    # 生成子代编码
                    base = species.lineage_code
                    suffix = 1
                    while f"{base}.{suffix}" in used_codes:
                        suffix += 1
                    child_code = f"{base}.{suffix}"
                    
                    child = species_generator.generate_advanced(
                        prompt=f"从「{species.common_name}」分化出的适应性变种，保留部分祖先特征但有明显差异",
                        lineage_code=child_code,
                        existing_species=existing_species,
                        parent_code=species.lineage_code,
                        habitat_type=species.habitat_type,
                    )
                    species_repository.upsert(child)
                    result["details"] = f"「{species.common_name}」分化出新物种「{child.common_name}」"
                    result["new_species"] = {
                        "lineage_code": child.lineage_code,
                        "common_name": child.common_name,
                        "parent_code": species.lineage_code,
                    }
                except Exception as e:
                    logger.error(f"[神启分化] 失败: {e}")
                    result["details"] = f"分化失败: {str(e)}"
                    result["error"] = True
    
    elif skill_id == "chaos_mutation":
        # 混沌突变：随机大幅改变物种特征
        if not target:
            result["details"] = "请指定目标物种"
            result["error"] = True
        else:
            species = species_repository.get_by_lineage(target)
            if not species:
                result["details"] = f"物种 {target} 不存在"
                result["error"] = True
            elif species.status != "alive":
                result["details"] = f"物种 {target} 已灭绝"
                result["error"] = True
            else:
                import random
                # 随机修改形态特征
                mutations = []
                for trait, value in species.morphology_stats.items():
                    if random.random() < 0.5:  # 50%概率改变每个特征
                        change = random.uniform(-0.3, 0.3)
                        new_value = max(0.1, min(1.0, value + change))
                        species.morphology_stats[trait] = round(new_value, 3)
                        mutations.append(f"{trait}: {value:.2f}→{new_value:.2f}")
                
                # 可能改变食性
                if random.random() < 0.2:
                    new_diet = random.choice(["herbivore", "carnivore", "omnivore", "detritivore"])
                    if new_diet != species.diet_type:
                        mutations.append(f"食性: {species.diet_type}→{new_diet}")
                        species.diet_type = new_diet
                
                species_repository.upsert(species)
                result["details"] = f"混沌突变改变了「{species.common_name}」的 {len(mutations)} 个特征"
                result["mutations"] = mutations[:5]  # 只返回前5个
    
    return {
        "success": True,
        "skill": skill.name,
        "cost": actual_cost,
        "result": result,
        "energy_remaining": energy_service.get_state().current,
    }


# ========== 信仰系统 API ==========

@router.get("/divine/faith", tags=["divine"])
def get_faith_status() -> dict:
    """获取信仰系统状态"""
    return divine_progression_service.get_faith_summary()


@router.post("/divine/faith/add", tags=["divine"])
def add_follower(request: dict) -> dict:
    """添加信徒
    
    Body:
    - lineage_code: 物种代码
    """
    lineage_code = request.get("lineage_code", "")
    logger.info(f"[信仰] 尝试添加信徒: {lineage_code}")
    
    if not lineage_code:
        raise HTTPException(status_code=400, detail="请提供物种代码")
    
    species = species_repository.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    if species.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {lineage_code} 已灭绝")
    
    # 从 morphology_stats 获取种群
    morph = species.morphology_stats or {}
    population = morph.get("population", 100000)
    trophic = species.trophic_level or 1
    
    success = divine_progression_service.add_follower(
        lineage_code, species.common_name, population, trophic
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="该物种已是信徒")
    
    logger.info(f"[信仰] 添加信徒成功: {species.common_name}")
    return {
        "success": True,
        "message": f"「{species.common_name}」已成为信徒",
        "faith_summary": divine_progression_service.get_faith_summary(),
    }


@router.post("/divine/faith/bless", tags=["divine"])
def bless_follower(request: dict) -> dict:
    """显圣 - 赐福信徒
    
    Body:
    - lineage_code: 信徒物种代码
    
    消耗20能量，使信徒获得神眷标记。
    """
    lineage_code = request.get("lineage_code", "")
    
    # 检查能量
    current_turn = simulation_engine.turn_counter
    cost = 20
    if energy_service.get_state().current < cost:
        raise HTTPException(status_code=400, detail=f"能量不足！显圣需要 {cost} 能量")
    
    success, message = divine_progression_service.bless_follower(lineage_code)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # 消耗能量
    success, msg = energy_service.spend_fixed(cost, current_turn, details=f"显圣: {lineage_code}")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    # 应用效果到物种：提升抽象特征
    species = species_repository.get_by_lineage(lineage_code)
    if species and species.abstract_traits:
        for trait in species.abstract_traits:
            species.abstract_traits[trait] = min(10.0, species.abstract_traits[trait] * 1.1)
        if not species.history_highlights:
            species.history_highlights = []
        species.history_highlights.append(f"获得神眷祝福，适应能力提升")
        species_repository.upsert(species)
    
    return {
        "success": True,
        "message": message,
        "energy_spent": cost,
        "faith_summary": divine_progression_service.get_faith_summary(),
    }


@router.post("/divine/faith/sanctify", tags=["divine"])
def sanctify_follower(request: dict) -> dict:
    """圣化 - 将信徒提升为圣物种
    
    Body:
    - lineage_code: 信徒物种代码
    
    消耗40能量，使信徒成为圣物种，永久免疫压制。
    """
    lineage_code = request.get("lineage_code", "")
    
    # 检查能量
    current_turn = simulation_engine.turn_counter
    cost = 40
    if energy_service.get_state().current < cost:
        raise HTTPException(status_code=400, detail=f"能量不足！圣化需要 {cost} 能量")
    
    success, message = divine_progression_service.sanctify_follower(lineage_code)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # 消耗能量
    success, msg = energy_service.spend_fixed(cost, current_turn, details=f"圣化: {lineage_code}")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    # 应用效果到物种
    species = species_repository.get_by_lineage(lineage_code)
    if species:
        species.is_protected = True
        species.protection_turns = 999
        species_repository.upsert(species)
    
    return {
        "success": True,
        "message": message,
        "energy_spent": cost,
        "faith_summary": divine_progression_service.get_faith_summary(),
    }


# ========== 神迹系统 API ==========

@router.get("/divine/miracles", tags=["divine"])
def get_miracles() -> dict:
    """获取所有神迹信息"""
    return {
        "miracles": divine_progression_service.get_all_miracles(),
        "charging": divine_progression_service.get_state().miracle_state.charging,
    }


@router.post("/divine/miracle/charge", tags=["divine"])
def start_miracle_charge(request: dict) -> dict:
    """开始蓄力神迹
    
    Body:
    - miracle_id: 神迹ID
    
    神迹需要蓄力多回合，蓄力期间能量被锁定。
    """
    miracle_id = request.get("miracle_id", "")
    
    if miracle_id not in MIRACLES:
        raise HTTPException(status_code=400, detail=f"未知的神迹: {miracle_id}")
    
    miracle = MIRACLES[miracle_id]
    
    # 检查能量
    if energy_service.get_state().current < miracle.cost:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！「{miracle.name}」需要 {miracle.cost} 能量"
        )
    
    success, message, cost = divine_progression_service.start_miracle_charge(miracle_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # 锁定能量（实际扣除）
    current_turn = simulation_engine.turn_counter
    energy_service.spend("pressure", current_turn, details=f"神迹蓄力: {miracle.name}", intensity=cost // 3)
    
    return {
        "success": True,
        "message": message,
        "miracle": divine_progression_service.get_miracle_info(miracle_id),
        "energy_locked": cost,
    }


@router.post("/divine/miracle/cancel", tags=["divine"])
def cancel_miracle_charge() -> dict:
    """取消蓄力神迹
    
    取消蓄力返还80%能量。
    """
    success, refund = divine_progression_service.cancel_miracle_charge()
    if not success:
        raise HTTPException(status_code=400, detail="没有正在蓄力的神迹")
    
    # 返还能量
    energy_service.add_energy(refund, "取消神迹蓄力")
    
    return {
        "success": True,
        "message": f"已取消蓄力，返还 {refund} 能量",
        "energy_refunded": refund,
        "current_energy": energy_service.get_state().current,
    }


@router.post("/divine/miracle/execute", tags=["divine"])
async def execute_miracle(request: dict) -> dict:
    """手动触发神迹
    
    Body:
    - miracle_id: 神迹ID
    - target: 目标（某些神迹需要）
    """
    miracle_id = request.get("miracle_id", "")
    target = request.get("target")
    
    logger.info(f"[神迹] 尝试释放: {miracle_id}")
    
    if miracle_id not in MIRACLES:
        raise HTTPException(status_code=400, detail=f"未知的神迹: {miracle_id}")
    
    miracle = MIRACLES[miracle_id]
    miracle_info = divine_progression_service.get_miracle_info(miracle_id)
    
    # 检查一次性神迹是否已使用
    if miracle.one_time and miracle_id in divine_progression_service.get_state().miracle_state.used_one_time:
        raise HTTPException(status_code=400, detail=f"「{miracle.name}」是一次性神迹，已使用过")
    
    # 检查冷却
    if miracle_info["current_cooldown"] > 0:
        raise HTTPException(
            status_code=400,
            detail=f"神迹冷却中，剩余 {miracle_info['current_cooldown']} 回合"
        )
    
    # 检查能量
    current_turn = simulation_engine.turn_counter
    if energy_service.get_state().current < miracle.cost:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！「{miracle.name}」需要 {miracle.cost} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    # 消耗能量
    success, msg = energy_service.spend_fixed(miracle.cost, current_turn, details=f"神迹: {miracle.name}")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    logger.info(f"[神迹] 消耗能量成功: {miracle.cost}, 神迹: {miracle.name}")
    
    # 设置冷却
    state = divine_progression_service.get_state()
    state.miracle_state.cooldowns[miracle_id] = miracle.cooldown
    state.miracle_state.miracles_cast += 1
    
    if miracle.one_time:
        state.miracle_state.used_one_time.append(miracle_id)
    
    # 执行神迹效果
    result = {"effect": "executed", "details": f"神迹「{miracle.name}」已释放"}
    
    if miracle_id == "tree_of_life":
        # 随机选择3个物种产生分化
        all_species = species_repository.list_species()
        alive = [sp for sp in all_species if sp.status == "alive"]
        import random
        selected = random.sample(alive, min(3, len(alive)))
        result["details"] = f"生命之树触发，{len(selected)} 个物种即将分化"
        result["affected_species"] = [sp.lineage_code for sp in selected]
    
    elif miracle_id == "judgement_day":
        # 清除低适应力物种（基于 abstract_traits 的适应性评估）
        all_species = species_repository.list_species()
        culled = 0
        survivors = []
        
        def calculate_fitness(sp):
            """计算物种适应度（0-1范围）"""
            traits = sp.abstract_traits or {}
            adaptability = traits.get("适应性", 5) / 10.0
            morph = sp.morphology_stats or {}
            morph_avg = sum(morph.values()) / max(1, len(morph)) if morph else 0.5
            return (adaptability + morph_avg) / 2
        
        for sp in all_species:
            if sp.status == "alive":
                fitness = calculate_fitness(sp)
                if fitness < 0.25:
                    sp.status = "extinct"
                    sp.extinction_turn = current_turn
                    sp.extinction_cause = "divine_judgement"
                    species_repository.upsert(sp)
                    culled += 1
                else:
                    # 存活者获得加成：提升抽象特征
                    if sp.abstract_traits:
                        for trait in sp.abstract_traits:
                            sp.abstract_traits[trait] = min(10.0, sp.abstract_traits[trait] * 1.05)
                    survivors.append(sp.lineage_code)
                    species_repository.upsert(sp)
        result["details"] = f"末日审判清除了 {culled} 个物种，{len(survivors)} 个物种获得神恩"
    
    elif miracle_id == "great_prosperity":
        # 大繁荣：提升所有物种的抽象特征（0-10范围）
        all_species = species_repository.list_species()
        boosted = 0
        for sp in all_species:
            if sp.status == "alive":
                # 提升抽象特征（适应性、繁殖速度等，0-10范围）
                if sp.abstract_traits:
                    for trait in sp.abstract_traits:
                        sp.abstract_traits[trait] = min(10.0, sp.abstract_traits[trait] * 1.1)
                # 标记为受到大繁荣祝福
                if not sp.history_highlights:
                    sp.history_highlights = []
                sp.history_highlights.append(f"回合{current_turn}: 获得大繁荣祝福，适应能力提升")
                species_repository.upsert(sp)
                boosted += 1
        result["details"] = f"大繁荣降临，{boosted} 个物种获得祝福，适应能力提升10%"
    
    elif miracle_id == "divine_sanctuary":
        # 神圣避难所：保护所有存活物种10回合
        all_species = species_repository.list_species()
        protected = 0
        for sp in all_species:
            if sp.status == "alive":
                sp.is_protected = True
                sp.protection_turns = max(sp.protection_turns or 0, 10)
                species_repository.upsert(sp)
                protected += 1
        result["details"] = f"神圣避难所庇护了 {protected} 个物种，持续10回合"
    
    elif miracle_id == "genesis_flood":
        # 创世洪水：海岸物种受冲击，降低抽象特征
        all_species = species_repository.list_species()
        affected = 0
        for sp in all_species:
            if sp.status == "alive" and sp.habitat_type in ("coastal", "marine", "freshwater"):
                # 海洋/水生物种受影响：降低抽象特征（适应性等）
                if sp.abstract_traits:
                    for trait in sp.abstract_traits:
                        sp.abstract_traits[trait] = max(1.0, sp.abstract_traits[trait] * 0.9)
                # 记录历史
                if not sp.history_highlights:
                    sp.history_highlights = []
                sp.history_highlights.append(f"回合{current_turn}: 遭受创世洪水冲击")
                affected += 1
                species_repository.upsert(sp)
        result["details"] = f"创世洪水重塑海岸，{affected} 个水生物种受到冲击"
    
    elif miracle_id == "miracle_evolution":
        # 奇迹进化：AI生成超常规物种
        if not target:
            result["details"] = "奇迹进化需要指定目标物种"
            result["error"] = True
        else:
            species = species_repository.get_by_lineage(target)
            if not species:
                result["details"] = f"目标物种 {target} 不存在"
                result["error"] = True
            else:
                try:
                    existing_species = species_repository.get_all()
                    used_codes = {s.lineage_code for s in existing_species}
                    suffix = 1
                    while f"{species.lineage_code}.M{suffix}" in used_codes:
                        suffix += 1
                    miracle_code = f"{species.lineage_code}.M{suffix}"
                    
                    miracle_species = species_generator.generate_advanced(
                        prompt=f"从「{species.common_name}」产生的奇迹进化体，拥有超越常理的能力和独特形态",
                        lineage_code=miracle_code,
                        existing_species=existing_species,
                        parent_code=species.lineage_code,
                    )
                    species_repository.upsert(miracle_species)
                    result["details"] = f"奇迹进化诞生了「{miracle_species.common_name}」！"
                    result["new_species"] = {
                        "lineage_code": miracle_species.lineage_code,
                        "common_name": miracle_species.common_name,
                    }
                except Exception as e:
                    logger.error(f"[奇迹进化] 失败: {e}")
                    result["details"] = f"奇迹进化失败: {str(e)}"
                    result["error"] = True
    
    logger.info(f"[神迹] 释放成功: {miracle.name}, 结果: {result['details']}")
    
    return {
        "success": True,
        "miracle": miracle.name,
        "cost": miracle.cost,
        "result": result,
        "cooldown": miracle.cooldown,
        "energy_remaining": energy_service.get_state().current,
    }


# ========== 预言赌注系统 API ==========

@router.get("/divine/wagers", tags=["divine"])
def get_wagers() -> dict:
    """获取预言赌注系统状态"""
    return divine_progression_service.get_wager_summary()


@router.post("/divine/wager/place", tags=["divine"])
def place_wager(request: dict) -> dict:
    """下注预言
    
    Body:
    - wager_type: 预言类型 (dominance/extinction/expansion/evolution/duel)
    - target_species: 目标物种代码
    - bet_amount: 下注金额
    - secondary_species: 第二物种（对决预言需要）
    - predicted_outcome: 预测结果（对决预言需要，填写预测获胜者）
    """
    logger.info(f"[预言] 收到下注请求: {request}")
    wager_type_str = request.get("wager_type", "")
    target_species = request.get("target_species", "")
    bet_amount = request.get("bet_amount", 0)
    secondary_species = request.get("secondary_species")
    predicted_outcome = request.get("predicted_outcome", "")
    
    try:
        wager_type = WagerType(wager_type_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"未知的预言类型: {wager_type_str}")
    
    # 验证物种存在
    species = species_repository.get_by_lineage(target_species)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {target_species} 不存在")
    
    if species.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {target_species} 已灭绝")
    
    # 对决预言需要第二物种
    if wager_type == WagerType.DUEL:
        if not secondary_species:
            raise HTTPException(status_code=400, detail="对决预言需要指定第二物种")
        sp2 = species_repository.get_by_lineage(secondary_species)
        if not sp2:
            raise HTTPException(status_code=404, detail=f"物种 {secondary_species} 不存在")
        if sp2.status != "alive":
            raise HTTPException(status_code=400, detail=f"物种 {secondary_species} 已灭绝")
    
    # 检查能量
    if energy_service.get_state().current < bet_amount:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！下注 {bet_amount} 能量，当前只有 {energy_service.get_state().current}"
        )
    
    # 记录初始状态（从 morphology_stats 获取种群，计算适应度）
    morph = species.morphology_stats or {}
    traits = species.abstract_traits or {}
    calculated_fitness = (traits.get("适应性", 5) / 10.0 + sum(morph.values()) / max(1, len(morph))) / 2 if morph else 0.5
    
    initial_state = {
        "population": morph.get("population", 10000),
        "fitness": calculated_fitness,
        "regions": len(species.regions) if hasattr(species, 'regions') and species.regions else 1,
    }
    
    current_turn = simulation_engine.turn_counter
    
    success, message, wager_id = divine_progression_service.place_wager(
        wager_type=wager_type,
        target_species=target_species,
        bet_amount=bet_amount,
        current_turn=current_turn,
        secondary_species=secondary_species,
        predicted_outcome=predicted_outcome,
        initial_state=initial_state,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    # 消耗能量
    success2, msg2 = energy_service.spend_fixed(bet_amount, current_turn, details=f"预言下注: {WAGER_TYPES[wager_type].name}")
    if not success2:
        raise HTTPException(status_code=400, detail=msg2)
    
    logger.info(f"[预言] 下注成功: {bet_amount} 能量, 目标: {target_species}")
    
    return {
        "success": True,
        "message": message,
        "wager_id": wager_id,
        "wager_type": WAGER_TYPES[wager_type].name,
        "potential_return": int(bet_amount * WAGER_TYPES[wager_type].multiplier),
        "energy_bet": bet_amount,
        "energy_remaining": energy_service.get_state().current,
    }


@router.post("/divine/wager/check", tags=["divine"])
def check_wager(request: dict) -> dict:
    """检查预言结果
    
    Body:
    - wager_id: 预言ID
    
    手动触发预言结算（通常在回合处理时自动检查）。
    """
    wager_id = request.get("wager_id", "")
    
    state = divine_progression_service.get_state()
    if wager_id not in state.wager_state.active_wagers:
        raise HTTPException(status_code=404, detail=f"预言 {wager_id} 不存在或已结算")
    
    wager = state.wager_state.active_wagers[wager_id]
    current_turn = simulation_engine.turn_counter
    
    # 检查是否到期
    if current_turn < wager.end_turn:
        remaining = wager.end_turn - current_turn
        return {
            "status": "in_progress",
            "message": f"预言进行中，剩余 {remaining} 回合",
            "wager": wager.to_dict(),
        }
    
    # 判断结果
    species = species_repository.get_by_lineage(wager.target_species)
    success = False
    reason = ""
    
    wager_type = wager.wager_type
    
    if wager_type == WagerType.EXTINCTION:
        # 灭绝预言
        success = species is None or species.status != "alive"
        reason = "物种已灭绝" if success else "物种仍存活"
    
    elif wager_type == WagerType.DOMINANCE:
        # 霸主预言 - 检查是否是同生态位最大种群
        if species and species.status == "alive":
            all_species = species_repository.list_species()
            same_niche = [sp for sp in all_species 
                         if sp.status == "alive" 
                         and sp.trophic_level == species.trophic_level]
            # 从 morphology_stats 获取种群
            def get_pop(sp):
                return (sp.morphology_stats or {}).get("population", 0)
            max_pop = max(get_pop(sp) for sp in same_niche) if same_niche else 0
            success = get_pop(species) >= max_pop
            reason = "已成为霸主" if success else "未能成为霸主"
        else:
            reason = "物种已灭绝"
    
    elif wager_type == WagerType.EXPANSION:
        # 扩张预言
        if species and species.status == "alive":
            initial_regions = wager.initial_state.get("regions", 1)
            current_regions = len(species.regions) if species.regions else 1
            new_regions = current_regions - initial_regions
            success = new_regions >= 3
            reason = f"扩展了 {new_regions} 个区域" if success else f"只扩展了 {new_regions} 个区域"
        else:
            reason = "物种已灭绝"
    
    elif wager_type == WagerType.EVOLUTION:
        # 演化预言 - 检查是否有后代
        all_species = species_repository.list_species()
        descendants = [sp for sp in all_species 
                       if sp.parent_code == wager.target_species 
                       and sp.born_turn and sp.born_turn > wager.start_turn]
        success = len(descendants) > 0
        reason = f"产生了 {len(descendants)} 个后代" if success else "未产生后代"
    
    elif wager_type == WagerType.DUEL:
        # 对决预言
        sp1 = species
        sp2 = species_repository.get_by_lineage(wager.secondary_species) if wager.secondary_species else None
        
        sp1_alive = sp1 and sp1.status == "alive"
        sp2_alive = sp2 and sp2.status == "alive"
        
        def get_pop(sp):
            return (sp.morphology_stats or {}).get("population", 0) if sp else 0
        
        if sp1_alive and not sp2_alive:
            winner = wager.target_species
        elif sp2_alive and not sp1_alive:
            winner = wager.secondary_species
        elif sp1_alive and sp2_alive:
            # 都存活，比较种群
            if get_pop(sp1) > get_pop(sp2):
                winner = wager.target_species
            else:
                winner = wager.secondary_species
        else:
            winner = None
        
        success = winner == wager.predicted_outcome
        reason = f"胜者: {winner}" if winner else "双方都灭绝"
    
    # 结算
    reward = divine_progression_service.resolve_wager(wager_id, success)
    
    if reward > 0:
        energy_service.add_energy(reward, f"预言成功: {WAGER_TYPES[wager_type].name}")
    
    return {
        "status": "resolved",
        "success": success,
        "reason": reason,
        "reward": reward,
        "current_energy": energy_service.get_state().current,
        "wager_summary": divine_progression_service.get_wager_summary(),
    }