from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime
import asyncio
import logging
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="ignore")
    except ValueError:
        pass

# 创建模块logger
logger = logging.getLogger(__name__)

from ..models.history import TurnLog
from ..models.species import Species  # 新增：Species类型注解
from ..repositories.environment_repository import environment_repository
from ..repositories.genus_repository import genus_repository
from ..repositories.history_repository import history_repository
from ..repositories.species_repository import species_repository
from ..schemas.requests import PressureConfig, TurnCommand
from ..schemas.responses import (
    EcosystemMetrics,
    ReemergenceEvent,
    SpeciesSnapshot,
    TurnReport,
)
from ..services.species.adaptation import AdaptationService
from ..services.species.ai_pressure_response import (
    AIPressureResponseService, 
    create_ai_pressure_service,
    SpeciesStatusEval,
    SpeciesNarrativeResult,
)
from ..services.species.background import BackgroundSpeciesManager
from ..services.species.gene_activation import GeneActivationService
from ..services.species.gene_flow import GeneFlowService
from ..services.analytics.critical_analyzer import CriticalAnalyzer
from ..services.analytics.exporter import ExportService
from ..services.system.embedding import EmbeddingService
from ..services.analytics.focus_processor import FocusBatchProcessor
from ..services.species.habitat_manager import habitat_manager  # 新增：栖息地管理器
from ..services.species.dispersal_engine import dispersal_engine, process_batch_dispersal  # 新增：矩阵化扩散引擎
from ..services.geo.map_evolution import MapEvolutionService
from ..services.geo.map_manager import MapStateManager
from ..services.geo.vegetation_cover import vegetation_cover_service
from ..services.species.migration import MigrationAdvisor
from ..services.species.reproduction import ReproductionService
from ..ai.model_router import ModelRouter
from ..services.species.niche import NicheAnalyzer
from ..services.system.pressure import PressureEscalationService
from ..services.analytics.report_builder import ReportBuilder
from ..services.species.speciation import SpeciationService
from ..services.species.tiering import SpeciesTieringService
from .environment import EnvironmentSystem
from .species import MortalityEngine, MortalityResult
from .tile_based_mortality import TileBasedMortalityEngine, AggregatedMortalityResult
from ..services.analytics.embedding_integration import EmbeddingIntegrationService


@dataclass(slots=True)
class SimulationContext:
    turn_index: int
    pressures_summary: str


class SimulationEngine:
    def __init__(
        self,
        environment: EnvironmentSystem,
        mortality: MortalityEngine,
        embeddings: EmbeddingService,
        router: ModelRouter,
        report_builder: ReportBuilder,
        exporter: ExportService,
        niche_analyzer: NicheAnalyzer,
        speciation: SpeciationService,
        background_manager: BackgroundSpeciesManager,
        tiering: SpeciesTieringService,
        focus_processor: FocusBatchProcessor,
        critical_analyzer: CriticalAnalyzer,
        escalation_service: PressureEscalationService,
        map_evolution: MapEvolutionService,
        migration_advisor: MigrationAdvisor,
        map_manager: MapStateManager,
        reproduction_service: ReproductionService,
        adaptation_service: AdaptationService,
        gene_flow_service: GeneFlowService,
        embedding_integration: EmbeddingIntegrationService | None = None,
    ) -> None:
        self.environment = environment
        self.mortality = mortality
        self.embeddings = embeddings
        self.router = router
        self.report_builder = report_builder
        self.exporter = exporter
        self.niche_analyzer = niche_analyzer
        self.speciation = speciation
        self.background_manager = background_manager
        self.tiering = tiering
        self.focus_processor = focus_processor
        self.critical_analyzer = critical_analyzer
        self.escalation_service = escalation_service
        self.map_evolution = map_evolution
        self.migration_advisor = migration_advisor
        self.map_manager = map_manager
        self.reproduction_service = reproduction_service
        self.adaptation_service = adaptation_service
        self.gene_flow_service = gene_flow_service
        self.gene_activation_service = GeneActivationService()
        self.tile_mortality = TileBasedMortalityEngine()  # 新增：按地块计算死亡率
        self.ai_pressure_service = create_ai_pressure_service(router)  # 新增：AI压力响应服务
        
        # 【新增】Embedding 集成服务 - 管理分类学、演化预测、叙事生成等扩展功能
        self.embedding_integration = embedding_integration or EmbeddingIntegrationService(embeddings, router)
        
        self.turn_counter = 0
        self.watchlist: set[str] = set()
        self._event_callback = None  # 事件回调函数
        self._use_tile_based_mortality = True  # 是否使用按地块计算的死亡率
        self._use_ai_pressure_response = True  # 是否使用AI压力响应修正
        self._use_embedding_integration = True  # 是否使用Embedding集成功能
    
    def _emit_event(self, event_type: str, message: str, category: str = "其他", **extra):
        """发送事件到前端"""
        if self._event_callback:
            try:
                self._event_callback(event_type, message, category, **extra)
            except Exception as e:
                logger.error(f"事件推送失败: {str(e)}")

    def update_watchlist(self, codes: set[str]) -> None:
        self.watchlist = set(codes)

    def _calculate_trophic_interactions(self, species_list: list) -> dict[str, float]:
        """计算营养级互动压力 (按区域细分)。
        
        标准5级食物链的压力传导：
        - T1 受 T2 的采食压力（grazing）
        - T2 受 T3 的捕食压力（predation_t3）
        - T3 受 T4 的捕食压力（predation_t4）
        - T4 受 T5 的捕食压力（predation_t5）
        - T5 作为顶级捕食者，只受食物匮乏影响
        
        同时计算各营养级的食物稀缺度：
        - t2_scarcity: T2的食物（T1）是否稀缺
        - t3_scarcity: T3的食物（T2）是否稀缺
        - t4_scarcity: T4的食物（T3）是否稀缺
        - t5_scarcity: T5的食物（T4）是否稀缺
        """
        global_biomass = defaultdict(float)
        region_biomass: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
        
        for sp in species_list:
            t_level = int(sp.trophic_level)
            population = sp.morphology_stats.get("population", 0)
            weight = sp.morphology_stats.get("body_weight_g", 1.0)
            biomass = population * weight
            global_biomass[t_level] += biomass
            
            region = self._resolve_region_label(sp)
            region_biomass[region][t_level] = region_biomass[region].get(t_level, 0.0) + biomass
        
        interactions: dict[str, float] = {}
        global_stats = self._compute_trophic_pressures(global_biomass)
        
        # 全局稀缺度
        interactions["t2_scarcity"] = global_stats["t2_scarcity"]
        interactions["t3_scarcity"] = global_stats["t3_scarcity"]
        interactions["t4_scarcity"] = global_stats["t4_scarcity"]
        interactions["t5_scarcity"] = global_stats["t5_scarcity"]
        
        region_stats: dict[str, dict[str, float]] = {}
        for region, biomap in region_biomass.items():
            stats = self._compute_trophic_pressures(biomap)
            region_stats[region] = stats
            interactions[f"t2_scarcity_{region}"] = stats["t2_scarcity"]
            interactions[f"t3_scarcity_{region}"] = stats["t3_scarcity"]
            interactions[f"t4_scarcity_{region}"] = stats["t4_scarcity"]
            interactions[f"t5_scarcity_{region}"] = stats["t5_scarcity"]
        
        # 计算每个物种受到的捕食压力
        for sp in species_list:
            region = self._resolve_region_label(sp)
            stats = region_stats.get(region, global_stats)
            lineage_key = f"predation_on_{sp.lineage_code}"
            trophic_level = int(sp.trophic_level)
            
            if trophic_level == 1:
                # T1: 受T2采食压力
                interactions[lineage_key] = stats["grazing_intensity"]
            elif trophic_level == 2:
                # T2: 受T3捕食压力
                interactions[lineage_key] = stats["predation_t3"]
            elif trophic_level == 3:
                # T3: 受T4捕食压力
                interactions[lineage_key] = stats["predation_t4"]
            elif trophic_level == 4:
                # T4: 受T5捕食压力
                interactions[lineage_key] = stats["predation_t5"]
            # T5: 顶级捕食者，不受捕食压力
        
        return interactions

    def _compute_trophic_pressures(self, biomass_map: dict[int, float]) -> dict[str, float]:
        """计算标准5级食物链的营养级压力
        
        压力传导方向（自下而上）：
        - T1 → 被T2采食
        - T2 → 被T3捕食
        - T3 → 被T4捕食
        - T4 → 被T5捕食
        - T5 → 顶级（无捕食者）
        
        稀缺性计算（自上而下）：
        - t2_scarcity: T2的食物（T1）短缺程度
        - t3_scarcity: T3的食物（T2）短缺程度
        - t4_scarcity: T4的食物（T3）短缺程度
        - t5_scarcity: T5的食物（T4）短缺程度
        """
        t1_biomass = biomass_map.get(1, 0.0)
        t2_biomass = biomass_map.get(2, 0.0)
        t3_biomass = biomass_map.get(3, 0.0)
        t4_biomass = biomass_map.get(4, 0.0)
        t5_biomass = biomass_map.get(5, 0.0)
        
        # 生态效率系数（用于判断压力）
        # 每上升一级，可支撑的生物量约为下级的10-15%
        EFFICIENCY = 0.12
        
        # 【修复】微生物生物量通常很小（克甚至毫克级别）
        # 使用 1e-6g 作为最小值避免除以零，而不是 1.0g
        MIN_BIOMASS = 1e-6
        
        # === T1 受 T2 的采食压力 ===
        grazing_intensity = 0.0
        t2_scarcity = 0.0
        if t1_biomass > MIN_BIOMASS:
            # T2 需要的 T1 生物量 = T2 / 效率
            required_t1 = t2_biomass / EFFICIENCY if t2_biomass > 0 else 0
            grazing_ratio = required_t1 / t1_biomass
            grazing_intensity = min(grazing_ratio * 0.5, 0.8)
            # 当 grazing_ratio > 1.0 时才开始产生稀缺
            # 这意味着 T2 的需求超过了 T1 的供给
            t2_scarcity = max(0.0, min(2.0, grazing_ratio - 1.0))
        elif t2_biomass > 0:
            t2_scarcity = 2.0  # 没有T1但有T2，T2面临严重食物短缺
        
        # === T2 受 T3 的捕食压力 ===
        predation_t3 = 0.0
        t3_scarcity = 0.0
        if t2_biomass > MIN_BIOMASS:
            required_t2 = t3_biomass / EFFICIENCY if t3_biomass > 0 else 0
            predation_ratio = required_t2 / t2_biomass
            predation_t3 = min(predation_ratio * 0.5, 0.8)
            t3_scarcity = max(0.0, min(2.0, predation_ratio - 1.0))
        elif t3_biomass > 0:
            t3_scarcity = 2.0
        
        # === T3 受 T4 的捕食压力 ===
        predation_t4 = 0.0
        t4_scarcity = 0.0
        if t3_biomass > MIN_BIOMASS:
            required_t3 = t4_biomass / EFFICIENCY if t4_biomass > 0 else 0
            predation_ratio = required_t3 / t3_biomass
            predation_t4 = min(predation_ratio * 0.5, 0.8)
            t4_scarcity = max(0.0, min(2.0, predation_ratio - 1.0))
        elif t4_biomass > 0:
            t4_scarcity = 2.0
        
        # === T4 受 T5 的捕食压力 ===
        predation_t5 = 0.0
        t5_scarcity = 0.0
        if t4_biomass > MIN_BIOMASS:
            required_t4 = t5_biomass / EFFICIENCY if t5_biomass > 0 else 0
            predation_ratio = required_t4 / t4_biomass
            predation_t5 = min(predation_ratio * 0.5, 0.8)
            t5_scarcity = max(0.0, min(2.0, predation_ratio - 1.0))
        elif t5_biomass > 0:
            t5_scarcity = 2.0
        
        return {
            "grazing_intensity": grazing_intensity,
            "predation_t3": predation_t3,
            "predation_t4": predation_t4,
            "predation_t5": predation_t5,
            "t2_scarcity": t2_scarcity,
            "t3_scarcity": t3_scarcity,
            "t4_scarcity": t4_scarcity,
            "t5_scarcity": t5_scarcity,
        }

    def _resolve_region_label(self, species: Species) -> str:
        habitat = (getattr(species, "habitat_type", "") or "").lower()
        marine_types = {"marine", "deep_sea", "coastal"}
        if habitat in marine_types:
            return "marine"
        return "terrestrial"

    def _compute_ecosystem_metrics(self, mortality: list[MortalityResult]) -> EcosystemMetrics:
        if not mortality:
            return EcosystemMetrics()
        
        total_biomass = 0.0
        marine_biomass = 0.0
        total_trophic = 0.0
        total_body_length = 0.0
        count = 0
        
        for item in mortality:
            species = item.species
            population = species.morphology_stats.get("population", 0)
            weight = species.morphology_stats.get("body_weight_g", 1.0)
            biomass = population * weight
            total_biomass += biomass
            if self._resolve_region_label(species) == "marine":
                marine_biomass += biomass
            total_trophic += species.trophic_level
            total_body_length += species.morphology_stats.get("body_length_cm", 0.0)
            count += 1
        
        terrestrial_biomass = max(0.0, total_biomass - marine_biomass)
        avg_trophic = (total_trophic / count) if count else 0.0
        avg_body = (total_body_length / count) if count else 0.0
        
        return EcosystemMetrics(
            total_biomass=total_biomass,
            terrestrial_biomass=terrestrial_biomass,
            marine_biomass=marine_biomass,
            average_trophic_level=avg_trophic,
            average_body_length_cm=avg_body,
        )

    async def run_turns_async(self, command: TurnCommand) -> list[TurnReport]:
        reports: list[TurnReport] = []
        for turn_num in range(command.rounds):
            logger.info(f"执行第 {turn_num + 1}/{command.rounds} 回合, turn_counter={self.turn_counter}")
            self._emit_event("turn_start", f"📅 开始第 {self.turn_counter} 回合", "系统")
            
            try:
                # ========== 【回合初始化】清理各服务缓存 ==========
                self.speciation.clear_tile_cache()
                self.migration_advisor.clear_tile_mortality_cache()
                
                temp_delta_for_habitats = 0.0
                sea_delta_for_habitats = 0.0
                # 1. 解析压力
                logger.info(f"解析压力...")
                self._emit_event("stage", "🌡️ 解析环境压力", "环境")
                pressures = self.environment.parse_pressures(command.pressures)
                modifiers = self.environment.apply_pressures(pressures)
                major_events = self.escalation_service.register(command.pressures, self.turn_counter)
                
                # 2. 地图演化与海平面变化
                logger.info(f"地图演化...")
                self._emit_event("stage", "🗺️ 地图演化与海平面变化", "地质")
                current_map_state = environment_repository.get_state()
                if not current_map_state:
                    logger.info(f"初始化地图状态...")
                    self._emit_event("info", "初始化地图状态", "地质")
                    current_map_state = environment_repository.save_state(
                        {"stage_name": "稳定期", "stage_progress": 0, "stage_duration": 0}
                    )
                
                map_changes = self.map_evolution.advance(
                    major_events, self.turn_counter, modifiers, current_map_state
                ) or []
                
                # 计算温度和海平面变化并更新地图状态
                if modifiers:
                    temp_change, sea_level_change = self.map_evolution.calculate_climate_changes(
                        modifiers, current_map_state
                    )
                    temp_delta_for_habitats = temp_change
                    sea_delta_for_habitats = sea_level_change
                    
                    if abs(temp_change) > 0.01 or abs(sea_level_change) > 0.01:
                        new_temp = current_map_state.global_avg_temperature + temp_change
                        new_sea_level = current_map_state.sea_level + sea_level_change
                        
                        logger.info(f"温度: {current_map_state.global_avg_temperature:.1f}°C → {new_temp:.1f}°C")
                        logger.info(f"海平面: {current_map_state.sea_level:.1f}m → {new_sea_level:.1f}m")
                        
                        # 更新地图状态
                        current_map_state.global_avg_temperature = new_temp
                        current_map_state.sea_level = new_sea_level
                        current_map_state.turn_index = self.turn_counter
                        environment_repository.save_state(current_map_state)
                        
                        # 根据新海平面重新分类地形
                        if abs(sea_level_change) > 0.5:
                            self.map_manager.reclassify_terrain_by_sea_level(new_sea_level)
                
                # 地形演化模块已退役，仅保留 MapEvolution 更新
                logger.info(f"[地形演化] 模块已退役，跳过 AI 地形演化步骤")
                self._emit_event("info", "⏭️ 地形演化模块已移除，采用 MapEvolution 结果", "地质")
                
                # 3. 获取物种列表（只处理存活的物种）
                logger.info(f"获取物种列表...")
                self._emit_event("stage", "🧬 获取物种列表", "物种")
                all_species = species_repository.list_species()
                species_batch = [sp for sp in all_species if sp.status == "alive"]
                
                # 获取已灭绝物种代码集合（用于共生依赖计算）
                extinct_codes = {sp.lineage_code for sp in all_species if sp.status == "extinct"}
                
                logger.info(f"当前物种数量: {len(species_batch)} (总共{len(all_species)}个，其中{len(extinct_codes)}个已灭绝)")
                self._emit_event("info", f"当前存活物种: {len(species_batch)} 个", "物种")
                
                # 【Embedding集成】回合开始钩子 - 更新索引
                if self._use_embedding_integration and species_batch:
                    try:
                        self.embedding_integration.on_turn_start(self.turn_counter, species_batch)
                        # 记录压力事件
                        self.embedding_integration.on_pressure_applied(
                            self.turn_counter, command.pressures, modifiers
                        )
                    except Exception as e:
                        logger.warning(f"[Embedding集成] 回合开始钩子失败: {e}")
                
                if species_batch and (abs(temp_delta_for_habitats) > 0.1 or abs(sea_delta_for_habitats) > 0.5):
                    habitat_manager.adjust_habitats_for_climate(
                        species_batch,
                        temp_delta_for_habitats,
                        sea_delta_for_habitats,
                        self.turn_counter,
                    )
                
                # 处理玩家干预：递减保护/压制回合数
                self._update_intervention_status(species_batch)
                
                if not species_batch:
                    logger.warning(f"没有存活物种，跳过此回合")
                    self._emit_event("warning", "没有存活物种，跳过此回合", "错误")
                    continue
                
                # 4. 分层与生态位分析
                logger.info(f"物种分层...")
                self._emit_event("stage", "📊 物种分层与生态位分析", "生态")
                tiered = self.tiering.classify(species_batch, self.watchlist)
                logger.info(f"Critical: {len(tiered.critical)}, Focus: {len(tiered.focus)}, Background: {len(tiered.background)}")
                self._emit_event("info", f"Critical: {len(tiered.critical)}, Focus: {len(tiered.focus)}, Background: {len(tiered.background)}", "生态")
                
                logger.info(f"生态位分析（迁徙前）...")
                # 获取栖息地数据用于地块重叠计算
                all_habitats = environment_repository.latest_habitats()
                all_tiles = environment_repository.list_tiles()
                niche_metrics = self.niche_analyzer.analyze(species_batch, habitat_data=all_habitats)
                
                # ========== 【方案B：第一阶段】初步死亡率评估（用于迁徙决策） ==========
                # 5. 第一次死亡率计算（基于当前栖息地）
                logger.info(f"【阶段1】计算营养级互动...")
                self._emit_event("stage", "⚔️ 【阶段1】计算营养级互动与死亡率", "生态")
                trophic_interactions = self._calculate_trophic_interactions(species_batch)
                
                logger.info(f"【阶段1】计算初步死亡率（迁徙前）...")
                
                # 【新增】使用按地块计算的死亡率引擎
                if self._use_tile_based_mortality and all_tiles:
                    logger.info(f"[地块死亡率] 构建地块-物种矩阵...")
                    self._emit_event("info", "🗺️ 使用按地块计算死亡率", "生态")
                    
                    # 构建矩阵（只需构建一次）
                    self.tile_mortality.build_matrices(species_batch, all_tiles, all_habitats)
                    
                    # 使用新引擎计算死亡率
                    preliminary_critical_results = self.tile_mortality.evaluate(
                        tiered.critical, modifiers, niche_metrics, tier="critical", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    preliminary_focus_results = self.tile_mortality.evaluate(
                        tiered.focus, modifiers, niche_metrics, tier="focus", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    preliminary_background_results = self.tile_mortality.evaluate(
                        tiered.background, modifiers, niche_metrics, tier="background", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                else:
                    # 降级：使用原有全局计算
                    preliminary_critical_results = self.mortality.evaluate(
                        tiered.critical, modifiers, niche_metrics, tier="critical", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    preliminary_focus_results = self.mortality.evaluate(
                        tiered.focus, modifiers, niche_metrics, tier="focus", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    preliminary_background_results = self.mortality.evaluate(
                        tiered.background, modifiers, niche_metrics, tier="background", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                
                preliminary_combined = preliminary_critical_results + preliminary_focus_results + preliminary_background_results
                logger.info(f"【阶段1】初步死亡率计算完成，用于迁徙决策")
                
                # ========== 【数据传递】将地块级死亡率传递给迁徙服务 ==========
                if self._use_tile_based_mortality and all_tiles:
                    # 清空旧缓存
                    self.migration_advisor.clear_tile_mortality_cache()
                    
                    # 传递地块死亡率数据
                    tile_mortality_data = self.tile_mortality.get_all_species_tile_mortality()
                    for lineage_code, tile_rates in tile_mortality_data.items():
                        self.migration_advisor.set_tile_mortality_data(lineage_code, tile_rates)
                    
                    logger.debug(f"[数据传递] 向迁徙服务传递了 {len(tile_mortality_data)} 个物种的地块死亡率数据")
                
                # ========== 【新增】消费者追踪猎物：更新猎物分布缓存 ==========
                all_habitats = environment_repository.latest_habitats()
                habitat_manager.update_prey_distribution_cache(species_batch, all_habitats)
                
                # 为消费者计算并设置猎物密度数据
                for sp in species_batch:
                    if sp.status != "alive" or not sp.id:
                        continue
                    trophic_level = getattr(sp, 'trophic_level', 1.0)
                    if trophic_level >= 2.0:  # 只为消费者计算
                        prey_tiles = habitat_manager.get_prey_tiles_for_consumer(trophic_level)
                        # 获取该物种当前栖息地的猎物密度
                        species_habitats = [h for h in all_habitats if h.species_id == sp.id]
                        current_prey_density = 0.0
                        if species_habitats and prey_tiles:
                            for hab in species_habitats:
                                tile_prey = prey_tiles.get(hab.tile_id, 0.0)
                                current_prey_density += tile_prey * hab.suitability
                            # 归一化
                            total_suitability = sum(h.suitability for h in species_habitats)
                            if total_suitability > 0:
                                current_prey_density /= total_suitability
                        self.migration_advisor.set_prey_density_data(sp.lineage_code, current_prey_density)
                
                logger.debug(f"[猎物追踪] 已更新消费者猎物密度数据")
                
                # ========== 【方案B：第二阶段】迁徙执行 ==========
                # 6. 迁徙建议与执行（基于初步死亡率）
                logger.info(f"【阶段2】迁徙建议与执行...")
                self._emit_event("stage", "🦅 【阶段2】迁徙建议与执行", "生态")
                
                # 【新增】获取处于迁徙冷却期的物种
                cooldown_species = {
                    sp.lineage_code for sp in species_batch 
                    if sp.status == "alive" and habitat_manager.is_migration_on_cooldown(
                        sp.lineage_code, self.turn_counter, cooldown_turns=2
                    )
                }
                if cooldown_species:
                    logger.debug(f"[迁徙冷却] {len(cooldown_species)} 个物种处于冷却期，跳过")
                
                migration_events = self.migration_advisor.plan(
                    preliminary_critical_results + preliminary_focus_results, 
                    modifiers, major_events, map_changes,
                    current_turn=self.turn_counter,
                    cooldown_species=cooldown_species
                )
                
                migration_count = 0
                symbiotic_follow_count = 0
                if migration_events and self.migration_advisor.enable_actual_migration:
                    logger.info(f"[迁徙] 执行 {len(migration_events)} 个迁徙事件...")
                    tiles = environment_repository.list_tiles()
                    
                    for event in migration_events:
                        migrating_species = next(
                            (sp for sp in species_batch if sp.lineage_code == event.lineage_code),
                            None
                        )
                        if migrating_species:
                            success = habitat_manager.execute_migration(
                                migrating_species, event, tiles, self.turn_counter
                            )
                            if success:
                                migration_count += 1
                                logger.info(f"[迁徙成功] {migrating_species.common_name}: {event.origin} → {event.destination}")
                                self._emit_event("migration", f"🗺️ 迁徙: {migrating_species.common_name} 从 {event.origin} 迁往 {event.destination}", "迁徙")
                                
                                # 【新增】处理共生物种追随迁徙
                                followers = habitat_manager.get_symbiotic_followers(migrating_species, species_batch)
                                if followers:
                                    # 获取迁徙后的新栖息地
                                    new_habitats = environment_repository.latest_habitats()
                                    new_tile_ids = [
                                        h.tile_id for h in new_habitats 
                                        if h.species_id == migrating_species.id
                                    ]
                                    
                                    for follower in followers:
                                        follow_success = habitat_manager.execute_symbiotic_following(
                                            migrating_species, follower, new_tile_ids, tiles, self.turn_counter
                                        )
                                        if follow_success:
                                            symbiotic_follow_count += 1
                    
                    log_msg = f"【阶段2】迁徙执行完成: {migration_count}/{len(migration_events)} 个物种成功迁徙"
                    if symbiotic_follow_count > 0:
                        log_msg += f", {symbiotic_follow_count} 个共生物种追随"
                    logger.info(log_msg)
                    self._emit_event("info", f"{migration_count} 个物种完成迁徙", "生态")
                else:
                    logger.debug(f"[迁徙] 生成了 {len(migration_events)} 个迁徙建议（未执行或无迁徙）")
                
                # 【平衡v2 新增】被动扩散机制 - 让物种更容易散布到地图各处
                # 每回合检查所有物种，部分触发被动扩散
                logger.debug(f"【阶段2.5】执行被动扩散...")
                try:
                    # 准备死亡率数据
                    mortality_data = {r.species.lineage_code: r.death_rate for r in preliminary_critical_results + preliminary_focus_results}
                    for r in background_results if 'background_results' in dir() else []:
                        mortality_data[r.species.lineage_code] = r.death_rate
                    
                    # 执行批量扩散
                    all_habitats = environment_repository.latest_habitats()
                    dispersal_results = process_batch_dispersal(
                        species_batch,
                        all_tiles,
                        all_habitats,
                        mortality_data,
                        self.turn_counter,
                        embedding_service=self.embedding_integration
                    )
                    
                    if dispersal_results:
                        dispersal_count = len(dispersal_results)
                        logger.info(f"【阶段2.5】被动扩散完成: {dispersal_count} 个物种扩散到新地块")
                        self._emit_event("info", f"{dispersal_count} 个物种被动扩散", "生态")
                except Exception as e:
                    logger.warning(f"[扩散引擎] 被动扩散失败: {e}")
                
                # ========== 【方案B：第三阶段】重新评估死亡率（基于迁徙后的栖息地） ==========
                # 7. 第二次生态位分析（基于迁徙后的新栖息地）
                if migration_count > 0:
                    logger.info(f"【阶段3】重新分析生态位（迁徙后）...")
                    self._emit_event("stage", "📊 【阶段3】重新分析生态位", "生态")
                    # 迁徙后重新获取栖息地数据
                    all_habitats = environment_repository.latest_habitats()
                    niche_metrics = self.niche_analyzer.analyze(species_batch, habitat_data=all_habitats)
                    logger.info(f"【阶段3】生态位重新分析完成")
                
                # 8. 第二次死亡率计算（基于迁徙后的栖息地）
                logger.info(f"【阶段3】重新计算死亡率（迁徙后）...")
                self._emit_event("stage", "💀 【阶段3】重新计算死亡率", "生态")
                
                # 注意：营养级互动不重新计算（物种食性不会因迁徙而改变）
                # 只重新计算死亡率（因为栖息地环境变了）
                
                # 【新增】迁徙后需要重新构建矩阵
                if self._use_tile_based_mortality and all_tiles:
                    if migration_count > 0:
                        # 迁徙后需要重新获取栖息地数据并重建矩阵
                        all_habitats = environment_repository.latest_habitats()
                        self.tile_mortality.build_matrices(species_batch, all_tiles, all_habitats)
                    
                    critical_results = self.tile_mortality.evaluate(
                        tiered.critical, modifiers, niche_metrics, tier="critical", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    focus_results = self.tile_mortality.evaluate(
                        tiered.focus, modifiers, niche_metrics, tier="focus", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    background_results = self.tile_mortality.evaluate(
                        tiered.background, modifiers, niche_metrics, tier="background", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                else:
                    critical_results = self.mortality.evaluate(
                        tiered.critical, modifiers, niche_metrics, tier="critical", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    focus_results = self.mortality.evaluate(
                        tiered.focus, modifiers, niche_metrics, tier="focus", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                    background_results = self.mortality.evaluate(
                        tiered.background, modifiers, niche_metrics, tier="background", 
                        trophic_interactions=trophic_interactions, extinct_codes=extinct_codes
                    )
                
                combined_results = critical_results + focus_results + background_results
                
                # ========== 【优化】AI综合状态评估（合并了压力评估+紧急响应） ==========
                # 使用新的综合评估方法，一次AI调用完成多项评估
                ai_status_evals = {}  # {lineage_code: SpeciesStatusEval}
                emergency_responses = []
                
                if self._use_ai_pressure_response and self.ai_pressure_service:
                    logger.info(f"【阶段3.5】AI综合状态评估...")
                    self._emit_event("stage", "🤖 【阶段3.5】AI综合状态评估", "AI")
                    
                    # 清空回合缓存
                    self.ai_pressure_service.clear_turn_cache()
                    
                    # 计算总压力
                    total_pressure = sum(abs(v) for v in modifiers.values())
                    
                    # 只有在高压力情况下才启用AI评估
                    if total_pressure >= self.ai_pressure_service.HIGH_PRESSURE_THRESHOLD:
                        # 准备死亡率数据
                        mortality_data = {r.species.lineage_code: r.death_rate for r in combined_results}
                        
                        # 生成压力上下文
                        pressure_context = "; ".join([
                            f"{k}: {v:.1f}" for k, v in modifiers.items() if abs(v) > 0.1
                        ]) or "环境稳定"
                        
                        try:
                            # 【优化】使用新的批量综合评估（合并了压力评估+紧急响应判断）
                            # 整体超时90秒，内部已有单物种30秒超时和规则fallback
                            critical_focus_species = tiered.critical + tiered.focus
                            species_count = len(critical_focus_species)
                            
                            # 发送AI进度事件
                            self._emit_event(
                                "ai_progress", 
                                f"AI评估 {species_count} 个物种", 
                                "AI",
                                total=species_count,
                                completed=0,
                                current_task="综合状态评估"
                            )
                            
                            ai_status_evals = await asyncio.wait_for(
                                self.ai_pressure_service.batch_evaluate_species_status(
                                    critical_focus_species,
                                    mortality_data,
                                    modifiers,
                                    pressure_context,
                                ),
                                timeout=90  # 整体90秒超时
                            )
                            
                            # 更新进度：评估完成
                            self._emit_event(
                                "ai_progress",
                                f"AI评估完成",
                                "AI",
                                total=species_count,
                                completed=species_count,
                                current_task="评估完成"
                            )
                            
                            if ai_status_evals:
                                logger.info(f"[AI综合评估] 获得 {len(ai_status_evals)} 个物种的状态评估")
                                self._emit_event("info", f"AI评估了 {len(ai_status_evals)} 个物种的综合状态", "AI")
                                
                                # 应用AI修正到死亡率
                                for result in combined_results:
                                    code = result.species.lineage_code
                                    if code in ai_status_evals:
                                        status_eval = ai_status_evals[code]
                                        old_rate = result.death_rate
                                        result.death_rate = status_eval.apply_to_death_rate(old_rate)
                                        
                                        # 保存AI评估结果到result（供后续叙事使用）
                                        result.ai_status_eval = status_eval
                                        
                                        if abs(result.death_rate - old_rate) > 0.01:
                                            logger.debug(
                                                f"[AI修正] {result.species.common_name}: "
                                                f"{old_rate:.1%} → {result.death_rate:.1%} "
                                                f"(策略: {status_eval.response_strategy}, "
                                                f"状态: {status_eval.emergency_level})"
                                            )
                                        
                                        # 检查是否处于紧急状态（从AI评估结果中获取）
                                        if status_eval.is_emergency and not result.species.is_background:
                                            self._emit_event(
                                                "warning", 
                                                f"⚠️ {result.species.common_name} 处于{status_eval.emergency_level}状态", 
                                                "紧急"
                                            )
                                            emergency_responses.append({
                                                "lineage_code": code,
                                                "common_name": result.species.common_name,
                                                "emergency_level": status_eval.emergency_level,
                                                "emergency_action": status_eval.emergency_action,
                                                "death_rate": result.death_rate,
                                            })
                            
                            # 更新危险追踪（用于下回合判断）
                            for result in combined_results:
                                self.ai_pressure_service.update_danger_tracking(
                                    result.species.lineage_code, result.death_rate
                                )
                        
                        except asyncio.TimeoutError:
                            logger.warning("[AI综合评估] 超时，跳过AI修正")
                        except Exception as e:
                            logger.warning(f"[AI综合评估] 失败: {e}")
                    else:
                        logger.debug(f"[AI综合评估] 压力不足 ({total_pressure:.1f}), 跳过AI评估")
                
                # ========== 【数据传递】将地块级数据传递给分化服务 ==========
                if self._use_tile_based_mortality and all_tiles:
                    # 清空旧缓存
                    self.speciation.clear_tile_cache()
                    
                    # 传递地块死亡率数据
                    tile_mortality_data = self.tile_mortality.get_all_species_tile_mortality()
                    for lineage_code, tile_rates in tile_mortality_data.items():
                        self.speciation.set_tile_mortality_data(lineage_code, tile_rates)
                    
                    # 传递地块种群分布数据
                    tile_population_data = self.tile_mortality.get_all_species_tile_population()
                    for lineage_code, tile_pops in tile_population_data.items():
                        self.speciation.set_tile_population_data(lineage_code, tile_pops)
                    
                    # 传递地块邻接关系
                    tile_adjacency = self.tile_mortality.get_tile_adjacency()
                    self.speciation.set_tile_adjacency(tile_adjacency)
                    
                    # 【核心改进】传递预筛选的分化候选数据
                    speciation_candidates = self.tile_mortality.get_speciation_candidates(
                        min_tile_population=100,
                        mortality_threshold=(0.03, 0.70),
                        min_mortality_gradient=0.15,
                    )
                    self.speciation.set_speciation_candidates(speciation_candidates)
                    
                    logger.debug(
                        f"[数据传递] 向分化服务传递了 {len(tile_mortality_data)} 个物种的地块死亡率数据, "
                        f"{len(tile_population_data)} 个物种的地块种群数据, "
                        f"{len(speciation_candidates)} 个分化候选物种"
                    )
                
                # 日志：对比迁徙前后的死亡率变化
                if migration_count > 0:
                    for final_result in combined_results:
                        prelim_result = next(
                            (r for r in preliminary_combined if r.species.lineage_code == final_result.species.lineage_code),
                            None
                        )
                        if prelim_result and abs(final_result.death_rate - prelim_result.death_rate) > 0.05:
                            logger.info(
                                f"[死亡率变化] {final_result.species.common_name}: "
                                f"{prelim_result.death_rate:.1%} → {final_result.death_rate:.1%}"
                            )
                
                logger.info(f"【阶段3】最终死亡率计算完成")
                
                # ========== 【方案B：第四阶段】应用死亡和繁殖 ==========
                # 【优化】死亡和繁殖并行计算，然后合并结果
                # 这更符合50万年时间尺度：死亡和繁殖是同时发生的过程
                logger.info(f"计算种群变化（死亡+繁殖并行）...")
                self._emit_event("stage", "💀🐣 计算种群变化", "物种")
                
                # P2: 更新环境动态修正系数（基于本回合的气候变化）
                temp_change = modifiers.get("temperature", 0.0) if modifiers else 0.0
                sea_level_change = 0.0
                if current_map_state:
                    prev_sea = getattr(current_map_state, '_prev_sea_level', current_map_state.sea_level)
                    sea_level_change = current_map_state.sea_level - prev_sea
                    current_map_state._prev_sea_level = current_map_state.sea_level
                self.reproduction_service.update_environmental_modifier(temp_change, sea_level_change)
                
                # 【修复】繁殖计算应基于死亡前的种群，而不是死亡后
                # 这样更符合生态学：活着的个体在繁殖的同时也在死亡
                # 记录死亡前的种群数（用于繁殖计算）
                initial_populations = {
                    item.species.lineage_code: item.initial_population
                    for item in combined_results
                }
                
                # 【修复】survival_rate 用于繁殖服务的"环境质量"评估
                # 不再双重惩罚，因为死亡率已经单独计算
                # 这里传 1.0 表示不额外惩罚繁殖
                survival_rates = {
                    item.species.lineage_code: 1.0  # 繁殖不再受死亡率惩罚
                    for item in combined_results
                }
                
                niche_data = {
                    code: (metrics.overlap, metrics.saturation)
                    for code, metrics in niche_metrics.items()
                }
                
                # 【优化】先计算繁殖增长（基于死亡前种群）
                # 临时设置种群为初始值
                for item in combined_results:
                    item.species.morphology_stats["population"] = item.initial_population
                
                reproduction_results = self.reproduction_service.apply_reproduction(
                    species_batch, niche_data, survival_rates,
                    habitat_manager=habitat_manager
                )
                
                # 【新逻辑】计算最终种群 = 初始种群 × (1 - 死亡率) + 繁殖增量
                # 这更符合连续时间的积分效果
                new_populations = {}
                for item in combined_results:
                    code = item.species.lineage_code
                    initial = item.initial_population
                    death_rate = item.death_rate
                    
                    # 繁殖后的种群（如果没有死亡）
                    repro_pop = reproduction_results.get(code, initial)
                    # 繁殖增量
                    repro_gain = max(0, repro_pop - initial)
                    
                    # 最终种群 = 存活者 + 繁殖增量 × 存活者比例
                    # 逻辑：只有存活的个体才能繁殖后代
                    survivors = int(initial * (1.0 - death_rate))
                    if initial > 0:
                        survivor_ratio = survivors / initial
                    else:
                        survivor_ratio = 0
                    
                    # 繁殖后代也受到一定的环境压力（但比成年个体小）
                    offspring_survival = 0.8 + 0.2 * (1.0 - death_rate)  # 80%-100%
                    effective_gain = int(repro_gain * survivor_ratio * offspring_survival)
                    
                    final_pop = survivors + effective_gain
                    new_populations[code] = max(0, final_pop)
                    
                    if abs(final_pop - initial) > initial * 0.3:
                        logger.debug(
                            f"[种群变化] {item.species.common_name}: "
                            f"{initial:,} → {final_pop:,} "
                            f"(死亡{death_rate:.1%}, 存活{survivors:,}, 繁殖+{effective_gain:,})"
                        )
                
                # 应用最终种群
                for species in species_batch:
                    if species.lineage_code in new_populations:
                        species.morphology_stats["population"] = new_populations[species.lineage_code]
                        species_repository.upsert(species)
                
                # 更新灭绝状态（基于最终种群）
                self._update_populations_extinction_check(combined_results, new_populations)
                
                logger.info(f"种群变化计算完成")
                self._emit_event("info", "种群变化计算完成", "物种")
                
                # 【新增】更新慢性衰退追踪
                # 用于下回合判断是否需要生存迁徙
                for result in combined_results:
                    old_pop = result.initial_population
                    new_pop = new_populations.get(result.species.lineage_code, result.survivors)
                    if old_pop > 0:
                        growth_rate = new_pop / old_pop
                    else:
                        growth_rate = 1.0
                    self.migration_advisor.update_decline_streak(
                        result.species.lineage_code,
                        result.death_rate,
                        growth_rate
                    )
                
                # 8.5.5 基因激活检查
                logger.info(f"检查休眠基因激活...")
                self._emit_event("stage", "🧬 检查休眠基因激活", "进化")
                activation_events = self.gene_activation_service.batch_check(
                    species_batch, 
                    critical_results + focus_results,
                    self.turn_counter
                )
                if activation_events:
                    logger.info(f"{len(activation_events)}个物种激活了休眠基因")
                    self._emit_event("info", f"{len(activation_events)}个物种激活了休眠基因", "进化")
                    for event in activation_events:
                        traits = event['activated_traits']
                        organs = event['activated_organs']
                        detail = f"{event['common_name']}: 特质{traits} 器官{organs}"
                        logger.debug(f"  - {detail}")
                        self._emit_event("activation", f"🔓 激活: {detail}", "进化")
                    for species in species_batch:
                        species_repository.upsert(species)
                
                # 8.6. 基因流动
                logger.info(f"应用基因流动...")
                self._emit_event("stage", "🔀 应用基因流动", "进化")
                gene_flow_count = self._apply_gene_flow(species_batch)
                logger.info(f"基因流动完成: {gene_flow_count}对物种发生基因流动")
                self._emit_event("info", f"基因流动完成: {gene_flow_count}对物种发生基因流动", "进化")
                
                # 8.6b. 【平衡优化v2】遗传漂变
                logger.info(f"应用遗传漂变...")
                drift_count = self._apply_genetic_drift(species_batch)
                if drift_count > 0:
                    logger.info(f"遗传漂变完成: {drift_count}个属更新了遗传距离")
                
                # 8.6c. 【平衡优化v2】自动杂交检测（使用AI生成杂交物种）
                logger.info(f"检测自动杂交...")
                auto_hybrids = await self._check_auto_hybridization_async(species_batch, self.turn_counter)
                if auto_hybrids:
                    logger.info(f"自动杂交完成: 产生了{len(auto_hybrids)}个杂交种")
                    self._emit_event("info", f"自然杂交产生了{len(auto_hybrids)}个杂交种", "杂交")
                    # 将杂交种加入物种列表
                    species_batch.extend(auto_hybrids)
                
                # 8.7. 亚种晋升检查
                logger.info(f"检查亚种晋升...")
                self._emit_event("stage", "⬆️ 检查亚种晋升", "物种")
                promotion_count = self._check_subspecies_promotion(species_batch, self.turn_counter)
                if promotion_count > 0:
                    logger.info(f"{promotion_count}个亚种晋升为独立种")
                    self._emit_event("info", f"{promotion_count}个亚种晋升为独立种", "物种")
                
                # 9. 【优化】并行+顺序处理AI任务
                # 阶段1并行：物种叙事 + 适应性演化（无依赖）
                # 阶段2顺序：物种分化（依赖适应性演化结果）
                logger.info(f"开始AI任务 (叙事∥适应 → 分化)...")
                self._emit_event("stage", "🔄 AI并行处理", "AI")
                
                # 任务名称（用于日志和进度显示）
                ai_task_names = [
                    "物种叙事+适应性",   # 并行阶段
                    "物种分化"           # 顺序阶段
                ]
                
                total_tasks = 2  # 两个阶段
                
                # 发送初始进度
                self._emit_event(
                    "ai_progress", 
                    f"AI任务开始 (0/{total_tasks})", 
                    "AI",
                    total=total_tasks,
                    completed=0,
                    current_task="初始化任务..."
                )
                
                # 心跳任务
                heartbeat_count = [0]
                async def send_heartbeat():
                    """发送心跳信号，让前端知道AI仍在运行"""
                    while True:
                        await asyncio.sleep(3)
                        heartbeat_count[0] += 1
                        self._emit_event("ai_heartbeat", f"心跳#{heartbeat_count[0]}", "AI")
                        logger.debug(f"[AI心跳] 已发送第 {heartbeat_count[0]} 次心跳")
                
                heartbeat_task = asyncio.create_task(send_heartbeat())
                
                adaptation_events = []
                branching = []
                narrative_results = []
                completed_count = 0
                
                try:
                    # ========== 阶段1：并行执行物种叙事 + 适应性演化 ==========
                    logger.info(f"[AI并行] 开始阶段1: {ai_task_names[0]} (1/{total_tasks})...")
                    self._emit_event("ai_progress", f"🔄 并行执行: {ai_task_names[0]}", "AI",
                                    total=total_tasks, completed=completed_count, current_task=ai_task_names[0])
                    
                    # 准备物种数据（包含AI状态评估结果）
                    species_narrative_data = []
                    
                    # Critical物种
                    for result in critical_results:
                        events = []
                        if hasattr(result, 'death_causes') and result.death_causes:
                            events.append(f"主要压力: {result.death_causes}")
                        species_narrative_data.append({
                            "species": result.species,
                            "tier": "critical",
                            "death_rate": result.death_rate,
                            "status_eval": getattr(result, 'ai_status_eval', None),
                            "events": events,
                        })
                    
                    # Focus物种
                    for result in focus_results:
                        events = []
                        if hasattr(result, 'death_causes') and result.death_causes:
                            events.append(f"主要压力: {result.death_causes}")
                        species_narrative_data.append({
                            "species": result.species,
                            "tier": "focus",
                            "death_rate": result.death_rate,
                            "status_eval": getattr(result, 'ai_status_eval', None),
                            "events": events,
                        })
                    
                    # 定义并行任务协程
                    async def run_narrative_task():
                        """物种叙事任务"""
                        if not species_narrative_data:
                            return []
                        global_env = "; ".join([
                            f"{k}: {v:.1f}" for k, v in modifiers.items() if abs(v) > 0.1
                        ]) or "环境稳定"
                        major_events_str = ", ".join([e.kind for e in major_events]) if major_events else "无"
                        
                        return await asyncio.wait_for(
                            self.ai_pressure_service.generate_species_narratives(
                                species_narrative_data,
                                self.turn_counter,
                                global_env,
                                major_events_str,
                            ),
                            timeout=180  # 3分钟超时
                        )
                    
                    async def run_adaptation_task():
                        """适应性演化任务"""
                        return await asyncio.wait_for(
                            self.adaptation_service.apply_adaptations_async(
                                species_batch, modifiers, self.turn_counter, pressures,
                                mortality_results=combined_results  # 【新增】传递死亡率结果（含植物压力）
                            ),
                            timeout=300  # 5分钟超时
                        )
                    
                    # 【核心优化】并行执行两个任务
                    parallel_results = await asyncio.gather(
                        run_narrative_task(),
                        run_adaptation_task(),
                        return_exceptions=True  # 单个任务失败不影响其他任务
                    )
                    
                    # 处理并行结果
                    narrative_result, adaptation_result = parallel_results
                    
                    # 处理叙事结果
                    if isinstance(narrative_result, Exception):
                        if isinstance(narrative_result, asyncio.TimeoutError):
                            logger.error(f"[AI并行] 物种叙事超时")
                        else:
                            logger.error(f"[AI并行] 物种叙事失败: {narrative_result}")
                        narrative_results = []
                    else:
                        narrative_results = narrative_result or []
                        # 将叙事结果应用到物种结果中
                        narrative_map = {nr.lineage_code: nr for nr in narrative_results}
                        for result in critical_results + focus_results:
                            code = result.species.lineage_code
                            if code in narrative_map:
                                nr = narrative_map[code]
                                result.ai_narrative = nr.narrative
                                result.ai_headline = nr.headline
                                result.ai_mood = nr.mood
                        logger.info(f"[AI并行] 物种叙事完成: {len(narrative_results)} 个")
                    
                    # 处理适应性结果
                    if isinstance(adaptation_result, Exception):
                        if isinstance(adaptation_result, asyncio.TimeoutError):
                            logger.error(f"[AI并行] 适应性演化超时")
                        else:
                            logger.error(f"[AI并行] 适应性演化失败: {adaptation_result}")
                        adaptation_events = []
                    else:
                        adaptation_events = adaptation_result or []
                        logger.info(f"[AI并行] 适应性演化完成: {len(adaptation_events)} 个")
                    
                    completed_count += 1
                    logger.info(f"[AI并行] 阶段1完成 ({completed_count}/{total_tasks})")
                    self._emit_event("ai_progress", f"✅ {ai_task_names[0]} 完成", "AI",
                                    total=total_tasks, completed=completed_count, current_task=ai_task_names[1])
                    
                    # ========== 阶段2：顺序执行物种分化 ==========
                    logger.info(f"[AI并行] 开始阶段2: {ai_task_names[1]} (2/{total_tasks})...")
                    self._emit_event("ai_progress", f"🔄 正在执行: {ai_task_names[1]}", "AI",
                                    total=total_tasks, completed=completed_count, current_task=ai_task_names[1])
                    
                    # 【Embedding集成】获取演化提示辅助分化决策
                    if self._use_embedding_integration:
                        try:
                            evolution_hints = {}
                            # 将环境修改器映射到压力向量类型
                            pressure_vectors = self.embedding_integration.map_pressures_to_vectors(modifiers)
                            
                            # 为高演化潜力的物种获取演化提示
                            for result in critical_results + focus_results:
                                sp = result.species
                                # 只为种群较大、死亡率中等的物种获取提示（分化候选）
                                pop = sp.morphology_stats.get("population", 0)
                                if pop > 5000 and 0.05 < result.death_rate < 0.5:
                                    hint = self.embedding_integration.get_evolution_hints(
                                        sp, pressure_vectors
                                    )
                                    if hint:
                                        evolution_hints[sp.lineage_code] = hint
                            
                            if evolution_hints:
                                self.speciation.set_evolution_hints(evolution_hints)
                                logger.info(f"[Embedding集成] 为 {len(evolution_hints)} 个物种提供演化提示")
                        except Exception as e:
                            logger.warning(f"[Embedding集成] 获取演化提示失败: {e}")
                    
                    try:
                        branching = await asyncio.wait_for(
                            self.speciation.process_async(
                                mortality_results=critical_results + focus_results,
                                existing_codes={s.lineage_code for s in species_batch},
                                average_pressure=sum(modifiers.values()) / (len(modifiers) or 1),
                                turn_index=self.turn_counter,
                                map_changes=map_changes,
                                major_events=major_events,
                                pressures=pressures,
                                trophic_interactions=trophic_interactions,
                            ),
                            timeout=600  # 10分钟超时
                        )
                        completed_count += 1
                        logger.info(f"[AI并行] 阶段2完成 ({completed_count}/{total_tasks})")
                    except asyncio.TimeoutError:
                        logger.error(f"[AI并行] {ai_task_names[1]} 超时")
                        branching = []
                        completed_count += 1
                        self._emit_event("ai_progress", f"⏱️ {ai_task_names[1]} 超时", "AI",
                                        total=total_tasks, completed=completed_count, current_task="完成")
                    except Exception as e:
                        logger.error(f"[AI并行] {ai_task_names[1]} 失败: {e}")
                        branching = []
                        completed_count += 1
                    
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                
                # 发送完成事件
                self._emit_event(
                    "ai_progress",
                    f"AI任务全部完成",
                    "AI",
                    total=total_tasks,
                    completed=total_tasks,
                    current_task="完成"
                )
                
                logger.info(f"[AI并行] 全部AI任务处理完成")
                
                # 处理适应性演化结果 (更新DB)
                # 注意：adaptation_service 已经在内部更新了 species 对象的属性，但我们需要在此处确保持久化
                # (apply_adaptations_async 的实现通常包含 upsert，再次检查)
                if adaptation_events:
                    logger.info(f"适应演化完成: {len(adaptation_events)}个物种发生变化")
                    self._emit_event("info", f"适应演化完成: {len(adaptation_events)}个物种发生变化", "进化")
                    for event in adaptation_events:
                        detail = f"{event['common_name']}: {event['type']} - {list(event['changes'].keys())}"
                        # print(f"  - {detail}")
                        self._emit_event("adaptation", f"🧬 进化: {detail}", "适应")
                    # 确保保存更新
                    for species in species_batch:
                        species_repository.upsert(species)
                
                # 处理分化结果 (新增物种加入)
                logger.info(f"分化事件数: {len(branching)}")
                self._emit_event("info", f"分化事件数: {len(branching)}", "物种")
                
                if branching:
                    logger.info(f"将新分化物种加入物种列表...")
                    all_species_updated = species_repository.list_species()
                    new_species = [sp for sp in all_species_updated if sp.status == "alive" and sp.lineage_code not in {s.lineage_code for s in species_batch}]
                    
                    if new_species:
                        # 直接使用分化时分配的初始种群
                        for sp in new_species:
                            pop = int(sp.morphology_stats.get("population", 0))
                            logger.info(f"  - {sp.common_name}: 初始人口 {pop:,}")
                            self._emit_event("speciation", f"🌱 新物种: {sp.common_name} (从 {sp.parent_code} 分化)", "分化")
                            
                            # 【Embedding集成】记录分化事件
                            if self._use_embedding_integration:
                                try:
                                    parent_sp = next(
                                        (s for s in species_batch if s.lineage_code == sp.parent_code), 
                                        None
                                    )
                                    if parent_sp:
                                        self.embedding_integration.on_speciation(
                                            self.turn_counter, parent_sp, [sp],
                                            trigger_reason="环境压力分化"
                                        )
                                except Exception as e:
                                    logger.warning(f"[Embedding集成] 记录分化事件失败: {e}")
                        
                        # 更新 species_batch 以包含新物种
                        species_batch.extend(new_species)
                        logger.info(f"新物种已加入，物种总数: {len(species_batch)}")
                
                
                # 10. 背景物种管理
                
                
                # 10. 背景物种管理
                logger.info(f"背景物种管理...")
                self._emit_event("stage", "🌾 背景物种管理", "生态")
                background_summary = self.background_manager.summarize(background_results)
                mass_extinction = self.background_manager.detect_mass_extinction(
                    combined_results
                )
                reemergence = []
                if mass_extinction:
                    promoted = self.background_manager.promote_candidates(background_results)
                    if promoted:
                        reemergence = self._rule_based_reemergence(promoted, modifiers)
                
                # 注意：步骤11（迁徙）已经在阶段2完成（Line 276-298），此处不再重复
                
                # 11. 构建报告 (Async)
                logger.info(f"构建回合报告 (AI)...")
                self._emit_event("stage", "📝 构建回合报告 (AI)", "报告")
                
                # 定义流式回调函数
                async def on_narrative_chunk(chunk: str):
                    self._emit_event("narrative_token", chunk, "报告")

                # 【优化】缩短超时时间，快速降级确保游戏流畅
                # 报告生成最多等待45秒，超时后立即降级为模板模式
                try:
                    self._emit_event("stage", "📝 生成回合报告...", "报告")
                    report = await asyncio.wait_for(
                        self._build_report_async(
                            combined_results,
                            pressures,
                            branching,
                            background_summary,
                            reemergence,
                            major_events,
                            map_changes,
                            migration_events,
                            stream_callback=on_narrative_chunk,
                        ),
                        timeout=45  # 缩短到45秒，快速降级
                    )
                    self._emit_event("stage", "✅ 报告生成完成", "报告")
                except asyncio.TimeoutError:
                    logger.warning(f"[报告生成] 超时（45秒），转为模板模式")
                    self._emit_event("warning", "⏱️ AI响应超时，使用快速模式", "报告")
                    # 禁用LLM润色，直接使用模板生成
                    self.report_builder.enable_llm_polish = False
                    try:
                        report = await asyncio.wait_for(
                            self._build_report_async(
                                combined_results,
                                pressures,
                                branching,
                                background_summary,
                                reemergence,
                                major_events,
                                map_changes,
                                migration_events,
                                stream_callback=None, 
                            ),
                            timeout=30  # 模板模式超时增加到30秒
                        )
                        if not report.narrative:
                            report.narrative = "由于 AI 响应超时，本回合使用简报模式。"
                        self._emit_event("stage", "✅ 快速报告生成完成", "报告")
                    except asyncio.TimeoutError:
                        # 模板模式也超时，生成最基本的报告
                        logger.warning(f"[报告生成] 模板模式也超时，使用最简报告")
                        self._emit_event("warning", "⏱️ 模板模式超时，使用最简报告", "报告")
                        report = TurnReport(
                            turn_index=self.turn_counter,
                            narrative="⚠️ 由于网络问题，本回合报告生成超时。演化数据已正常保存，您可以在物种面板查看详细信息。",
                            pressures_summary="报告生成超时，环境压力摘要不可用。",
                            species=[],
                            branching_events=[],
                            major_events=major_events,
                        )
                        self._emit_event("stage", "✅ 最简报告生成完成", "报告")
                    finally:
                        # 恢复LLM润色设置
                        self.report_builder.enable_llm_polish = True
                
                # 12. 保存地图快照
                # 【修复】重新查询数据库获取最新物种列表
                # 这样可以正确处理：
                # - 本回合灭绝的物种（清除其栖息地记录）
                # - 本回合新分化的物种（初始化其栖息地记录）
                logger.info(f"保存地图栖息地快照...")
                self._emit_event("stage", "💾 保存地图快照", "系统")
                all_species_final = species_repository.list_species()
                self.map_manager.snapshot_habitats(
                    all_species_final, turn_index=self.turn_counter
                )
                
                # 12.0 【新增】根据植物分布更新地块覆盖物
                # 随着植物物种增多，地块覆盖物从裸地变为草原、森林等
                logger.info(f"更新植被覆盖...")
                self._emit_event("stage", "🌿 更新植被覆盖", "环境")
                try:
                    tiles = environment_repository.list_tiles()
                    habitats = environment_repository.latest_habitats()
                    species_map = {sp.id: sp for sp in all_species_final if sp.id}
                    
                    updated_tiles = vegetation_cover_service.update_vegetation_cover(
                        tiles, habitats, species_map
                    )
                    if updated_tiles:
                        environment_repository.upsert_tiles(updated_tiles)
                        logger.info(f"[植被覆盖] 更新了 {len(updated_tiles)} 个地块的覆盖物")
                except Exception as e:
                    logger.warning(f"[植被覆盖] 更新失败: {e}")
                
                # 12.1 保存人口快照（用于族谱视图的当前/峰值人口）
                # 【修复】使用最新物种列表，确保：
                # - 灭绝物种保存 population=0 的快照
                # - 新分化物种也保存快照
                logger.info(f"保存人口快照...")
                self._save_population_snapshots(all_species_final, self.turn_counter)
                
                # 【Embedding集成】记录灭绝事件
                if self._use_embedding_integration:
                    try:
                        for result in combined_results:
                            if result.species.status == "extinct":
                                # 【修复】正确获取死因：优先使用death_causes，否则使用灭绝原因
                                cause = ""
                                if hasattr(result, 'death_causes') and result.death_causes:
                                    cause = result.death_causes
                                elif result.species.morphology_stats.get("extinction_reason"):
                                    cause = result.species.morphology_stats["extinction_reason"]
                                else:
                                    cause = f"死亡率{result.death_rate:.1%}"
                                
                                self.embedding_integration.on_extinction(
                                    self.turn_counter,
                                    result.species,
                                    cause=cause
                                )
                    except Exception as e:
                        logger.warning(f"[Embedding集成] 记录灭绝事件失败: {e}")
                
                # 【Embedding集成】回合结束钩子 - 更新分类树、导出数据
                embedding_turn_data = {}
                if self._use_embedding_integration:
                    try:
                        embedding_turn_data = self.embedding_integration.on_turn_end(
                            self.turn_counter, species_batch
                        )
                        if embedding_turn_data.get("taxonomy"):
                            logger.info(f"[Embedding集成] 分类树已更新")
                    except Exception as e:
                        logger.warning(f"[Embedding集成] 回合结束钩子失败: {e}")
                
                # 14. 保存历史记录
                logger.info(f"保存历史记录...")
                self._emit_event("stage", "💾 保存历史记录", "系统")
                
                # 将 embedding 集成数据添加到报告中（可选）
                record_data = report.model_dump(mode="json")
                if embedding_turn_data:
                    record_data["embedding_integration"] = {
                        "has_taxonomy": "taxonomy" in embedding_turn_data,
                        "has_narrative": "narrative" in embedding_turn_data,
                    }
                
                history_repository.log_turn(
                    TurnLog(
                        turn_index=report.turn_index,
                        pressures_summary=report.pressures_summary,
                        narrative=report.narrative,
                        record_data=record_data,
                    )
                )
                
                # 15. 导出数据
                logger.info(f"导出数据...")
                self._emit_event("stage", "💾 导出数据", "系统")
                self.exporter.export_turn(report, species_batch)
                
                # 16. 【关键修复】更新 MapState.turn_index（确保回合数持久化）
                map_state_for_update = environment_repository.get_state()
                if map_state_for_update:
                    map_state_for_update.turn_index = self.turn_counter
                    environment_repository.save_state(map_state_for_update)
                    logger.debug(f"MapState.turn_index 已更新为 {self.turn_counter}")
                
                self.turn_counter += 1
                reports.append(report)
                logger.info(f"回合 {report.turn_index} 完成")
                # 【优化】发送详细的完成信息，让前端知道进度
                self._emit_event("turn_complete", f"✅ 回合 {report.turn_index} 完成，正在返回数据...", "系统")
                
            except Exception as e:
                logger.error(f"回合 {turn_num + 1} 执行失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                
                # 继续执行下一回合，不要完全中断
                continue
                
        logger.info(f"所有回合完成，共生成 {len(reports)} 个报告")
        return reports

    # 保留 run_turns 方法以兼容旧调用
    def run_turns(self, *args, **kwargs):
        raise NotImplementedError("Use run_turns_async instead")
    
    def _save_population_snapshots(self, species_list: list, turn_index: int) -> None:
        """保存人口快照到数据库（用于族谱视图的当前/峰值人口）
        
        【重要】必须为所有物种保存快照，包括灭绝物种（population=0）
        这样族谱视图才能正确显示"当前规模=0"
        """
        from ..models.species import PopulationSnapshot
        
        snapshots = []
        for species in species_list:
            if species.id is None:
                continue
            
            population = int(species.morphology_stats.get("population", 0) or 0)
            
            # 【修复】不再跳过 population <= 0 的物种
            # 灭绝物种也需要记录 population=0 的快照
            # 这样族谱的"当前规模"才能正确显示
            
            snapshots.append(PopulationSnapshot(
                species_id=species.id,
                turn_index=turn_index,
                region_id=0,  # 全局快照
                count=population,
                death_count=0,
                survivor_count=population,
                population_share=0.0,
                ecological_pressure={}
            ))
        
        if snapshots:
            species_repository.add_population_snapshots(snapshots)
            logger.info(f"[人口快照] 保存了 {len(snapshots)} 条记录 (回合 {turn_index})")

    async def _build_report_async(
        self,
        mortality,
        pressures,
        branching_events,
        background_summary,
        reemergence_events,
        major_events,
        map_changes,
        migration_events,
        stream_callback=None,
    ) -> TurnReport:
        species_snapshots: list[SpeciesSnapshot] = []
        # 【修复】确保种群数量在JavaScript安全整数范围内
        MAX_SAFE_POPULATION = 9_007_199_254_740_991  # JavaScript安全整数上限
        def safe_pop(sp):
            raw = sp.morphology_stats.get("population", 0) or 0
            return max(0, min(int(raw), MAX_SAFE_POPULATION))
        total_pop = sum(safe_pop(item.species) for item in mortality)
        for item in mortality:
            population = safe_pop(item.species)
            share = (population / total_pop) if total_pop else 0
            species_snapshots.append(
                SpeciesSnapshot(
                    lineage_code=item.species.lineage_code,
                    latin_name=item.species.latin_name,
                    common_name=item.species.common_name,
                    population=population,
                    population_share=share,
                    deaths=item.deaths,
                    death_rate=item.death_rate,
                    ecological_role=item.species.description,
                    status=item.species.status,
                    notes=item.notes,
                    niche_overlap=item.niche_overlap,
                    resource_pressure=item.resource_pressure,
                    is_background=item.is_background,
                    tier=item.tier,
                    trophic_level=item.species.trophic_level,
                    grazing_pressure=item.grazing_pressure,
                    predation_pressure=item.predation_pressure,
                    ai_narrative=item.ai_narrative if item.ai_narrative else None,  # 【新增】物种叙事
                )
            )
        
        ecosystem_metrics = self._compute_ecosystem_metrics(mortality)
        
        # 【新增】提取物种详情（器官、能力、里程碑等）用于明星物种展示
        species_details = {}
        for item in mortality:
            sp = item.species
            species_details[sp.lineage_code] = {
                'organs': sp.organs or {},
                'capabilities': sp.capabilities or [],
                'abstract_traits': sp.abstract_traits or {},
                'achieved_milestones': getattr(sp, 'achieved_milestones', []) or [],
                'life_form_stage': getattr(sp, 'life_form_stage', 0),
                'growth_form': getattr(sp, 'growth_form', ''),
                'trophic_level': sp.trophic_level,
                'habitat_type': sp.habitat_type,
                'history_highlights': getattr(sp, 'history_highlights', []) or [],
            }
        
        # 【优化】V2报告生成器支持纪录片旁白风格
        narrative = await self.report_builder.build_turn_narrative_async(
            species_snapshots,
            pressures,
            background_summary,
            reemergence_events,
            major_events,
            map_changes,
            migration_events,
            branching_events=branching_events,
            stream_callback=stream_callback,
            species_details=species_details,
            turn_index=self.turn_counter,  # 【新增】传递回合索引用于纪录片叙事
        )
        
        # 获取当前地图状态（确保读取最新更新的状态）
        map_state = environment_repository.get_state()
        sea_level = map_state.sea_level if map_state else 0.0
        global_temp = map_state.global_avg_temperature if map_state else 15.0
        tectonic_stage = map_state.stage_name if map_state else "稳定期"
        
        # 如果有地图变化事件，从第一个事件中提取阶段信息（更准确）
        if map_changes and len(map_changes) > 0:
            tectonic_stage = map_changes[0].stage
        
        return TurnReport(
            turn_index=self.turn_counter,
            pressures_summary="; ".join(p.narrative for p in pressures),
            narrative=narrative,
            species=species_snapshots,
            branching_events=branching_events,
            background_summary=background_summary,
            reemergence_events=reemergence_events,
            major_events=major_events,
            map_changes=map_changes,
            migration_events=migration_events,
            sea_level=sea_level,
            global_temperature=global_temp,
            tectonic_stage=tectonic_stage,
            ecosystem_metrics=ecosystem_metrics,
        )

    def _update_populations(self, mortality_results) -> None:
        """【已废弃】旧的种群更新方法，保留用于兼容。
        
        新逻辑在 run_turns_async 中直接计算种群变化。
        """
        # 不再使用此方法进行种群更新
        # 只保留灭绝检查
        pass
    
    def _update_populations_extinction_check(
        self, 
        mortality_results, 
        final_populations: dict[str, int]
    ) -> None:
        """检测灭绝条件并更新物种状态。
        
        【平衡修复v2】降低灭绝阈值，让高压力真正导致灭绝
        
        灭绝条件（50万年时间尺度）：
        - 单回合死亡率≥80%：灾难性死亡，直接灭绝（原90%）
        - 死亡率≥60%且连续2回合：种群衰退严重，灭绝（原70%）
        - 死亡率≥50%且连续3回合：长期不适应环境，灭绝（原60%）
        - 死亡率≥40%且连续4回合：慢性衰退，灭绝（新增）
        - 种群<100且死亡率>40%：种群过小，无法恢复（原50%）
        
        Args:
            mortality_results: 死亡率计算结果
            final_populations: 最终种群数量 {lineage_code: population}
        """
        for item in mortality_results:
            species = item.species
            final_pop = final_populations.get(species.lineage_code, 0)
            death_rate = item.death_rate
            streak_key = "mortality_streak"
            mortality_streak = int(species.morphology_stats.get(streak_key, 0) or 0)
            
            # 【平衡v2】追踪连续高死亡率（从60%降到40%开始计数）
            if death_rate >= 0.40:
                mortality_streak += 1
            else:
                mortality_streak = 0
            species.morphology_stats[streak_key] = mortality_streak
            
            extinction_triggered = False
            extinction_reason = ""
            
            # 【平衡v2】条件1：单回合死亡率≥80%（原90%）
            if death_rate >= 0.80:
                extinction_triggered = True
                extinction_reason = f"单回合死亡率{death_rate:.1%}，种群崩溃"
            # 【平衡v2】条件2：死亡率≥60%且连续2回合（原70%）
            elif death_rate >= 0.60 and mortality_streak >= 2:
                extinction_triggered = True
                extinction_reason = f"连续{mortality_streak}回合高死亡率（≥60%），种群衰退"
            # 【平衡v2】条件3：死亡率≥50%且连续3回合（原60%）
            elif death_rate >= 0.50 and mortality_streak >= 3:
                extinction_triggered = True
                extinction_reason = f"连续{mortality_streak}回合中高死亡率（≥50%），长期不适应环境"
            # 【新增】条件4：死亡率≥40%且连续4回合（慢性衰退）
            elif death_rate >= 0.40 and mortality_streak >= 4:
                extinction_triggered = True
                extinction_reason = f"连续{mortality_streak}回合持续衰退（≥40%），无法恢复"
            # 【平衡v2】条件5：种群过小且死亡率>40%（原50%）
            elif final_pop < 100 and death_rate > 0.40:
                extinction_triggered = True
                extinction_reason = f"种群过小({final_pop})且死亡率高({death_rate:.1%})，无法恢复"
            
            # 执行灭绝
            if extinction_triggered and species.status == "alive":
                logger.info(f"[灭绝] {species.common_name} ({species.lineage_code}): {extinction_reason}")
                self._emit_event("extinction", f"💀 灭绝: {species.common_name} - {extinction_reason}", "死亡")
                species.status = "extinct"
                species.morphology_stats["population"] = 0
                species.morphology_stats["extinction_turn"] = self.turn_counter
                species.morphology_stats["extinction_reason"] = extinction_reason
                
                # 记录灭绝事件
                from ..models.species import LineageEvent
                species_repository.log_event(
                    LineageEvent(
                        lineage_code=species.lineage_code,
                        event_type="extinction",
                        payload={
                            "turn": self.turn_counter,
                            "reason": extinction_reason,
                            "final_population": final_pop,
                            "death_rate": death_rate,
                        }
                    )
                )
                species_repository.upsert(species)

    def _rule_based_reemergence(self, candidates, modifiers):
        """基于规则筛选背景物种重现。
        
        筛选标准：
        1. 种群数量相对较大（前30%）
        2. 基因多样性高（>0.7）
        3. 适应性强（environment_sensitivity < 0.5）
        4. 与当前压力匹配的特性
        """
        if not candidates:
            return []
        
        # 计算每个候选物种的潜力分数
        scored_candidates: list[tuple[Species, float, str]] = []
        
        for species in candidates:
            population = species.morphology_stats.get("population", 0)
            gene_div = species.hidden_traits.get("gene_diversity", 0.5)
            env_sens = species.hidden_traits.get("environment_sensitivity", 0.5)
            evo_pot = species.hidden_traits.get("evolution_potential", 0.5)
            
            # 基础分数：种群规模（对数）+ 基因多样性
            import math
            score = math.log1p(population) * 0.3 + gene_div * 30 + (1 - env_sens) * 20 + evo_pot * 20
            
            # 分析与当前压力的匹配度
            reason_parts = []
            match_bonus = 0
            
            if "temperature" in modifiers:
                cold_res = species.abstract_traits.get("耐寒性", 5)
                heat_res = species.abstract_traits.get("耐热性", 5)
                if cold_res >= 7 or heat_res >= 7:
                    match_bonus += 10
                    reason_parts.append("温度适应性强")
            
            if "drought" in modifiers:
                drought_res = species.abstract_traits.get("耐旱性", 5)
                if drought_res >= 7:
                    match_bonus += 10
                    reason_parts.append("高耐旱性")
            
            # 检查是否有独特生态位
            desc = species.description.lower()
            if any(kw in desc for kw in ("极端", "深海", "化能", "特殊")):
                match_bonus += 5
                reason_parts.append("占据独特生态位")
            
            score += match_bonus
            
            # 生成理由
            if not reason_parts:
                reason_parts.append("基因多样性高" if gene_div > 0.7 else "种群规模稳定")
            reason = f"灾变后生态位空缺，该物种{reason_parts[0]}，具备重新扩张潜力"
            
            scored_candidates.append((species, score, reason))
        
        # 按分数排序，取前30%
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        num_to_select = max(1, len(scored_candidates) // 3)
        
        events = []
        for species, score, reason in scored_candidates[:num_to_select]:
            species.is_background = False
            species_repository.upsert(species)
            events.append(
                ReemergenceEvent(
                    lineage_code=species.lineage_code,
                    reason=reason,
                )
            )
        
        return events
    
    def _apply_gene_flow(self, species_batch: list) -> int:
        """应用基因流动"""
        genus_groups = {}
        for species in species_batch:
            if not species.genus_code:
                continue
            if species.genus_code not in genus_groups:
                genus_groups[species.genus_code] = []
            genus_groups[species.genus_code].append(species)
        
        total_flow_count = 0
        for genus_code, species_list in genus_groups.items():
            if len(species_list) <= 1:
                continue
            
            genus = genus_repository.get_by_code(genus_code)
            if not genus:
                continue
            
            flow_count = self.gene_flow_service.apply_gene_flow(genus, species_list)
            total_flow_count += flow_count
        
        return total_flow_count
    
    def _apply_genetic_drift(self, species_batch: list) -> int:
        """应用遗传漂变
        
        【平衡优化v2】每回合对同属物种间的遗传距离增加漂变量，
        模拟50万年时间内的突变积累。
        
        这使得即使有基因交流，物种间的遗传距离也会逐渐增加，
        最终超过基因交流阈值，实现真正的分化。
        
        Returns:
            更新了遗传距离的属数量
        """
        from ..core.config import get_settings
        _settings = get_settings()
        drift_per_turn = _settings.genetic_drift_per_turn  # 默认0.008
        
        # 按属分组
        genus_codes = set()
        for species in species_batch:
            if species.genus_code and species.status == "alive":
                genus_codes.add(species.genus_code)
        
        updated_count = 0
        for genus_code in genus_codes:
            genus = genus_repository.get_by_code(genus_code)
            if not genus or not genus.genetic_distances:
                continue
            
            # 对所有距离增加漂变量
            new_distances = {}
            for key, dist in genus.genetic_distances.items():
                # 漂变量随距离衰减（距离远的物种漂变效应小）
                effective_drift = drift_per_turn * (1.0 - dist * 0.3)
                new_dist = min(1.0, dist + effective_drift)
                new_distances[key] = new_dist
            
            if new_distances:
                genus_repository.update_distances(genus_code, new_distances, self.turn_counter)
                updated_count += 1
                logger.debug(f"[遗传漂变] {genus_code}属更新了{len(new_distances)}对物种的遗传距离")
        
        return updated_count
    
    async def _check_auto_hybridization_async(self, species_batch: list, turn_index: int) -> list:
        """异步自动杂交检测（使用AI生成杂交物种）
        
        【平衡优化v2】每回合检测同属近缘物种，有一定概率自动产生杂交种。
        这让杂交不再只是玩家手动操作，而是自然发生的演化事件。
        【AI集成】使用LLM生成杂交物种的名称、描述和属性。
        
        条件：
        1. 同属物种
        2. 遗传距离 < 杂交阈值
        3. 地理分布有重叠
        4. 随机概率检测
        
        Returns:
            新产生的杂交种列表
        """
        import random
        from ..core.config import get_settings
        from ..services.species.hybridization import HybridizationService
        from ..services.species.genetic_distance import GeneticDistanceCalculator
        
        _settings = get_settings()
        auto_chance = _settings.auto_hybridization_chance  # 默认0.08
        
        # 初始化杂交服务（传入router以启用AI生成，传入embeddings以支持语义距离）
        genetic_calc = GeneticDistanceCalculator(embedding_service=self.embeddings)
        hybrid_service = HybridizationService(genetic_calc, router=self.router)
        
        # 按属分组
        genus_groups = {}
        for species in species_batch:
            if species.status != "alive" or not species.genus_code:
                continue
            if species.genus_code not in genus_groups:
                genus_groups[species.genus_code] = []
            genus_groups[species.genus_code].append(species)
        
        new_hybrids = []
        
        # 收集已存在的编码（用于杂交种编码生成）
        existing_codes = {sp.lineage_code for sp in species_batch}
        
        # 收集待处理的杂交任务
        hybridization_tasks = []
        
        for genus_code, species_list in genus_groups.items():
            if len(species_list) < 2:
                continue
            
            genus = genus_repository.get_by_code(genus_code)
            if not genus:
                continue
            
            # 检查每对物种
            for i, sp1 in enumerate(species_list):
                for sp2 in species_list[i+1:]:
                    # 随机概率检测
                    if random.random() > auto_chance:
                        continue
                    
                    # 检查杂交可行性
                    distance_key = f"{min(sp1.lineage_code, sp2.lineage_code)}-{max(sp1.lineage_code, sp2.lineage_code)}"
                    distance = genus.genetic_distances.get(distance_key, 0.5)
                    
                    can_hybrid, fertility = hybrid_service.can_hybridize(sp1, sp2, distance)
                    if not can_hybrid:
                        continue
                    
                    # 种群检查：双方都需要有一定种群
                    pop1 = sp1.morphology_stats.get("population", 0) or 0
                    pop2 = sp2.morphology_stats.get("population", 0) or 0
                    if pop1 < 100 or pop2 < 100:
                        continue
                    
                    # 添加到任务列表
                    hybridization_tasks.append({
                        "sp1": sp1,
                        "sp2": sp2,
                        "distance": distance,
                        "fertility": fertility,
                        "pop1": pop1,
                        "pop2": pop2,
                    })
                    
                    # 每属每回合最多产生1个自动杂交种
                    break
                else:
                    continue
                break
        
        # 批量处理杂交任务（使用异步AI调用）
        for task in hybridization_tasks:
            sp1, sp2 = task["sp1"], task["sp2"]
            distance, fertility = task["distance"], task["fertility"]
            pop1, pop2 = task["pop1"], task["pop2"]
            
            # 异步创建杂交种（传入现有编码集合以生成唯一编码）
            hybrid = await hybrid_service.create_hybrid_async(
                sp1, sp2, turn_index, distance, existing_codes
            )
            if hybrid:
                # 将新生成的编码加入集合，防止重复
                existing_codes.add(hybrid.lineage_code)
                # 设置初始种群（较小的亲本种群的10%）
                initial_pop = int(min(pop1, pop2) * 0.1)
                hybrid.morphology_stats["population"] = max(50, initial_pop)
                
                species_repository.upsert(hybrid)
                new_hybrids.append(hybrid)
                
                logger.info(
                    f"[自动杂交] {sp1.common_name} × {sp2.common_name} "
                    f"产生杂交种 {hybrid.common_name} (可育性:{fertility:.0%})"
                )
                self._emit_event(
                    "info", 
                    f"🧬 自然杂交！{sp1.common_name} × {sp2.common_name} → {hybrid.common_name}",
                    "杂交"
                )
        
        return new_hybrids
    
    def _check_subspecies_promotion(self, species_batch: list, turn_index: int) -> int:
        """检查亚种是否应晋升为独立种"""
        promotion_count = 0
        
        for species in species_batch:
            if species.taxonomic_rank != "subspecies":
                continue
            
            divergence_turns = turn_index - species.created_turn
            
            # 【平衡优化v2】缩短晋升时间从15回合到10回合
            if divergence_turns >= 10:
                species.taxonomic_rank = "species"
                species_repository.upsert(species)
                promotion_count += 1
                logger.debug(f"  - {species.common_name} ({species.lineage_code}) 晋升为独立种")
        
        return promotion_count
    
    def _update_intervention_status(self, species_batch: list) -> None:
        """更新玩家干预状态（递减保护/压制回合数）"""
        for species in species_batch:
            updated = False
            
            # 处理保护状态
            is_protected = getattr(species, 'is_protected', False) or False
            protection_turns = getattr(species, 'protection_turns', 0) or 0
            
            if is_protected and protection_turns > 0:
                species.protection_turns = protection_turns - 1
                if species.protection_turns <= 0:
                    species.is_protected = False
                    species.protection_turns = 0
                    logger.info(f"[干预结束] {species.common_name} 的保护状态已结束")
                    self._emit_event("info", f"🛡️ {species.common_name} 的保护已结束", "干预")
                updated = True
            
            # 处理压制状态
            is_suppressed = getattr(species, 'is_suppressed', False) or False
            suppression_turns = getattr(species, 'suppression_turns', 0) or 0
            
            if is_suppressed and suppression_turns > 0:
                species.suppression_turns = suppression_turns - 1
                if species.suppression_turns <= 0:
                    species.is_suppressed = False
                    species.suppression_turns = 0
                    logger.info(f"[干预结束] {species.common_name} 的压制状态已结束")
                    self._emit_event("info", f"⚔️ {species.common_name} 的压制已结束", "干预")
                updated = True
            
            if updated:
                species_repository.upsert(species)
