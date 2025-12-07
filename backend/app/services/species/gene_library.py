"""
属基因库管理服务

[DEPRECATED] 该模块在基因多样性重构后逐步废弃
============================================
新的基因多样性系统使用 Embedding 向量距离判断可达性，
不再需要属级基因库来管理休眠基因池。

推荐迁移路径:
- 休眠基因判断: 使用 GeneDiversityService.is_reachable()
- 基因激活:     使用 GeneActivationService（已重构为 Embedding-based）
- 继承逻辑:     使用 GeneDiversityService.inherit_radius()

本模块保留用于兼容现有存档和渐进迁移，未来版本将移除。
"""
from __future__ import annotations

import logging
import random
import warnings

from ...models.genus import Genus
from ...models.species import Species
from ...repositories.genus_repository import genus_repository

logger = logging.getLogger(__name__)

# 废弃警告常量
_DEPRECATION_MSG = (
    "GeneLibraryService 已废弃，将在未来版本移除。"
    "请迁移到 GeneDiversityService 的 Embedding-based 基因多样性系统。"
)


class GeneLibraryService:
    """管理属级基因库，记录属的演化潜力
    
    .. deprecated::
        此类已废弃。请使用 GeneDiversityService 替代。
        新系统使用 Embedding 向量距离判断基因可达性，
        无需维护独立的属级基因库。
    """
    
    def __init__(self):
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
    
    def record_discovery(
        self, 
        genus_code: str, 
        discoveries: dict,
        discoverer_code: str,
        turn: int
    ):
        """记录新基因发现到属基因库"""
        if not discoveries:
            return
        
        genus = genus_repository.get_by_code(genus_code)
        if not genus:
            return
        
        if not genus.gene_library:
            genus.gene_library = {"traits": {}, "organs": {}}
        
        if "new_traits" in discoveries:
            for trait_name, trait_data in discoveries["new_traits"].items():
                if trait_name not in genus.gene_library.get("traits", {}):
                    genus.gene_library.setdefault("traits", {})[trait_name] = {
                        "max_value": trait_data.get("max_value", 10.0),
                        "description": trait_data.get("description", ""),
                        "discovered_by": discoverer_code,
                        "discovered_turn": turn,
                        "activation_count": 0
                    }
                    logger.info(f"[基因库] {genus.name_common}属发现新特质: {trait_name} (by {discoverer_code})")
        
        if "new_organs" in discoveries:
            for organ_name, organ_data in discoveries["new_organs"].items():
                if organ_name not in genus.gene_library.get("organs", {}):
                    genus.gene_library.setdefault("organs", {})[organ_name] = {
                        "category": organ_data.get("category", "sensory"),
                        "type": organ_data.get("type", organ_name),
                        "parameters": organ_data.get("parameters", {}),
                        "description": organ_data.get("description", ""),
                        "discovered_by": discoverer_code,
                        "discovered_turn": turn,
                        "activation_count": 0
                    }
                    logger.info(f"[基因库] {genus.name_common}属发现新器官: {organ_name} (by {discoverer_code})")
        
        genus.updated_turn = turn
        genus_repository.upsert(genus)
    
    def inherit_dormant_genes(
        self, 
        parent: Species, 
        child: Species,
        genus: Genus | None = None
    ):
        """子代继承休眠基因 v3.0 - 从基因库补充额外基因 + 新突变
        
        【v3.0 重构】
        - 父代休眠基因的直接继承已移至 _create_species（深拷贝，100%继承）
        - 本方法现在只负责：
          1. 从父代表型特质生成额外的休眠基因潜力
          2. 从父代器官生成变异潜力
          3. 新突变（遗传负荷模拟）
          4. 从属基因库继承额外基因（无数量上限）
        - genus 参数改为可选，即使没有 genus 也能处理新突变
        """
        # 导入新的基因常量
        try:
            from .gene_constants import (
                DominanceType, 
                MutationEffect, 
                roll_dominance,
                HARMFUL_MUTATIONS,
            )
        except ImportError:
            # 回退到旧行为
            DominanceType = None
            MutationEffect = None
            roll_dominance = None
            HARMFUL_MUTATIONS = None
        
        if not child.dormant_genes:
            child.dormant_genes = {"traits": {}, "organs": {}}
        
        child.dormant_genes.setdefault("traits", {})
        child.dormant_genes.setdefault("organs", {})
        
        added_count = 0
        harmful_added = 0
        
        # === 1. 从父代表型特质生成休眠基因潜力 ===
        # 这些是父代已表达的特质，子代可以获得更强的变异潜力
        for trait_name, trait_value in (parent.abstract_traits or {}).items():
            if trait_name in child.dormant_genes["traits"]:
                continue  # 已存在则跳过
                
            if random.random() < 0.80:  # 80% 概率生成变异潜力
                dominance = roll_dominance("trait") if roll_dominance else "codominant"
                dom_value = dominance.value if hasattr(dominance, 'value') else dominance
                
                child.dormant_genes["traits"][trait_name] = {
                    "potential_value": min(15.0, trait_value * 1.20),  # 潜力值比当前值高20%
                    "activation_threshold": 0.20,
                    "pressure_types": self._infer_pressure_types(trait_name),
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": parent.lineage_code,
                    "dominance": dom_value,
                    "mutation_effect": "beneficial",
                }
                added_count += 1
        
        # === 2. 从父代器官生成变异潜力 ===
        if parent.organs:
            for organ_cat, organ_data in parent.organs.items():
                if random.random() < 0.75:  # 75% 概率生成器官变异潜力
                    organ_name = f"{organ_data.get('type', organ_cat)}_variant"
                    if organ_name not in child.dormant_genes["organs"]:
                        dominance = roll_dominance("organ") if roll_dominance else "codominant"
                        dom_value = dominance.value if hasattr(dominance, 'value') else dominance
                        
                        child.dormant_genes["organs"][organ_name] = {
                            "organ_data": {
                                "category": organ_cat,
                                "type": organ_data.get("type", organ_cat) + "_evolved",
                                "parameters": {**organ_data.get("parameters", {}), "efficiency": 1.2}
                            },
                            "activation_threshold": 0.25,
                            "pressure_types": ["competition", "predation"],
                            "exposure_count": 0,
                            "activated": False,
                            "inherited_from": parent.lineage_code,
                            "dominance": dom_value,
                            "development_stage": None,
                            "stage_start_turn": None,
                        }
                        added_count += 1
        
        # === 3. 新突变：子代独有的有害突变（遗传负荷模拟） ===
        if HARMFUL_MUTATIONS and random.random() < 0.10:  # 10% 概率产生新的有害突变
            harmful_list = [m for m in HARMFUL_MUTATIONS 
                          if m["effect"] in (MutationEffect.MILDLY_HARMFUL, MutationEffect.HARMFUL)]
            if harmful_list:
                harmful = random.choice(harmful_list)
                harm_name = harmful["name"]
                if harm_name not in child.dormant_genes["traits"]:
                    child.dormant_genes["traits"][harm_name] = {
                        "potential_value": 0,
                        "target_trait": harmful.get("target_trait"),
                        "value_modifier": harmful.get("value_modifier", -1.0),
                        "activation_threshold": 0.35,
                        "pressure_types": ["disease", "starvation"],
                        "exposure_count": 0,
                        "activated": False,
                        "inherited_from": "de_novo_mutation",
                        "dominance": DominanceType.RECESSIVE.value if DominanceType else "recessive",
                        "mutation_effect": harmful["effect"].value if hasattr(harmful["effect"], 'value') else str(harmful["effect"]),
                        "description": harmful.get("description", ""),
                    }
                    harmful_added += 1
                    logger.debug(f"[新突变] {child.lineage_code} 产生新有害突变: {harm_name}")
        
        # === 4. 从基因库继承（无数量上限） ===
        if genus and genus.gene_library:
            # 特质：继承所有可用的基因库特质（无上限）
            available_traits = list(genus.gene_library.get("traits", {}).keys())
            for trait_name in available_traits:
                if trait_name not in child.abstract_traits and trait_name not in child.dormant_genes["traits"]:
                    trait_data = genus.gene_library["traits"][trait_name]
                    dominance = roll_dominance("trait") if roll_dominance else "codominant"
                    dom_value = dominance.value if hasattr(dominance, 'value') else dominance
                    
                    child.dormant_genes["traits"][trait_name] = {
                        "potential_value": trait_data["max_value"] * random.uniform(0.8, 1.0),
                        "activation_threshold": 0.20,
                        "pressure_types": ["competition", "starvation"],
                        "exposure_count": 0,
                        "activated": False,
                        "inherited_from": trait_data["discovered_by"],
                        "dominance": dom_value,
                        "mutation_effect": "beneficial",
                    }
                    added_count += 1
            
            # 器官：继承所有可用的基因库器官（无上限）
            available_organs = list(genus.gene_library.get("organs", {}).keys())
            for organ_name in available_organs:
                if organ_name not in child.dormant_genes["organs"]:
                    organ_data = genus.gene_library["organs"][organ_name]
                    dominance = roll_dominance("organ") if roll_dominance else "codominant"
                    dom_value = dominance.value if hasattr(dominance, 'value') else dominance
                    
                    child.dormant_genes["organs"][organ_name] = {
                        "organ_data": {
                            "category": organ_data["category"],
                            "type": organ_data["type"],
                            "parameters": organ_data["parameters"]
                        },
                        "activation_threshold": 0.25,
                        "pressure_types": ["competition", "predation"],
                        "exposure_count": 0,
                        "activated": False,
                        "inherited_from": organ_data["discovered_by"],
                        "dominance": dom_value,
                        "development_stage": None,
                        "stage_start_turn": None,
                    }
                    added_count += 1
        
        if added_count > 0:
            if harmful_added > 0:
                logger.info(f"[基因补充] {child.lineage_code} 获得了 {added_count} 个额外休眠基因 (含 {harmful_added} 个新突变)")
            else:
                logger.info(f"[基因补充] {child.lineage_code} 获得了 {added_count} 个额外休眠基因")
    
    def update_activation_count(self, genus_code: str, gene_name: str, gene_type: str):
        """更新基因激活计数"""
        genus = genus_repository.get_by_code(genus_code)
        if not genus or not genus.gene_library:
            return
        
        if gene_type in genus.gene_library and gene_name in genus.gene_library[gene_type]:
            genus.gene_library[gene_type][gene_name]["activation_count"] += 1
            genus_repository.upsert(genus)
    
    def _infer_pressure_types(self, trait_name: str) -> list[str]:
        """根据特质名推断触发压力类型"""
        mapping = {
            "耐寒性": ["cold", "temperature"],
            "耐热性": ["heat", "temperature"],
            "耐旱性": ["drought", "humidity"],
            "耐盐性": ["salinity", "osmotic"],
            "耐极寒": ["extreme_cold", "polar"],
            "耐高压": ["deep_ocean", "high_pressure"],
            "光照需求": ["darkness", "light"],
        }
        return mapping.get(trait_name, ["adaptive"])

