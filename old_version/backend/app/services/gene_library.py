"""属基因库管理服务"""
from __future__ import annotations

import random

from ..models.genus import Genus
from ..models.species import Species
from ..repositories.genus_repository import genus_repository


class GeneLibraryService:
    """管理属级基因库，记录属的演化潜力"""
    
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
                    print(f"[基因库] {genus.name_common}属发现新特质: {trait_name} (by {discoverer_code})")
        
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
                    print(f"[基因库] {genus.name_common}属发现新器官: {organ_name} (by {discoverer_code})")
        
        genus.updated_turn = turn
        genus_repository.upsert(genus)
    
    def inherit_dormant_genes(
        self, 
        parent: Species, 
        child: Species,
        genus: Genus
    ):
        """子代继承休眠基因"""
        if not child.dormant_genes:
            child.dormant_genes = {"traits": {}, "organs": {}}
        
        child.dormant_genes.setdefault("traits", {})
        child.dormant_genes.setdefault("organs", {})
        
        inherited_count = 0
        
        for trait_name, trait_value in parent.abstract_traits.items():
            if random.random() < 0.25:
                child.dormant_genes["traits"][trait_name] = {
                    "potential_value": min(15.0, trait_value * 1.15),
                    "activation_threshold": 0.6,
                    "pressure_types": self._infer_pressure_types(trait_name),
                    "exposure_count": 0,
                    "activated": False,
                    "inherited_from": parent.lineage_code
                }
                inherited_count += 1
        
        if genus and genus.gene_library:
            available_traits = list(genus.gene_library.get("traits", {}).keys())
            if available_traits:
                inherit_count = min(2, len(available_traits))
                for trait_name in random.sample(available_traits, inherit_count):
                    if trait_name not in child.abstract_traits and trait_name not in child.dormant_genes["traits"]:
                        trait_data = genus.gene_library["traits"][trait_name]
                        child.dormant_genes["traits"][trait_name] = {
                            "potential_value": trait_data["max_value"] * random.uniform(0.7, 0.9),
                            "activation_threshold": 0.65,
                            "pressure_types": ["adaptive"],
                            "exposure_count": 0,
                            "activated": False,
                            "inherited_from": trait_data["discovered_by"]
                        }
                        inherited_count += 1
            
            available_organs = list(genus.gene_library.get("organs", {}).keys())
            if available_organs:
                inherit_count = min(1, len(available_organs))
                for organ_name in random.sample(available_organs, inherit_count):
                    if organ_name not in child.dormant_genes["organs"]:
                        organ_data = genus.gene_library["organs"][organ_name]
                        child.dormant_genes["organs"][organ_name] = {
                            "organ_data": {
                                "category": organ_data["category"],
                                "type": organ_data["type"],
                                "parameters": organ_data["parameters"]
                            },
                            "activation_threshold": 0.70,
                            "pressure_types": ["adaptive"],
                            "exposure_count": 0,
                            "activated": False,
                            "inherited_from": organ_data["discovered_by"]
                        }
                        inherited_count += 1
        
        if inherited_count > 0:
            print(f"[基因遗传] {child.lineage_code} 继承了 {inherited_count} 个休眠基因")
    
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

