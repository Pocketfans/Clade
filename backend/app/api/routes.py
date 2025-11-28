from __future__ import annotations

import logging
from pathlib import Path
import uuid
import json
import httpx
import asyncio
from queue import Queue

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
from fastapi.responses import StreamingResponse
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
from ..services.analytics.focus_processor import FocusBatchProcessor
from ..services.geo.map_evolution import MapEvolutionService
from ..services.geo.map_manager import MapStateManager
from ..services.species.migration import MigrationAdvisor
from ..services.species.reproduction import ReproductionService
from ..services.species.habitat_manager import habitat_manager
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

router = APIRouter(prefix="", tags=["simulation"])

settings = get_settings()
environment_system = EnvironmentSystem(settings.map_width, settings.map_height)
mortality_engine = MortalityEngine(settings.batch_rule_limit)
embedding_service = EmbeddingService(settings.embedding_provider)
model_router = ModelRouter(
    {
        "turn_report": ModelConfig(provider="local", model="template-narrator"),
        "focus_batch": ModelConfig(
            provider="local", 
            model="focus-template",
            extra_body={"response_format": {"type": "json_object"}}  # 强制JSON数组
        ),
        "critical_detail": ModelConfig(provider="local", model="critical-template"),
        "speciation": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}  # 强制JSON
        ),
        "speciation_batch": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}  # 强制JSON
        ),
        "reemergence": ModelConfig(provider="local", model="reemergence-template"),
        "pressure_escalation": ModelConfig(provider="local", model="pressure-template"),
        "migration": ModelConfig(provider="local", model="migration-template"),
        "species_generation": ModelConfig(
            provider="openai", 
            model=settings.species_gen_model,
            extra_body={"response_format": {"type": "json_object"}}  # 强制JSON
        ),
        "pressure_adaptation": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,  # 使用与分化相同的模型
            extra_body={"response_format": {"type": "json_object"}}  # 强制JSON
        ),
        "narrative": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}  # 强制JSON
        ),
        # 【新增】综合状态评估（合并了压力评估+紧急响应）
        "species_status_eval": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,
            extra_body={"response_format": {"type": "json_object"}}
        ),
        # 【新增】物种叙事（合并了Critical+Focus增润）
        "species_narrative": ModelConfig(
            provider="openai", 
            model=settings.speciation_model,  # 使用与分化相同的模型
            extra_body={"response_format": {"type": "json_object"}}
        ),
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
genetic_distance_calculator = GeneticDistanceCalculator()
hybridization_service = HybridizationService(genetic_distance_calculator)
gene_flow_service = GeneFlowService()
save_manager = SaveManager(settings.saves_dir, embedding_service=embedding_service)
species_generator = SpeciesGenerator(model_router)
ui_config_path = Path(settings.ui_config_path)
pressure_templates: list[PressureTemplate] = [
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
    
    # 2.2 应用 Capability Routes
    for capability, route_config in config.capability_routes.items():
        if capability not in model_router.routes:
            continue
            
        provider = config.providers.get(route_config.provider_id)
        active_provider = provider or default_provider
        
        if active_provider:
            # 构建 extra_body
            extra_body = None
            if route_config.enable_thinking:
                extra_body = {
                    "enable_thinking": True,
                    "thinking_budget": 4096 # 默认 budget
                }

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
                "extra_body": extra_body
            }
            logger.debug(f"[配置] 已设置 {capability} -> Provider: {active_provider.name}, Model: {route_config.model}, Thinking: {route_config.enable_thinking}")

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
                    "extra_body": current_config.extra_body
                }
                logger.debug(f"[配置] 自动应用默认服务商到 {cap_name}: {default_provider.name} (Model: {model_to_use})")

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
_backend_session_id: str = ""


def set_backend_session_id(session_id: str) -> None:
    """设置后端会话ID（由 main.py 在启动时调用）"""
    global _backend_session_id
    _backend_session_id = session_id


def get_backend_session_id() -> str:
    """获取后端会话ID"""
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
async def run_turns(command: TurnCommand):
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
        
        # 【能量系统】回合开始前恢复能量
        current_turn = simulation_engine.turn_counter
        regen = energy_service.regenerate(current_turn)
        if regen > 0:
            push_simulation_event("energy", f"⚡ 神力恢复 +{regen}", "系统")
        
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
        
        reports = await simulation_engine.run_turns_async(command)
        
        elapsed = time_module.time() - start_time
        logger.info(f"[推演完成] 生成了 {len(reports)} 个报告, 耗时 {elapsed:.1f}秒")
        
        # 【诊断日志】记录响应数据量，帮助排查卡顿问题
        if reports:
            total_species = sum(len(r.species) for r in reports)
            logger.info(f"[响应准备] 返回 {len(reports)} 个报告, 共 {total_species} 个物种快照")
        
        # 【关键】先发送完成事件，让前端知道推演已完成
        push_simulation_event("complete", f"推演完成！生成了 {len(reports)} 个报告", "系统")
        push_simulation_event("turn_complete", f"回合推演完成", "系统")
        
        action_queue["running"] = False
        action_queue["queued_rounds"] = max(action_queue["queued_rounds"] - command.rounds, 0)
        simulation_running = False
        
        # 【关键修复】使用线程池执行自动保存，避免阻塞事件循环
        latest_turn = reports[-1].turn_index if reports else 0
        
        def do_autosave():
            """在后台线程执行自动保存"""
            try:
                _perform_autosave(latest_turn)
            except Exception as e:
                logger.warning(f"[后台任务] 自动保存失败: {e}")
        
        # 启动后台线程任务（不等待完成）
        asyncio.get_event_loop().run_in_executor(None, do_autosave)
        
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


@router.get("/lineage", response_model=LineageTree)
def get_lineage_tree() -> LineageTree:
    nodes: list[LineageNode] = []
    all_species = species_repository.list_species()
    all_genera = genus_repository.list_all()
    
    genus_distances = {}
    for genus in all_genera:
        genus_distances[genus.code] = genus.genetic_distances
    
    descendant_map: dict[str, int] = {}
    for species in all_species:
        if species.parent_code:
            descendant_map[species.parent_code] = descendant_map.get(species.parent_code, 0) + 1
    
    # 获取所有物种的最新人口快照
    from ..repositories.species_repository import session_scope
    from ..models.species import PopulationSnapshot
    from sqlmodel import select, func
    
    for species in all_species:
        # 获取该物种的峰值人口和当前人口
        with session_scope() as session:
            # 当前人口 (最新回合)
            latest_pop_query = (
                select(PopulationSnapshot)
                .where(PopulationSnapshot.species_id == species.id)
                .order_by(PopulationSnapshot.turn_index.desc())
                .limit(1)
            )
            latest_pop = session.exec(latest_pop_query).first()
            current_pop = latest_pop.count if latest_pop else 0
            
            # 峰值人口
            peak_query = select(func.max(PopulationSnapshot.count)).where(
                PopulationSnapshot.species_id == species.id
            )
            peak_pop = session.exec(peak_query).first() or 0
        
        # 推断生态角色
        desc_lower = species.description.lower()
        if any(kw in desc_lower for kw in ["植物", "藻类", "光合", "生产者", "plant", "algae"]):
            ecological_role = "producer"
        elif any(kw in desc_lower for kw in ["食草", "herbivore", "草食"]):
            ecological_role = "herbivore"
        elif any(kw in desc_lower for kw in ["食肉", "carnivore", "捕食"]):
            ecological_role = "carnivore"
        elif any(kw in desc_lower for kw in ["杂食", "omnivore"]):
            ecological_role = "omnivore"
        else:
            ecological_role = "unknown"
        
        # 推断tier
        tier = "background" if species.is_background else None
        
        # 推断灭绝回合
        extinction_turn = None
        if species.status == "extinct":
            with session_scope() as session:
                last_turn_query = (
                    select(PopulationSnapshot.turn_index)
                    .where(PopulationSnapshot.species_id == species.id)
                    .order_by(PopulationSnapshot.turn_index.desc())
                    .limit(1)
                )
                last_turn = session.exec(last_turn_query).first()
                extinction_turn = last_turn if last_turn else 0
        
        genetic_distances_to_siblings = {}
        if species.genus_code and species.genus_code in genus_distances:
            for key, distance in genus_distances[species.genus_code].items():
                if species.lineage_code in key:
                    other_code = key.replace(f"{species.lineage_code}-", "").replace(f"-{species.lineage_code}", "")
                    if other_code != species.lineage_code:
                        genetic_distances_to_siblings[other_code] = distance
        
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
    return LineageTree(nodes=nodes)


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
    limit_tiles: int = 6000, 
    limit_habitats: int = 500,
    view_mode: str = "terrain",
    species_code: str | None = None,
) -> MapOverview:
    try:
        logger.debug(f"[地图查询] 请求地块数: {limit_tiles}, 栖息地数: {limit_habitats}, 视图模式: {view_mode}, 物种: {species_code}")
        
        species_id = None
        if species_code:
            species = species_repository.get_by_lineage(species_code)
            if species:
                species_id = species.id
        
        overview = map_manager.get_overview(
            tile_limit=limit_tiles, 
            habitat_limit=limit_habitats,
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
        # 推断生态角色
        desc_lower = species.description.lower()
        if any(kw in desc_lower for kw in ["植物", "藻类", "光合", "生产者", "plant", "algae"]):
            ecological_role = "producer"
        elif any(kw in desc_lower for kw in ["食草", "herbivore", "草食"]):
            ecological_role = "herbivore"
        elif any(kw in desc_lower for kw in ["食肉", "carnivore", "捕食"]):
            ecological_role = "carnivore"
        elif any(kw in desc_lower for kw in ["杂食", "omnivore"]):
            ecological_role = "omnivore"
        else:
            ecological_role = "unknown"
        
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
                
                # 推断生态角色
                desc_lower = species.description.lower()
                if any(kw in desc_lower for kw in ["植物", "藻类", "光合", "生产者", "plant", "algae"]):
                    ecological_role = "producer"
                elif any(kw in desc_lower for kw in ["食草", "herbivore", "草食"]):
                    ecological_role = "herbivore"
                elif any(kw in desc_lower for kw in ["食肉", "carnivore", "捕食"]):
                    ecological_role = "carnivore"
                elif any(kw in desc_lower for kw in ["杂食", "omnivore"]):
                    ecological_role = "omnivore"
                else:
                    ecological_role = "unknown"
                
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
                    ecological_role=ecological_role
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


@router.post("/config/test-api")
def test_api_connection(request: dict) -> dict:
    """测试 API 连接是否有效"""
    
    api_type = request.get("type", "chat")  # chat 或 embedding
    base_url = request.get("base_url", "").rstrip("/")
    api_key = request.get("api_key", "")
    model = request.get("model", "")
    # provider = request.get("provider", "") # 可选，用于更精细的逻辑
    
    if not base_url or not api_key:
        return {"success": False, "message": "请提供 API Base URL 和 API Key"}
    
    try:
        if api_type == "embedding":
            # 测试 embedding API
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
        else:
            # 测试 chat API
            # URL 构建优化：自动适配不同的 API Base 风格
            if base_url.endswith("/v1"):
                # 标准 OpenAI 兼容格式，直接加 /chat/completions
                url = f"{base_url}/chat/completions"
            elif "/v1" in base_url:
                # URL 中已包含 /v1/，直接加 chat/completions
                if "chat/completions" not in base_url:
                    url = f"{base_url}/chat/completions" if base_url.endswith("/") else f"{base_url}/chat/completions"
                else:
                    url = base_url
            elif "openai.azure.com" in base_url:
                 # Azure 特殊处理
                 url = f"{base_url}/chat/completions"
            elif "chat/completions" in base_url:
                # URL 已包含完整路径
                url = base_url
            else:
                # 用户可能漏掉了 /v1，自动补全
                # 例如：https://api.deepseek.com -> https://api.deepseek.com/v1/chat/completions
                url = f"{base_url}/v1/chat/completions"

            logger.debug(f"[测试 Chat] URL: {url} | Model: {model}")

            body = {
                "model": model or "Pro/deepseek-ai/DeepSeek-V3.2-Exp",
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
            error_msg = error_json.get("error", {}).get("message", error_text[:200])
        except:
            error_msg = error_text[:200]
        
        return {
            "success": False,
            "message": f"❌ HTTP 错误 {e.response.status_code}",
            "details": error_msg
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


@router.get("/ecosystem/food-web", tags=["ecosystem"])
def get_food_web():
    """获取真实的食物网数据
    
    返回基于物种prey_species字段的真实捕食关系，用于前端可视化。
    
    返回格式：
    {
        "nodes": [
            {
                "id": "A1",
                "name": "物种名称",
                "trophic_level": 2.0,
                "population": 1000,
                "diet_type": "herbivore",
                "habitat_type": "marine",
                "prey_count": 2,
                "predator_count": 3
            }
        ],
        "links": [
            {
                "source": "A1",  // 猎物
                "target": "B1",  // 捕食者
                "value": 0.7,    // 偏好比例
                "predator_name": "捕食者名称",
                "prey_name": "猎物名称"
            }
        ],
        "keystone_species": ["A1", "A2"],  // 关键物种
        "trophic_levels": {1: ["A1"], 2: ["B1", "B2"]},
        "total_species": 10,
        "total_links": 15
    }
    """
    all_species = species_repository.list_species()
    return predation_service.build_food_web(all_species)


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
def execute_hybridization(request: dict) -> dict:
    """执行杂交
    
    Body:
    - species_a: 物种A的lineage_code
    - species_b: 物种B的lineage_code
    
    消耗能量点。
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
    
    # 执行杂交
    hybrid = hybridization_service.create_hybrid(species_a, species_b, current_turn)
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