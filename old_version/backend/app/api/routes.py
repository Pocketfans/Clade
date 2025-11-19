from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..core.config import get_settings
from ..ai.prompts import PROMPT_TEMPLATES
from ..models.config import UIConfig
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
)
from ..services.adaptation import AdaptationService
from ..services.background import BackgroundConfig, BackgroundSpeciesManager
from ..services.gene_flow import GeneFlowService
from ..services.genetic_distance import GeneticDistanceCalculator
from ..services.hybridization import HybridizationService
from ..services.critical_analyzer import CriticalAnalyzer
from ..services.exporter import ExportService
from ..services.embedding import EmbeddingService
from ..services.focus_processor import FocusBatchProcessor
from ..services.map_evolution import MapEvolutionService
from ..services.map_manager import MapStateManager
from ..services.migration import MigrationAdvisor
from ..services.terrain_evolution import TerrainEvolutionService
from ..services.reproduction import ReproductionService
from ..ai.model_router import ModelConfig, ModelRouter
from ..services.niche import NicheAnalyzer
from ..services.pressure import PressureEscalationService
from ..services.report_builder import ReportBuilder
from ..services.speciation import SpeciationService
from ..services.tiering import SpeciesTieringService, TieringConfig
from ..services.save_manager import SaveManager
from ..services.species_generator import SpeciesGenerator
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
        "focus_batch": ModelConfig(provider="local", model="focus-template"),
        "critical_detail": ModelConfig(provider="local", model="critical-template"),
        "speciation": ModelConfig(provider="openai", model="gpt-4o-mini"),  # 使用真实AI进行命名
        "reemergence": ModelConfig(provider="local", model="reemergence-template"),
        "pressure_escalation": ModelConfig(provider="local", model="pressure-template"),
        "migration": ModelConfig(provider="local", model="migration-template"),
        "species_generation": ModelConfig(provider="openai", model="gpt-4o-mini"),  # 物种生成也需要AI
        "terrain_evolution": ModelConfig(provider="openai", model="gpt-4o"),
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
terrain_evolution = TerrainEvolutionService(model_router)
reproduction_service = ReproductionService(
    global_carrying_capacity=settings.global_carrying_capacity,  # 从配置读取
    turn_years=500_000,  # 每回合50万年
)
adaptation_service = AdaptationService()
genetic_distance_calculator = GeneticDistanceCalculator()
hybridization_service = HybridizationService(genetic_distance_calculator)
gene_flow_service = GeneFlowService()
save_manager = SaveManager(settings.saves_dir)
species_generator = SpeciesGenerator(model_router)
ui_config_path = Path(settings.ui_config_path)
pressure_templates: list[PressureTemplate] = [
    PressureTemplate(kind="temperature", label="极寒", description="降低全局温度，冲击热敏物种。"),
    PressureTemplate(kind="humidity", label="湿度骤变", description="湿润或干燥环境，影响蒸腾。"),
    PressureTemplate(kind="drought", label="干旱", description="水源紧张，考验耐旱与迁徙能力。"),
    PressureTemplate(kind="flood", label="洪水", description="低洼地块被淹，迫使栖息地迁移。"),
    PressureTemplate(kind="volcano", label="火山活动", description="局部高温与火山灰，触发灾变事件。"),
    PressureTemplate(kind="predator", label="捕食者激增", description="高阶捕食者数量提升，对食物链造成压力。"),
    PressureTemplate(kind="competitor", label="竞争者扩散", description="同生态位物种爆发，压缩资源。"),
    PressureTemplate(kind="resource_bonus", label="资源奖赏", description="短期内食物/矿物丰富，可引导繁殖。"),
]
pressure_queue: list[list[PressureConfig]] = []


def apply_ui_config(config: UIConfig) -> UIConfig:
    # 如果提供了分功能配置，优先使用
    if config.capability_configs:
        print(f"[配置] 应用capability_configs: {list(config.capability_configs.keys())}")
        for capability, cap_config in config.capability_configs.items():
            if capability in model_router.routes:
                route = model_router.routes[capability]
                # 更新路由配置
                model_router.routes[capability] = ModelConfig(
                    provider=cap_config.provider,
                    model=cap_config.model,
                    endpoint=route.endpoint,
                )
                # 设置该能力的专属 override
                if not model_router.overrides:
                    model_router.overrides = {}
                model_router.overrides[capability] = {
                    "base_url": cap_config.base_url,
                    "api_key": cap_config.api_key,
                    "timeout": cap_config.timeout,
                }
                print(f"[配置] 已设置{capability}的override: provider={cap_config.provider}, base_url={'***' if cap_config.base_url else None}, api_key={'***' if cap_config.api_key else None}")
    # 否则使用全局配置（向后兼容）
    else:
        model_router.api_base_url = (config.ai_base_url or settings.ai_base_url)
        model_router.api_key = config.ai_api_key or settings.ai_api_key
        model_router.timeout = config.ai_timeout or settings.ai_request_timeout
        if config.ai_provider or config.ai_model:
            for capability, route in model_router.routes.items():
                model_router.routes[capability] = ModelConfig(
                    provider=config.ai_provider or route.provider,
                    model=config.ai_model or route.model,
                    endpoint=route.endpoint,
                )
    
    # Embedding 配置（默认启用）
    embedding_service.provider = config.embedding_provider or settings.embedding_provider
    embedding_service.api_base_url = config.embedding_base_url
    embedding_service.api_key = config.embedding_api_key
    embedding_service.model = config.embedding_model
    # 如果配置了完整的 embedding 信息，则启用；否则禁用
    embedding_service.enabled = bool(
        config.embedding_api_key and 
        config.embedding_base_url and 
        config.embedding_model
    )
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
    terrain_evolution=terrain_evolution,
    reproduction_service=reproduction_service,
    adaptation_service=adaptation_service,
    gene_flow_service=gene_flow_service,
)
watchlist: set[str] = set()
action_queue = {"queued_rounds": 0, "running": False}


def initialize_environment() -> None:
    try:
        print("[环境初始化] 开始初始化地图...")
        # 确保数据库列完整
        environment_repository.ensure_map_state_columns()
        map_manager.ensure_initialized()
        tiles = environment_repository.list_tiles(limit=10)
        print(f"[环境初始化] 地图初始化完成，地块数量: {len(tiles)}")
        if len(tiles) > 0:
            print(f"[环境初始化] 示例地块: x={tiles[0].x}, y={tiles[0].y}, biome={tiles[0].biome}")
    except Exception as e:
        print(f"[环境初始化错误] {str(e)}")
        import traceback
        print(traceback.format_exc())


@router.post("/turns/run", response_model=list[TurnReport])
def run_turns(command: TurnCommand) -> list[TurnReport]:
    import traceback
    try:
        print(f"[推演开始] 回合数: {command.rounds}, 压力数: {len(command.pressures)}")
        action_queue["running"] = True
        simulation_engine.update_watchlist(watchlist)
        pressures = list(command.pressures)
        if not pressures and pressure_queue:
            pressures = pressure_queue.pop(0)
            action_queue["queued_rounds"] = max(action_queue["queued_rounds"] - 1, 0)
        command.pressures = pressures
        print(f"[推演执行] 应用压力: {[p.kind for p in pressures]}")
        reports = simulation_engine.run_turns(command)
        print(f"[推演完成] 生成了 {len(reports)} 个报告")
        action_queue["running"] = False
        action_queue["queued_rounds"] = max(action_queue["queued_rounds"] - command.rounds, 0)
        return reports
    except Exception as e:
        action_queue["running"] = False
        print(f"[推演错误] {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"推演执行失败: {str(e)}")


@router.post("/species/edit", response_model=LineageNode)
def edit_species(request: SpeciesEditRequest) -> LineageNode:
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
    return LineageNode(
        lineage_code=species.lineage_code,
        parent_code=species.parent_code,
        latin_name=species.latin_name,
        common_name=species.common_name,
        state=species.status,
        population_share=1.0,
        major_events=["manual_edit"],
    )


@router.get("/watchlist")
def get_watchlist() -> dict[str, list[str]]:
    """获取当前玩家关注的物种列表（Critical 层）"""
    return {"watching": sorted(watchlist)}


@router.post("/watchlist")
def update_watchlist(request: WatchlistRequest) -> dict[str, list[str]]:
    """更新玩家关注的物种列表（Critical 层）
    
    最多可以关注 critical_limit 个物种（通常是3个）。
    这些物种将获得最详细的 AI 分析和报告。
    """
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
        
        # 推断生态角色 (基于描述中的关键词)
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
        
        # 推断tier (基于是否为背景物种)
        tier = "background" if species.is_background else None
        
        # 推断灭绝回合 (如果已灭绝)
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
    limit_tiles: int = 3200, 
    limit_habitats: int = 500,
    view_mode: str = "terrain",
) -> MapOverview:
    try:
        print(f"[地图查询] 请求地块数: {limit_tiles}, 栖息地数: {limit_habitats}, 视图模式: {view_mode}")
        overview = map_manager.get_overview(
            tile_limit=limit_tiles, 
            habitat_limit=limit_habitats,
            view_mode=view_mode,  # type: ignore
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
    
    # 过滤morphology_stats中的非float字段（如extinction_reason可能是字符串）
    morphology_stats = {
        k: v for k, v in species.morphology_stats.items()
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
def create_save(request: CreateSaveRequest) -> dict:
    """创建新存档"""
    try:
        print(f"[存档API] 创建存档: {request.save_name}, 剧本: {request.scenario}")
        
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
        print(f"[存档API] 初始化地图...")
        map_manager.ensure_initialized()
        
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
def save_game(request: SaveGameRequest) -> dict:
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
def load_game(request: LoadGameRequest) -> dict:
    """加载游戏存档"""
    try:
        save_data = save_manager.load_game(request.save_name)
        return {"success": True, "turn_index": save_data.get("turn_index", 0)}
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
    import httpx
    import json
    
    api_type = request.get("type", "chat")  # chat 或 embedding
    base_url = request.get("base_url", "").rstrip("/")
    api_key = request.get("api_key", "")
    model = request.get("model", "")
    provider = request.get("provider", "")
    
    if not base_url or not api_key:
        return {"success": False, "message": "请提供 API Base URL 和 API Key"}
    
    try:
        if api_type == "embedding":
            # 测试 embedding API
            url = f"{base_url}/embeddings"
            body = {
                "model": model or "text-embedding-ada-002",
                "input": "test"
            }
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            print(f"[测试 Embedding] URL: {url}")
            print(f"[测试 Embedding] Model: {model}")
            print(f"[测试 Embedding] API Key 前缀: {api_key[:10]}...")
            
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
            url = f"{base_url}/chat/completions"
            body = {
                "model": model or "gpt-3.5-turbo",
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
    
    # 获取embedding向量（要求使用真实embedding）
    try:
        vectors = embedding_service.embed(
            [species_a.description, species_b.description], 
            require_real=True
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    if len(vectors) != 2 or not vectors[0] or not vectors[1]:
        raise HTTPException(status_code=500, detail="无法计算生态位向量")
    
    # 转换为numpy数组
    vec_a = np.array(vectors[0], dtype=float)
    vec_b = np.array(vectors[1], dtype=float)
    
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
