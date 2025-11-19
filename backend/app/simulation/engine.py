from __future__ import annotations

from dataclasses import dataclass
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
from ..repositories.environment_repository import environment_repository
from ..repositories.genus_repository import genus_repository
from ..repositories.history_repository import history_repository
from ..repositories.species_repository import species_repository
from ..schemas.requests import PressureConfig, TurnCommand
from ..schemas.responses import ReemergenceEvent, SpeciesSnapshot, TurnReport
from ..services.adaptation import AdaptationService
from ..services.background import BackgroundSpeciesManager
from ..services.gene_activation import GeneActivationService
from ..services.gene_flow import GeneFlowService
from ..services.critical_analyzer import CriticalAnalyzer
from ..services.exporter import ExportService
from ..services.embedding import EmbeddingService
from ..services.focus_processor import FocusBatchProcessor
from ..services.map_evolution import MapEvolutionService
from ..services.map_manager import MapStateManager
from ..services.migration import MigrationAdvisor
from ..services.reproduction import ReproductionService
from ..ai.model_router import ModelRouter
from ..services.niche import NicheAnalyzer
from ..services.pressure import PressureEscalationService
from ..services.report_builder import ReportBuilder
from ..services.speciation import SpeciationService
from ..services.tiering import SpeciesTieringService
from .environment import EnvironmentSystem
from .species import MortalityEngine


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
        terrain_evolution,
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
        self.terrain_evolution = terrain_evolution
        self.reproduction_service = reproduction_service
        self.adaptation_service = adaptation_service
        self.gene_flow_service = gene_flow_service
        self.gene_activation_service = GeneActivationService()
        self.turn_counter = 0
        self.watchlist: set[str] = set()

    def update_watchlist(self, codes: set[str]) -> None:
        self.watchlist = set(codes)

    def _calculate_trophic_interactions(self, species_list: list) -> dict[str, float]:
        """计算营养级互动压力 (Scheme B)
        
        1. 计算每一层的总生物量
        2. 计算 T2 对 T1 的啃食压力
        3. 计算 T3+ 对 T2 的捕食压力
        """
        biomass_by_trophic = {}  # key: trophic_int (1,2,3...), value: total_biomass
        
        # 1. 统计生物量
        for sp in species_list:
            t_level = int(sp.trophic_level)
            pop = sp.morphology_stats.get("population", 0)
            weight = sp.morphology_stats.get("body_weight_g", 1.0)
            biomass = pop * weight
            
            biomass_by_trophic[t_level] = biomass_by_trophic.get(t_level, 0.0) + biomass
            
        interactions = {}
        
        # 2. 计算各层压力
        # T2 吃 T1 -> T1受到的 grazing_pressure
        t1_biomass = biomass_by_trophic.get(1, 1.0)
        t2_biomass = biomass_by_trophic.get(2, 0.0)
        
        # 啃食压力 = T2总需求 / T1总供给 (简化模型)
        # 假设T2单位生物量需要消耗 10倍 T1生物量 (10%传递率逆推)
        # raw_grazing_ratio: >1.0 意味着T2处于饥饿状态 (Scarcity)
        raw_grazing_ratio = (t2_biomass * 10.0) / max(t1_biomass, 1.0)
        grazing_intensity = min(raw_grazing_ratio, 1.0)  # 上限100%压力 (对T1)
        
        # 记录 T2 的食物短缺压力 (Bottom-Up)
        # 如果 ratio > 1.0, scarcity = ratio - 1.0 (例如 ratio=1.5, scarcity=0.5)
        # 限制最大短缺压力为 2.0 (即3倍需求)
        t2_scarcity = max(0.0, min(2.0, raw_grazing_ratio - 0.8)) # 0.8起算，留一点缓冲
        interactions["t2_scarcity"] = t2_scarcity

        # 将全局压力分配给每个T1物种
        for sp in species_list:
            if int(sp.trophic_level) == 1:
                # 这里可以根据物种防御属性进行微调，暂时简化为平均分配
                interactions[f"predation_on_{sp.lineage_code}"] = grazing_intensity
        
        # T3+ 吃 T2 -> T2受到的 predation_pressure
        # 计算所有 T3+ 的总生物量
        predator_biomass = sum(b for t, b in biomass_by_trophic.items() if t >= 3)
        prey_biomass = t2_biomass
        
        if prey_biomass > 0:
            raw_predation_ratio = (predator_biomass * 10.0) / prey_biomass
            predation_intensity = min(raw_predation_ratio, 1.0)
            
            # 记录 T3+ 的食物短缺压力
            t3_scarcity = max(0.0, min(2.0, raw_predation_ratio - 0.8))
            interactions["t3_scarcity"] = t3_scarcity
            
            for sp in species_list:
                if int(sp.trophic_level) == 2:
                    interactions[f"predation_on_{sp.lineage_code}"] = predation_intensity
        else:
            # 如果没有猎物，捕食者面临严重饥荒
            if predator_biomass > 0:
                interactions["t3_scarcity"] = 2.0 # 最大饥荒

                    
        return interactions

    async def run_turns_async(self, command: TurnCommand) -> list[TurnReport]:
        reports: list[TurnReport] = []
        for turn_num in range(command.rounds):
            logger.info(f"执行第 {turn_num + 1}/{command.rounds} 回合, turn_counter={self.turn_counter}")
            try:
                # 1. 解析压力
                logger.info(f"解析压力...")
                pressures = self.environment.parse_pressures(command.pressures)
                modifiers = self.environment.apply_pressures(pressures)
                major_events = self.escalation_service.register(command.pressures, self.turn_counter)
                
                # 2. 地图演化与海平面变化
                logger.info(f"地图演化...")
                current_map_state = environment_repository.get_state()
                if not current_map_state:
                    logger.info(f"初始化地图状态...")
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
                
                # 2.5. AI驱动的地形演化 (Async)
                logger.info(f"地形演化 (AI)...")
                tiles = environment_repository.list_tiles()
                prev_state = environment_repository.get_state() if self.turn_counter > 0 else None
                updated_tiles, terrain_events = await self.terrain_evolution.evolve_terrain_async(
                    tiles, pressures, current_map_state, prev_state, self.turn_counter
                )
                if updated_tiles:
                    environment_repository.upsert_tiles(updated_tiles)
                    print(f"[地形] 更新了 {len(updated_tiles)} 个地块")
                if terrain_events:
                    map_changes.extend(terrain_events)
                
                # 3. 获取物种列表（只处理存活的物种）
                logger.info(f"获取物种列表...")
                all_species = species_repository.list_species()
                species_batch = [sp for sp in all_species if sp.status == "alive"]
                logger.info(f"当前物种数量: {len(species_batch)} (总共{len(all_species)}个，其中{len(all_species)-len(species_batch)}个已灭绝)")
                
                if not species_batch:
                    logger.warning(f"没有存活物种，跳过此回合")
                    continue
                
                # 4. 分层与生态位分析
                logger.info(f"物种分层...")
                tiered = self.tiering.classify(species_batch, self.watchlist)
                logger.info(f"Critical: {len(tiered.critical)}, Focus: {len(tiered.focus)}, Background: {len(tiered.background)}")
                
                logger.info(f"生态位分析...")
                niche_metrics = self.niche_analyzer.analyze(species_batch)
                
                # 5. 死亡率计算
                logger.info(f"计算营养级互动...")
                trophic_interactions = self._calculate_trophic_interactions(species_batch)
                
                logger.info(f"计算死亡率...")
                critical_results = self.mortality.evaluate(
                    tiered.critical, modifiers, niche_metrics, tier="critical", trophic_interactions=trophic_interactions
                )
                focus_results = self.mortality.evaluate(
                    tiered.focus, modifiers, niche_metrics, tier="focus", trophic_interactions=trophic_interactions
                )
                background_results = self.mortality.evaluate(
                    tiered.background, modifiers, niche_metrics, tier="background", trophic_interactions=trophic_interactions
                )
                
                # 6. AI增润 (Async)
                logger.info(f"AI增润 (Critical)...")
                await self.critical_analyzer.enhance_async(critical_results)
                
                logger.info(f"AI增润 (Focus)...")
                await self.focus_processor.enhance_async(focus_results)
                
                combined_results = critical_results + focus_results + background_results
                
                # 7. 更新种群（死亡后的存活者）
                logger.info(f"更新种群数据...")
                self._update_populations(combined_results)
                
                # 8. 应用繁殖增长（50万年的自然增长）
                logger.info(f"计算繁殖增长...")
                survival_rates = {
                    item.species.lineage_code: (1.0 - item.death_rate)
                    for item in combined_results
                }
                niche_data = {
                    code: (metrics.overlap, metrics.saturation)
                    for code, metrics in niche_metrics.items()
                }
                new_populations = self.reproduction_service.apply_reproduction(
                    species_batch, niche_data, survival_rates
                )
                # 应用繁殖后的种群数量
                for species in species_batch:
                    if species.lineage_code in new_populations:
                        species.morphology_stats["population"] = new_populations[species.lineage_code]
                        species_repository.upsert(species)
                logger.info(f"繁殖完成，种群更新")
                
                # 8.5. 应用渐进演化和退化机制
                logger.info(f"应用适应性演化（渐进演化+退化）...")
                adaptation_events = await self.adaptation_service.apply_adaptations_async(
                    species_batch, modifiers, self.turn_counter
                )
                # 更新适应后的物种数据
                for species in species_batch:
                    species_repository.upsert(species)
                logger.info(f"适应演化完成: {len(adaptation_events)}个物种发生变化")
                for event in adaptation_events:
                    print(f"  - {event['common_name']}: {event['type']} - {list(event['changes'].keys())}")
                
                # 8.5.5 基因激活检查
                logger.info(f"检查休眠基因激活...")
                activation_events = self.gene_activation_service.batch_check(
                    species_batch, 
                    critical_results + focus_results,
                    self.turn_counter
                )
                if activation_events:
                    logger.info(f"{len(activation_events)}个物种激活了休眠基因")
                    for event in activation_events:
                        traits = event['activated_traits']
                        organs = event['activated_organs']
                        print(f"  - {event['common_name']}: 特质{traits} 器官{organs}")
                    for species in species_batch:
                        species_repository.upsert(species)
                
                # 8.6. 基因流动
                logger.info(f"应用基因流动...")
                gene_flow_count = self._apply_gene_flow(species_batch)
                logger.info(f"基因流动完成: {gene_flow_count}对物种发生基因流动")
                
                # 8.7. 亚种晋升检查
                logger.info(f"检查亚种晋升...")
                promotion_count = self._check_subspecies_promotion(species_batch, self.turn_counter)
                if promotion_count > 0:
                    logger.info(f"{promotion_count}个亚种晋升为独立种")
                
                # 9. 分化处理 (Async)
                logger.info(f"处理物种分化 (AI)...")
                branching = await self.speciation.process_async(
                    mortality_results=critical_results + focus_results,
                    existing_codes={s.lineage_code for s in species_batch},
                    average_pressure=sum(modifiers.values()) / (len(modifiers) or 1),
                    turn_index=self.turn_counter,
                    map_changes=map_changes,
                    major_events=major_events,
                )
                logger.info(f"分化事件数: {len(branching)}")
                
                # 10. 背景物种管理
                logger.info(f"背景物种管理...")
                background_summary = self.background_manager.summarize(background_results)
                mass_extinction = self.background_manager.detect_mass_extinction(
                    combined_results
                )
                reemergence = []
                if mass_extinction:
                    promoted = self.background_manager.promote_candidates(background_results)
                    if promoted:
                        reemergence = self._rule_based_reemergence(promoted, modifiers)
                
                # 11. 迁徙建议
                logger.info(f"迁徙建议...")
                migration_events = self.migration_advisor.plan(
                    critical_results + focus_results, modifiers, major_events, map_changes
                )
                
                # 12. 构建报告 (Async)
                logger.info(f"构建回合报告 (AI)...")
                report = await self._build_report_async(
                    combined_results,
                    pressures,
                    branching,
                    background_summary,
                    reemergence,
                    major_events,
                    map_changes,
                    migration_events,
                )
                
                # 13. 保存地图快照
                logger.info(f"保存地图栖息地快照...")
                self.map_manager.snapshot_habitats(
                    species_batch, turn_index=self.turn_counter
                )
                
                # 14. 保存历史记录
                logger.info(f"保存历史记录...")
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
                self.exporter.export_turn(report, species_batch)
                
                self.turn_counter += 1
                reports.append(report)
                logger.info(f"回合 {report.turn_index} 完成")
                
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
        
        narrative = await self.report_builder.build_turn_narrative_async(
            species_snapshots,
            pressures,
            background_summary,
            reemergence_events,
            major_events,
            map_changes,
            migration_events,
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
        )

    def _update_populations(self, mortality_results) -> None:
        """更新种群数量并检测灭绝条件。
        
        灭绝条件：
        1. 种群低于最小生存阈值（基于体型动态计算）
        2. 连续3回合死亡率>50%
        3. 单回合死亡率>85%（灾难性死亡）
        """
        for item in mortality_results:
            species = item.species
            current_population = item.survivors
            death_rate = item.death_rate
            
            # 计算最小生存阈值（基于体型）
            body_length = species.morphology_stats.get("body_length_cm", 1.0)
            if body_length < 0.01:  # 细菌
                min_threshold = 1000
            elif body_length < 0.1:  # 原生动物
                min_threshold = 500
            elif body_length < 1.0:  # 小型无脊椎
                min_threshold = 200
            elif body_length < 10.0:  # 昆虫、小鱼
                min_threshold = 50
            elif body_length < 50.0:  # 中型脊椎动物
                min_threshold = 20
            else:  # 大型动物
                min_threshold = 10
            
            # 追踪连续高死亡率
            high_mortality_count = species.hidden_traits.get("high_mortality_turns", 0)
            if death_rate > 0.5:
                high_mortality_count += 1
            else:
                high_mortality_count = 0  # 重置计数器
            species.hidden_traits["high_mortality_turns"] = high_mortality_count
            
            # 检查灭绝条件
            extinction_triggered = False
            extinction_reason = ""
            
            # 条件1：种群低于阈值
            if current_population < min_threshold:
                extinction_triggered = True
                extinction_reason = f"种群{current_population}低于最小生存阈值{min_threshold}"
            
            # 条件2：连续高死亡率
            elif high_mortality_count >= 3:
                extinction_triggered = True
                extinction_reason = f"连续{high_mortality_count}回合死亡率超过50%，种群无法恢复"
            
            # 条件3：灾难性死亡
            elif death_rate > 0.85:
                extinction_triggered = True
                extinction_reason = f"单回合死亡率{death_rate:.1%}过高，种群崩溃"
            
            # 执行灭绝
            if extinction_triggered and species.status == "alive":
                logger.info(f"[灭绝] {species.common_name} ({species.lineage_code}): {extinction_reason}")
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
