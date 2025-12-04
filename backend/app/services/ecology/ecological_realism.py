"""生态拟真系统 (Ecological Realism System)

实现基于语义驱动的生态学机制，提升生态系统的真实性和复杂性。

【核心模块】
1. Allee 效应：小种群困境
2. 密度依赖疾病：高密度种群的疾病压力
3. 环境综合变数：长周期环境波动
4. 空间显式捕食：地理重叠影响捕食效率
5. 能量同化效率：基于物种特征的动态效率
6. 垂直生态位分层：减少同层竞争
7. 适应滞后：环境变化速率与适应能力的匹配
8. 互利共生网络：自动识别和维护共生关系

【设计原则】
- 语义驱动，拒绝硬编码
- 所有生态学判断通过 embedding 语义匹配实现
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.environment import MapTile, HabitatPopulation
    from ..system.embedding import EmbeddingService
    from .semantic_anchors import SemanticAnchorService

logger = logging.getLogger(__name__)


# ============================================================================
# 配置数据类
# ============================================================================

@dataclass
class EcologicalRealismConfig:
    """生态拟真配置"""
    
    # ========== Allee 效应 ==========
    enable_allee_effect: bool = True
    allee_critical_ratio: float = 0.1    # MVP 临界比例（相对于承载力）
    allee_max_penalty: float = 0.4       # 最大繁殖惩罚
    allee_steepness: float = 5.0         # S型曲线陡峭度
    
    # ========== 密度依赖疾病 ==========
    enable_density_disease: bool = True
    disease_density_threshold: float = 0.7  # 触发疾病的密度阈值
    disease_base_mortality: float = 0.15    # 基础疾病死亡率
    disease_social_factor: float = 0.3      # 群居性影响系数
    disease_resistance_factor: float = 0.5  # 抗病性减免系数
    
    # ========== 环境综合变数 ==========
    enable_env_fluctuation: bool = True
    fluctuation_period_turns: int = 20      # 波动周期（回合）
    fluctuation_amplitude: float = 0.2      # 波动幅度
    latitude_sensitivity: float = 1.5       # 高纬度敏感系数
    specialist_sensitivity: float = 1.3     # 专化物种敏感系数
    
    # ========== 空间显式捕食 ==========
    enable_spatial_predation: bool = True
    min_overlap_for_predation: float = 0.1  # 最小重叠度才能捕食
    overlap_efficiency_factor: float = 0.6  # 重叠度对效率的影响
    
    # ========== 能量同化效率 ==========
    enable_dynamic_assimilation: bool = True
    herbivore_base_efficiency: float = 0.12     # 草食基础效率
    carnivore_base_efficiency: float = 0.25     # 肉食基础效率
    detritivore_base_efficiency: float = 0.20   # 腐食基础效率
    filter_feeder_efficiency: float = 0.15      # 滤食效率
    endotherm_penalty: float = 0.7              # 恒温动物效率惩罚
    
    # ========== 垂直生态位 ==========
    enable_vertical_niche: bool = True
    same_layer_competition: float = 1.0     # 同层竞争系数
    adjacent_layer_competition: float = 0.3 # 相邻层竞争系数
    distant_layer_competition: float = 0.05 # 远层竞争系数
    
    # ========== 适应滞后 ==========
    enable_adaptation_lag: bool = True
    env_change_tracking_window: int = 5     # 环境变化追踪窗口（回合）
    max_adaptation_penalty: float = 0.3     # 最大适应惩罚
    plasticity_protection: float = 0.5      # 高可塑性保护系数
    generation_time_factor: float = 0.1     # 世代时间影响
    
    # ========== 互利共生 ==========
    enable_mutualism: bool = True
    mutualism_threshold: float = 0.6        # 共生匹配阈值
    mutualism_benefit: float = 0.1          # 共生伙伴存在时的加成
    mutualism_penalty: float = 0.15         # 共生伙伴灭绝时的惩罚


@dataclass
class AlleeEffectResult:
    """Allee 效应计算结果"""
    species_code: str
    population: int
    carrying_capacity: int
    ratio: float                    # 种群/承载力比例
    allee_factor: float             # Allee 效应因子 (0-1)
    reproduction_modifier: float    # 繁殖效率修正
    is_below_mvp: bool              # 是否低于 MVP


@dataclass
class DiseaseResult:
    """疾病压力计算结果"""
    species_code: str
    density_ratio: float            # 密度比例
    sociality_score: float          # 群居性得分
    resistance_score: float         # 抗病性得分
    disease_pressure: float         # 疾病压力
    mortality_modifier: float       # 死亡率修正


@dataclass 
class VerticalNicheResult:
    """垂直生态位分析结果"""
    species_code: str
    dominant_layer: str             # 主要活动层
    layer_profile: dict[str, float] # 各层相似度
    competition_modifier: float     # 竞争修正系数


@dataclass
class MutualismLink:
    """互利共生链接"""
    species_a: str
    species_b: str
    relationship_type: str          # pollination, seed_dispersal, mycorrhizal
    strength: float                 # 关系强度
    benefit_a: float                # A 从关系中获得的收益
    benefit_b: float                # B 从关系中获得的收益


# ============================================================================
# 生态拟真服务
# ============================================================================

class EcologicalRealismService:
    """生态拟真服务
    
    提供基于语义驱动的生态学机制计算。
    """
    
    def __init__(
        self,
        semantic_anchor_service: 'SemanticAnchorService',
        config: EcologicalRealismConfig | None = None,
    ):
        self._anchors = semantic_anchor_service
        self._config = config or EcologicalRealismConfig()
        
        # 环境变化追踪（用于适应滞后）
        self._env_history: list[dict[str, float]] = []
        
        # 互利共生网络缓存
        self._mutualism_network: dict[str, list[MutualismLink]] = {}
        self._mutualism_last_update: int = -1
        
        # 统计信息
        self._stats = {
            "allee_calculations": 0,
            "disease_calculations": 0,
            "spatial_predation_calculations": 0,
            "mutualism_links_found": 0,
        }
    
    # ========================================================================
    # 模块 1: Allee 效应
    # ========================================================================
    
    def calculate_allee_effect(
        self,
        species: 'Species',
        carrying_capacity: int,
    ) -> AlleeEffectResult:
        """计算 Allee 效应
        
        当种群规模低于阈值时，繁殖效率非线性下降。
        
        【生态学原理】
        - 配偶难觅：种群稀疏时个体难以找到交配对象
        - 集体防御崩溃：群居物种失去群体保护优势
        - 遗传多样性丧失：近交衰退加剧
        
        Args:
            species: 物种对象
            carrying_capacity: 环境承载力
            
        Returns:
            AlleeEffectResult
        """
        self._stats["allee_calculations"] += 1
        cfg = self._config
        
        population = species.morphology_stats.get("population", 0)
        
        # 计算种群与承载力的比例
        if carrying_capacity <= 0:
            ratio = 0.0
        else:
            ratio = population / carrying_capacity
        
        # MVP 临界点
        mvp_ratio = cfg.allee_critical_ratio
        is_below_mvp = ratio < mvp_ratio
        
        # S型曲线：当 ratio < mvp_ratio 时急剧下降
        # allee_factor = 1 / (1 + exp(-k * (ratio - threshold)))
        if ratio <= 0:
            allee_factor = 0.0
        elif ratio >= mvp_ratio * 2:
            allee_factor = 1.0
        else:
            x = (ratio - mvp_ratio) * cfg.allee_steepness
            allee_factor = 1.0 / (1.0 + math.exp(-x))
        
        # 群居性修正：群居物种受 Allee 效应影响更大
        sociality = self._anchors.compute_similarity(species, "social_behavior")
        sociality_modifier = 1.0 + (sociality - 0.5) * 0.4  # 群居物种惩罚更重
        
        # 繁殖效率修正
        reproduction_modifier = allee_factor
        if is_below_mvp:
            # MVP 以下时额外惩罚
            penalty = (1.0 - allee_factor) * cfg.allee_max_penalty * sociality_modifier
            reproduction_modifier = max(0.1, allee_factor - penalty)
        
        return AlleeEffectResult(
            species_code=species.lineage_code,
            population=population,
            carrying_capacity=carrying_capacity,
            ratio=ratio,
            allee_factor=allee_factor,
            reproduction_modifier=reproduction_modifier,
            is_below_mvp=is_below_mvp,
        )
    
    # ========================================================================
    # 模块 2: 密度依赖疾病
    # ========================================================================
    
    def calculate_disease_pressure(
        self,
        species: 'Species',
        density_ratio: float,
    ) -> DiseaseResult:
        """计算密度依赖疾病压力
        
        高密度种群自动面临更高的疾病/寄生虫压力。
        
        【生态学原理】
        - 密度效应：拥挤环境加速病原体传播
        - 社会性放大：群居物种传播风险更高
        - 免疫权衡：繁殖投入高的物种免疫力相对较弱
        
        Args:
            species: 物种对象
            density_ratio: 种群密度比例（当前/承载力）
            
        Returns:
            DiseaseResult
        """
        self._stats["disease_calculations"] += 1
        cfg = self._config
        
        if not cfg.enable_density_disease:
            return DiseaseResult(
                species_code=species.lineage_code,
                density_ratio=density_ratio,
                sociality_score=0.0,
                resistance_score=0.0,
                disease_pressure=0.0,
                mortality_modifier=0.0,
            )
        
        # 计算群居性和抗病性
        sociality_score = self._anchors.compute_similarity(species, "social_behavior")
        resistance_score = self._anchors.compute_similarity(species, "disease_resistant")
        
        # 基础疾病压力（只在高密度时触发）
        if density_ratio < cfg.disease_density_threshold:
            base_pressure = 0.0
        else:
            excess = density_ratio - cfg.disease_density_threshold
            base_pressure = min(1.0, excess * 2.0) * cfg.disease_base_mortality
        
        # 群居性放大
        social_amplification = 1.0 + sociality_score * cfg.disease_social_factor
        
        # 抗病性减免
        resistance_reduction = 1.0 - resistance_score * cfg.disease_resistance_factor
        
        # 最终疾病压力
        disease_pressure = base_pressure * social_amplification * resistance_reduction
        disease_pressure = max(0.0, min(0.5, disease_pressure))  # 上限 50%
        
        return DiseaseResult(
            species_code=species.lineage_code,
            density_ratio=density_ratio,
            sociality_score=sociality_score,
            resistance_score=resistance_score,
            disease_pressure=disease_pressure,
            mortality_modifier=disease_pressure,
        )
    
    # ========================================================================
    # 模块 3: 环境综合变数
    # ========================================================================
    
    def calculate_env_fluctuation_modifier(
        self,
        species: 'Species',
        turn_index: int,
        latitude: float = 0.5,  # 0=赤道, 1=极地
    ) -> float:
        """计算环境波动对物种的影响
        
        模拟地质时间尺度的长周期环境波动。
        
        【生态学原理】
        - 米兰科维奇周期：约10万年的冰期-间冰期循环
        - 火山活动周期：超级火山的长期影响与恢复
        - 海洋环流变迁：营养盐分布的长期变化
        
        Args:
            species: 物种对象
            turn_index: 当前回合
            latitude: 纬度 (0=赤道, 1=极地)
            
        Returns:
            承载力修正因子 (0.5-1.5)
        """
        cfg = self._config
        
        if not cfg.enable_env_fluctuation:
            return 1.0
        
        # 基础周期波动（模拟米兰科维奇周期）
        period = cfg.fluctuation_period_turns
        phase = (turn_index % period) / period * 2 * math.pi
        base_fluctuation = math.sin(phase) * cfg.fluctuation_amplitude
        
        # 高纬度地区波动更剧烈
        latitude_modifier = 1.0 + (latitude - 0.5) * cfg.latitude_sensitivity
        
        # 专化物种对波动更敏感
        specialist_score = self._anchors.compute_similarity(species, "specialist")
        generalist_score = self._anchors.compute_similarity(species, "generalist")
        specialization = specialist_score - generalist_score
        specialization_modifier = 1.0 + specialization * cfg.specialist_sensitivity * 0.5
        
        # 计算最终波动
        fluctuation = base_fluctuation * latitude_modifier * specialization_modifier
        
        # 返回修正因子（波动对专化物种影响更大）
        modifier = 1.0 + fluctuation
        return max(0.5, min(1.5, modifier))
    
    # ========================================================================
    # 模块 4: 空间显式捕食效率
    # ========================================================================
    
    def calculate_spatial_predation_efficiency(
        self,
        predator: 'Species',
        prey: 'Species',
        predator_tiles: set[int],
        prey_tiles: set[int],
    ) -> float:
        """计算空间重叠对捕食效率的影响
        
        捕食效率受捕食者与猎物的地理重叠程度影响。
        
        【生态学原理】
        - 空间隔离是重要的避难所机制
        - 捕食者必须"找到"猎物才能捕食
        - 迁徙和扩散改变捕食压力分布
        
        Args:
            predator: 捕食者物种
            prey: 猎物物种
            predator_tiles: 捕食者栖息地块
            prey_tiles: 猎物栖息地块
            
        Returns:
            捕食效率修正 (0-1)
        """
        self._stats["spatial_predation_calculations"] += 1
        cfg = self._config
        
        if not cfg.enable_spatial_predation:
            return 1.0
        
        if not predator_tiles or not prey_tiles:
            return 0.0
        
        # 计算地块重叠度
        overlap = len(predator_tiles & prey_tiles)
        total_prey_tiles = len(prey_tiles)
        
        if total_prey_tiles == 0:
            return 0.0
        
        overlap_ratio = overlap / total_prey_tiles
        
        # 最小重叠度阈值
        if overlap_ratio < cfg.min_overlap_for_predation:
            return 0.0
        
        # 计算捕食策略与防御策略的对抗
        # 伏击猎手在小范围内效率高
        ambush_score = self._anchors.compute_similarity(predator, "ambush_hunter")
        # 追逐猎手需要更大范围
        pursuit_score = self._anchors.compute_similarity(predator, "pursuit_hunter")
        # 群猎在重叠区域效率最高
        pack_score = self._anchors.compute_similarity(predator, "pack_hunter")
        
        # 猎物防御能力
        speed_defense = self._anchors.compute_similarity(prey, "speed_defense")
        armor_defense = self._anchors.compute_similarity(prey, "armor_defense")
        camouflage = self._anchors.compute_similarity(prey, "camouflage_defense")
        
        # 策略对抗修正
        # 伏击对伪装效果差，对速度防御效果好
        if ambush_score > 0.5:
            strategy_modifier = 1.0 - camouflage * 0.3 + speed_defense * 0.2
        # 追逐对速度防御效果差
        elif pursuit_score > 0.5:
            strategy_modifier = 1.0 - speed_defense * 0.4
        # 群猎对装甲防御有优势
        elif pack_score > 0.5:
            strategy_modifier = 1.0 + armor_defense * 0.2
        else:
            strategy_modifier = 1.0 - (speed_defense + armor_defense + camouflage) * 0.15
        
        # 最终效率 = 重叠度 × 策略修正
        efficiency = overlap_ratio ** cfg.overlap_efficiency_factor * strategy_modifier
        
        return max(0.0, min(1.0, efficiency))
    
    # ========================================================================
    # 模块 5: 能量同化效率
    # ========================================================================
    
    def calculate_assimilation_efficiency(
        self,
        species: 'Species',
    ) -> float:
        """计算物种的能量同化效率
        
        基于物种特征动态计算能量转化效率。
        
        【生态学原理】
        - 肉食性动物同化效率高（~30%），草食性较低（~15%）
        - 变温动物效率高于恒温动物（无需产热）
        - 滤食性、腐食性等特殊策略有独特效率
        
        Args:
            species: 物种对象
            
        Returns:
            同化效率 (0.05-0.35)
        """
        cfg = self._config
        
        if not cfg.enable_dynamic_assimilation:
            return 0.10  # 默认 10%
        
        # 计算各饮食类型的相似度
        herbivore = self._anchors.compute_similarity(species, "herbivore")
        carnivore = self._anchors.compute_similarity(species, "carnivore")
        omnivore = self._anchors.compute_similarity(species, "omnivore")
        detritivore = self._anchors.compute_similarity(species, "detritivore")
        filter_feeder = self._anchors.compute_similarity(species, "filter_feeder")
        
        # 加权平均基础效率
        total_weight = herbivore + carnivore + omnivore + detritivore + filter_feeder
        if total_weight < 0.01:
            base_efficiency = 0.10
        else:
            base_efficiency = (
                herbivore * cfg.herbivore_base_efficiency +
                carnivore * cfg.carnivore_base_efficiency +
                omnivore * (cfg.herbivore_base_efficiency + cfg.carnivore_base_efficiency) / 2 +
                detritivore * cfg.detritivore_base_efficiency +
                filter_feeder * cfg.filter_feeder_efficiency
            ) / total_weight
        
        # 代谢类型修正
        endotherm = self._anchors.compute_similarity(species, "endotherm")
        ectotherm = self._anchors.compute_similarity(species, "ectotherm")
        
        # 恒温动物需要能量维持体温，效率降低
        if endotherm > ectotherm:
            metabolic_modifier = cfg.endotherm_penalty
        else:
            metabolic_modifier = 1.0
        
        # 最终效率
        efficiency = base_efficiency * metabolic_modifier
        
        return max(0.05, min(0.35, efficiency))
    
    # ========================================================================
    # 模块 6: 垂直生态位分层
    # ========================================================================
    
    def calculate_vertical_niche_overlap(
        self,
        species_a: 'Species',
        species_b: 'Species',
    ) -> float:
        """计算两物种的垂直生态位重叠度
        
        【生态学原理】
        - 森林分层：林冠层、林下层、灌木层、地被层
        - 水体分层：表层、中层、底栖
        - 空间分离减少竞争排斥
        
        Args:
            species_a: 物种 A
            species_b: 物种 B
            
        Returns:
            垂直重叠度 (0-1)
        """
        cfg = self._config
        
        if not cfg.enable_vertical_niche:
            return 1.0  # 默认完全重叠
        
        # 获取垂直生态位分布
        layers = [
            "canopy", "understory", "ground", "subterranean",
            "aquatic_surface", "aquatic_pelagic", "aquatic_benthic"
        ]
        
        profile_a = {layer: self._anchors.compute_similarity(species_a, layer) for layer in layers}
        profile_b = {layer: self._anchors.compute_similarity(species_b, layer) for layer in layers}
        
        # 计算主要活动层
        dominant_a = max(profile_a.items(), key=lambda x: x[1])
        dominant_b = max(profile_b.items(), key=lambda x: x[1])
        
        # 如果在同一层，完全竞争
        if dominant_a[0] == dominant_b[0]:
            return cfg.same_layer_competition
        
        # 检查是否相邻层
        layer_adjacency = {
            ("canopy", "understory"): True,
            ("understory", "ground"): True,
            ("ground", "subterranean"): True,
            ("aquatic_surface", "aquatic_pelagic"): True,
            ("aquatic_pelagic", "aquatic_benthic"): True,
        }
        
        pair = (dominant_a[0], dominant_b[0])
        reverse_pair = (dominant_b[0], dominant_a[0])
        
        if pair in layer_adjacency or reverse_pair in layer_adjacency:
            return cfg.adjacent_layer_competition
        
        # 远层
        return cfg.distant_layer_competition
    
    def analyze_vertical_niche(
        self,
        species: 'Species',
    ) -> VerticalNicheResult:
        """分析物种的垂直生态位"""
        layers = [
            "canopy", "understory", "ground", "subterranean",
            "aquatic_surface", "aquatic_pelagic", "aquatic_benthic"
        ]
        
        profile = {layer: self._anchors.compute_similarity(species, layer) for layer in layers}
        dominant = max(profile.items(), key=lambda x: x[1])
        
        return VerticalNicheResult(
            species_code=species.lineage_code,
            dominant_layer=dominant[0],
            layer_profile=profile,
            competition_modifier=1.0,  # 默认，需要与其他物种比较
        )
    
    # ========================================================================
    # 模块 7: 适应滞后
    # ========================================================================
    
    def track_environment_change(
        self,
        turn_index: int,
        global_temp: float,
        global_humidity: float,
        resource_level: float,
    ):
        """追踪环境变化
        
        Args:
            turn_index: 当前回合
            global_temp: 全球平均温度
            global_humidity: 全球平均湿度
            resource_level: 资源水平
        """
        self._env_history.append({
            "turn": turn_index,
            "temp": global_temp,
            "humidity": global_humidity,
            "resources": resource_level,
        })
        
        # 保持追踪窗口大小
        window = self._config.env_change_tracking_window
        if len(self._env_history) > window:
            self._env_history = self._env_history[-window:]
    
    def calculate_adaptation_lag_penalty(
        self,
        species: 'Species',
    ) -> float:
        """计算适应滞后惩罚
        
        当环境变化速率超过物种适应能力时，产生额外死亡压力。
        
        【生态学原理】
        - 演化需要时间，快速变化导致适应不良
        - 可塑性高的物种能更快响应
        - 世代时间短的物种演化更快
        
        Args:
            species: 物种对象
            
        Returns:
            适应惩罚 (0-0.3)
        """
        cfg = self._config
        
        if not cfg.enable_adaptation_lag or len(self._env_history) < 2:
            return 0.0
        
        # 计算环境变化速率
        history = self._env_history
        if len(history) < 2:
            return 0.0
        
        # 温度变化率
        temp_change = abs(history[-1]["temp"] - history[0]["temp"])
        humidity_change = abs(history[-1]["humidity"] - history[0]["humidity"])
        resource_change = abs(history[-1]["resources"] - history[0]["resources"])
        
        # 综合变化率
        total_change = temp_change * 0.5 + humidity_change * 0.3 + resource_change * 0.2
        
        # 物种适应能力
        # 高可塑性 = 适应快
        plasticity = self._anchors.compute_similarity(species, "high_plasticity")
        
        # 世代时间短 = 演化快
        generation_time = species.morphology_stats.get("generation_time_days", 365)
        # 归一化：1天=1.0, 365天=0.0
        generation_factor = max(0.0, 1.0 - math.log(generation_time + 1) / 6.0)
        
        # 适应能力
        adaptation_capacity = plasticity * cfg.plasticity_protection + generation_factor * cfg.generation_time_factor
        adaptation_capacity = min(1.0, adaptation_capacity)
        
        # 如果变化速率 > 适应能力，产生惩罚
        if total_change > adaptation_capacity:
            penalty = (total_change - adaptation_capacity) * cfg.max_adaptation_penalty
            return min(cfg.max_adaptation_penalty, penalty)
        
        return 0.0
    
    # ========================================================================
    # 模块 8: 互利共生网络
    # ========================================================================
    
    def discover_mutualism_links(
        self,
        species_list: Sequence['Species'],
        turn_index: int,
    ) -> list[MutualismLink]:
        """发现物种间的互利共生关系
        
        【生态学原理】
        - 传粉者-开花植物：相互依赖的繁殖关系
        - 种子散布者-果实植物：扩散与食物交换
        - 菌根共生：营养物质交换
        
        Args:
            species_list: 所有物种
            turn_index: 当前回合
            
        Returns:
            发现的共生链接列表
        """
        cfg = self._config
        
        if not cfg.enable_mutualism:
            return []
        
        # 每5回合更新一次
        if turn_index - self._mutualism_last_update < 5:
            all_links = []
            for links in self._mutualism_network.values():
                all_links.extend(links)
            return all_links
        
        alive_species = [sp for sp in species_list if sp.status == "alive"]
        new_links = []
        
        # 共生类型定义
        mutualism_pairs = [
            ("pollinator", "flowering_plant", "pollination"),
            ("seed_disperser", "fruit_plant", "seed_dispersal"),
            ("mycorrhizal", "flowering_plant", "mycorrhizal"),
            ("nitrogen_fixer", "flowering_plant", "nitrogen_fixation"),
        ]
        
        for sp_a in alive_species:
            for sp_b in alive_species:
                if sp_a.lineage_code >= sp_b.lineage_code:
                    continue  # 避免重复检测
                
                for anchor_a, anchor_b, rel_type in mutualism_pairs:
                    score_a = self._anchors.compute_similarity(sp_a, anchor_a)
                    score_b = self._anchors.compute_similarity(sp_b, anchor_b)
                    
                    # 也检查反向
                    score_a_rev = self._anchors.compute_similarity(sp_a, anchor_b)
                    score_b_rev = self._anchors.compute_similarity(sp_b, anchor_a)
                    
                    # 正向匹配
                    if score_a > cfg.mutualism_threshold and score_b > cfg.mutualism_threshold:
                        strength = (score_a + score_b) / 2
                        new_links.append(MutualismLink(
                            species_a=sp_a.lineage_code,
                            species_b=sp_b.lineage_code,
                            relationship_type=rel_type,
                            strength=strength,
                            benefit_a=cfg.mutualism_benefit * score_b,
                            benefit_b=cfg.mutualism_benefit * score_a,
                        ))
                    
                    # 反向匹配
                    elif score_a_rev > cfg.mutualism_threshold and score_b_rev > cfg.mutualism_threshold:
                        strength = (score_a_rev + score_b_rev) / 2
                        new_links.append(MutualismLink(
                            species_a=sp_a.lineage_code,
                            species_b=sp_b.lineage_code,
                            relationship_type=rel_type,
                            strength=strength,
                            benefit_a=cfg.mutualism_benefit * score_b_rev,
                            benefit_b=cfg.mutualism_benefit * score_a_rev,
                        ))
        
        # 更新缓存
        self._mutualism_network.clear()
        for link in new_links:
            if link.species_a not in self._mutualism_network:
                self._mutualism_network[link.species_a] = []
            if link.species_b not in self._mutualism_network:
                self._mutualism_network[link.species_b] = []
            self._mutualism_network[link.species_a].append(link)
            self._mutualism_network[link.species_b].append(link)
        
        self._mutualism_last_update = turn_index
        self._stats["mutualism_links_found"] = len(new_links)
        
        logger.info(f"[互利共生] 发现 {len(new_links)} 个共生关系")
        return new_links
    
    def get_mutualism_benefit(
        self,
        species: 'Species',
        all_species: Sequence['Species'],
    ) -> float:
        """获取物种从共生关系中获得的收益
        
        Args:
            species: 目标物种
            all_species: 所有物种
            
        Returns:
            收益修正 (-0.15 到 +0.1)
        """
        cfg = self._config
        
        if not cfg.enable_mutualism:
            return 0.0
        
        code = species.lineage_code
        links = self._mutualism_network.get(code, [])
        
        if not links:
            return 0.0
        
        alive_codes = {sp.lineage_code for sp in all_species if sp.status == "alive"}
        
        total_benefit = 0.0
        total_penalty = 0.0
        
        for link in links:
            partner = link.species_b if link.species_a == code else link.species_a
            benefit = link.benefit_a if link.species_a == code else link.benefit_b
            
            if partner in alive_codes:
                # 伙伴存活，获得收益
                total_benefit += benefit
            else:
                # 伙伴灭绝，受到惩罚
                total_penalty += cfg.mutualism_penalty * link.strength
        
        net_benefit = total_benefit - total_penalty
        return max(-0.15, min(0.1, net_benefit))
    
    # ========================================================================
    # 统计与配置
    # ========================================================================
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            "env_history_length": len(self._env_history),
            "mutualism_species_count": len(self._mutualism_network),
        }
    
    def update_config(self, config: EcologicalRealismConfig):
        """更新配置"""
        self._config = config


# 全局单例
_ecological_realism_service: EcologicalRealismService | None = None


def get_ecological_realism_service(
    semantic_anchor_service: 'SemanticAnchorService',
    config: EcologicalRealismConfig | None = None,
) -> EcologicalRealismService:
    """获取生态拟真服务实例"""
    global _ecological_realism_service
    
    if _ecological_realism_service is None:
        _ecological_realism_service = EcologicalRealismService(
            semantic_anchor_service, config
        )
    
    return _ecological_realism_service

