"""语义锚点服务 (Semantic Anchor Service)

基于 Embedding 的语义匹配系统，替代硬编码的类型判断。

【设计原则】
所有生态学判断通过 embedding 语义匹配实现，而非关键词枚举：
- ❌ 避免: if diet_type == "carnivore"
- ✅ 采用: 计算与"肉食性捕食者"的语义相似度

【核心功能】
1. 预定义语义锚点的批量编码和缓存
2. 高效的 batch 相似度计算接口
3. 锚点 embedding 在服务启动时预计算

【使用方式】
```python
anchor_service = SemanticAnchorService(embedding_service)
anchor_service.initialize()

# 计算物种与各锚点的相似度
sociality_score = anchor_service.compute_similarity(species, "social_behavior")
resistance_score = anchor_service.compute_similarity(species, "disease_resistant")
```
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ..system.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class SemanticAnchor:
    """语义锚点定义"""
    name: str                    # 锚点名称（用于代码引用）
    description: str             # 锚点描述文本
    category: str = ""           # 类别（用于分组）
    vector: np.ndarray | None = None  # 缓存的向量


# 预定义语义锚点
SEMANTIC_ANCHORS = {
    # ========== 社会性与疾病 ==========
    "social_behavior": SemanticAnchor(
        name="social_behavior",
        description="群居生活、社会性动物、集群行为、群体活动、蜂群、兽群、鱼群",
        category="sociality"
    ),
    "solitary_behavior": SemanticAnchor(
        name="solitary_behavior",
        description="独居、独行、领地性强、单独活动、不合群",
        category="sociality"
    ),
    "disease_resistant": SemanticAnchor(
        name="disease_resistant",
        description="免疫力强、抗病性、耐受病原体、健壮体质、抵抗力强",
        category="disease"
    ),
    "disease_susceptible": SemanticAnchor(
        name="disease_susceptible",
        description="免疫力弱、易感染、体质虚弱、抵抗力差",
        category="disease"
    ),
    
    # ========== 环境适应性 ==========
    "generalist": SemanticAnchor(
        name="generalist",
        description="广适性、环境耐受、机会主义、适应力强、杂食、分布广泛",
        category="adaptability"
    ),
    "specialist": SemanticAnchor(
        name="specialist",
        description="专化、狭适性、特化环境、敏感、对特定条件依赖、专一性强",
        category="adaptability"
    ),
    
    # ========== 捕食策略 ==========
    "ambush_hunter": SemanticAnchor(
        name="ambush_hunter",
        description="伏击、埋伏、隐蔽等待、突袭、潜伏捕猎",
        category="hunting"
    ),
    "pursuit_hunter": SemanticAnchor(
        name="pursuit_hunter",
        description="追逐捕猎、耐力追踪、持久奔跑、长距离追击",
        category="hunting"
    ),
    "pack_hunter": SemanticAnchor(
        name="pack_hunter",
        description="群体协作围猎、团队捕猎、配合狩猎、分工合作",
        category="hunting"
    ),
    
    # ========== 防御策略 ==========
    "speed_defense": SemanticAnchor(
        name="speed_defense",
        description="快速逃跑、敏捷、高速奔跑、迅速躲避",
        category="defense"
    ),
    "armor_defense": SemanticAnchor(
        name="armor_defense",
        description="硬壳装甲、厚皮防护、坚硬外骨骼、保护性结构",
        category="defense"
    ),
    "camouflage_defense": SemanticAnchor(
        name="camouflage_defense",
        description="保护色伪装、拟态、隐蔽、融入环境",
        category="defense"
    ),
    "group_defense": SemanticAnchor(
        name="group_defense",
        description="群体警戒、集体防御、互相保护、警报系统",
        category="defense"
    ),
    
    # ========== 饮食类型 ==========
    "herbivore": SemanticAnchor(
        name="herbivore",
        description="草食、植食、以植物为食、纤维素消化、素食",
        category="diet"
    ),
    "carnivore": SemanticAnchor(
        name="carnivore",
        description="肉食、捕食者、以动物为食、高蛋白、猎杀",
        category="diet"
    ),
    "omnivore": SemanticAnchor(
        name="omnivore",
        description="杂食、什么都吃、机会主义取食、食性广泛",
        category="diet"
    ),
    "detritivore": SemanticAnchor(
        name="detritivore",
        description="腐食、分解者、以有机碎屑为食、清道夫",
        category="diet"
    ),
    "filter_feeder": SemanticAnchor(
        name="filter_feeder",
        description="滤食、过滤进食、悬浮物取食、浮游生物",
        category="diet"
    ),
    
    # ========== 代谢类型 ==========
    "endotherm": SemanticAnchor(
        name="endotherm",
        description="恒温、温血、高代谢、维持体温、内温动物",
        category="metabolism"
    ),
    "ectotherm": SemanticAnchor(
        name="ectotherm",
        description="变温、冷血、低代谢、体温随环境、外温动物",
        category="metabolism"
    ),
    
    # ========== 垂直生态位 ==========
    "canopy": SemanticAnchor(
        name="canopy",
        description="树冠层活动、林冠、高处栖息、树顶、空中活动",
        category="vertical_niche"
    ),
    "understory": SemanticAnchor(
        name="understory",
        description="林下层、灌木丛、中层活动、次冠层",
        category="vertical_niche"
    ),
    "ground": SemanticAnchor(
        name="ground",
        description="地面活动、地栖、穴居、土壤、地表生活",
        category="vertical_niche"
    ),
    "subterranean": SemanticAnchor(
        name="subterranean",
        description="地下、穴居、土壤深层、洞穴生活",
        category="vertical_niche"
    ),
    "aquatic_surface": SemanticAnchor(
        name="aquatic_surface",
        description="水面漂浮、表层水域、浅水区、水面生活",
        category="vertical_niche"
    ),
    "aquatic_pelagic": SemanticAnchor(
        name="aquatic_pelagic",
        description="开阔水域、中层水域、远洋、游泳",
        category="vertical_niche"
    ),
    "aquatic_benthic": SemanticAnchor(
        name="aquatic_benthic",
        description="水底、底栖、海床、湖底、底层生活",
        category="vertical_niche"
    ),
    
    # ========== 可塑性 ==========
    "high_plasticity": SemanticAnchor(
        name="high_plasticity",
        description="适应力强、表型可变、行为灵活、学习能力强、可塑性高",
        category="plasticity"
    ),
    "low_plasticity": SemanticAnchor(
        name="low_plasticity",
        description="特化、固定形态、行为刻板、专一性强、可塑性低",
        category="plasticity"
    ),
    
    # ========== 共生角色 ==========
    "pollinator": SemanticAnchor(
        name="pollinator",
        description="传粉者、访花、采蜜、花粉传播、授粉",
        category="symbiosis"
    ),
    "flowering_plant": SemanticAnchor(
        name="flowering_plant",
        description="开花植物、花蜜、花粉、被子植物、招引传粉者",
        category="symbiosis"
    ),
    "seed_disperser": SemanticAnchor(
        name="seed_disperser",
        description="种子传播者、散布种子、果实消费、种子散播",
        category="symbiosis"
    ),
    "fruit_plant": SemanticAnchor(
        name="fruit_plant",
        description="果实植物、浆果、坚果、肉质果、吸引动物",
        category="symbiosis"
    ),
    "nitrogen_fixer": SemanticAnchor(
        name="nitrogen_fixer",
        description="固氮菌、根瘤菌、氮循环、共生固氮",
        category="symbiosis"
    ),
    "mycorrhizal": SemanticAnchor(
        name="mycorrhizal",
        description="菌根共生、真菌共生、营养交换、根系共生",
        category="symbiosis"
    ),
    
    # ========== 繁殖策略 ==========
    "r_strategist": SemanticAnchor(
        name="r_strategist",
        description="r策略、高繁殖率、多子代、快速成熟、短寿命",
        category="reproduction"
    ),
    "k_strategist": SemanticAnchor(
        name="k_strategist",
        description="K策略、低繁殖率、少子代、慢成熟、长寿命、亲代投资",
        category="reproduction"
    ),
}


class SemanticAnchorService:
    """语义锚点服务
    
    提供基于 Embedding 的语义匹配能力，替代硬编码的类型判断。
    
    【核心功能】
    1. 预计算所有语义锚点的向量
    2. 计算物种与锚点的相似度
    3. 批量计算物种的生态学属性
    """
    
    def __init__(self, embedding_service: 'EmbeddingService'):
        self._embedding = embedding_service
        self._anchors: dict[str, SemanticAnchor] = {}
        self._initialized = False
        self._species_cache: dict[str, np.ndarray] = {}  # lineage_code -> vector
        
        # 统计信息
        self._stats = {
            "anchor_count": 0,
            "similarity_calls": 0,
            "cache_hits": 0,
        }
    
    def initialize(self) -> int:
        """初始化语义锚点（预计算所有锚点向量）
        
        Returns:
            初始化的锚点数量
        """
        if self._initialized:
            return len(self._anchors)
        
        logger.info("[语义锚点] 开始初始化...")
        
        # 复制预定义锚点
        self._anchors = {k: SemanticAnchor(
            name=v.name,
            description=v.description,
            category=v.category,
        ) for k, v in SEMANTIC_ANCHORS.items()}
        
        # 批量计算向量
        descriptions = [anchor.description for anchor in self._anchors.values()]
        vectors = self._embedding.embed(descriptions)
        
        # 存储向量
        for i, (name, anchor) in enumerate(self._anchors.items()):
            anchor.vector = np.array(vectors[i], dtype=np.float32)
        
        self._initialized = True
        self._stats["anchor_count"] = len(self._anchors)
        
        logger.info(f"[语义锚点] 初始化完成，共 {len(self._anchors)} 个锚点")
        return len(self._anchors)
    
    def get_anchor(self, name: str) -> SemanticAnchor | None:
        """获取指定锚点"""
        return self._anchors.get(name)
    
    def list_anchors(self, category: str | None = None) -> list[str]:
        """列出锚点名称"""
        if category:
            return [name for name, anchor in self._anchors.items() 
                    if anchor.category == category]
        return list(self._anchors.keys())
    
    def _get_species_vector(self, species: 'Species') -> np.ndarray:
        """获取物种的向量（带缓存）"""
        if species.lineage_code in self._species_cache:
            self._stats["cache_hits"] += 1
            return self._species_cache[species.lineage_code]
        
        # 构建物种描述文本
        text = self._build_species_text(species)
        vector = np.array(self._embedding.embed_single(text), dtype=np.float32)
        
        # 缓存
        self._species_cache[species.lineage_code] = vector
        return vector
    
    def _build_species_text(self, species: 'Species') -> str:
        """构建物种描述文本用于语义匹配"""
        parts = [
            species.common_name,
            species.description,
        ]
        
        # 添加抽象特征
        traits = species.abstract_traits or {}
        trait_parts = []
        for trait_name, value in traits.items():
            if value > 7:
                trait_parts.append(f"高{trait_name}")
            elif value < 3:
                trait_parts.append(f"低{trait_name}")
        
        if trait_parts:
            parts.append(" ".join(trait_parts))
        
        return " ".join(parts)
    
    def compute_similarity(
        self,
        species: 'Species',
        anchor_name: str,
    ) -> float:
        """计算物种与指定锚点的相似度
        
        Args:
            species: 物种对象
            anchor_name: 锚点名称
            
        Returns:
            相似度 (0-1)
        """
        self._stats["similarity_calls"] += 1
        
        anchor = self._anchors.get(anchor_name)
        if anchor is None or anchor.vector is None:
            logger.warning(f"[语义锚点] 未找到锚点: {anchor_name}")
            return 0.0
        
        species_vec = self._get_species_vector(species)
        
        # 计算余弦相似度
        similarity = self._cosine_similarity(species_vec, anchor.vector)
        
        # 映射到 0-1 范围（余弦相似度原本是 -1 到 1）
        return (similarity + 1.0) / 2.0
    
    def compute_similarity_batch(
        self,
        species_list: Sequence['Species'],
        anchor_name: str,
    ) -> dict[str, float]:
        """批量计算物种与锚点的相似度
        
        Args:
            species_list: 物种列表
            anchor_name: 锚点名称
            
        Returns:
            {lineage_code: similarity}
        """
        anchor = self._anchors.get(anchor_name)
        if anchor is None or anchor.vector is None:
            return {sp.lineage_code: 0.0 for sp in species_list}
        
        results = {}
        for species in species_list:
            results[species.lineage_code] = self.compute_similarity(species, anchor_name)
        
        return results
    
    def compute_category_profile(
        self,
        species: 'Species',
        category: str,
    ) -> dict[str, float]:
        """计算物种在某个类别下所有锚点的相似度分布
        
        Args:
            species: 物种对象
            category: 锚点类别
            
        Returns:
            {anchor_name: similarity}
        """
        anchors_in_category = self.list_anchors(category)
        return {
            name: self.compute_similarity(species, name)
            for name in anchors_in_category
        }
    
    def get_dominant_anchor(
        self,
        species: 'Species',
        category: str,
    ) -> tuple[str, float]:
        """获取物种在某类别下最匹配的锚点
        
        Args:
            species: 物种对象
            category: 锚点类别
            
        Returns:
            (锚点名称, 相似度)
        """
        profile = self.compute_category_profile(species, category)
        if not profile:
            return ("unknown", 0.0)
        
        best = max(profile.items(), key=lambda x: x[1])
        return best
    
    def compute_multi_anchor_score(
        self,
        species: 'Species',
        anchor_weights: dict[str, float],
    ) -> float:
        """加权计算多个锚点的综合得分
        
        Args:
            species: 物种对象
            anchor_weights: {anchor_name: weight}
            
        Returns:
            加权综合得分
        """
        total_weight = sum(anchor_weights.values())
        if total_weight <= 0:
            return 0.0
        
        weighted_sum = 0.0
        for anchor_name, weight in anchor_weights.items():
            similarity = self.compute_similarity(species, anchor_name)
            weighted_sum += similarity * weight
        
        return weighted_sum / total_weight
    
    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """计算余弦相似度"""
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        
        if norm_a < 1e-8 or norm_b < 1e-8:
            return 0.0
        
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
    
    def clear_species_cache(self):
        """清除物种向量缓存"""
        self._species_cache.clear()
    
    def remove_species_from_cache(self, lineage_code: str):
        """从缓存中移除物种（物种描述更新时调用）"""
        self._species_cache.pop(lineage_code, None)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            "species_cache_size": len(self._species_cache),
            "initialized": self._initialized,
        }


# 全局单例（通过依赖注入使用）
_semantic_anchor_service: SemanticAnchorService | None = None


def get_semantic_anchor_service(
    embedding_service: 'EmbeddingService'
) -> SemanticAnchorService:
    """获取语义锚点服务实例"""
    global _semantic_anchor_service
    
    if _semantic_anchor_service is None:
        _semantic_anchor_service = SemanticAnchorService(embedding_service)
        _semantic_anchor_service.initialize()
    
    return _semantic_anchor_service






