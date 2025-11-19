from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from ..models.species import LineageEvent, Species

logger = logging.getLogger(__name__)
from ..repositories.genus_repository import genus_repository
from ..repositories.species_repository import species_repository
from ..schemas.responses import BranchingEvent
from .gene_library import GeneLibraryService
from .genetic_distance import GeneticDistanceCalculator
from .trait_config import TraitConfig
from .trophic import TrophicLevelCalculator


class SpeciationService:
    """根据存活数据和演化潜力，生成新的谱系并记录事件。"""

    def __init__(self, router) -> None:
        self.router = router
        self.trophic_calculator = TrophicLevelCalculator()
        self.genetic_calculator = GeneticDistanceCalculator()
        self.gene_library_service = GeneLibraryService()

    def process(
        self,
        mortality_results,
        existing_codes: set[str],
        average_pressure: float,
        turn_index: int,
        map_changes: list = None,
        major_events: list = None,
    ) -> list[BranchingEvent]:
        """处理物种分化 - 基于体型和生态策略的动态门槛。
        
        分化条件：
        1. 种群达到动态门槛（基于体型、繁殖策略、代谢率）
        2. 演化潜力>0.6
        3. 有环境压力（2.0-15.0）或资源饱和>0.8
        4. 死亡率在适应范围内（10-50%）
        5. 随机性（基于演化潜力）
        
        分化门槛设计原理：
        - 微生物（r策略）：需要大种群（百万级）才有意义分化
        - 小型生物：十万级
        - 中型生物（鱼类、鸟类）：万级
        - 大型生物（哺乳动物）：千级
        - 超大型生物（大象、鲸鱼）：百级
        """
        events: list[BranchingEvent] = []
        import random
        
        for result in mortality_results:
            species = result.species
            survivors = result.survivors
            death_rate = result.death_rate
            resource_pressure = result.resource_pressure
            
            # 条件1：计算该物种的动态分化门槛（提高60%以进一步降低分化频率）
            base_threshold = self._calculate_speciation_threshold(species)
            min_population = int(base_threshold * 1.6)  # P3-4: 从1.4提高到1.6，降低物种增长速度
            
            # 调试日志：输出分化门槛信息
            logger.debug(f"[分化检查] {species.common_name} ({species.lineage_code}): "
                  f"存活{survivors:,} / 门槛{min_population:,} (基准{base_threshold:,}) "
                  f"体长{species.morphology_stats.get('body_length_cm', 0):.4f}cm")
            
            if survivors < min_population:
                continue
            
            # 条件2：演化潜力（提高要求以降低分化频率）
            evo_potential = species.hidden_traits.get("evolution_potential", 0.0)
            if evo_potential < 0.7:  # P1-1: 从0.6提高到0.7
                continue
            
            # 条件3：压力显著或资源饱和（降低压力要求）
            # 环境压力或资源竞争都可能导致分化
            has_pressure = (1.5 <= average_pressure <= 15.0) or (resource_pressure > 0.8)
            
            # P3-5: 自然辐射演化（无压力时也有极小概率分化）
            if not has_pressure:
                # 如果种群巨大且无压力，可能有1%的基础概率发生自然分化
                if survivors > min_population * 2 and random.random() < 0.01:
                    has_pressure = True
                    speciation_type = "辐射演化"
                else:
                    continue
            
            # 条件4：适应压力（放宽死亡率窗口）
            # 降低下限以允许在较低压力下分化，保持上限防止在灭绝边缘分化
            if death_rate < 0.05 or death_rate > 0.60:  # P1-1: 从0.12-0.45放宽到0.05-0.60
                continue
            
            # 条件5：随机性（进一步降低概率）
            # 演化潜力0.7：22%概率
            # 演化潜力0.8：27%概率
            # 演化潜力1.0：37%概率
            base_chance = (0.2 + (evo_potential * 0.5)) * 0.55  # P3-4: 从0.7降到0.55，进一步降低分化率
            
            # P3-3: 增加多样性分化类型的概率修正
            speciation_bonus = 0.0
            speciation_type = "生态隔离"  # 默认类型
            
            # 检测地理隔离机会
            if map_changes:
                for change in (map_changes or []):
                    change_type = change.get("change_type", "") if isinstance(change, dict) else getattr(change, "change_type", "")
                    if change_type in ["uplift", "volcanic", "glaciation"]:
                        speciation_bonus += 0.15  # 地理隔离提升15%分化概率
                        speciation_type = "地理隔离"
                        break
            
            # 检测极端环境特化
            if major_events:
                for event in (major_events or []):
                    severity = event.get("severity", "") if isinstance(event, dict) else getattr(event, "severity", "")
                    if severity in ["extreme", "catastrophic"]:
                        speciation_bonus += 0.10  # 极端环境提升10%分化概率
                        speciation_type = "极端环境特化"
                        break
            
            # 检测捕食者-被捕食者协同演化
            # 如果该物种与其他物种有显著生态位重叠，可能触发协同演化
            if result.niche_overlap > 0.4:
                speciation_bonus += 0.08  # 协同演化提升8%分化概率
                speciation_type = "协同演化"
            
            speciation_chance = base_chance + speciation_bonus
            if random.random() > speciation_chance:
                continue
            
            # 决定分化出几个子种（2-3个）
            num_offspring = random.choice([2, 2, 3])  # 2个的概率更高
            logger.info(f"[分化] {species.common_name} 将分化出 {num_offspring} 个子种")
            
            # 生成多个谱系编码
            new_codes = self._generate_multiple_lineage_codes(
                species.lineage_code, existing_codes, num_offspring
            )
            for code in new_codes:
                existing_codes.add(code)
            
            # 种群分配：奠基者效应
            # 父代保留大部分(60-80%)，子代瓜分剩余的小部分(Founder Effect)
            retention_ratio = random.uniform(0.60, 0.80)
            parent_remaining = max(100, int(survivors * retention_ratio))
            
            # 更新父系物种种群
            species.morphology_stats["population"] = parent_remaining
            species_repository.upsert(species)
            
            # 剩余种群分配给子种（略有不均以模拟适应性差异）
            # 子代作为奠基者群体，数量较少
            remaining_pop = survivors - parent_remaining
            pop_splits = []
            for i in range(num_offspring):
                if i == num_offspring - 1:
                    # 最后一个获得剩余
                    pop_splits.append(remaining_pop)
                else:
                    # 随机分配20-40%的剩余种群
                    ratio = random.uniform(0.25, 0.40)
                    allocated = int(remaining_pop * ratio)
                    pop_splits.append(allocated)
                    remaining_pop -= allocated
            
            # 为每个子种调用AI并创建物种
            for idx, (new_code, population) in enumerate(zip(new_codes, pop_splits)):
                ai_payload = {
                    "parent_lineage": species.lineage_code,
                    "latin_name": species.latin_name,
                    "common_name": species.common_name,
                    "environment_pressure": average_pressure,
                    "traits": species.description,
                    "survivors": population,
                    "speciation_type": speciation_type,
                    "map_changes_summary": self._summarize_map_changes(map_changes) if map_changes else "",
                    "major_events_summary": self._summarize_major_events(major_events) if major_events else "",
                    "parent_trophic_level": species.trophic_level,
                    "offspring_index": idx + 1,  # 第几个子种
                    "total_offspring": num_offspring,  # 总共几个子种
                }
                
                ai_response = self.router.invoke("speciation", ai_payload)
                # 调试：输出完整的AI响应
                logger.debug(f"[分化AI调用] 完整响应: {list(ai_response.keys()) if isinstance(ai_response, dict) else type(ai_response)}")
                if "error" in ai_response:
                    logger.error(f"[分化AI错误] {ai_response['error']}")
                if "content" not in ai_response:
                    logger.warning(f"[分化AI警告] 响应中没有content字段，provider={ai_response.get('provider')}, model={ai_response.get('model')}")
                    logger.warning(f"[分化AI警告] 完整响应: {ai_response}")
                
                ai_content = ai_response.get("content") if isinstance(ai_response, dict) else {}
                if not isinstance(ai_content, dict):
                    logger.warning(f"[分化AI警告] content不是字典: {type(ai_content)}")
                    ai_content = {}
                
                new_species = self._create_species(
                    parent=species,
                    new_code=new_code,
                    survivors=population,
                    turn_index=turn_index,
                    ai_payload=ai_content,
                    average_pressure=average_pressure,
                )
                species_repository.upsert(new_species)
                
                self._update_genetic_distances(new_species, species, turn_index)
                
                if ai_content.get("genetic_discoveries") and new_species.genus_code:
                    self.gene_library_service.record_discovery(
                        genus_code=new_species.genus_code,
                        discoveries=ai_content["genetic_discoveries"],
                        discoverer_code=new_species.lineage_code,
                        turn=turn_index
                    )
                
                if new_species.genus_code:
                    genus = genus_repository.get_by_code(new_species.genus_code)
                    if genus:
                        self.gene_library_service.inherit_dormant_genes(species, new_species, genus)
                        species_repository.upsert(new_species)
                
                species_repository.log_event(
                    LineageEvent(
                        lineage_code=new_code,
                        event_type="speciation",
                        payload={"parent": species.lineage_code, "turn": turn_index},
                    )
                )
                
                event_desc = ai_content.get("event_description") if ai_content else None
                if not event_desc:
                    event_desc = f"{species.common_name}在压力{average_pressure:.1f}条件下分化出{new_code}"
                
                # 生成分化原因
                reason_text = ai_content.get("reason") or ai_content.get("speciation_reason")
                if not reason_text:
                    if speciation_type == "地理隔离":
                        reason_text = f"{species.common_name}因地形剧变导致种群地理隔离，各隔离群体独立演化产生生殖隔离"
                    elif speciation_type == "极端环境特化":
                        reason_text = f"{species.common_name}在极端环境压力下，部分种群演化出特化适应能力，与原种群形成生态分离"
                    elif speciation_type == "协同演化":
                        reason_text = f"{species.common_name}与竞争物种的生态位重叠导致竞争排斥，促使种群分化到不同资源梯度"
                    else:
                        reason_text = f"{species.common_name}种群在演化压力下发生生态位分化"
                
                events.append(
                    BranchingEvent(
                        parent_lineage=species.lineage_code,
                        new_lineage=new_code,
                        description=event_desc,
                        timestamp=datetime.utcnow(),
                        reason=reason_text,
                    )
                )
        return events

    def _next_lineage_code(self, parent_code: str, existing_codes: set[str]) -> str:
        """生成单个子代编码（保留用于向后兼容）"""
        base = f"{parent_code}a"
        idx = 1
        new_code = f"{base}{idx}"
        while new_code in existing_codes:
            idx += 1
            new_code = f"{base}{idx}"
        return new_code
    
    def _generate_multiple_lineage_codes(
        self, parent_code: str, existing_codes: set[str], num_offspring: int
    ) -> list[str]:
        """生成多个子代编码，使用字母后缀 (A1→A1a, A1b, A1c)
        
        Args:
            parent_code: 父代编码 (如 "A1")
            existing_codes: 已存在的编码集合
            num_offspring: 需要生成的子代数量
            
        Returns:
            子代编码列表 (如 ["A1a", "A1b", "A1c"])
        """
        letters = "abcdefghijklmnopqrstuvwxyz"
        codes = []
        
        for i in range(num_offspring):
            letter = letters[i]
            new_code = f"{parent_code}{letter}"
            
            # 如果编码已存在，添加数字后缀
            if new_code in existing_codes:
                idx = 1
                while f"{new_code}{idx}" in existing_codes:
                    idx += 1
                new_code = f"{new_code}{idx}"
            
            codes.append(new_code)
        
        return codes

    def _create_species(
        self,
        parent: Species,
        new_code: str,
        survivors: int,
        turn_index: int,
        ai_payload,
        average_pressure: float,
    ) -> Species:
        """创建新的分化物种。
        
        新物种从父代继承大部分属性，但有一些变化：
        - 基因多样性略微增加
        - 描述可能由 AI 修改以反映新特征
        
        种群分配逻辑：
        - 新物种从原物种中分离出20-40%的个体
        - 原物种保留60-80%
        - 总数略减（模拟分化过程的损耗）
        """
        # 计算分离比例（子代更适应，获得更多个体）
        import random
        
        # 父代保留大部分
        parent_retention = random.uniform(0.60, 0.80)
        parent_remaining = max(100, int(survivors * parent_retention))
        
        # 新物种获得剩余部分的一定比例 (Founder Effect)
        remaining = survivors - parent_remaining
        new_population = max(50, int(remaining * random.uniform(0.6, 0.8)))
        
        # 更新父系物种的种群数量（在数据库中）
        parent.morphology_stats["population"] = parent_remaining
        from ..repositories.species_repository import species_repository
        species_repository.upsert(parent)
        
        morphology = dict(parent.morphology_stats)
        morphology["population"] = new_population
        
        hidden = dict(parent.hidden_traits)
        hidden["gene_diversity"] = min(1.0, hidden.get("gene_diversity", 0.5) + 0.05)
        
        # 继承父代的 abstract_traits，并应用 AI 建议的变化
        abstract = TraitConfig.merge_traits(parent.abstract_traits, {})
        trait_changes = ai_payload.get("trait_changes") or {}
        if isinstance(trait_changes, dict):
            for trait_name, change in trait_changes.items():
                try:
                    if isinstance(change, str):
                        change_value = float(change.replace("+", ""))
                    else:
                        change_value = float(change)
                    
                    current_value = abstract.get(trait_name, 5.0)
                    new_val = current_value + change_value
                    abstract[trait_name] = TraitConfig.clamp_trait(round(new_val, 2))
                except (ValueError, TypeError):
                    pass
        
        # 应用形态学变化
        morphology_changes = ai_payload.get("morphology_changes") or {}
        if isinstance(morphology_changes, dict):
            for morph_name, change_factor in morphology_changes.items():
                if morph_name in morphology:
                    try:
                        # change_factor 是倍数，如 1.2 表示增大20%
                        factor = float(change_factor)
                        morphology[morph_name] = morphology[morph_name] * factor
                    except (ValueError, TypeError):
                        pass
        
        # 从AI响应中提取名称和描述
        latin = ai_payload.get("latin_name")
        common = ai_payload.get("common_name")
        description = ai_payload.get("description")
        
        # 如果AI未返回名称或描述，使用回退逻辑
        if not latin or not common or not description or len(str(description).strip()) < 80:
            logger.warning(f"[分化警告] AI返回不完整，使用回退命名: latin={latin}, common={common}")
            # 回退到规则命名
            if not latin:
                latin = self._fallback_latin_name(parent.latin_name, ai_payload)
            if not common:
                common = self._fallback_common_name(parent.common_name, ai_payload)
            if not description or len(str(description).strip()) < 80:
                key_innovations = ai_payload.get("key_innovations", [])
                innovations_text = "，演化出" + "、".join(key_innovations) if key_innovations else ""
                description = f"{parent.description}在环境压力{average_pressure:.1f}下发生适应性变化{innovations_text}。"
                if len(description) < 120:
                    description = parent.description
        
        # 【防重名】检查并处理重名情况
        latin = self._ensure_unique_latin_name(latin, new_code)
        common = self._ensure_unique_common_name(common, new_code)
        
        # 计算新物种的营养级
        all_species = species_repository.list_species()
        new_trophic = self.trophic_calculator.calculate_trophic_level(
            Species(
                lineage_code=new_code,
                latin_name=latin,
                common_name=common,
                description=description,
                morphology_stats=morphology,
                abstract_traits=abstract,
                hidden_traits=hidden,
                ecological_vector=None,
                trophic_level=parent.trophic_level  # 临时值
            ),
            all_species
        )
        
        # 【克莱伯定律修正】基于体重和营养级重算代谢率
        # SMR ∝ Mass^-0.25
        mass_g = morphology.get("body_weight_g", 1.0)
        morphology["metabolic_rate"] = self.trophic_calculator.estimate_kleiber_metabolic_rate(
            mass_g, new_trophic
        )
        
        # 验证属性变化是否符合营养级规则
        validation_ok, validation_msg = self._validate_trait_changes(
            parent.abstract_traits, abstract, new_trophic
        )
        if not validation_ok:
            logger.warning(f"[分化警告] 属性验证失败: {validation_msg}，将自动钳制数值")
            # 智能钳制：根据营养级限制缩放属性，而不是直接回退
            abstract = self._clamp_traits_to_limit(abstract, parent.abstract_traits, new_trophic)

        
        # 继承并更新器官系统
        organs = self._inherit_and_update_organs(
            parent=parent,
            ai_payload=ai_payload,
            turn_index=turn_index
        )
        
        # 更新能力标签
        capabilities = self._update_capabilities(parent, organs)
        
        # 不再继承 ecological_vector，让系统基于 description 自动计算 embedding
        return Species(
            lineage_code=new_code,
            latin_name=latin,
            common_name=common,
            description=description,
            morphology_stats=morphology,
            abstract_traits=abstract,
            hidden_traits=hidden,
            ecological_vector=None,  # 不继承，让系统自动计算
            parent_code=parent.lineage_code,
            status="alive",
            created_turn=turn_index,
            trophic_level=new_trophic,
            organs=organs,
            capabilities=capabilities,
            genus_code=parent.genus_code,
            taxonomic_rank="subspecies",
        )
    
    def _calculate_speciation_threshold(self, species: Species) -> int:
        """计算物种的分化门槛 - 基于多维度生态学指标。
        
        综合考虑：
        1. 体型（体长、体重） - 主要因素
        2. 繁殖策略（世代时间、繁殖速度） - r/K策略
        3. 代谢率 - 能量周转速度
        4. 营养级 - 从描述推断
        
        Returns:
            最小种群数量（需要达到此数量才能分化）
        """
        import math
        
        # 1. 基于体型的基础门槛
        body_length_cm = species.morphology_stats.get("body_length_cm", 1.0)
        body_weight_g = species.morphology_stats.get("body_weight_g", 1.0)
        
        # 使用体长作为主要指标（更直观）
        if body_length_cm < 0.01:  # <0.1mm - 细菌级别
            base_threshold = 2_000_000  # 200万
        elif body_length_cm < 0.1:  # 0.1mm-1mm - 原生动物
            base_threshold = 1_000_000  # 100万
        elif body_length_cm < 1.0:  # 1mm-1cm - 小型无脊椎动物
            base_threshold = 100_000   # 10万
        elif body_length_cm < 10.0:  # 1cm-10cm - 昆虫、小鱼
            base_threshold = 10_000    # 1万
        elif body_length_cm < 50.0:  # 10cm-50cm - 中型脊椎动物
            base_threshold = 2_000     # 2千
        elif body_length_cm < 200.0:  # 50cm-2m - 大型哺乳动物
            base_threshold = 500       # 500
        else:  # >2m - 超大型动物（大象、鲸鱼）
            base_threshold = 100       # 100
        
        # 体重修正（提供额外验证）
        # 1g以下：微小生物
        # 1-1000g：小型生物
        # 1kg-100kg：中型生物
        # >100kg：大型生物
        if body_weight_g < 1.0:
            weight_factor = 1.2  # 微小生物需要更大种群
        elif body_weight_g < 1000:
            weight_factor = 1.0
        elif body_weight_g < 100_000:
            weight_factor = 0.8
        else:
            weight_factor = 0.6  # 大型生物门槛更低
        
        # 2. 繁殖策略修正
        generation_time = species.morphology_stats.get("generation_time_days", 365)
        reproduction_speed = species.abstract_traits.get("繁殖速度", 5)
        
        # r策略物种（快繁殖，短世代）需要更大种群
        # K策略物种（慢繁殖，长世代）较小种群即可
        if generation_time < 30 and reproduction_speed >= 7:
            # r策略：微生物、昆虫
            repro_factor = 1.5
        elif generation_time < 365 and reproduction_speed >= 5:
            # 中等：小型哺乳动物、鸟类
            repro_factor = 1.0
        else:
            # K策略：大型哺乳动物
            repro_factor = 0.7
        
        # 3. 代谢率修正
        metabolic_rate = species.morphology_stats.get("metabolic_rate", 3.0)
        # 高代谢率（>5.0）= 需要更多个体维持种群
        # 低代谢率（<2.0）= 少量个体即可
        if metabolic_rate > 5.0:
            metabolic_factor = 1.3
        elif metabolic_rate > 3.0:
            metabolic_factor = 1.0
        else:
            metabolic_factor = 0.8
        
        # 4. 营养级修正（从描述推断）
        desc_lower = species.description.lower()
        if any(kw in desc_lower for kw in ["顶级捕食", "apex", "大型捕食者", "食物链顶端"]):
            trophic_factor = 0.5  # 顶级捕食者种群小
        elif any(kw in desc_lower for kw in ["捕食", "carnivore", "肉食", "掠食"]):
            trophic_factor = 0.7  # 捕食者
        elif any(kw in desc_lower for kw in ["杂食", "omnivore"]):
            trophic_factor = 0.9
        elif any(kw in desc_lower for kw in ["草食", "herbivore", "食草"]):
            trophic_factor = 1.0  # 草食动物种群大
        elif any(kw in desc_lower for kw in ["生产者", "光合", "植物", "藻类", "producer", "photosyn"]):
            trophic_factor = 1.2  # 初级生产者种群最大
        else:
            trophic_factor = 1.0
        
        # 5. 综合计算
        threshold = int(
            base_threshold 
            * weight_factor 
            * repro_factor 
            * metabolic_factor 
            * trophic_factor
        )
        
        # 确保在合理范围内
        # 最小：50（濒危大型动物也需要一定基数）
        # 最大：500万（即使是细菌也不需要无限大）
        threshold = max(50, min(threshold, 5_000_000))
        
        return threshold
    
    def _summarize_map_changes(self, map_changes: list) -> str:
        """总结地图变化用于分化原因描述。"""
        if not map_changes:
            return ""
        
        change_types = []
        for change in map_changes[:3]:  # 最多取3个
            if isinstance(change, dict):
                ctype = change.get("change_type", "")
            else:
                ctype = getattr(change, "change_type", "")
            
            if ctype == "uplift":
                change_types.append("地壳抬升")
            elif ctype == "volcanic":
                change_types.append("火山活动")
            elif ctype == "glaciation":
                change_types.append("冰川推进")
            elif ctype == "subsidence":
                change_types.append("地壳下沉")
        
        return "、".join(change_types) if change_types else "地形变化"
    
    def _summarize_major_events(self, major_events: list) -> str:
        """总结重大事件用于分化原因描述。"""
        if not major_events:
            return ""
        
        for event in major_events[:1]:  # 取第一个
            if isinstance(event, dict):
                desc = event.get("description", "")
                severity = event.get("severity", "")
            else:
                desc = getattr(event, "description", "")
                severity = getattr(event, "severity", "")
            
            if desc:
                return f"{severity}级{desc}"
        
        return "重大环境事件"
    
    def _fallback_latin_name(self, parent_latin: str, ai_content: dict) -> str:
        """回退拉丁命名逻辑"""
        import hashlib
        # 提取父系属名
        genus = parent_latin.split()[0] if ' ' in parent_latin else "Species"
        # 基于key_innovations生成种加词
        innovations = ai_content.get("key_innovations", [])
        if innovations:
            # 从第一个创新中提取关键词
            innovation = innovations[0].lower()
            if "鞭毛" in innovation or "游" in innovation:
                epithet = "natans"
            elif "深" in innovation or "底" in innovation:
                epithet = "profundus"
            elif "快" in innovation or "速" in innovation:
                epithet = "velox"
            elif "慢" in innovation or "缓" in innovation:
                epithet = "lentus"
            elif "大" in innovation or "巨" in innovation:
                epithet = "magnus"
            elif "小" in innovation or "微" in innovation:
                epithet = "minutus"
            elif "透明" in innovation:
                epithet = "hyalinus"
            elif "耐盐" in innovation or "盐" in innovation:
                epithet = "salinus"
            elif "耐热" in innovation or "热" in innovation:
                epithet = "thermophilus"
            elif "耐寒" in innovation or "冷" in innovation:
                epithet = "cryophilus"
            else:
                # 使用hash确保唯一性
                hash_suffix = hashlib.md5(str(innovations).encode()).hexdigest()[:6]
                epithet = f"sp{hash_suffix}"
        else:
            # 完全随机
            hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:6]
            epithet = f"sp{hash_suffix}"
        return f"{genus} {epithet}"
    
    def _fallback_common_name(self, parent_common: str, ai_content: dict) -> str:
        """回退中文命名逻辑"""
        import hashlib
        # 提取类群名（通常是最后2-3个字）
        if len(parent_common) >= 2:
            taxon = parent_common[-2:] if parent_common[-1] in "虫藻菌类贝鱼" else parent_common[-3:]
        else:
            taxon = "生物"
        
        # 从key_innovations提取特征词
        innovations = ai_content.get("key_innovations", [])
        if innovations:
            innovation = innovations[0]
            # 提取前2个字作为特征词
            if "鞭毛" in innovation:
                if "多" in innovation or "4" in innovation or "增" in innovation:
                    feature = "多鞭"
                elif "长" in innovation:
                    feature = "长鞭"
                else:
                    feature = "异鞭"
            elif "游" in innovation or "速" in innovation:
                if "快" in innovation or "提升" in innovation:
                    feature = "快游"
                else:
                    feature = "慢游"
            elif "深" in innovation or "底" in innovation:
                feature = "深水"
            elif "浅" in innovation or "表" in innovation:
                feature = "浅水"
            elif "耐盐" in innovation or "盐" in innovation:
                feature = "耐盐"
            elif "透明" in innovation:
                feature = "透明"
            elif "大" in innovation or "巨" in innovation:
                feature = "巨型"
            elif "小" in innovation or "微" in innovation:
                feature = "微型"
            elif "滤食" in innovation:
                feature = "滤食"
            elif "夜" in innovation:
                feature = "夜行"
            else:
                # 提取前两个字
                words = [c for c in innovation if '\u4e00' <= c <= '\u9fff']
                feature = ''.join(words[:2]) if len(words) >= 2 else "变异"
        else:
            # 使用hash生成唯一标识
            hash_suffix = hashlib.md5(str(ai_content).encode()).hexdigest()[:2]
            feature = f"型{hash_suffix}"
        
        return f"{feature}{taxon}"
    
    def _ensure_unique_latin_name(self, latin_name: str, lineage_code: str) -> str:
        """确保拉丁学名唯一，使用罗马数字后缀处理重名
        
        策略：
        1. 如果名称唯一，直接返回
        2. 如果重名，尝试添加罗马数字 II, III, IV, V
        3. 如果罗马数字超过V，使用谱系编码作为亚种名
        
        Args:
            latin_name: AI生成的拉丁学名
            lineage_code: 谱系编码
            
        Returns:
            唯一的拉丁学名
        """
        all_species = species_repository.list_species()
        existing_names = {sp.latin_name.lower() for sp in all_species}
        
        # 如果名称唯一，直接返回
        if latin_name.lower() not in existing_names:
            return latin_name
        
        logger.info(f"[防重名] 检测到拉丁学名重复: {latin_name}")
        
        # 尝试添加罗马数字后缀 II-V
        roman_numerals = ["II", "III", "IV", "V"]
        for numeral in roman_numerals:
            variant = f"{latin_name} {numeral}"
            if variant.lower() not in existing_names:
                logger.info(f"[防重名] 使用罗马数字: {variant}")
                return variant
        
        # 如果罗马数字超过V，使用谱系编码作为亚种标识
        logger.info(f"[防重名] 罗马数字已超过V，使用谱系编码标识")
        parts = latin_name.split()
        if len(parts) >= 2:
            genus, species_name = parts[0], parts[1]
            subspecies_suffix = lineage_code.lower().replace("_", "")
            
            # 使用 subsp. 格式
            variant = f"{genus} {species_name} subsp. {subspecies_suffix}"
            if variant.lower() not in existing_names:
                logger.info(f"[防重名] 使用亚种标识: {variant}")
                return variant
        
        # 最终兜底：直接加谱系编码
        return f"{latin_name} [{lineage_code}]"
    
    def _ensure_unique_common_name(self, common_name: str, lineage_code: str) -> str:
        """确保中文俗名唯一，使用罗马数字后缀处理重名
        
        策略：
        1. 如果名称唯一，直接返回
        2. 如果重名，尝试添加罗马数字 II, III, IV, V
        3. 如果罗马数字超过V，使用世代标记
        
        Args:
            common_name: AI生成的中文俗名
            lineage_code: 谱系编码
            
        Returns:
            唯一的中文俗名
        """
        all_species = species_repository.list_species()
        existing_names = {sp.common_name for sp in all_species}
        
        # 如果名称唯一，直接返回
        if common_name not in existing_names:
            return common_name
        
        logger.info(f"[防重名] 检测到中文俗名重复: {common_name}")
        
        # 尝试添加罗马数字后缀 II-V
        roman_numerals = ["II", "III", "IV", "V"]
        for numeral in roman_numerals:
            variant = f"{common_name}{numeral}"
            if variant not in existing_names:
                logger.info(f"[防重名] 添加罗马数字: {variant}")
                return variant
        
        # 如果罗马数字超过V，使用世代标记
        logger.info(f"[防重名] 罗马数字已超过V，使用世代标记")
        for i in range(6, 50):
            variant = f"{common_name}-{i}代"
            if variant not in existing_names:
                logger.info(f"[防重名] 使用世代标记: {variant}")
                return variant
        
        # 最终兜底：添加谱系编码
        return f"{common_name}({lineage_code})"
    
    def _validate_trait_changes(
        self, old_traits: dict, new_traits: dict, trophic_level: float
    ) -> tuple[bool, str]:
        """验证属性变化是否符合营养级规则
        
        Returns:
            (验证是否通过, 错误信息)
        """
        # 获取营养级对应的属性上限
        limits = self.trophic_calculator.get_attribute_limits(trophic_level)
        
        # 1. 检查总和变化
        old_sum = sum(old_traits.values())
        new_sum = sum(new_traits.values())
        sum_diff = new_sum - old_sum
        
        if sum_diff > 8:
            return False, f"属性总和增加{sum_diff}，超过上限8"
        
        # 2. 检查总和是否超过营养级上限
        if new_sum > limits["total"]:
            return False, f"属性总和{new_sum}超过营养级{trophic_level:.1f}的上限{limits['total']}"
        
        # 3. 检查单个属性是否超过特化上限
        above_specialized = [
            (k, v) for k, v in new_traits.items() if v > limits["specialized"]
        ]
        if above_specialized:
            return False, f"属性{above_specialized[0][0]}={above_specialized[0][1]}超过特化上限{limits['specialized']}"
        
        # 4. 检查超过基础上限的属性数量
        above_base_count = sum(1 for v in new_traits.values() if v > limits["base"])
        if above_base_count > 2:
            return False, f"{above_base_count}个属性超过基础上限{limits['base']}，最多允许2个"
        
        # 5. 检查权衡（有增必有减，除非是营养级提升）
        increases = sum(1 for k, v in new_traits.items() if v > old_traits.get(k, 0))
        decreases = sum(1 for k, v in new_traits.items() if v < old_traits.get(k, 0))
        
        if increases > 0 and decreases == 0 and sum_diff > 3:
            return False, "有属性提升但无权衡代价"
        
        return True, "验证通过"
    
    def _inherit_and_update_organs(
        self, parent: Species, ai_payload: dict, turn_index: int
    ) -> dict:
        """继承父代器官并应用AI返回的结构化创新
        
        Args:
            parent: 父系物种
            ai_payload: AI返回的数据（包含structural_innovations）
            turn_index: 当前回合
            
        Returns:
            更新后的器官字典
        """
        # 1. 继承父代所有器官（深拷贝）
        organs = {}
        for category, organ_data in parent.organs.items():
            organs[category] = dict(organ_data)
        
        # 2. 解析AI返回的structural_innovations
        innovations = ai_payload.get("structural_innovations", [])
        if not isinstance(innovations, list):
            return organs
        
        for innovation in innovations:
            if not isinstance(innovation, dict):
                continue
            
            category = innovation.get("category", "unknown")
            organ_type = innovation.get("type", "unknown")
            parameters = innovation.get("parameters", {})
            
            # 3. 判断是新器官还是器官改进
            if category in organs:
                # 器官改进：更新参数
                organs[category]["type"] = organ_type
                organs[category]["parameters"] = parameters
                organs[category]["modified_turn"] = turn_index
                organs[category]["is_active"] = True
                logger.info(f"[器官演化] 改进器官: {category} → {organ_type}")
            else:
                # 新器官：创建记录
                organs[category] = {
                    "type": organ_type,
                    "parameters": parameters,
                    "acquired_turn": turn_index,
                    "is_active": True
                }
                logger.info(f"[器官演化] 获得新器官: {category} → {organ_type}")
        
        return organs
    
    def _update_capabilities(self, parent: Species, organs: dict) -> list[str]:
        """根据器官更新能力标签
        
        Args:
            parent: 父系物种
            organs: 当前器官字典
            
        Returns:
            能力标签列表（中文）
        """
        # 能力映射表：旧英文标签 -> 中文标签
        legacy_map = {
            "photosynthesis": "光合作用",
            "autotrophy": "自养",
            "flagellar_motion": "鞭毛运动",
            "chemical_detection": "化学感知",
            "heterotrophy": "异养",
            "chemosynthesis": "化能合成",
            "extremophile": "嗜极生物",
            "ciliary_motion": "纤毛运动",
            "limb_locomotion": "附肢运动",
            "swimming": "游泳",
            "light_detection": "感光",
            "vision": "视觉",
            "touch_sensation": "触觉",
            "aerobic_respiration": "有氧呼吸",
            "digestion": "消化",
            "armor": "盔甲",
            "spines": "棘刺",
            "venom": "毒素"
        }

        capabilities = set()
        
        # 继承并转换父代能力
        for cap in parent.capabilities:
            if cap in legacy_map:
                capabilities.add(legacy_map[cap])
            else:
                # 如果已经是中文或其他未映射的，直接保留
                capabilities.add(cap)
        
        # 根据活跃器官添加能力标签
        for category, organ_data in organs.items():
            if not organ_data.get("is_active", True):
                continue  # 跳过已退化的器官
            
            organ_type = organ_data.get("type", "").lower()
            
            # 运动能力
            if category == "locomotion":
                if "flagella" in organ_type or "flagellum" in organ_type or "鞭毛" in organ_type:
                    capabilities.add("鞭毛运动")
                elif "cilia" in organ_type or "纤毛" in organ_type:
                    capabilities.add("纤毛运动")
                elif "leg" in organ_type or "limb" in organ_type or "足" in organ_type or "肢" in organ_type:
                    capabilities.add("附肢运动")
                elif "fin" in organ_type or "鳍" in organ_type:
                    capabilities.add("游泳")
            
            # 感觉能力
            elif category == "sensory":
                if "eye" in organ_type or "ocellus" in organ_type or "眼" in organ_type:
                    capabilities.add("感光")
                    capabilities.add("视觉")
                elif "photoreceptor" in organ_type or "eyespot" in organ_type or "光感受" in organ_type or "眼点" in organ_type:
                    capabilities.add("感光")
                elif "mechanoreceptor" in organ_type or "机械感受" in organ_type:
                    capabilities.add("触觉")
                elif "chemoreceptor" in organ_type or "化学感受" in organ_type:
                    capabilities.add("化学感知")
            
            # 代谢能力
            elif category == "metabolic":
                if "chloroplast" in organ_type or "photosynthetic" in organ_type or "叶绿体" in organ_type or "光合" in organ_type:
                    capabilities.add("光合作用")
                elif "mitochondria" in organ_type or "线粒体" in organ_type:
                    capabilities.add("有氧呼吸")
            
            # 消化能力
            elif category == "digestive":
                if organ_data.get("is_active", True):
                    capabilities.add("消化")
            
            # 防御能力
            elif category == "defense":
                if "shell" in organ_type or "carapace" in organ_type or "壳" in organ_type or "甲" in organ_type:
                    capabilities.add("盔甲")
                elif "spine" in organ_type or "thorn" in organ_type or "刺" in organ_type or "棘" in organ_type:
                    capabilities.add("棘刺")
                elif "toxin" in organ_type or "毒" in organ_type:
                    capabilities.add("毒素")
        
        return list(capabilities)
    
    def _update_genetic_distances(self, offspring: Species, parent: Species, turn_index: int):
        """更新遗传距离矩阵"""
        if not parent.genus_code:
            return
        
        genus = genus_repository.get_by_code(parent.genus_code)
        if not genus:
            return
        
        all_species = species_repository.list_species()
        genus_species = [sp for sp in all_species if sp.genus_code == parent.genus_code and sp.status == "alive"]
        
        new_distances = {}
        for sibling in genus_species:
            if sibling.lineage_code == offspring.lineage_code:
                continue
            
            distance = self.genetic_calculator.calculate_distance(offspring, sibling)
            key = self._make_distance_key(offspring.lineage_code, sibling.lineage_code)
            new_distances[key] = distance
        
        genus_repository.update_distances(parent.genus_code, new_distances, turn_index)
    
    def _make_distance_key(self, code1: str, code2: str) -> str:
        """生成距离键"""
        if code1 < code2:
            return f"{code1}-{code2}"
        return f"{code2}-{code1}"
    
    def _clamp_traits_to_limit(self, traits: dict, parent_traits: dict, trophic_level: float) -> dict:
        """智能钳制属性到营养级限制范围内
        
        策略：
        1. 单个属性不超过特化上限
        2. 属性总和不超过营养级上限和父代+5.0
        3. 最多2个属性超过基础上限
        """
        limits = self.trophic_calculator.get_attribute_limits(trophic_level)
        
        clamped = dict(traits)
        
        # 1. 钳制单个属性到特化上限
        for k, v in clamped.items():
            if v > limits["specialized"]:
                clamped[k] = limits["specialized"]
        
        # 2. 检查并钳制总和
        current_sum = sum(clamped.values())
        parent_sum = sum(parent_traits.values())
        
        # 总和最多增加5.0（保守的演化步长，比原本允许的8更严格）
        max_increase = 5.0
        target_max_sum = min(limits["total"], parent_sum + max_increase)
        
        if current_sum > target_max_sum:
            # 计算需要缩减的量
            excess = current_sum - target_max_sum
            # 只缩减增加的属性（保持权衡原则）
            increased_traits = {k: v for k, v in clamped.items() if v > parent_traits.get(k, 0)}
            
            if increased_traits:
                # 按增加量比例分配缩减（增加多的缩减多）
                total_increase = sum(v - parent_traits.get(k, 0) for k, v in increased_traits.items())
                if total_increase > 0:
                    for k, v in increased_traits.items():
                        increase = v - parent_traits.get(k, 0)
                        reduction = excess * (increase / total_increase)
                        clamped[k] = max(parent_traits.get(k, 0), v - reduction)
            
            # 如果还是超了（说明没有增加的属性或不足以缩减），全局缩放
            current_sum = sum(clamped.values())
            if current_sum > target_max_sum:
                scale = target_max_sum / current_sum
                for k in clamped:
                    clamped[k] *= scale
        
        # 3. 确保最多2个属性超过基础上限
        base_limit = limits["base"]
        specialized_traits = [(k, v) for k, v in clamped.items() if v > base_limit]
        if len(specialized_traits) > 2:
            # 保留最高的2个，其余降到基础上限
            specialized_traits.sort(key=lambda x: x[1], reverse=True)
            keep_specialized = {k for k, _ in specialized_traits[:2]}
            
            for k, v in clamped.items():
                if v > base_limit and k not in keep_specialized:
                    clamped[k] = base_limit
        
        return {k: round(v, 2) for k, v in clamped.items()}
