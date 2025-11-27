from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
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
from ..services.species.background import BackgroundSpeciesManager
from ..services.species.gene_activation import GeneActivationService
from ..services.species.gene_flow import GeneFlowService
from ..services.analytics.critical_analyzer import CriticalAnalyzer
from ..services.analytics.exporter import ExportService
from ..services.system.embedding import EmbeddingService
from ..services.analytics.focus_processor import FocusBatchProcessor
from ..services.species.habitat_manager import habitat_manager  # 新增：栖息地管理器
from ..services.geo.map_evolution import MapEvolutionService
from ..services.geo.map_manager import MapStateManager
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
        self.turn_counter = 0
        self.watchlist: set[str] = set()
        self._event_callback = None  # 事件回调函数
    
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
                niche_metrics = self.niche_analyzer.analyze(species_batch, habitat_data=all_habitats)
                
                # ========== 【方案B：第一阶段】初步死亡率评估（用于迁徙决策） ==========
                # 5. 第一次死亡率计算（基于当前栖息地）
                logger.info(f"【阶段1】计算营养级互动...")
                self._emit_event("stage", "⚔️ 【阶段1】计算营养级互动与死亡率", "生态")
                trophic_interactions = self._calculate_trophic_interactions(species_batch)
                
                logger.info(f"【阶段1】计算初步死亡率（迁徙前）...")
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
                
                # ========== 【方案B：第二阶段】迁徙执行 ==========
                # 6. 迁徙建议与执行（基于初步死亡率）
                logger.info(f"【阶段2】迁徙建议与执行...")
                self._emit_event("stage", "🦅 【阶段2】迁徙建议与执行", "生态")
                migration_events = self.migration_advisor.plan(
                    preliminary_critical_results + preliminary_focus_results, modifiers, major_events, map_changes
                )
                
                migration_count = 0
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
                    logger.info(f"【阶段2】迁徙执行完成: {migration_count}/{len(migration_events)} 个物种成功迁徙")
                    self._emit_event("info", f"{migration_count} 个物种完成迁徙", "生态")
                else:
                    logger.debug(f"[迁徙] 生成了 {len(migration_events)} 个迁徙建议（未执行或无迁徙）")
                
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
                # 10. 更新种群（应用最终死亡率）
                logger.info(f"更新种群数据...")
                self._emit_event("stage", "💀 更新种群数据", "物种")
                self._update_populations(combined_results)
                
                # 11. 应用繁殖增长（50万年的自然增长）
                logger.info(f"计算繁殖增长...")
                self._emit_event("stage", "🐣 计算繁殖增长", "物种")
                
                # P2: 更新环境动态修正系数（基于本回合的气候变化）
                # 修复：modifiers 是 dict[str, float]，直接获取值
                temp_change = modifiers.get("temperature", 0.0) if modifiers else 0.0
                sea_level_change = 0.0  # 海平面变化在 map_evolution 中单独计算
                if current_map_state:
                    # 从地图状态获取海平面变化（与上回合比较）
                    prev_sea = getattr(current_map_state, '_prev_sea_level', current_map_state.sea_level)
                    sea_level_change = current_map_state.sea_level - prev_sea
                    current_map_state._prev_sea_level = current_map_state.sea_level
                self.reproduction_service.update_environmental_modifier(temp_change, sea_level_change)
                
                survival_rates = {
                    item.species.lineage_code: (1.0 - item.death_rate)
                    for item in combined_results
                }
                niche_data = {
                    code: (metrics.overlap, metrics.saturation)
                    for code, metrics in niche_metrics.items()
                }
                new_populations = self.reproduction_service.apply_reproduction(
                    species_batch, niche_data, survival_rates,
                    habitat_manager=habitat_manager  # P3: 传递habitat_manager用于区域承载力
                )
                # 应用繁殖后的种群数量
                for species in species_batch:
                    if species.lineage_code in new_populations:
                        species.morphology_stats["population"] = new_populations[species.lineage_code]
                        species_repository.upsert(species)
                logger.info(f"繁殖完成，种群更新")
                self._emit_event("info", "繁殖完成，种群更新", "物种")
                
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
                        print(f"  - {detail}")
                        self._emit_event("activation", f"🔓 激活: {detail}", "进化")
                    for species in species_batch:
                        species_repository.upsert(species)
                
                # 8.6. 基因流动
                logger.info(f"应用基因流动...")
                self._emit_event("stage", "🔀 应用基因流动", "进化")
                gene_flow_count = self._apply_gene_flow(species_batch)
                logger.info(f"基因流动完成: {gene_flow_count}对物种发生基因流动")
                self._emit_event("info", f"基因流动完成: {gene_flow_count}对物种发生基因流动", "进化")
                
                # 8.7. 亚种晋升检查
                logger.info(f"检查亚种晋升...")
                self._emit_event("stage", "⬆️ 检查亚种晋升", "物种")
                promotion_count = self._check_subspecies_promotion(species_batch, self.turn_counter)
                if promotion_count > 0:
                    logger.info(f"{promotion_count}个亚种晋升为独立种")
                    self._emit_event("info", f"{promotion_count}个亚种晋升为独立种", "物种")
                
                # 9. 【修改】顺序处理所有AI相关任务（避免并发请求过多导致API卡死）
                # 包括：AI增润、适应性演化、物种分化
                logger.info(f"开始AI顺序任务 (增润 + 适应 + 分化)...")
                self._emit_event("stage", "🔄 AI顺序处理", "AI")
                
                # 定义任务名称
                ai_task_names = [
                    "Critical增润",
                    "Focus增润", 
                    "适应性演化",
                    "物种分化"
                ]
                
                total_tasks = len(ai_task_names)
                
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
                        await asyncio.sleep(3)  # 每3秒发送一次
                        heartbeat_count[0] += 1
                        self._emit_event("ai_heartbeat", f"心跳#{heartbeat_count[0]}", "AI")
                        logger.debug(f"[AI心跳] 已发送第 {heartbeat_count[0]} 次心跳")
                
                heartbeat_task = asyncio.create_task(send_heartbeat())
                
                # 【修改】顺序执行AI任务，避免并发请求过多
                adaptation_events = []
                branching = []
                completed_count = 0
                
                try:
                    # 任务1: Critical增润
                    logger.info(f"[AI顺序] 开始 {ai_task_names[0]} (1/{total_tasks})...")
                    self._emit_event("ai_progress", f"🔄 正在执行: {ai_task_names[0]}", "AI",
                                    total=total_tasks, completed=completed_count, current_task=ai_task_names[0])
                    try:
                        await asyncio.wait_for(
                            self.critical_analyzer.enhance_async(critical_results),
                            timeout=180  # 3分钟超时
                        )
                        completed_count += 1
                        logger.info(f"[AI顺序] {ai_task_names[0]} 完成 ({completed_count}/{total_tasks})")
                        self._emit_event("ai_progress", f"✅ {ai_task_names[0]} 完成", "AI",
                                        total=total_tasks, completed=completed_count, current_task=ai_task_names[1])
                    except asyncio.TimeoutError:
                        logger.error(f"[AI顺序] {ai_task_names[0]} 超时")
                        completed_count += 1
                        self._emit_event("ai_progress", f"⏱️ {ai_task_names[0]} 超时", "AI",
                                        total=total_tasks, completed=completed_count, current_task=ai_task_names[1])
                    except Exception as e:
                        logger.error(f"[AI顺序] {ai_task_names[0]} 失败: {e}")
                        completed_count += 1
                    
                    # 任务2: Focus增润
                    logger.info(f"[AI顺序] 开始 {ai_task_names[1]} (2/{total_tasks})...")
                    self._emit_event("ai_progress", f"🔄 正在执行: {ai_task_names[1]}", "AI",
                                    total=total_tasks, completed=completed_count, current_task=ai_task_names[1])
                    try:
                        await asyncio.wait_for(
                            self.focus_processor.enhance_async(focus_results),
                            timeout=180  # 3分钟超时
                        )
                        completed_count += 1
                        logger.info(f"[AI顺序] {ai_task_names[1]} 完成 ({completed_count}/{total_tasks})")
                        self._emit_event("ai_progress", f"✅ {ai_task_names[1]} 完成", "AI",
                                        total=total_tasks, completed=completed_count, current_task=ai_task_names[2])
                    except asyncio.TimeoutError:
                        logger.error(f"[AI顺序] {ai_task_names[1]} 超时")
                        completed_count += 1
                        self._emit_event("ai_progress", f"⏱️ {ai_task_names[1]} 超时", "AI",
                                        total=total_tasks, completed=completed_count, current_task=ai_task_names[2])
                    except Exception as e:
                        logger.error(f"[AI顺序] {ai_task_names[1]} 失败: {e}")
                        completed_count += 1
                    
                    # 任务3: 适应性演化
                    logger.info(f"[AI顺序] 开始 {ai_task_names[2]} (3/{total_tasks})...")
                    self._emit_event("ai_progress", f"🔄 正在执行: {ai_task_names[2]}", "AI",
                                    total=total_tasks, completed=completed_count, current_task=ai_task_names[2])
                    try:
                        adaptation_events = await asyncio.wait_for(
                            self.adaptation_service.apply_adaptations_async(
                                species_batch, modifiers, self.turn_counter, pressures
                            ),
                            timeout=300  # 5分钟超时（适应性演化可能有多个AI调用）
                        )
                        completed_count += 1
                        logger.info(f"[AI顺序] {ai_task_names[2]} 完成 ({completed_count}/{total_tasks})")
                        self._emit_event("ai_progress", f"✅ {ai_task_names[2]} 完成", "AI",
                                        total=total_tasks, completed=completed_count, current_task=ai_task_names[3])
                    except asyncio.TimeoutError:
                        logger.error(f"[AI顺序] {ai_task_names[2]} 超时")
                        completed_count += 1
                        self._emit_event("ai_progress", f"⏱️ {ai_task_names[2]} 超时", "AI",
                                        total=total_tasks, completed=completed_count, current_task=ai_task_names[3])
                    except Exception as e:
                        logger.error(f"[AI顺序] {ai_task_names[2]} 失败: {e}")
                        completed_count += 1
                    
                    # 任务4: 物种分化
                    logger.info(f"[AI顺序] 开始 {ai_task_names[3]} (4/{total_tasks})...")
                    self._emit_event("ai_progress", f"🔄 正在执行: {ai_task_names[3]}", "AI",
                                    total=total_tasks, completed=completed_count, current_task=ai_task_names[3])
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
                                trophic_interactions=trophic_interactions,  # 传递营养级互动信息
                            ),
                            timeout=600  # 10分钟超时（物种分化可能有很多AI调用）
                        )
                        completed_count += 1
                        logger.info(f"[AI顺序] {ai_task_names[3]} 完成 ({completed_count}/{total_tasks})")
                    except asyncio.TimeoutError:
                        logger.error(f"[AI顺序] {ai_task_names[3]} 超时")
                        branching = []
                        completed_count += 1
                        self._emit_event("ai_progress", f"⏱️ {ai_task_names[3]} 超时", "AI",
                                        total=total_tasks, completed=completed_count, current_task="完成")
                    except Exception as e:
                        logger.error(f"[AI顺序] {ai_task_names[3]} 失败: {e}")
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
                
                logger.info(f"[AI顺序] 全部AI任务处理完成")
                
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

                # 【修复】再次强制加入超时保护，防止报告生成阶段永久卡死
                # 如果AI生成超时，会自动降级为模板生成，确保游戏能继续
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
                            stream_callback=on_narrative_chunk,
                        ),
                        timeout=120
                    )
                except asyncio.TimeoutError:
                    logger.error(f"[报告生成] AI 生成超时，转为使用模板生成")
                    self._emit_event("warning", "AI响应超时，使用简报模式", "报告")
                    # 禁用回调以跳过AI
                    report = await self._build_report_async(
                        combined_results,
                        pressures,
                        branching,
                        background_summary,
                        reemergence,
                        major_events,
                        map_changes,
                        migration_events,
                        stream_callback=None, 
                    )
                    if not report.narrative:
                        report.narrative = "由于 AI 响应超时，本回合详细叙事已省略。"
                
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
                
                # 12.1 保存人口快照（用于族谱视图的当前/峰值人口）
                # 【修复】使用最新物种列表，确保：
                # - 灭绝物种保存 population=0 的快照
                # - 新分化物种也保存快照
                logger.info(f"保存人口快照...")
                self._save_population_snapshots(all_species_final, self.turn_counter)
                
                # 14. 保存历史记录
                logger.info(f"保存历史记录...")
                self._emit_event("stage", "💾 保存历史记录", "系统")
                history_repository.log_turn(
                    TurnLog(
                        turn_index=report.turn_index,
                        pressures_summary=report.pressures_summary,
                        narrative=report.narrative,
                        record_data=report.model_dump(mode="json"),
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
                self._emit_event("turn_complete", f"✅ 回合 {report.turn_index} 完成", "系统")
                
            except Exception as e:
                logger.error(f"回合 {turn_num + 1} 执行失败: {str(e)}")
                import traceback
                print(traceback.format_exc())
                
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
        total_pop = sum(
            item.species.morphology_stats.get("population", 0) for item in mortality
        )
        for item in mortality:
            population = int(item.species.morphology_stats.get("population", 0) or 0)
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
                )
            )
        
        ecosystem_metrics = self._compute_ecosystem_metrics(mortality)
        narrative = await self.report_builder.build_turn_narrative_async(
            species_snapshots,
            pressures,
            background_summary,
            reemergence_events,
            major_events,
            map_changes,
            migration_events,
            stream_callback=stream_callback,
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
        """更新种群数量并检测灭绝条件。
        
        灭绝条件（50万年时间尺度，淘汰更严格）：
        - 单回合死亡率≥90%：灾难性死亡，直接灭绝
        - 死亡率≥70%且连续2回合：种群衰退严重，灭绝
        - 死亡率≥60%且连续3回合：长期不适应环境，灭绝
        
        设计理念：50万年足够让不适应的物种被自然选择淘汰
        """
        for item in mortality_results:
            species = item.species
            current_population = item.survivors
            death_rate = item.death_rate
            streak_key = "mortality_streak"
            mortality_streak = int(species.morphology_stats.get(streak_key, 0) or 0)
            
            # 追踪连续高死亡率（门槛从75%降到60%）
            if death_rate >= 0.60:
                mortality_streak += 1
            else:
                mortality_streak = 0
            species.morphology_stats[streak_key] = mortality_streak
            
            # 【修复】更严格的灭绝条件，让淘汰更快
            extinction_triggered = False
            extinction_reason = ""
            
            # 条件1：单回合死亡率≥90%（从98%降低）
            if death_rate >= 0.90:
                extinction_triggered = True
                extinction_reason = f"单回合死亡率{death_rate:.1%}，种群崩溃"
            # 条件2：死亡率≥70%且连续2回合（从85%降低）
            elif death_rate >= 0.70 and mortality_streak >= 2:
                extinction_triggered = True
                extinction_reason = f"连续{mortality_streak}回合高死亡率（≥70%），种群衰退"
            # 条件3：死亡率≥60%且连续3回合（新增）
            elif death_rate >= 0.60 and mortality_streak >= 3:
                extinction_triggered = True
                extinction_reason = f"连续{mortality_streak}回合中高死亡率（≥60%），长期不适应环境"
            
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
                            "final_population": current_population,
                            "death_rate": death_rate,
                        }
                    )
                )
            else:
                # 正常更新种群
                species.morphology_stats["population"] = current_population
            
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
    
    def _check_subspecies_promotion(self, species_batch: list, turn_index: int) -> int:
        """检查亚种是否应晋升为独立种"""
        promotion_count = 0
        
        for species in species_batch:
            if species.taxonomic_rank != "subspecies":
                continue
            
            divergence_turns = turn_index - species.created_turn
            
            if divergence_turns >= 15:
                species.taxonomic_rank = "species"
                species_repository.upsert(species)
                promotion_count += 1
                print(f"  - {species.common_name} ({species.lineage_code}) 晋升为独立种")
        
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
