"""植物竞争计算器 - 处理植物间的光照和养分竞争

【设计原理】
植物竞争主要体现在两个维度：
1. 光照竞争：高大植物遮蔽矮小植物，与growth_form和木质化程度相关
2. 养分竞争：根系发达的植物抢夺更多土壤养分

【优化】
- 全矩阵化计算：使用numpy批量处理所有地块和物种
- Embedding增强：利用物种向量相似度预测竞争强度
- 缓存优化：避免重复计算

【竞争结果】
- 竞争压力转化为额外死亡率
- 竞争劣势方需要更多演化适应（如耐阴性、浅根策略）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.environment import HabitatPopulation, MapTile
    from ..system.embedding import EmbeddingService

from .trait_config import PlantTraitConfig  # 【统一】使用统一的植物检测

logger = logging.getLogger(__name__)


@dataclass
class PlantCompetitionResult:
    """单个植物物种的竞争结果"""
    species_id: int
    lineage_code: str
    
    # 光照竞争
    light_received: float  # 接收到的相对光照量 (0-1)
    light_competitors: int  # 遮蔽它的物种数量
    light_pressure: float   # 光照竞争压力 (0-1)
    
    # 养分竞争
    nutrient_share: float   # 获得的养分份额 (0-1)
    nutrient_competitors: int  # 养分竞争者数量
    nutrient_pressure: float  # 养分竞争压力 (0-1)
    
    # 综合竞争压力
    total_pressure: float  # 总竞争压力 (0-1)


# 生长形式的高度等级（用于光照竞争）- 向量化用
GROWTH_FORM_TO_HEIGHT_RANK = {
    "aquatic": 0,   # 水生藻类：无光照竞争（水下）
    "moss": 1,      # 苔藓：最矮
    "herb": 2,      # 草本：中等
    "shrub": 3,     # 灌木：较高
    "tree": 4,      # 乔木：最高
}

# 生长形式的基准高度（厘米）
GROWTH_FORM_TO_BASE_HEIGHT = {
    "aquatic": 0.1,   # 水生：假设漂浮
    "moss": 5,        # 苔藓：约5cm
    "herb": 50,       # 草本：约50cm
    "shrub": 200,     # 灌木：约2m
    "tree": 1000,     # 乔木：约10m起步
}


class PlantCompetitionCalculator:
    """植物竞争计算器（矩阵优化版）
    
    【优化特性】
    1. 全矩阵化：一次计算所有地块×物种的竞争
    2. Embedding增强：相似物种竞争更激烈
    3. 向量化属性提取：避免逐个循环
    """
    
    # 光照竞争系数
    LIGHT_REDUCTION_PER_LAYER = 0.25
    MAX_LIGHT_PRESSURE = 0.4
    
    # 养分竞争系数
    MAX_NUTRIENT_PRESSURE = 0.3
    
    # 总压力上限
    MAX_TOTAL_PRESSURE = 0.5
    
    def __init__(self, embedding_service: 'EmbeddingService | None' = None):
        self._embeddings = embedding_service
        self._cache: dict[int, dict[int, PlantCompetitionResult]] = {}
        
        # 矩阵缓存
        self._last_pressure_matrix: np.ndarray | None = None
        self._species_similarity_matrix: np.ndarray | None = None
    
    def set_embedding_service(self, embedding_service: 'EmbeddingService') -> None:
        """设置Embedding服务"""
        self._embeddings = embedding_service
    
    def compute_competition_matrix(
        self,
        species_list: Sequence['Species'],
        population_matrix: np.ndarray,
        tile_resources: np.ndarray,
    ) -> np.ndarray:
        """【核心】矩阵化计算植物竞争压力
        
        Args:
            species_list: 物种列表
            population_matrix: (n_tiles, n_species) 种群分布矩阵
            tile_resources: (n_tiles,) 地块资源向量
            
        Returns:
            (n_tiles, n_species) 竞争压力矩阵
        """
        n_tiles, n_species = population_matrix.shape
        
        # ========== 1. 提取物种属性向量 ==========
        plant_mask, heights, root_strengths, weights = self._extract_plant_attributes(species_list)
        
        # 非植物压力为0
        if not np.any(plant_mask):
            return np.zeros((n_tiles, n_species), dtype=np.float32)
        
        # ========== 2. 计算生物量矩阵 ==========
        # biomass_matrix[tile, species] = population × weight
        biomass_matrix = population_matrix * weights[np.newaxis, :]
        
        # ========== 3. 矩阵化光照竞争 ==========
        light_pressure = self._compute_light_pressure_matrix(
            population_matrix, biomass_matrix, heights, plant_mask
        )
        
        # ========== 4. 矩阵化养分竞争 ==========
        nutrient_pressure = self._compute_nutrient_pressure_matrix(
            population_matrix, biomass_matrix, root_strengths, tile_resources, plant_mask
        )
        
        # ========== 5. Embedding相似度增强（可选）==========
        similarity_boost = self._compute_similarity_boost_matrix(
            species_list, population_matrix, plant_mask
        )
        
        # ========== 6. 综合竞争压力 ==========
        # 总压力 = 光照压力×0.6 + 养分压力×0.4，再乘以相似度加成
        total_pressure = (
            light_pressure * 0.6 + nutrient_pressure * 0.4
        ) * similarity_boost
        
        # 非植物压力置0
        total_pressure[:, ~plant_mask] = 0.0
        
        # 缓存结果
        self._last_pressure_matrix = np.clip(total_pressure, 0.0, self.MAX_TOTAL_PRESSURE)
        
        return self._last_pressure_matrix
    
    def _extract_plant_attributes(
        self, 
        species_list: Sequence['Species']
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """向量化提取植物属性
        
        Returns:
            (plant_mask, heights, root_strengths, weights)
        """
        n = len(species_list)
        
        plant_mask = np.zeros(n, dtype=bool)
        heights = np.zeros(n, dtype=np.float32)
        root_strengths = np.zeros(n, dtype=np.float32)
        weights = np.zeros(n, dtype=np.float32)
        
        for i, sp in enumerate(species_list):
            # 【统一】使用 PlantTraitConfig.is_plant
            is_plant_species = PlantTraitConfig.is_plant(sp)
            plant_mask[i] = is_plant_species
            
            if is_plant_species:
                # 计算有效高度
                growth_form = getattr(sp, 'growth_form', 'aquatic')
                base_height = GROWTH_FORM_TO_BASE_HEIGHT.get(growth_form, 10)
                
                traits = sp.abstract_traits or {}
                lignification = traits.get("木质化程度", 0.0)
                height_modifier = 1.0 + lignification * 0.1
                
                body_length = sp.morphology_stats.get("body_length_cm", 1.0)
                heights[i] = max(body_length, base_height) * height_modifier
                
                # 计算根系强度
                root_dev = traits.get("根系发达度", 0.0)
                nutrient_abs = traits.get("养分吸收", 5.0)
                life_stage = getattr(sp, 'life_form_stage', 0)
                stage_bonus = max(0, life_stage - 3) * 0.5 if life_stage >= 4 else 0
                
                if growth_form == "aquatic":
                    root_strengths[i] = 0.1
                else:
                    root_strengths[i] = max(0.1, root_dev + nutrient_abs * 0.2 + stage_bonus)
            
            weights[i] = sp.morphology_stats.get("body_weight_g", 1.0)
        
        return plant_mask, heights, root_strengths, weights
    
    def _compute_light_pressure_matrix(
        self,
        population_matrix: np.ndarray,
        biomass_matrix: np.ndarray,
        heights: np.ndarray,
        plant_mask: np.ndarray,
    ) -> np.ndarray:
        """矩阵化计算光照竞争压力
        
        原理：每个物种的光照压力 = 被更高物种遮蔽的程度
        """
        n_tiles, n_species = population_matrix.shape
        light_pressure = np.zeros((n_tiles, n_species), dtype=np.float32)
        
        # 只处理植物
        plant_indices = np.where(plant_mask)[0]
        if len(plant_indices) == 0:
            return light_pressure
        
        # 按高度排序（降序）
        sorted_indices = plant_indices[np.argsort(-heights[plant_indices])]
        sorted_heights = heights[sorted_indices]
        
        # 对每个地块计算
        for tile_idx in range(n_tiles):
            tile_biomass = biomass_matrix[tile_idx, sorted_indices]
            
            # 跳过空地块
            if tile_biomass.sum() < 1e-10:
                continue
            
            # 累积遮蔽（从高到低）
            remaining_light = 1.0
            
            for i, sp_idx in enumerate(sorted_indices):
                # 当前物种获得的光照
                current_light = remaining_light
                
                # 光照压力 = 1 - 获得的光照
                pressure = max(0.0, 1.0 - current_light)
                light_pressure[tile_idx, sp_idx] = min(self.MAX_LIGHT_PRESSURE, pressure * 0.5)
                
                # 该物种遮蔽下层
                if tile_biomass[i] > 0:
                    # 遮蔽比例与生物量相关
                    shade_factor = min(1.0, np.log10(tile_biomass[i] + 1) / 10.0)
                    shade_ratio = self.LIGHT_REDUCTION_PER_LAYER * (0.3 + 0.7 * shade_factor)
                    remaining_light = max(0.05, remaining_light * (1.0 - shade_ratio))
        
        return light_pressure
    
    def _compute_nutrient_pressure_matrix(
        self,
        population_matrix: np.ndarray,
        biomass_matrix: np.ndarray,
        root_strengths: np.ndarray,
        tile_resources: np.ndarray,
        plant_mask: np.ndarray,
    ) -> np.ndarray:
        """矩阵化计算养分竞争压力
        
        原理：每个物种的养分份额 ∝ 根系力 × log(生物量)
        """
        n_tiles, n_species = population_matrix.shape
        nutrient_pressure = np.zeros((n_tiles, n_species), dtype=np.float32)
        
        # 计算根系竞争力矩阵
        # root_power[tile, species] = root_strength × log(biomass + 1)
        log_biomass = np.log10(biomass_matrix + 1)
        root_power_matrix = root_strengths[np.newaxis, :] * log_biomass
        
        # 只考虑植物
        root_power_matrix[:, ~plant_mask] = 0.0
        
        # 每个地块的总根系力
        total_root_power = root_power_matrix.sum(axis=1, keepdims=True)  # (n_tiles, 1)
        
        # 避免除零
        total_root_power = np.maximum(total_root_power, 1e-10)
        
        # 每个物种的份额
        share_matrix = root_power_matrix / total_root_power  # (n_tiles, n_species)
        
        # 植物数量（每个地块）
        plant_count = (population_matrix[:, plant_mask] > 0).sum(axis=1, keepdims=True)  # (n_tiles, 1)
        plant_count = np.maximum(plant_count, 1)
        
        # 理想份额
        ideal_share = 1.0 / plant_count  # (n_tiles, 1)
        
        # 养分压力 = max(0, 理想份额 - 实际份额) / 理想份额
        with np.errstate(divide='ignore', invalid='ignore'):
            pressure = np.maximum(0, ideal_share - share_matrix) / ideal_share
            pressure = np.nan_to_num(pressure, 0.0)
        
        # 地块资源稀缺性修正
        scarcity_modifier = 1.0 + (1.0 - tile_resources[:, np.newaxis] / 100.0) * 0.5
        nutrient_pressure = pressure * scarcity_modifier
        
        # 非植物压力置0
        nutrient_pressure[:, ~plant_mask] = 0.0
        
        return np.clip(nutrient_pressure, 0.0, self.MAX_NUTRIENT_PRESSURE)
    
    def _compute_similarity_boost_matrix(
        self,
        species_list: Sequence['Species'],
        population_matrix: np.ndarray,
        plant_mask: np.ndarray,
    ) -> np.ndarray:
        """计算Embedding相似度竞争加成
        
        相似物种竞争更激烈
        """
        n_tiles, n_species = population_matrix.shape
        
        # 默认无加成
        boost_matrix = np.ones((n_tiles, n_species), dtype=np.float32)
        
        if self._embeddings is None:
            return boost_matrix
        
        try:
            # 获取物种向量
            plant_indices = np.where(plant_mask)[0]
            if len(plant_indices) < 2:
                return boost_matrix
            
            plant_codes = [species_list[i].lineage_code for i in plant_indices]
            vectors, found_codes = self._embeddings.get_species_vectors(plant_codes)
            
            if vectors.shape[0] < 2:
                return boost_matrix
            
            # 计算相似度矩阵 (n_plants × n_plants)
            # 归一化
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-10)
            normalized = vectors / norms
            
            similarity_matrix = normalized @ normalized.T  # 余弦相似度
            
            # 对每个地块，计算每个物种与共存物种的平均相似度
            code_to_idx = {code: i for i, code in enumerate(found_codes)}
            
            for tile_idx in range(n_tiles):
                tile_pop = population_matrix[tile_idx, :]
                present_plants = [i for i in plant_indices if tile_pop[i] > 0]
                
                if len(present_plants) < 2:
                    continue
                
                for sp_idx in present_plants:
                    code = species_list[sp_idx].lineage_code
                    if code not in code_to_idx:
                        continue
                    
                    vec_idx = code_to_idx[code]
                    
                    # 与其他共存物种的平均相似度
                    similarities = []
                    for other_idx in present_plants:
                        if other_idx == sp_idx:
                            continue
                        other_code = species_list[other_idx].lineage_code
                        if other_code in code_to_idx:
                            other_vec_idx = code_to_idx[other_code]
                            similarities.append(similarity_matrix[vec_idx, other_vec_idx])
                    
                    if similarities:
                        avg_similarity = np.mean(similarities)
                        # 相似度越高，竞争加成越大（1.0-1.5倍）
                        boost_matrix[tile_idx, sp_idx] = 1.0 + avg_similarity * 0.5
            
        except Exception as e:
            logger.debug(f"[PlantCompetition] Embedding计算失败: {e}")
        
        return boost_matrix
    
    def get_pressure_matrix(self) -> np.ndarray | None:
        """获取上次计算的压力矩阵"""
        return self._last_pressure_matrix
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._last_pressure_matrix = None
        self._species_similarity_matrix = None
    
    # ==================== 兼容旧接口 ====================
    
    def is_plant(self, species: 'Species') -> bool:
        """判断物种是否为植物
        
        【统一】委托给 PlantTraitConfig.is_plant，避免重复实现
        """
        return PlantTraitConfig.is_plant(species)
    
    def calculate_batch_competition(
        self,
        tiles: dict[int, 'MapTile'],
        species_list: Sequence['Species'],
        habitats: Sequence['HabitatPopulation'],
    ) -> dict[int, dict[int, PlantCompetitionResult]]:
        """批量计算（兼容旧接口，内部使用矩阵优化）"""
        self.clear_cache()
        
        # 构建映射
        species_map = {sp.id: sp for sp in species_list if sp.id}
        tile_list = sorted(tiles.values(), key=lambda t: t.id)
        tile_id_to_idx = {t.id: i for i, t in enumerate(tile_list)}
        species_id_to_idx = {sp.id: i for i, sp in enumerate(species_list) if sp.id}
        
        n_tiles = len(tile_list)
        n_species = len(species_list)
        
        if n_tiles == 0 or n_species == 0:
            return {}
        
        # 构建种群矩阵
        population_matrix = np.zeros((n_tiles, n_species), dtype=np.float64)
        for habitat in habitats:
            tile_idx = tile_id_to_idx.get(habitat.tile_id)
            species_idx = species_id_to_idx.get(habitat.species_id)
            if tile_idx is not None and species_idx is not None:
                population_matrix[tile_idx, species_idx] = habitat.population
        
        # 地块资源向量
        tile_resources = np.array([
            getattr(t, 'resource', 50.0) for t in tile_list
        ], dtype=np.float32)
        
        # 矩阵计算
        pressure_matrix = self.compute_competition_matrix(
            species_list, population_matrix, tile_resources
        )
        
        # 转换为结果字典
        results = {}
        for tile_idx, tile in enumerate(tile_list):
            tile_id = tile.id
            results[tile_id] = {}
            
            for species_idx, sp in enumerate(species_list):
                if sp.id is None or population_matrix[tile_idx, species_idx] == 0:
                    continue
                if not self.is_plant(sp):
                    continue
                
                pressure = pressure_matrix[tile_idx, species_idx]
                
                results[tile_id][sp.id] = PlantCompetitionResult(
                    species_id=sp.id,
                    lineage_code=sp.lineage_code,
                    light_received=1.0 - pressure * 0.6,
                    light_competitors=0,  # 简化
                    light_pressure=pressure * 0.6,
                    nutrient_share=1.0 - pressure * 0.4,
                    nutrient_competitors=0,  # 简化
                    nutrient_pressure=pressure * 0.4,
                    total_pressure=pressure,
                )
        
        self._cache = results
        return results
    
    def get_competition_pressure_matrix(
        self,
        species_list: Sequence['Species'],
        tile_results: dict[int, dict[int, PlantCompetitionResult]],
        n_tiles: int,
    ) -> np.ndarray:
        """获取压力矩阵（兼容旧接口）"""
        if self._last_pressure_matrix is not None:
            return self._last_pressure_matrix
        
        # 从结果重建
        n_species = len(species_list)
        pressure_matrix = np.zeros((n_tiles, n_species), dtype=np.float32)
        
        species_idx_map = {sp.id: idx for idx, sp in enumerate(species_list) if sp.id}
        
        for tile_id, species_results in tile_results.items():
            if tile_id >= n_tiles:
                continue
            for species_id, result in species_results.items():
                species_idx = species_idx_map.get(species_id)
                if species_idx is not None:
                    pressure_matrix[tile_id, species_idx] = result.total_pressure
        
        return pressure_matrix
    
    def get_species_competition_summary(
        self,
        species: 'Species',
        species_list: Sequence['Species'],
    ) -> dict:
        """【新增】获取单个物种的竞争压力摘要（用于AI演化决策）
        
        Args:
            species: 目标物种
            species_list: 所有物种列表
            
        Returns:
            竞争摘要字典，包含压力值和主要竞争者
        """
        if not self.is_plant(species):
            return {
                "is_plant": False,
                "light_pressure": 0.0,
                "nutrient_pressure": 0.0,
                "total_pressure": 0.0,
                "main_competitors": [],
                "competition_strategy": "none",
            }
        
        # 从缓存获取该物种的竞争结果
        species_results = []
        for tile_id, tile_results in self._cache.items():
            if species.id in tile_results:
                species_results.append(tile_results[species.id])
        
        if not species_results:
            return {
                "is_plant": True,
                "light_pressure": 0.0,
                "nutrient_pressure": 0.0,
                "total_pressure": 0.0,
                "main_competitors": [],
                "competition_strategy": "pioneer",  # 无竞争者，先锋策略
            }
        
        # 计算平均竞争压力
        avg_light = sum(r.light_pressure for r in species_results) / len(species_results)
        avg_nutrient = sum(r.nutrient_pressure for r in species_results) / len(species_results)
        avg_total = sum(r.total_pressure for r in species_results) / len(species_results)
        
        # 找出主要竞争者（与该物种共存且高度更高的植物）
        main_competitors = self._find_main_competitors(species, species_list)
        
        # 推荐竞争策略
        strategy = self._suggest_competition_strategy(species, avg_light, avg_nutrient)
        
        return {
            "is_plant": True,
            "light_pressure": round(avg_light, 3),
            "nutrient_pressure": round(avg_nutrient, 3),
            "total_pressure": round(avg_total, 3),
            "main_competitors": main_competitors,
            "competition_strategy": strategy,
        }
    
    def _find_main_competitors(
        self,
        species: 'Species',
        species_list: Sequence['Species'],
        max_count: int = 3,
    ) -> list[dict]:
        """找出主要竞争者"""
        competitors = []
        
        species_height = self._get_species_height(species)
        species_root = self._get_species_root_strength(species)
        
        for other in species_list:
            if other.id == species.id or not self.is_plant(other):
                continue
            
            other_height = self._get_species_height(other)
            other_root = self._get_species_root_strength(other)
            
            # 计算竞争关系
            competes_for_light = other_height > species_height
            competes_for_nutrients = other_root > species_root * 0.8
            
            if competes_for_light or competes_for_nutrients:
                threat_level = 0.0
                threat_type = []
                
                if competes_for_light:
                    threat_level += (other_height - species_height) / max(species_height, 1.0) * 0.6
                    threat_type.append("光照")
                
                if competes_for_nutrients:
                    threat_level += (other_root - species_root) / max(species_root, 0.1) * 0.4
                    threat_type.append("养分")
                
                competitors.append({
                    "lineage_code": other.lineage_code,
                    "common_name": other.common_name,
                    "threat_level": min(1.0, threat_level),
                    "threat_type": "/".join(threat_type),
                    "growth_form": getattr(other, 'growth_form', 'unknown'),
                })
        
        # 按威胁程度排序，取前N个
        competitors.sort(key=lambda x: x["threat_level"], reverse=True)
        return competitors[:max_count]
    
    def _get_species_height(self, species: 'Species') -> float:
        """获取物种高度"""
        growth_form = getattr(species, 'growth_form', 'aquatic')
        base_height = GROWTH_FORM_TO_BASE_HEIGHT.get(growth_form, 10)
        
        traits = species.abstract_traits or {}
        lignification = traits.get("木质化程度", 0.0)
        height_modifier = 1.0 + lignification * 0.1
        
        body_length = species.morphology_stats.get("body_length_cm", 1.0)
        return max(body_length, base_height) * height_modifier
    
    def _get_species_root_strength(self, species: 'Species') -> float:
        """获取物种根系强度"""
        growth_form = getattr(species, 'growth_form', 'aquatic')
        if growth_form == "aquatic":
            return 0.1
        
        traits = species.abstract_traits or {}
        root_dev = traits.get("根系发达度", 0.0)
        nutrient_abs = traits.get("养分吸收", 5.0)
        life_stage = getattr(species, 'life_form_stage', 0)
        stage_bonus = max(0, life_stage - 3) * 0.5 if life_stage >= 4 else 0
        
        return max(0.1, root_dev + nutrient_abs * 0.2 + stage_bonus)
    
    def _suggest_competition_strategy(
        self,
        species: 'Species',
        light_pressure: float,
        nutrient_pressure: float,
    ) -> str:
        """根据竞争压力推荐演化策略"""
        growth_form = getattr(species, 'growth_form', 'aquatic')
        life_stage = getattr(species, 'life_form_stage', 0)
        
        if light_pressure < 0.1 and nutrient_pressure < 0.1:
            return "pioneer"  # 先锋策略：无竞争压力，可快速扩张
        
        if light_pressure > nutrient_pressure * 1.5:
            # 光照竞争为主
            if growth_form in ["moss", "herb"]:
                return "shade_tolerance"  # 耐阴策略
            elif life_stage >= 5:
                return "height_growth"  # 增高策略（成为乔木）
            else:
                return "canopy_gap"  # 林窗策略
        
        elif nutrient_pressure > light_pressure * 1.5:
            # 养分竞争为主
            if life_stage >= 4:
                return "deep_rooting"  # 深根策略
            else:
                return "nutrient_efficiency"  # 高效吸收策略
        
        else:
            # 综合竞争
            if light_pressure + nutrient_pressure > 0.4:
                return "niche_specialization"  # 生态位特化
            else:
                return "generalist"  # 泛化策略
    
    def format_competition_context(
        self,
        species: 'Species',
        species_list: Sequence['Species'],
    ) -> str:
        """【新增】格式化竞争上下文（直接用于Prompt）
        
        Args:
            species: 目标物种
            species_list: 所有物种列表
            
        Returns:
            格式化的竞争上下文文本
        """
        summary = self.get_species_competition_summary(species, species_list)
        
        if not summary["is_plant"]:
            return ""
        
        lines = ["【植物竞争状态】"]
        lines.append(f"光照竞争压力: {summary['light_pressure']:.0%}")
        lines.append(f"养分竞争压力: {summary['nutrient_pressure']:.0%}")
        lines.append(f"综合竞争压力: {summary['total_pressure']:.0%}")
        
        if summary["main_competitors"]:
            competitors_str = ", ".join([
                f"{c['common_name']}({c['threat_type']})"
                for c in summary["main_competitors"]
            ])
            lines.append(f"主要竞争者: {competitors_str}")
        else:
            lines.append("主要竞争者: 无（先锋物种）")
        
        strategy_names = {
            "pioneer": "先锋策略（快速扩张）",
            "shade_tolerance": "耐阴策略（发展耐阴性）",
            "height_growth": "增高策略（发展木质化）",
            "canopy_gap": "林窗策略（利用林窗）",
            "deep_rooting": "深根策略（发展根系）",
            "nutrient_efficiency": "高效吸收（提升养分吸收）",
            "niche_specialization": "生态位特化（差异化演化）",
            "generalist": "泛化策略（均衡发展）",
            "none": "非植物",
        }
        strategy_desc = strategy_names.get(summary["competition_strategy"], "未知")
        lines.append(f"建议演化策略: {strategy_desc}")
        
        # 【新增】获取食草动物压力
        herbivory = self.get_herbivory_pressure(species, species_list)
        if herbivory["pressure"] > 0.1:
            lines.append(f"\n【食草动物压力】")
            lines.append(f"被捕食压力: {herbivory['pressure']:.0%}")
            if herbivory["predators"]:
                lines.append(f"主要食草者: {', '.join(herbivory['predators'])}")
            lines.append(f"建议防御策略: {herbivory['suggested_defense']}")
        
        return "\n".join(lines)
    
    def get_herbivory_pressure(
        self,
        species: 'Species',
        species_list: Sequence['Species'],
    ) -> dict:
        """获取食草动物对该植物的捕食压力
        
        【增强】
        - 显式捕食关系：基于 prey_species 字段
        - 隐式捕食关系：基于营养级和栖息地推断
        
        Args:
            species: 目标植物物种
            species_list: 所有物种列表
            
        Returns:
            食草压力信息字典
        """
        if not self.is_plant(species):
            return {
                "pressure": 0.0,
                "predators": [],
                "suggested_defense": "none",
                "herbivore_count": 0,
                "implicit_pressure": 0.0,
            }
        
        # 找出所有将该植物作为猎物的食草动物
        herbivores = []
        total_predation_pressure = 0.0
        implicit_pressure = 0.0
        
        plant_habitat = getattr(species, 'habitat_type', 'unknown')
        
        for other in species_list:
            # 跳过自己和植物
            if other.id == species.id or self.is_plant(other):
                continue
            
            trophic = getattr(other, 'trophic_level', 0)
            diet = getattr(other, 'diet_type', '')
            other_habitat = getattr(other, 'habitat_type', 'unknown')
            
            # 显式捕食关系
            prey_species = getattr(other, 'prey_species', []) or []
            prey_preferences = getattr(other, 'prey_preferences', {}) or {}
            
            if species.lineage_code in prey_species:
                preference = prey_preferences.get(species.lineage_code, 0.5)
                population = other.morphology_stats.get("population", 0) or 0
                
                # 计算捕食压力：种群规模 × 偏好 / 归一化因子
                pressure_contribution = (population * preference) / 100000.0
                total_predation_pressure += pressure_contribution
                
                herbivores.append({
                    "lineage_code": other.lineage_code,
                    "common_name": other.common_name,
                    "population": population,
                    "preference": preference,
                    "pressure": pressure_contribution,
                    "type": "explicit",
                })
            
            # 【新增】隐式捕食关系推断
            # 草食动物（T2.0-2.5）可能捕食同栖息地的所有植物
            elif 2.0 <= trophic < 2.5 and diet in ['herbivore', 'omnivore']:
                # 检查栖息地兼容性
                if self._is_habitat_compatible(plant_habitat, other_habitat):
                    population = other.morphology_stats.get("population", 0) or 0
                    # 隐式压力较低（没有明确偏好）
                    pressure_contribution = (population * 0.1) / 100000.0
                    implicit_pressure += pressure_contribution
                    
                    herbivores.append({
                        "lineage_code": other.lineage_code,
                        "common_name": other.common_name,
                        "population": population,
                        "preference": 0.1,
                        "pressure": pressure_contribution,
                        "type": "implicit",
                    })
        
        # 按压力排序
        herbivores.sort(key=lambda x: x["pressure"], reverse=True)
        top_predators = [h["common_name"] for h in herbivores[:3]]
        
        # 归一化压力到0-1
        total_pressure = total_predation_pressure + implicit_pressure * 0.5  # 隐式压力权重降低
        normalized_pressure = min(1.0, total_pressure)
        
        # 推荐防御策略
        plant_traits = species.abstract_traits or {}
        current_chemical_defense = plant_traits.get("化学防御", 0.0)
        current_physical_defense = plant_traits.get("物理防御", 0.0)
        
        if normalized_pressure < 0.1:
            suggested_defense = "无需（压力低）"
        elif normalized_pressure > 0.5:
            # 高压力
            if current_chemical_defense < 3 and current_physical_defense < 3:
                suggested_defense = "紧急：发展化学防御（毒素/单宁）+ 物理防御（刺/硬壳）"
            else:
                suggested_defense = "快速繁殖（r-策略应对高压力）"
        elif current_chemical_defense < current_physical_defense:
            suggested_defense = "化学防御（发展毒素/单宁/苦味物质）"
        elif current_physical_defense < current_chemical_defense:
            suggested_defense = "物理防御（发展刺/硬壳/硅化表皮）"
        else:
            suggested_defense = "均衡防御（化学+物理）"
        
        return {
            "pressure": normalized_pressure,
            "predators": top_predators,
            "suggested_defense": suggested_defense,
            "herbivore_count": len(herbivores),
            "explicit_pressure": total_predation_pressure,
            "implicit_pressure": implicit_pressure,
        }
    
    def _is_habitat_compatible(self, plant_habitat: str, animal_habitat: str) -> bool:
        """检查栖息地是否兼容（动物能否接触到植物）"""
        # 定义栖息地兼容性
        compatibility = {
            "marine": ["marine", "coastal"],
            "freshwater": ["freshwater", "amphibious"],
            "coastal": ["coastal", "marine", "terrestrial", "amphibious"],
            "terrestrial": ["terrestrial", "amphibious", "aerial", "coastal"],
            "amphibious": ["amphibious", "freshwater", "terrestrial", "coastal"],
        }
        return animal_habitat in compatibility.get(plant_habitat, [plant_habitat])
    
    def format_herbivory_context_for_prompt(
        self,
        species: 'Species',
        species_list: Sequence['Species'],
    ) -> str:
        """【新增】格式化食草压力上下文（供Prompt使用）
        
        Args:
            species: 目标植物物种
            species_list: 所有物种列表
            
        Returns:
            格式化的食草压力上下文文本
        """
        herbivory = self.get_herbivory_pressure(species, species_list)
        
        if herbivory["pressure"] < 0.05:
            return "食草动物威胁: 无（暂无显著食草压力）"
        
        lines = []
        pressure_level = "低" if herbivory["pressure"] < 0.2 else "中" if herbivory["pressure"] < 0.5 else "高"
        lines.append(f"食草动物威胁: {pressure_level} ({herbivory['pressure']:.0%})")
        
        if herbivory["predators"]:
            lines.append(f"主要食草者: {', '.join(herbivory['predators'][:3])}")
        
        lines.append(f"食草动物数量: {herbivory['herbivore_count']}种")
        
        if herbivory["implicit_pressure"] > 0.05:
            lines.append(f"潜在威胁: 存在{herbivory['implicit_pressure']:.0%}的隐式捕食风险")
        
        lines.append(f"建议防御策略: {herbivory['suggested_defense']}")
        
        # 防御建议细节
        if herbivory["pressure"] > 0.3:
            lines.append("\n💡 高压防御建议:")
            lines.append("  - 化学防御: 发展毒素、单宁、苦味生物碱")
            lines.append("  - 物理防御: 发展刺、硅化表皮、蜡质层")
            lines.append("  - 器官建议: 毒腺、刺毛、树脂道")
        
        return "\n".join(lines)


# 全局实例
plant_competition_calculator = PlantCompetitionCalculator()
