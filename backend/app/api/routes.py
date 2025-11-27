from __future__ import annotations

from pathlib import Path
import uuid
import json
import httpx
import asyncio
from queue import Queue

from fastapi import APIRouter, HTTPException
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
from ..ai.model_router import ModelConfig, ModelRouter
from ..services.species.niche import NicheAnalyzer
from ..services.system.pressure import PressureEscalationService
from ..services.analytics.report_builder import ReportBuilder
from ..services.species.speciation import SpeciationService
from ..services.species.tiering import SpeciesTieringService, TieringConfig
from ..services.system.save_manager import SaveManager
from ..services.species.species_generator import SpeciesGenerator
from ..services.analytics.ecosystem_health import EcosystemHealthService
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
report_builder = ReportBuilder(model_router)
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
map_manager = MapStateManager(settings.map_width, settings.map_height)
reproduction_service = ReproductionService(
    global_carrying_capacity=settings.global_carrying_capacity,  # 从配置读取
    turn_years=500_000,  # 每回合50万年
)
adaptation_service = AdaptationService(model_router)
genetic_distance_calculator = GeneticDistanceCalculator()
hybridization_service = HybridizationService(genetic_distance_calculator)
gene_flow_service = GeneFlowService()
save_manager = SaveManager(settings.saves_dir)
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
        print("[配置] 检测到旧版配置，正在迁移到多服务商结构...")
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
            print(f"[配置] 已设置 {capability} -> Provider: {active_provider.name}, Model: {route_config.model}, Thinking: {route_config.enable_thinking}")

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
                print(f"[配置] 自动应用默认服务商到 {cap_name}: {default_provider.name} (Model: {model_to_use})")

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
        embedding_service.provider = config.embedding_provider or settings.embedding_provider
        embedding_service.api_base_url = config.embedding_base_url
        embedding_service.api_key = config.embedding_api_key
        embedding_service.model = config.embedding_model
        embedding_service.enabled = True
    else:
        embedding_service.enabled = False

    return config


ui_config = apply_ui_config(environment_repository.load_ui_config(ui_config_path))
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
)
watchlist: set[str] = set()
action_queue = {"queued_rounds": 0, "running": False}


def initialize_environment() -> None:
    """启动时的环境初始化：确保数据库结构完整，恢复回合计数器"""
    try:
        print("[环境初始化] 开始检查数据库结构...")
        # 确保数据库列完整
        environment_repository.ensure_map_state_columns()
        environment_repository.ensure_tile_columns()
        
        # 检查地图是否存在（但不自动生成）
        tiles = environment_repository.list_tiles(limit=10)
        if len(tiles) > 0:
            print(f"[环境初始化] 发现现有地图，地块数量: {len(tiles)}")
            print(f"[环境初始化] 示例地块: x={tiles[0].x}, y={tiles[0].y}, biome={tiles[0].biome}")
        else:
            print(f"[环境初始化] 未发现地图数据，等待创建存档时生成")
        
        # 【关键修复】恢复回合计数器：优先从 MapState，其次从历史记录
        try:
            # 方法1：从 MapState 恢复（最可靠）
            map_state = environment_repository.get_state()
            if map_state and map_state.turn_index > 0:
                simulation_engine.turn_counter = map_state.turn_index + 1
                print(f"[环境初始化] 从 MapState 恢复回合计数器: {simulation_engine.turn_counter}")
            else:
                # 方法2：从历史记录恢复
                logs = history_repository.list_turns(limit=1)
                if logs:
                    last_turn = logs[0].turn_index
                    simulation_engine.turn_counter = last_turn + 1  # 下一个回合
                    print(f"[环境初始化] 从历史记录恢复回合计数器: {simulation_engine.turn_counter}")
                else:
                    print(f"[环境初始化] 未发现历史记录，回合计数器保持为 0")
        except Exception as e:
            print(f"[环境初始化] 恢复回合计数器失败: {e}")
            
    except Exception as e:
        print(f"[环境初始化错误] {str(e)}")
        import traceback
        print(traceback.format_exc())


def push_simulation_event(event_type: str, message: str, category: str = "其他"):
    """推送演化事件到前端"""
    global simulation_events, simulation_running
    if simulation_running:
        try:
            simulation_events.put({
                "type": event_type,
                "message": message,
                "category": category,
                "timestamp": __import__("time").time()
            })
        except Exception as e:
            print(f"[事件推送错误] {str(e)}")


@router.get("/events/stream")
async def stream_simulation_events():
    """Server-Sent Events 端点，实时推送演化事件"""
    async def event_generator():
        global simulation_events
        
        # 发送连接确认
        yield f"data: {json.dumps({'type': 'connected', 'message': '已连接到事件流'})}\n\n"
        
        while True:
            try:
                # 检查是否有新事件（非阻塞）
                if not simulation_events.empty():
                    event = simulation_events.get_nowait()
                    yield f"data: {json.dumps(event)}\n\n"
                else:
                    # 发送心跳保持连接
                    yield f": heartbeat\n\n"
                    await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[SSE错误] {str(e)}")
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


@router.post("/turns/run", response_model=list[TurnReport])
async def run_turns(command: TurnCommand) -> list[TurnReport]:
    import traceback
    global simulation_running
    try:
        print(f"[推演开始] 回合数: {command.rounds}, 压力数: {len(command.pressures)}")
        
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
        print(f"[推演执行] 应用压力: {[p.kind for p in pressures]}")
        
        push_simulation_event("pressure", f"应用压力: {', '.join([p.kind for p in pressures]) if pressures else '自然演化'}", "环境")
        
        # 将推送函数传递给引擎
        simulation_engine._event_callback = push_simulation_event
        
        reports = await simulation_engine.run_turns_async(command)
        print(f"[推演完成] 生成了 {len(reports)} 个报告")
        
        push_simulation_event("complete", f"推演完成！生成了 {len(reports)} 个报告", "系统")
        
        action_queue["running"] = False
        action_queue["queued_rounds"] = max(action_queue["queued_rounds"] - command.rounds, 0)
        simulation_running = False
        
        return reports
    except Exception as e:
        action_queue["running"] = False
        simulation_running = False
        print(f"[推演错误] {str(e)}")
        print(traceback.format_exc())
        push_simulation_event("error", f"推演失败: {str(e)}", "错误")
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
        print(f"[地图查询] 请求地块数: {limit_tiles}, 栖息地数: {limit_habitats}, 视图模式: {view_mode}, 物种: {species_code}")
        
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
        print(f"[地图查询] 返回地块数: {len(overview.tiles)}, 栖息地数: {len(overview.habitats)}")
        return overview
    except Exception as e:
        print(f"[地图查询错误] {str(e)}")
        import traceback
        print(traceback.format_exc())
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
        
        population = int(species.morphology_stats.get("population", 0) or 0)
        
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
        print(f"[存档API] 查询到 {len(saves)} 个存档")
        return saves
    except Exception as e:
        print(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"列出存档失败: {str(e)}")


@router.post("/saves/create")
async def create_save(request: CreateSaveRequest) -> dict:
    """创建新存档"""
    try:
        print(f"[存档API] 创建存档: {request.save_name}, 剧本: {request.scenario}")
        
        # 【关键修复】重置回合计数器
        simulation_engine.turn_counter = 0
        print(f"[存档API] 回合计数器已重置为 0")
        
        # 1. 清空当前数据库（确保新存档从干净状态开始）
        print(f"[存档API] 清空当前数据...")
        from ..core.database import session_scope
        from ..models.species import Species
        from ..models.environment import MapTile, MapState, HabitatPopulation
        from ..models.history import TurnLog
        
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
        
        print(f"[存档API] 数据清空完成")
        
        # 2. 初始化地图
        print(f"[存档API] 初始化地图，种子: {request.map_seed if request.map_seed else '随机'}")
        map_manager.ensure_initialized(map_seed=request.map_seed)
        
        # 3. 初始化物种
        if request.scenario == "空白剧本" and request.species_prompts:
            print(f"[存档API] 空白剧本，生成 {len(request.species_prompts)} 个物种")
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
                print(f"[存档API] 生成物种: {species.lineage_code} - {species.common_name}")
        else:
            # 原初大陆：使用默认物种
            print(f"[存档API] 原初大陆，加载默认物种...")
            from ..core.seed import seed_defaults
            seed_defaults()
        
        # 3.5 初始化物种栖息地分布（关键！）
        print(f"[存档API] 初始化物种栖息地分布...")
        all_species = species_repository.list_species()
        if all_species:
            map_manager.snapshot_habitats(all_species, turn_index=0, force_recalculate=True)
            print(f"[存档API] 栖息地分布初始化完成，{len(all_species)} 个物种已分布到地图")
        else:
            print(f"[存档API警告] 没有物种需要分布")
        
        # 3.6 创建初始人口快照（修复bug：系谱树需要这个数据）
        print(f"[存档API] 创建初始人口快照...")
        from ..models.species import PopulationSnapshot
        if all_species:
            snapshots = []
            for species in all_species:
                population = int(species.morphology_stats.get("population", 0) or 0)
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
                print(f"[存档API] 初始人口快照创建完成，{len(snapshots)} 条记录")
        
        # 3.7 创建初始回合报告（修复bug：前端需要显示物种数量）
        print(f"[存档API] 创建初始回合报告...")
        if all_species:
            from ..schemas.responses import SpeciesSnapshot
            initial_species = []
            # 计算总人口用于计算population_share
            total_population = sum(int(sp.morphology_stats.get("population", 0) or 0) for sp in all_species)
            for species in all_species:
                population = int(species.morphology_stats.get("population", 0) or 0)
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
            print(f"[存档API] 初始回合报告创建完成")
        
        # 4. 创建存档元数据
        metadata = save_manager.create_save(request.save_name, request.scenario)
        
        # 5. 立即保存游戏状态到存档文件
        print(f"[存档API] 保存初始游戏状态到存档文件...")
        save_manager.save_game(request.save_name, turn_index=0)
        
        # 6. 更新物种数量
        species_count = len(species_repository.list_species())
        metadata["species_count"] = species_count
        print(f"[存档API] 存档创建完成，物种数: {species_count}")
        
        return metadata
    except Exception as e:
        print(f"[存档API错误] {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"创建存档失败: {str(e)}")


@router.post("/saves/save")
async def save_game(request: SaveGameRequest) -> dict:
    """保存当前游戏状态"""
    try:
        # 获取当前回合数
        from ..repositories.history_repository import history_repository
        logs = history_repository.list_turns(limit=1)
        turn_index = logs[0].turn_index if logs else 0
        
        save_dir = save_manager.save_game(request.save_name, turn_index)
        return {"success": True, "save_dir": str(save_dir), "turn_index": turn_index}
    except Exception as e:
        print(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存游戏失败: {str(e)}")


@router.post("/saves/load")
async def load_game(request: LoadGameRequest) -> dict:
    """加载游戏存档"""
    try:
        save_data = save_manager.load_game(request.save_name)
        turn_index = save_data.get("turn_index", 0)
        
        # 【关键修复】更新 simulation_engine 的回合计数器
        simulation_engine.turn_counter = turn_index
        print(f"[存档加载] 已恢复回合计数器: {turn_index}")
        
        return {"success": True, "turn_index": turn_index}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[存档API错误] {str(e)}")
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
        print(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除存档失败: {str(e)}")


@router.post("/species/generate")
def generate_species(request: GenerateSpeciesRequest) -> dict:
    """使用AI生成物种"""
    try:
        species = species_generator.generate_from_prompt(request.prompt, request.lineage_code)
        species_repository.upsert(species)
        return {
            "success": True,
            "species": {
                "lineage_code": species.lineage_code,
                "latin_name": species.latin_name,
                "common_name": species.common_name,
                "description": species.description,
            }
        }
    except Exception as e:
        print(f"[物种生成API错误] {str(e)}")
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
            
            print(f"[测试 Embedding] URL: {url}")
            print(f"[测试 Embedding] Model: {model}")
            
            response = httpx.post(url, json=body, headers=headers, timeout=10)
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
                url = f"{base_url}/chat/completions"
            elif "openai.azure.com" in base_url:
                 # Azure 特殊处理 (示例)
                 # .../openai/deployments/{model}/chat/completions?api-version=...
                 # 这里暂不处理复杂情况，假设用户填写的 Base URL 能适配
                 url = f"{base_url}/chat/completions"
            else:
                # 默认行为，尝试追加 /chat/completions
                # 如果用户填写的是 host (e.g., https://api.deepseek.com)，则追加 /chat/completions
                # 如果用户漏了 /v1，通常 API 文档会要求带上。
                # 这里我们做一个简单的检查，如果 base_url 不含 chat/completions，就加上
                if "chat/completions" not in base_url:
                     url = f"{base_url}/chat/completions"
                else:
                     url = base_url

            print(f"[测试 Chat] URL: {url} | Model: {model}")

            body = {
                "model": model or "Pro/deepseek-ai/DeepSeek-V3.2-Exp",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            response = httpx.post(url, json=body, headers=headers, timeout=10)
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
    """对比两个物种的生态位"""
    import numpy as np
    
    # 获取两个物种
    species_a = species_repository.get_by_lineage(request.species_a)
    species_b = species_repository.get_by_lineage(request.species_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_b} 不存在")
    
    print(f"[生态位对比] 对比物种: {species_a.common_name} vs {species_b.common_name}")
    
    # 获取embedding向量（如果embedding服务不可用，使用生态向量）
    try:
        vectors = embedding_service.embed(
            [species_a.description, species_b.description], 
            require_real=True
        )
        vec_a = np.array(vectors[0], dtype=float)
        vec_b = np.array(vectors[1], dtype=float)
        print(f"[生态位对比] 使用embedding向量")
    except (RuntimeError, Exception) as e:
        # 降级到使用生态向量
        print(f"[生态位对比] Embedding服务不可用，使用生态向量: {str(e)}")
        vec_a = np.array(species_a.ecological_vector or [0.5] * 128, dtype=float)
        vec_b = np.array(species_b.ecological_vector or [0.5] * 128, dtype=float)
    
    if len(vec_a) == 0 or len(vec_b) == 0:
        raise HTTPException(status_code=500, detail="无法计算生态位向量，物种数据不完整")
    
    # 计算余弦相似度
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    
    if norm_a == 0 or norm_b == 0:
        similarity = 0.0
    else:
        similarity = float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
        similarity = max(0.0, min(1.0, similarity))  # 限制在0-1之间
    
    # 计算重叠度（基于相似度）
    overlap = similarity
    
    # 计算竞争强度（考虑种群规模）
    pop_a = float(species_a.morphology_stats.get("population", 0) or 0)
    pop_b = float(species_b.morphology_stats.get("population", 0) or 0)
    
    # 竞争强度 = 相似度 * (种群规模因子)
    total_pop = pop_a + pop_b
    if total_pop > 0:
        pop_factor = min(1.0, (pop_a * pop_b) / (total_pop ** 2) * 4)  # 归一化
    else:
        pop_factor = 0.0
    
    competition_intensity = similarity * pop_factor
    
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
        print(f"[日志读取错误] {e}")
        return {"logs": [f"读取失败: {str(e)}"]}


# ========== 生态系统健康指标 API ==========

# 游戏状态 API
@router.get("/game/state", tags=["game"])
def get_game_state() -> dict:
    """获取当前游戏状态，包含回合数等关键信息
    
    前端刷新页面时应调用此 API 获取正确的回合数。
    
    返回的 turn_index 是 0-based 索引：
    - turn_index = 0 表示准备执行第 0 回合（前端显示"第 1 回合"）
    - turn_index = 1 表示第 0 回合已完成，准备执行第 1 回合（前端显示"第 2 回合"）
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


# ========== 玩家干预 API ==========

@router.post("/intervention/protect", response_model=InterventionResponse, tags=["intervention"])
def protect_species(request: ProtectSpeciesRequest) -> InterventionResponse:
    """保护指定物种
    
    保护效果：
    - 死亡率降低50%
    - 持续指定回合数
    """
    species = species_repository.get_by_lineage(request.lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.lineage_code} 不存在")
    
    if species.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {request.lineage_code} 已灭绝，无法保护")
    
    # 设置保护状态
    species.is_protected = True
    species.protection_turns = request.turns
    species_repository.upsert(species)
    
    return InterventionResponse(
        success=True,
        message=f"已对 {species.common_name} ({request.lineage_code}) 实施保护，持续 {request.turns} 回合",
        species_code=request.lineage_code,
        effect_duration=request.turns
    )


@router.post("/intervention/suppress", response_model=InterventionResponse, tags=["intervention"])
def suppress_species(request: SuppressSpeciesRequest) -> InterventionResponse:
    """压制指定物种
    
    压制效果：
    - 死亡率增加30%
    - 持续指定回合数
    """
    species = species_repository.get_by_lineage(request.lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.lineage_code} 不存在")
    
    if species.status != "alive":
        raise HTTPException(status_code=400, detail=f"物种 {request.lineage_code} 已灭绝，无需压制")
    
    # 设置压制状态
    species.is_suppressed = True
    species.suppression_turns = request.turns
    species_repository.upsert(species)
    
    return InterventionResponse(
        success=True,
        message=f"已对 {species.common_name} ({request.lineage_code}) 实施压制，持续 {request.turns} 回合",
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
                # 分配到目标地块
                from ..services.species.habitat_manager import habitat_manager
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
