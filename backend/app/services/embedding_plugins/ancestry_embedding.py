"""血统压缩向量插件

使用 embedding 压缩物种的历史和血统信息，支持：
- 血统语义压缩
- 遗传惯性预测
- 分化信号评估

数据契约：
- 必需字段: all_species
- 可选字段: branching_events
- 降级策略: 基于 lineage_code 推断祖先

【张量集成】
- 使用 SpeciationMonitor 的分化信号
- 优先采用张量检测的隔离和分歧数据
- 集成地理隔离区域数和生态分化得分
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING, List, Optional

from .base import EmbeddingPlugin, PluginConfig
from .registry import register_plugin

if TYPE_CHECKING:
    from ...models.species import Species
    from ...simulation.context import SimulationContext

import logging
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AncestryVector:
    """血统向量"""
    lineage_code: str
    vector: np.ndarray
    generation: int
    ancestor_codes: List[str]
    trait_history: dict[str, List[float]] = field(default_factory=dict)


@register_plugin("ancestry")
class AncestryEmbeddingPlugin(EmbeddingPlugin):
    """血统压缩向量插件
    
    MVP 功能:
    1. 计算血统向量
    2. 遗传惯性评估
    3. 分化信号评估
    4. 血统相似度计算
    
    张量集成:
    - 优先使用 SpeciationMonitor 的分化信号
    - 集成隔离区域数和生态分化得分
    """
    
    required_context_fields = {"all_species"}
    # 启用张量数据
    use_tensor_data = True
    
    @property
    def name(self) -> str:
        return "ancestry"
    
    def _do_initialize(self) -> None:
        """初始化"""
        self._ancestry_cache: dict[str, AncestryVector] = {}
        self._trait_history: dict[str, dict[str, List[float]]] = {}
        self._tensor_speciation_signals: dict[str, dict] = {}  # 缓存张量分化信号
    
    def build_index(self, ctx: 'SimulationContext') -> int:
        """构建血统向量索引"""
        store = self._get_vector_store()
        
        species_list = ctx.all_species or []
        if not species_list:
            return 0
        
        texts = []
        ids = []
        metadata_list = []
        candidate_ancestries = []
        
        for sp in species_list:
            ancestry = self._compute_ancestry_vector(sp, ctx)
            if ancestry:
                # 使用向量作为索引
                texts.append(self._ancestry_to_text(ancestry, sp))
                ids.append(sp.lineage_code)
                metadata_list.append({
                    "generation": ancestry.generation,
                    "ancestor_count": len(ancestry.ancestor_codes),
                })
                candidate_ancestries.append(ancestry)
        
        if not texts:
            return 0
        
        vectors = self._embed_texts(texts)
        if not vectors:
            return 0
        
        # 同时更新 ancestry 向量
        for i, code in enumerate(ids):
            ancestry = candidate_ancestries[i]
            ancestry.vector = np.array(vectors[i])
            self._ancestry_cache[code] = ancestry
        
        return store.add_batch(ids, vectors, metadata_list)
    
    def _ancestry_to_text(self, ancestry: 'AncestryVector', species: 'Species') -> str:
        """将血统信息转换为文本"""
        parts = [
            f"物种 {species.lineage_code}",
            f"代数: {ancestry.generation}",
        ]
        
        if ancestry.ancestor_codes:
            parts.append(f"祖先链: {' -> '.join(ancestry.ancestor_codes[-3:])}")
        
        # 添加物种描述
        desc = getattr(species, 'description', '')
        if desc:
            parts.append(desc[:200])
        
        return "; ".join(parts)
    
    def _compute_ancestry_vector(
        self, 
        species: 'Species', 
        ctx: 'SimulationContext'
    ) -> Optional[AncestryVector]:
        """计算物种的血统向量"""
        # 获取祖先链
        ancestor_codes = self._get_ancestor_chain(species)
        generation = len(ancestor_codes) + 1
        
        # 更新特征历史
        self._update_trait_history(species)
        
        return AncestryVector(
            lineage_code=species.lineage_code,
            vector=np.array([]),  # 稍后填充
            generation=generation,
            ancestor_codes=ancestor_codes,
            trait_history=self._trait_history.get(species.lineage_code, {}),
        )
    
    def _get_ancestor_chain(self, species: 'Species') -> List[str]:
        """从 lineage_code 推断祖先链"""
        code = species.lineage_code
        parts = code.split("_")
        
        ancestors = []
        for i in range(len(parts) - 1):
            ancestor_code = "_".join(parts[:i+1])
            ancestors.append(ancestor_code)
        
        return ancestors
    
    def _update_trait_history(self, species: 'Species') -> None:
        """更新特征历史"""
        code = species.lineage_code
        traits = getattr(species, 'abstract_traits', None) or {}
        
        if code not in self._trait_history:
            self._trait_history[code] = {}
        
        for trait, value in traits.items():
            if trait not in self._trait_history[code]:
                self._trait_history[code][trait] = []
            
            self._trait_history[code][trait].append(value)
            
            # 限制历史长度
            if len(self._trait_history[code][trait]) > 20:
                self._trait_history[code][trait] = self._trait_history[code][trait][-20:]
    
    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """搜索血统相似的物种"""
        store = self._get_vector_store(create=False)
        if not store or store.size == 0:
            return []
        
        query_vec = self.embeddings.embed_single(query)
        results = store.search(query_vec, top_k)
        self._stats.searches += 1
        
        return [
            {"lineage_code": r.id, "similarity": round(r.score, 3), **r.metadata}
            for r in results
        ]
    
    def predict_genetic_inertia(
        self, 
        species: 'Species', 
        target_trait: str
    ) -> dict[str, Any]:
        """预测遗传惯性
        
        遗传惯性 = 特征历史的稳定性
        高惯性 = 难以改变
        """
        ancestry = self._ancestry_cache.get(species.lineage_code)
        if not ancestry:
            return {"inertia": 0.5, "confidence": 0}
        
        trait_history = ancestry.trait_history.get(target_trait, [])
        
        if len(trait_history) < 2:
            return {"inertia": 0.5, "confidence": 0.1}
        
        # 计算变化幅度
        history_array = np.array(trait_history)
        variance = float(np.var(history_array))
        mean_value = float(np.mean(history_array))
        
        # 低变化 = 高惯性
        inertia = 1 / (1 + variance)
        
        # 趋势分析
        if len(trait_history) >= 3:
            trend = float(np.polyfit(range(len(trait_history)), trait_history, 1)[0])
        else:
            trend = 0
        
        return {
            "inertia": round(inertia, 3),
            "mean_value": round(mean_value, 2),
            "variance": round(variance, 3),
            "trend": round(trend, 3),
            "trend_direction": "increasing" if trend > 0.1 else ("decreasing" if trend < -0.1 else "stable"),
            "confidence": min(1.0, len(trait_history) / 10),
        }
    
    def should_speciate(
        self, 
        species: 'Species', 
        threshold: float = 0.6
    ) -> dict[str, Any]:
        """判断是否应该发生物种分化
        
        【张量集成】优先使用张量分化信号
        """
        lineage_code = species.lineage_code
        
        # 【张量优先】检查张量分化信号
        if self.has_tensor_data and self.has_tensor_speciation_signal(lineage_code):
            # 获取详细的分化信息
            isolation_regions = self.tensor_bridge.get_species_isolation_regions(lineage_code)
            divergence_score = self.tensor_bridge.get_species_divergence_score(lineage_code)
            
            # 地理隔离（2+区域）或生态分化（>阈值）都触发分化
            should_speciate = isolation_regions >= 2 or divergence_score >= threshold
            
            reason = []
            if isolation_regions >= 2:
                reason.append(f"地理隔离({isolation_regions}区域)")
            if divergence_score >= threshold:
                reason.append(f"生态分化({divergence_score:.2f})")
            
            return {
                "should_speciate": should_speciate,
                "tensor_triggered": True,
                "isolation_regions": isolation_regions,
                "divergence_score": round(divergence_score, 3),
                "threshold": threshold,
                "reason": ", ".join(reason) if reason else "张量信号检测",
            }
        
        # 回退：使用血统向量距离
        ancestry = self._ancestry_cache.get(lineage_code)
        if not ancestry or not ancestry.ancestor_codes:
            return {"should_speciate": False, "reason": "无祖先数据"}
        
        parent_code = ancestry.ancestor_codes[-1] if ancestry.ancestor_codes else None
        if not parent_code or parent_code not in self._ancestry_cache:
            return {"should_speciate": False, "reason": "无法获取父代向量"}
        
        parent_ancestry = self._ancestry_cache[parent_code]
        
        # 计算向量距离
        if len(ancestry.vector) == 0 or len(parent_ancestry.vector) == 0:
            return {"should_speciate": False, "reason": "向量未初始化"}
        
        distance = float(np.linalg.norm(ancestry.vector - parent_ancestry.vector))
        should_speciate = distance > threshold
        
        return {
            "should_speciate": should_speciate,
            "tensor_triggered": False,
            "distance_from_parent": round(distance, 3),
            "threshold": threshold,
            "generation": ancestry.generation,
            "reason": "血统向量与祖先差异过大" if should_speciate else "仍在祖先变异范围内",
        }
    
    def calculate_divergence_score(
        self, 
        species_a: 'Species', 
        species_b: 'Species'
    ) -> dict[str, Any]:
        """计算两个物种的分化程度"""
        ancestry_a = self._ancestry_cache.get(species_a.lineage_code)
        ancestry_b = self._ancestry_cache.get(species_b.lineage_code)
        
        if not ancestry_a or not ancestry_b:
            return {"divergence": 0, "confidence": 0}
        
        # 向量距离
        if len(ancestry_a.vector) > 0 and len(ancestry_b.vector) > 0:
            vector_distance = float(np.linalg.norm(ancestry_a.vector - ancestry_b.vector))
        else:
            vector_distance = 1.0
        
        # 共同祖先
        common_ancestors = set(ancestry_a.ancestor_codes) & set(ancestry_b.ancestor_codes)
        
        # 代数差异
        generation_diff = abs(ancestry_a.generation - ancestry_b.generation)
        
        # 综合分化分数
        ancestor_factor = 1 - len(common_ancestors) / max(len(ancestry_a.ancestor_codes), 1) if ancestry_a.ancestor_codes else 1
        divergence = vector_distance * 0.5 + ancestor_factor * 0.3 + min(generation_diff / 10, 0.2)
        
        return {
            "divergence": round(divergence, 3),
            "vector_distance": round(vector_distance, 3),
            "common_ancestor_count": len(common_ancestors),
            "generation_diff": generation_diff,
            "confidence": 0.8 if ancestry_a.generation > 2 and ancestry_b.generation > 2 else 0.4,
        }
    
    def get_ancestry_summary(self) -> dict[str, Any]:
        """获取血统摘要"""
        if not self._ancestry_cache:
            return {}
        
        generations = [a.generation for a in self._ancestry_cache.values()]
        
        return {
            "total_species": len(self._ancestry_cache),
            "avg_generation": round(sum(generations) / len(generations), 2) if generations else 0,
            "max_generation": max(generations) if generations else 0,
            "species_with_history": sum(1 for a in self._ancestry_cache.values() if a.trait_history),
        }

