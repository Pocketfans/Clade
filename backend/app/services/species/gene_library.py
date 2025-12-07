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
        genus: Genus
    ):
        """子代继承休眠基因 v2.0 - 支持显隐性、发育阶段、有害突变
        
        【v2.0 更新】
        - 继承显隐性类型
        - 继承有害突变（遗传负荷）
        - 器官发育状态重置
        - 隐性有害突变有更高的继承概率（被自然选择保留）
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
        
        if not child.dormant_genes:
            child.dormant_genes = {"traits": {}, "organs": {}}
        
        child.dormant_genes.setdefault("traits", {})
        child.dormant_genes.setdefault("organs", {})
        
        inherited_count = 0
        harmful_inherited = 0
        
        # === 1. 从父代休眠基因继承（保留新字段） ===
        # 【修复】提高继承概率：确保子代能继承父代 90%+ 的基因
        if parent.dormant_genes:
            # 继承特质
            parent_traits = parent.dormant_genes.get("traits", {})
            for trait_name, gene_data in parent_traits.items():
                if gene_data.get("activated"):
                    continue  # 跳过已激活的
                
                # 计算继承概率【提高：基础概率从 0.50 提升到 0.90】
                inherit_prob = 0.90
                
                # 有害突变的继承概率
                mutation_effect = gene_data.get("mutation_effect", "beneficial")
                is_harmful = mutation_effect in ("mildly_harmful", "harmful", "lethal")
                
                if is_harmful:
                    dominance = gene_data.get("dominance", "codominant")
                    if dominance == "recessive":
                        inherit_prob = 0.85  # 隐性有害突变容易遗传（被自然选择隐藏）
                    else:
                        inherit_prob = 0.40  # 显性有害突变难以遗传
                
                if random.random() < inherit_prob:
                    # 复制基因数据并更新
                    new_gene = dict(gene_data)
                    new_gene["exposure_count"] = 0
                    new_gene["activated"] = False
                    new_gene["inherited_from"] = parent.lineage_code
                    
                    child.dormant_genes["traits"][trait_name] = new_gene
                    inherited_count += 1
                    if is_harmful:
                        harmful_inherited += 1
            
            # 继承器官【提高：从 0.40 提升到 0.85】
            parent_organs = parent.dormant_genes.get("organs", {})
            for organ_name, gene_data in parent_organs.items():
                if gene_data.get("activated") and gene_data.get("development_stage") == 3:
                    continue  # 跳过已成熟的器官
                
                if random.random() < 0.85:
                    new_gene = dict(gene_data)
                    new_gene["exposure_count"] = 0
                    new_gene["activated"] = False
                    new_gene["development_stage"] = None  # 重置发育阶段
                    new_gene["stage_start_turn"] = None
                    new_gene["inherited_from"] = parent.lineage_code
                    
                    child.dormant_genes["organs"][organ_name] = new_gene
                    inherited_count += 1
        
        # === 2. 从父代表型特质生成休眠基因 ===
        # 【提高】从 0.50 提升到 0.80，确保表型特质也能稳定遗传
        for trait_name, trait_value in (parent.abstract_traits or {}).items():
            if trait_name in child.dormant_genes["traits"]:
                continue
                
            if random.random() < 0.80:
                dominance = roll_dominance("trait") if roll_dominance else "codominant"
                dom_value = dominance.value if hasattr(dominance, 'value') else dominance
                
                child.dormant_genes["traits"][trait_name] = {
                    "potential_value": min(15.0, trait_value * 1.20),
                    "activation_threshold": 0.20,
                    "pressure_types": self._infer_pressure_types(trait_name),
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": parent.lineage_code,
                    "dominance": dom_value,
                    "mutation_effect": "beneficial",
                }
                inherited_count += 1
        
        # === 3. 从父代器官生成变异潜力 ===
        # 【提高】从 0.40 提升到 0.75，确保器官变异潜力能稳定遗传
        if parent.organs:
            for organ_cat, organ_data in parent.organs.items():
                if random.random() < 0.75:
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
                        inherited_count += 1
        
        # === 4. 新突变：子代独有的有害突变（遗传负荷模拟） ===
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
                    harmful_inherited += 1
                    logger.debug(f"[新突变] {child.lineage_code} 产生新有害突变: {harm_name}")
        
        # === 5. 从基因库继承 ===
        if genus and genus.gene_library:
            available_traits = list(genus.gene_library.get("traits", {}).keys())
            if available_traits:
                inherit_count = min(4, len(available_traits))
                for trait_name in random.sample(available_traits, inherit_count):
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
                        inherited_count += 1
            
            available_organs = list(genus.gene_library.get("organs", {}).keys())
            if available_organs:
                inherit_count = min(2, len(available_organs))
                for organ_name in random.sample(available_organs, inherit_count):
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
                        inherited_count += 1
        
        if inherited_count > 0:
            if harmful_inherited > 0:
                logger.info(f"[基因遗传] {child.lineage_code} 继承了 {inherited_count} 个休眠基因 (含 {harmful_inherited} 个有害)")
            else:
                logger.info(f"[基因遗传] {child.lineage_code} 继承了 {inherited_count} 个休眠基因")
    
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

