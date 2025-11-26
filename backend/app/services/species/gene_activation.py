"""休眠基因激活服务"""
from __future__ import annotations

import logging
import random

from ...models.species import Species
from .gene_library import GeneLibraryService
from .trait_config import TraitConfig

logger = logging.getLogger(__name__)


class GeneActivationService:
    """处理物种休眠基因的激活"""
    
    def __init__(self):
        self.gene_library_service = GeneLibraryService()
    
    def check_and_activate(
        self,
        species: Species,
        death_rate: float,
        pressure_type: str,
        turn: int
    ) -> dict:
        """检查并激活休眠基因
        
        Returns:
            激活结果字典 {"traits": [...], "organs": [...]}
        """
        if not species.dormant_genes:
            return {"traits": [], "organs": []}
        
        activated = {"traits": [], "organs": []}
        
        if not species.stress_exposure:
            species.stress_exposure = {}
        
        species.stress_exposure.setdefault(pressure_type, {"count": 0, "max_death_rate": 0.0})
        species.stress_exposure[pressure_type]["count"] += 1
        species.stress_exposure[pressure_type]["max_death_rate"] = max(
            species.stress_exposure[pressure_type]["max_death_rate"],
            death_rate
        )
        
        activated_traits = self._check_trait_activation(species, death_rate, pressure_type, turn)
        activated_organs = self._check_organ_activation(species, death_rate, pressure_type, turn)
        
        activated["traits"] = activated_traits
        activated["organs"] = activated_organs
        
        return activated
    
    def _check_trait_activation(
        self,
        species: Species,
        death_rate: float,
        pressure_type: str,
        turn: int
    ) -> list[str]:
        """检查特质激活"""
        activated = []
        
        if "traits" not in species.dormant_genes:
            return activated
        
        for trait_name, gene_data in species.dormant_genes["traits"].items():
            if gene_data.get("activated", False):
                continue
            
            if pressure_type in gene_data.get("pressure_types", []):
                gene_data["exposure_count"] = gene_data.get("exposure_count", 0) + 1
            
            activation_threshold = gene_data.get("activation_threshold", 0.65)
            exposure_count = gene_data.get("exposure_count", 0)
            evolution_potential = species.hidden_traits.get("evolution_potential", 0.5)
            
            if (death_rate > activation_threshold and
                exposure_count >= 3 and
                random.random() < evolution_potential * 0.35):
                
                potential_value = gene_data.get("potential_value", 8.0)
                test_traits = dict(species.abstract_traits)
                test_traits[trait_name] = TraitConfig.clamp_trait(potential_value)
                
                valid, error_msg = TraitConfig.validate_traits_with_trophic(
                    test_traits, species.trophic_level
                )
                
                if valid:
                    species.abstract_traits[trait_name] = TraitConfig.clamp_trait(potential_value)
                    gene_data["activated"] = True
                    gene_data["activation_turn"] = turn
                    activated.append(trait_name)
                    
                    logger.info(f"[基因激活] {species.common_name} 激活特质: {trait_name} = {potential_value:.1f}")
                    
                    if species.genus_code:
                        self.gene_library_service.update_activation_count(
                            species.genus_code, trait_name, "traits"
                        )
                else:
                    logger.warning(f"[基因激活] {species.common_name} 激活{trait_name}失败: {error_msg}")
        
        return activated
    
    def _check_organ_activation(
        self,
        species: Species,
        death_rate: float,
        pressure_type: str,
        turn: int
    ) -> list[str]:
        """检查器官激活"""
        activated = []
        
        if "organs" not in species.dormant_genes:
            return activated
        
        for organ_name, gene_data in species.dormant_genes["organs"].items():
            if gene_data.get("activated", False):
                continue
            
            if pressure_type in gene_data.get("pressure_types", []):
                gene_data["exposure_count"] = gene_data.get("exposure_count", 0) + 1
            
            activation_threshold = gene_data.get("activation_threshold", 0.70)
            exposure_count = gene_data.get("exposure_count", 0)
            evolution_potential = species.hidden_traits.get("evolution_potential", 0.5)
            
            if (death_rate > activation_threshold and
                exposure_count >= 3 and
                random.random() < evolution_potential * 0.30):
                
                organ_data = gene_data.get("organ_data", {})
                organ_category = organ_data.get("category", "sensory")
                
                species.organs[organ_category] = {
                    "type": organ_data.get("type", organ_name),
                    "parameters": organ_data.get("parameters", {}),
                    "acquired_turn": turn,
                    "is_active": True
                }
                gene_data["activated"] = True
                gene_data["activation_turn"] = turn
                activated.append(organ_name)
                
                logger.info(f"[基因激活] {species.common_name} 激活器官: {organ_name} ({organ_category})")
                
                if species.genus_code:
                    self.gene_library_service.update_activation_count(
                        species.genus_code, organ_name, "organs"
                    )
        
        return activated
    
    def batch_check(self, species_list: list[Species], mortality_results: list, turn: int):
        """批量检查物种的基因激活"""
        activation_events = []
        
        mortality_map = {}
        for r in mortality_results:
            if isinstance(r, dict):
                code = r.get("lineage_code")
            else:
                code = r.species.lineage_code
            if code:
                mortality_map[code] = r
        
        for species in species_list:
            if species.lineage_code not in mortality_map:
                continue
            
            result = mortality_map[species.lineage_code]
            
            if isinstance(result, dict):
                death_rate = result.get("death_rate", 0.0)
            else:
                death_rate = result.death_rate
            
            if death_rate < 0.5:
                continue
            
            pressure_type = self._infer_pressure_type(result)
            
            activated = self.check_and_activate(species, death_rate, pressure_type, turn)
            
            if activated["traits"] or activated["organs"]:
                activation_events.append({
                    "lineage_code": species.lineage_code,
                    "common_name": species.common_name,
                    "activated_traits": activated["traits"],
                    "activated_organs": activated["organs"],
                    "death_rate": death_rate
                })
        
        return activation_events
    
    def _infer_pressure_type(self, mortality_result) -> str:
        """从死亡率结果推断压力类型"""
        # 处理 dataclass 对象
        if not isinstance(mortality_result, dict):
            # 如果是 MortalityResult 对象，它可能没有 pressure_breakdown 字段
            # 这里的逻辑需要检查 MortalityResult 定义
            return "adaptive"

        if "pressure_breakdown" in mortality_result:
            breakdown = mortality_result["pressure_breakdown"]
            if breakdown.get("temperature", 0) > 0.3:
                return "temperature"
            if breakdown.get("humidity", 0) > 0.3:
                return "drought"
            if breakdown.get("resource_competition", 0) > 0.3:
                return "competition"
        
        return "adaptive"

