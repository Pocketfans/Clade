"""休眠基因激活服务 v2.0

【完整重构版本】整合以下新机制：
1. 器官渐进发育（4阶段系统）
2. 显隐性遗传（影响表达效果）
3. 基因连锁（相关基因一起激活/代价）
4. 有害突变（遗传负荷）
5. 水平基因转移 HGT（微生物特有）
6. 细化压力类型系统

基于 Embedding 的基因激活机制：
- 使用 GeneDiversityService 判断压力方向是否在可达半径内
- 压力匹配时激活概率加成
- 所有参数从 GeneDiversityConfig 读取
"""
from __future__ import annotations

import logging
import random
import warnings
from typing import TYPE_CHECKING

from ...models.species import Species
from .gene_diversity import GeneDiversityService
from .trait_config import TraitConfig
from .gene_constants import (
    PRESSURE_GENE_MAPPING,
    LEGACY_PRESSURE_MAPPING,
    GENE_LINKAGE_GROUPS,
    LINKAGE_INDEX,
    OrganStage,
    ORGAN_DEVELOPMENT_CONFIG,
    DominanceType,
    DOMINANCE_EXPRESSION_FACTOR,
    MutationEffect,
    HGT_CONFIG,
    get_pressure_response,
    get_linkage_group,
    roll_dominance,
    roll_mutation_effect,
    get_random_harmful_mutation,
    is_hgt_eligible,
)

if TYPE_CHECKING:
    from ...models.config import GeneDiversityConfig
    from .gene_library import GeneLibraryService

logger = logging.getLogger(__name__)


def _load_gene_diversity_config() -> "GeneDiversityConfig | None":
    """从 settings.json 加载基因多样性配置"""
    try:
        from ...core.config import PROJECT_ROOT
        from ...repositories.environment_repository import environment_repository
        ui_cfg = environment_repository.load_ui_config(PROJECT_ROOT / "data/settings.json")
        return ui_cfg.gene_diversity
    except Exception:
        return None


class GeneActivationService:
    """处理物种休眠基因的激活
    
    【v2.0 新功能】
    - 器官渐进发育：原基→初级→功能→成熟
    - 显隐性遗传：影响特质表达值
    - 基因连锁：相关基因同时激活，有代价
    - 有害突变：可能激活有害基因
    - 水平基因转移：微生物从邻近物种获取基因
    
    【Embedding 集成】
    - 使用 GeneDiversityService 的 is_reachable() 判断压力方向是否在可达范围内
    - 压力匹配时应用 pressure_match_bonus 加成
    - 激活后消耗半径（通过 consume_on_activation）
    """
    
    def __init__(self, embedding_service=None, gene_diversity_service: GeneDiversityService | None = None):
        self._gene_library_service: "GeneLibraryService | None" = None
        self.embedding = embedding_service
        self.gene_diversity = gene_diversity_service or GeneDiversityService(embedding_service)
        self._config: "GeneDiversityConfig | None" = None
    
    @property
    def gene_library_service(self) -> "GeneLibraryService":
        """[DEPRECATED] 惰性加载 GeneLibraryService，仅用于旧存档兼容"""
        if self._gene_library_service is None:
            warnings.warn(
                "GeneLibraryService 已废弃，请迁移到 GeneDiversityService",
                DeprecationWarning,
                stacklevel=2
            )
            from .gene_library import GeneLibraryService
            self._gene_library_service = GeneLibraryService()
        return self._gene_library_service
    
    @property
    def config(self) -> "GeneDiversityConfig":
        """懒加载配置"""
        if self._config is None:
            self._config = _load_gene_diversity_config()
        if self._config is None:
            from ...models.config import GeneDiversityConfig
            self._config = GeneDiversityConfig()
        return self._config
    
    # ================================================================
    # 主入口
    # ================================================================
    
    def check_and_activate(
        self,
        species: Species,
        death_rate: float,
        pressure_type: str,
        turn: int,
        nearby_species: list[Species] | None = None
    ) -> dict:
        """检查并激活休眠基因
        
        Args:
            species: 目标物种
            death_rate: 当前死亡率
            pressure_type: 压力类型
            turn: 当前回合
            nearby_species: 附近物种列表（用于 HGT）
        
        Returns:
            激活结果字典 {
                "traits": [...],
                "organs": [...],
                "organ_development": [...],  # 器官发育进展
                "linked_effects": [...],      # 连锁效果
                "harmful_activated": [...],   # 有害突变激活
                "hgt_acquired": [...]         # HGT 获得的基因
            }
        """
        # 确保新字段初始化
        try:
            self.gene_diversity.ensure_initialized(species)
        except Exception:
            pass

        # 旧存档/初始剧本可能没有休眠基因，自动补齐
        if not species.dormant_genes or not any(species.dormant_genes.values()):
            self._bootstrap_dormant_genes(species)
        
        # 初始化结果
        result = {
            "traits": [],
            "organs": [],
            "organ_development": [],
            "linked_effects": [],
            "harmful_activated": [],
            "hgt_acquired": []
        }
        
        # 更新压力暴露记录
        if not species.stress_exposure:
            species.stress_exposure = {}
        
        # 转换旧压力类型到新类型
        mapped_pressure = self._map_pressure_type(pressure_type)
        
        species.stress_exposure.setdefault(mapped_pressure, {"count": 0, "max_death_rate": 0.0})
        species.stress_exposure[mapped_pressure]["count"] += 1
        species.stress_exposure[mapped_pressure]["max_death_rate"] = max(
            species.stress_exposure[mapped_pressure]["max_death_rate"],
            death_rate
        )
        
        # 1. 检查特质激活（含显隐性和连锁）
        activated_traits, linked_effects, harmful = self._check_trait_activation(
            species, death_rate, mapped_pressure, turn
        )
        result["traits"] = activated_traits
        result["linked_effects"] = linked_effects
        result["harmful_activated"] = harmful
        
        # 2. 检查器官发育/激活（渐进系统）
        activated_organs, development_progress = self._check_organ_activation(
            species, death_rate, mapped_pressure, turn
        )
        result["organs"] = activated_organs
        result["organ_development"] = development_progress
        
        # 3. 检查水平基因转移（仅微生物）
        if is_hgt_eligible(species) and nearby_species:
            hgt_acquired = self._check_horizontal_gene_transfer(
                species, nearby_species, turn
            )
            result["hgt_acquired"] = hgt_acquired
        
        return result
    
    # ================================================================
    # 特质激活（含显隐性、连锁、有害突变）
    # ================================================================
    
    def _check_trait_activation(
        self,
        species: Species,
        death_rate: float,
        pressure_type: str,
        turn: int
    ) -> tuple[list[str], list[dict], list[str]]:
        """检查特质激活
        
        Returns:
            (activated_traits, linked_effects, harmful_activated)
        """
        activated = []
        linked_effects = []
        harmful_activated = []
        
        if "traits" not in species.dormant_genes:
            return activated, linked_effects, harmful_activated
        
        cfg = self.config
        base_activation_chance = cfg.activation_chance_per_turn
        pressure_match_bonus = cfg.pressure_match_bonus
        death_rate_threshold = getattr(cfg, 'activation_death_rate_threshold', 0.25)
        min_exposure = getattr(cfg, 'activation_min_exposure', 1)
        
        reachable = self._is_reachable(species, pressure_type)
        
        # 获取压力响应信息
        pressure_response = get_pressure_response(pressure_type)
        responsive_traits = pressure_response.get("responsive_traits", []) if pressure_response else []

        for trait_name, gene_data in list(species.dormant_genes["traits"].items()):
            if gene_data.get("activated", False):
                continue
            
            # 增加暴露计数
            gene_data["exposure_count"] = gene_data.get("exposure_count", 0) + 1
            
            # 检查压力匹配（新系统：检查响应特质列表）
            pressure_matched = (
                pressure_type in gene_data.get("pressure_types", []) or
                trait_name in responsive_traits or
                any(t in trait_name for t in responsive_traits)
            )
            
            exposure_count = gene_data.get("exposure_count", 0)
            evolution_potential = species.hidden_traits.get("evolution_potential", 0.5)
            
            # 计算激活概率
            activation_prob = base_activation_chance * (1.0 + evolution_potential)
            if pressure_matched:
                activation_prob *= pressure_match_bonus
            
            # 检查是否是有害突变
            mutation_effect = gene_data.get("mutation_effect", MutationEffect.BENEFICIAL.value)
            is_harmful = mutation_effect in (
                MutationEffect.MILDLY_HARMFUL.value, 
                MutationEffect.HARMFUL.value,
                MutationEffect.LETHAL.value
            )
            
            # 有害突变激活概率更低（被自然选择抑制）
            if is_harmful:
                activation_prob *= 0.3  # 只有30%的概率激活有害突变
            
            # 激活条件检查
            if (death_rate > death_rate_threshold and
                exposure_count >= min_exposure and
                reachable and
                random.random() < activation_prob):
                
                # 获取潜力值和显隐性
                potential_value = gene_data.get("potential_value", 8.0)
                dominance = gene_data.get("dominance", DominanceType.CODOMINANT.value)
                
                # 应用显隐性效果
                expression_factor = DOMINANCE_EXPRESSION_FACTOR.get(
                    DominanceType(dominance) if isinstance(dominance, str) else dominance,
                    0.6
                )
                expressed_value = potential_value * expression_factor
                
                # 有害突变：负值效果
                if is_harmful:
                    value_modifier = gene_data.get("value_modifier", -1.0)
                    target_trait = gene_data.get("target_trait", trait_name)
                    
                    # 应用有害效果到目标特质
                    if target_trait and target_trait in species.abstract_traits:
                        current = species.abstract_traits.get(target_trait, 5.0)
                        new_value = max(0, current + value_modifier)
                        species.abstract_traits[target_trait] = TraitConfig.clamp_trait(new_value)
                        harmful_activated.append(trait_name)
                        logger.warning(f"[有害突变] {species.common_name} 激活有害基因: {trait_name}, {target_trait} {value_modifier:+.1f}")
                    
                    gene_data["activated"] = True
                    gene_data["activation_turn"] = turn
                    continue
                
                # 验证特质合法性
                test_traits = dict(species.abstract_traits)
                test_traits[trait_name] = TraitConfig.clamp_trait(expressed_value)
                
                valid, error_msg = TraitConfig.validate_traits_with_trophic(
                    test_traits, species.trophic_level
                )
                
                if valid:
                    species.abstract_traits[trait_name] = TraitConfig.clamp_trait(expressed_value)
                    gene_data["activated"] = True
                    gene_data["activation_turn"] = turn
                    gene_data["expressed_value"] = expressed_value
                    activated.append(trait_name)
                    
                    try:
                        self.gene_diversity.consume_on_activation(species)
                        self.gene_diversity.record_direction(species, self._direction_id(pressure_type))
                    except Exception:
                        pass
                    
                    logger.info(
                        f"[基因激活] {species.common_name} 激活特质: {trait_name} = {expressed_value:.1f} "
                        f"(显隐性: {dominance}, 系数: {expression_factor:.2f})"
                    )
                    
                    # 检查基因连锁
                    linkage = get_linkage_group(trait_name)
                    if linkage:
                        linked_result = self._apply_gene_linkage(species, linkage, turn)
                        if linked_result:
                            linked_effects.append(linked_result)
                    
                    if species.genus_code:
                        try:
                            self.gene_library_service.update_activation_count(
                                species.genus_code, trait_name, "traits"
                            )
                        except Exception:
                            pass
                else:
                    logger.warning(f"[基因激活] {species.common_name} 激活{trait_name}失败: {error_msg}")
        
        return activated, linked_effects, harmful_activated
    
    def _apply_gene_linkage(self, species: Species, linkage: dict, turn: int) -> dict | None:
        """应用基因连锁效果"""
        result = {
            "primary": linkage["primary"],
            "linked_activated": [],
            "tradeoffs_applied": []
        }
        
        # 激活连锁基因
        for linked_trait in linkage.get("linked", []):
            if linked_trait not in species.abstract_traits:
                # 给予连锁特质基础值
                base_value = 5.0 + random.uniform(-1, 1)
                species.abstract_traits[linked_trait] = TraitConfig.clamp_trait(base_value)
                result["linked_activated"].append(linked_trait)
                logger.info(f"[基因连锁] {species.common_name} 连锁激活: {linked_trait} = {base_value:.1f}")
        
        # 应用代价
        for trait_name, penalty in linkage.get("tradeoff", []):
            if trait_name in species.abstract_traits:
                old_value = species.abstract_traits[trait_name]
                new_value = max(0, old_value + penalty)
                species.abstract_traits[trait_name] = TraitConfig.clamp_trait(new_value)
                result["tradeoffs_applied"].append({
                    "trait": trait_name,
                    "change": penalty,
                    "old": old_value,
                    "new": new_value
                })
                logger.info(f"[基因代价] {species.common_name} {trait_name}: {old_value:.1f} → {new_value:.1f}")
        
        return result if result["linked_activated"] or result["tradeoffs_applied"] else None
    
    # ================================================================
    # 器官渐进发育系统
    # ================================================================
    
    def _check_organ_activation(
        self,
        species: Species,
        death_rate: float,
        pressure_type: str,
        turn: int
    ) -> tuple[list[str], list[dict]]:
        """检查器官发育和激活
        
        器官发育遵循4阶段渐进系统：
        原基(0) → 初级(1) → 功能(2) → 成熟(3)
        
        Returns:
            (matured_organs, development_progress)
        """
        matured = []
        development_progress = []
        
        if "organs" not in species.dormant_genes:
            return matured, development_progress
        
        cfg = self.config
        organ_discovery_chance = cfg.organ_discovery_chance
        pressure_match_bonus = cfg.pressure_match_bonus
        death_rate_threshold = getattr(cfg, 'activation_death_rate_threshold', 0.25) + 0.05
        min_exposure = getattr(cfg, 'activation_min_exposure', 1)
        
        reachable = self._is_reachable(species, pressure_type)
        evolution_potential = species.hidden_traits.get("evolution_potential", 0.5)
        
        # 获取压力响应信息
        pressure_response = get_pressure_response(pressure_type)
        responsive_organs = pressure_response.get("responsive_organs", []) if pressure_response else []

        for organ_name, gene_data in list(species.dormant_genes["organs"].items()):
            # 检查器官是否已完全成熟
            current_stage = gene_data.get("development_stage", None)
            
            if gene_data.get("activated", False) and current_stage == OrganStage.MATURE.value:
                continue  # 已成熟，跳过
            
            # 增加暴露计数
            gene_data["exposure_count"] = gene_data.get("exposure_count", 0) + 1
            
            # 压力匹配检查
            pressure_matched = (
                pressure_type in gene_data.get("pressure_types", []) or
                organ_name in responsive_organs or
                any(o in organ_name for o in responsive_organs)
            )
            
            exposure_count = gene_data.get("exposure_count", 0)
            
            # 如果还未开始发育，检查是否触发原基形成
            if current_stage is None:
                activation_prob = organ_discovery_chance * (1.0 + evolution_potential * 2)
                if pressure_matched:
                    activation_prob *= pressure_match_bonus
                
                if (death_rate > death_rate_threshold and
                    exposure_count >= min_exposure and
                    reachable and
                    random.random() < activation_prob):
                    
                    # 开始发育：形成原基
                    gene_data["development_stage"] = OrganStage.PRIMORDIUM.value
                    gene_data["stage_start_turn"] = turn
                    gene_data["activated"] = True  # 标记为已激活（但未成熟）
                    gene_data["activation_turn"] = turn
                    
                    development_progress.append({
                        "organ": organ_name,
                        "event": "primordium_formed",
                        "stage": OrganStage.PRIMORDIUM.value,
                        "stage_name": "原基",
                        "efficiency": 0.0
                    })
                    
                    logger.info(f"[器官发育] {species.common_name} 形成原基: {organ_name}")
                    
                    try:
                        self.gene_diversity.consume_on_activation(species)
                    except Exception:
                        pass
            
            else:
                # 已经在发育中，检查是否推进到下一阶段
                progress_result = self._advance_organ_development(
                    species, organ_name, gene_data, turn, evolution_potential, pressure_matched
                )
                
                if progress_result:
                    development_progress.append(progress_result)
                    
                    # 检查是否达到成熟
                    if progress_result.get("stage") == OrganStage.MATURE.value:
                        matured.append(organ_name)
                        
                        # 将成熟器官添加到物种器官列表
                        organ_data = gene_data.get("organ_data", {})
                        organ_category = organ_data.get("category", "sensory")
                        
                        species.organs[organ_category] = {
                            "type": organ_data.get("type", organ_name),
                            "parameters": organ_data.get("parameters", {}),
                            "acquired_turn": turn,
                            "is_active": True,
                            "maturity": 1.0
                        }
                        
                        logger.info(f"[器官成熟] {species.common_name} 器官发育完成: {organ_name} ({organ_category})")
        
        return matured, development_progress
    
    def _advance_organ_development(
        self,
        species: Species,
        organ_name: str,
        gene_data: dict,
        turn: int,
        evolution_potential: float,
        pressure_matched: bool
    ) -> dict | None:
        """推进器官发育阶段（快速发育版本：总计2-5回合成熟）"""
        current_stage = OrganStage(gene_data.get("development_stage", 0))
        stage_start = gene_data.get("stage_start_turn", turn)
        turns_in_stage = turn - stage_start
        
        if current_stage == OrganStage.MATURE:
            return None  # 已成熟
        
        # 获取发育配置
        dev_config = ORGAN_DEVELOPMENT_CONFIG
        failure_chance = dev_config["failure_chance"].get(current_stage, 0.05)
        
        # 使用随机化的回合数范围（如果存在）
        if "turns_per_stage_range" in dev_config:
            range_config = dev_config["turns_per_stage_range"].get(current_stage, (1, 2))
            required_turns = random.randint(range_config[0], range_config[1])
        else:
            required_turns = dev_config["turns_per_stage"].get(current_stage, 1)
        
        # 演化潜力加速发育（高潜力可能直接跳过阶段）
        if evolution_potential > 0.6 and random.random() < evolution_potential * 0.3:
            required_turns = 0  # 高演化潜力可以直接推进
        
        # 压力匹配加速发育
        if pressure_matched:
            required_turns = max(0, required_turns - 1)
        
        if turns_in_stage < required_turns:
            return None  # 还未达到发育时间
        
        # 检查发育失败（退化）
        if random.random() < failure_chance:
            # 发育失败，退化一个阶段
            if current_stage.value > 0:
                new_stage = OrganStage(current_stage.value - 1)
                gene_data["development_stage"] = new_stage.value
                gene_data["stage_start_turn"] = turn
                
                return {
                    "organ": organ_name,
                    "event": "development_failed",
                    "stage": new_stage.value,
                    "stage_name": _stage_name(new_stage),
                    "efficiency": dev_config["efficiency_by_stage"][new_stage]
                }
            else:
                # 原基退化，器官发育失败
                gene_data["development_stage"] = None
                gene_data["activated"] = False
                return {
                    "organ": organ_name,
                    "event": "development_aborted",
                    "stage": -1,
                    "stage_name": "退化消失",
                    "efficiency": 0.0
                }
        
        # 发育成功，推进到下一阶段
        next_stage = OrganStage(current_stage.value + 1)
        gene_data["development_stage"] = next_stage.value
        gene_data["stage_start_turn"] = turn
        
        efficiency = dev_config["efficiency_by_stage"][next_stage]
        
        # 更新部分功能的器官到物种器官列表（功能原型阶段开始生效）
        if next_stage.value >= OrganStage.FUNCTIONAL.value:
            organ_data = gene_data.get("organ_data", {})
            organ_category = organ_data.get("category", "sensory")
            
            species.organs[organ_category] = {
                "type": organ_data.get("type", organ_name),
                "parameters": {
                    **organ_data.get("parameters", {}),
                    "efficiency_modifier": efficiency  # 效率修正
                },
                "acquired_turn": gene_data.get("activation_turn", turn),
                "is_active": True,
                "maturity": efficiency,
                "development_stage": next_stage.value
            }
        
        return {
            "organ": organ_name,
            "event": "stage_advanced",
            "stage": next_stage.value,
            "stage_name": _stage_name(next_stage),
            "efficiency": efficiency
        }
    
    # ================================================================
    # 水平基因转移 (HGT)
    # ================================================================
    
    def _check_horizontal_gene_transfer(
        self,
        species: Species,
        nearby_species: list[Species],
        turn: int
    ) -> list[dict]:
        """检查水平基因转移（仅微生物）"""
        acquired = []
        
        if not is_hgt_eligible(species):
            return acquired
        
        # 基础 HGT 概率
        hgt_chance = HGT_CONFIG["base_chance_per_turn"]
        
        # 找到符合条件的供体物种
        eligible_donors = [
            s for s in nearby_species
            if s.lineage_code != species.lineage_code and is_hgt_eligible(s)
        ]
        
        if not eligible_donors:
            return acquired
        
        # 同域物种加成
        hgt_chance += HGT_CONFIG["sympatric_bonus"] * min(len(eligible_donors), 3) / 3
        
        if random.random() > hgt_chance:
            return acquired
        
        # 随机选择一个供体
        donor = random.choice(eligible_donors)
        
        # 可转移的特质
        transferable = HGT_CONFIG["transferable_traits"]
        donor_traits = donor.abstract_traits or {}
        
        # 找到供体有但接收者没有的可转移特质
        candidates = [
            (name, value) for name, value in donor_traits.items()
            if name in transferable and name not in (species.abstract_traits or {})
        ]
        
        if not candidates:
            return acquired
        
        # 随机选择一个特质转移
        trait_name, donor_value = random.choice(candidates)
        
        # 转移效率
        efficiency = random.uniform(*HGT_CONFIG["transfer_efficiency"])
        transferred_value = donor_value * efficiency
        
        # 整合稳定性检查
        if random.random() > HGT_CONFIG["integration_stability"]:
            logger.info(f"[HGT] {species.common_name} 从 {donor.common_name} 获取 {trait_name} 但整合失败")
            return acquired
        
        # 成功转移
        species.abstract_traits[trait_name] = TraitConfig.clamp_trait(transferred_value)
        
        acquired.append({
            "trait": trait_name,
            "value": transferred_value,
            "donor": donor.common_name,
            "donor_code": donor.lineage_code,
            "efficiency": efficiency
        })
        
        logger.info(
            f"[HGT] {species.common_name} 从 {donor.common_name} 获取基因: "
            f"{trait_name} = {transferred_value:.1f} (效率 {efficiency:.0%})"
        )
        
        return acquired
    
    # ================================================================
    # Bootstrap 和辅助方法
    # ================================================================
    
    def _bootstrap_dormant_genes(self, species: Species) -> None:
        """为缺失休眠基因的物种补齐基础基因
        
        包含：有害突变、显隐性、新压力类型
        """
        if species.dormant_genes is None:
            species.dormant_genes = {"traits": {}, "organs": {}}
        species.dormant_genes.setdefault("traits", {})
        species.dormant_genes.setdefault("organs", {})
        
        traits = list((species.abstract_traits or {}).items())
        traits = sorted(traits, key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0, reverse=True)[:2]
        
        for name, value in traits:
            enhanced = f"强化{name}" if not name.startswith("强化") else name
            dominance = roll_dominance("trait")
            
            species.dormant_genes["traits"].setdefault(
                enhanced,
                {
                    "potential_value": min(15.0, (value or 0) * 1.2 if isinstance(value, (int, float)) else 6.0),
                    "activation_threshold": 0.2,
                    "pressure_types": self._infer_pressure_types_for_trait(name),
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": "bootstrap",
                    "dominance": dominance.value,
                    "mutation_effect": MutationEffect.BENEFICIAL.value,
                },
            )
        
        # 通用适应性特质
        species.dormant_genes["traits"].setdefault(
            "适应性",
            {
                "potential_value": 7.0,
                "activation_threshold": 0.15,
                "pressure_types": ["competition", "starvation"],
                "exposure_count": 0,
                "activated": False,
                "inherited_from": "bootstrap",
                "dominance": DominanceType.CODOMINANT.value,
                "mutation_effect": MutationEffect.BENEFICIAL.value,
            },
        )
        
        # 添加一个有害突变（15%概率）
        if random.random() < 0.15:
            harmful = get_random_harmful_mutation()
            if harmful:
                species.dormant_genes["traits"][harmful["name"]] = {
                    "potential_value": 0,
                    "target_trait": harmful.get("target_trait"),
                    "value_modifier": harmful.get("value_modifier", -1.0),
                    "activation_threshold": 0.3,
                    "pressure_types": ["starvation", "disease"],
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": "mutation",
                    "dominance": DominanceType.RECESSIVE.value,
                    "mutation_effect": harmful["effect"].value if isinstance(harmful["effect"], MutationEffect) else harmful["effect"],
                    "description": harmful.get("description", "")
                }
        
        # 通用感知器官
        species.dormant_genes["organs"].setdefault(
            "感知提升",
            {
                "organ_data": {
                    "category": "sensory",
                    "type": "bootstrap_sensor",
                    "parameters": {"sensitivity": 0.4},
                },
                "activation_threshold": 0.2,
                "pressure_types": ["predation", "hunting", "competition"],
                "exposure_count": 0,
                "activated": False,
                "inherited_from": "bootstrap",
                "dominance": DominanceType.CODOMINANT.value,
                "development_stage": None,  # 未开始发育
            },
        )
    
    def _map_pressure_type(self, pressure_type: str) -> str:
        """将旧压力类型映射到新的细化类型"""
        if pressure_type in PRESSURE_GENE_MAPPING:
            return pressure_type
        
        # 查找兼容映射
        if pressure_type in LEGACY_PRESSURE_MAPPING:
            mapped = LEGACY_PRESSURE_MAPPING[pressure_type]
            if mapped:
                return mapped[0]
        
        return pressure_type
    
    def _infer_pressure_types_for_trait(self, trait_name: str) -> list[str]:
        """根据特质名推断触发压力类型（使用新系统）"""
        mapping = {
            "耐寒性": ["cold", "temperature_fluctuation"],
            "耐热性": ["heat", "temperature_fluctuation"],
            "耐旱性": ["drought"],
            "耐盐性": ["salinity"],
            "免疫力": ["disease", "parasitism"],
            "运动能力": ["predation", "hunting"],
            "繁殖速度": ["starvation", "competition"],
            "社会性": ["competition"],
            "光合效率": ["light_limitation"],
            "固碳能力": ["light_limitation", "nutrient_poor"],
            "攻击性": ["hunting", "competition"],
            "防御能力": ["predation"],
            "代谢效率": ["starvation"],
            "感知敏锐": ["predation", "hunting"],
        }
        for key, types in mapping.items():
            if key in trait_name:
                return types
        return ["competition", "starvation"]
    
    # ================================================================
    # 批量处理
    # ================================================================
    
    def batch_check(
        self, 
        species_list: list[Species], 
        mortality_results: list, 
        turn: int
    ) -> list[dict]:
        """批量检查物种的基因激活"""
        activation_events = []
        
        mortality_map = {}
        for r in mortality_results:
            if isinstance(r, dict):
                code = r.get("lineage_code")
            else:
                code = getattr(r, 'lineage_code', None) or getattr(r.species, 'lineage_code', None)
            if code:
                mortality_map[code] = r
        
        for species in species_list:
            if species.lineage_code not in mortality_map:
                continue
            
            result = mortality_map[species.lineage_code]
            
            if isinstance(result, dict):
                death_rate = result.get("death_rate", 0.0)
            else:
                death_rate = getattr(result, 'death_rate', 0.0)
            
            if death_rate < 0.1:
                continue
            
            pressure_type = self._infer_pressure_type(result)
            
            # 获取附近物种用于 HGT（简化：使用全部物种列表）
            nearby = [s for s in species_list if s.lineage_code != species.lineage_code]
            
            activated = self.check_and_activate(
                species, death_rate, pressure_type, turn, nearby_species=nearby
            )
            
            if any(activated.values()):
                activation_events.append({
                    "lineage_code": species.lineage_code,
                    "common_name": species.common_name,
                    "activated_traits": activated["traits"],
                    "activated_organs": activated["organs"],
                    "organ_development": activated["organ_development"],
                    "linked_effects": activated["linked_effects"],
                    "harmful_activated": activated["harmful_activated"],
                    "hgt_acquired": activated["hgt_acquired"],
                    "death_rate": death_rate
                })
        
        return activation_events
    
    def _infer_pressure_type(self, mortality_result) -> str:
        """从死亡率结果推断压力类型（使用新系统）"""
        if not isinstance(mortality_result, dict):
            return "competition"

        if "pressure_breakdown" in mortality_result:
            breakdown = mortality_result["pressure_breakdown"]
            if breakdown.get("temperature", 0) > 0.3:
                return "heat" if breakdown.get("heat", 0) > breakdown.get("cold", 0) else "cold"
            if breakdown.get("humidity", 0) > 0.3:
                return "drought"
            if breakdown.get("resource_competition", 0) > 0.3:
                return "competition"
            if breakdown.get("predation", 0) > 0.3:
                return "predation"
        
        return "competition"

    # ================================================================
    # Embedding/可达性辅助
    # ================================================================
    
    def _is_reachable(self, species: Species, pressure_type: str) -> bool:
        """基于 Embedding 判断该压力方向是否在可达半径内"""
        try:
            radius = getattr(species, "gene_diversity_radius", None)
            if radius is None:
                self.gene_diversity.ensure_initialized(species)
                radius = species.gene_diversity_radius

            target_vec = self.gene_diversity.get_pressure_vector(pressure_type)
            return self.gene_diversity.is_reachable(
                species.ecological_vector, target_vec, radius
            )
        except Exception:
            return True

    def _direction_id(self, pressure_type: str) -> int:
        """使用稳定哈希把压力类型映射为方向索引"""
        return abs(hash(pressure_type)) % 10_000


# ================================================================
# 辅助函数
# ================================================================

def _stage_name(stage: OrganStage) -> str:
    """获取发育阶段的中文名称"""
    names = {
        OrganStage.PRIMORDIUM: "原基",
        OrganStage.PRIMITIVE: "初级结构",
        OrganStage.FUNCTIONAL: "功能原型",
        OrganStage.MATURE: "成熟器官",
    }
    return names.get(stage, f"阶段{stage.value}")
