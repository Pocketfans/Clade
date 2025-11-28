"""自动分类学服务 - 基于 Embedding 聚类生成生物分类树

【核心功能】
1. 对物种 embedding 进行多层次聚类
2. 自动生成门-纲-目-科-属等分类层级
3. 为类群生成名称和定义特征
4. 维护分类树结构，支持增量更新

【v2.0 优化】
- 使用批量 embedding 接口
- 支持大规模物种（10000+）
- 利用 EmbeddingService 的向量存储

【算法】
- 第一层（门级）：K-means 聚类，k=3~5
- 第二层（纲级）：层次聚类，自动确定类数
- 第三层（科/属级）：HDBSCAN 密度聚类
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import numpy as np

if TYPE_CHECKING:
    from ...models.species import Species
    from ...models.taxonomy import Clade, TaxonomyTree
    from ..system.embedding import EmbeddingService
    from ...ai.model_router import ModelRouter

logger = logging.getLogger(__name__)


@dataclass
class CladeInfo:
    """类群信息（内存数据结构）"""
    id: int
    name: str
    latin_name: str
    rank: str
    parent_id: int | None
    depth: int
    centroid: np.ndarray
    member_codes: list[str]
    defining_traits: dict[str, Any] = field(default_factory=dict)
    cohesion: float = 0.0
    children: list['CladeInfo'] = field(default_factory=list)


@dataclass 
class TaxonomyResult:
    """分类学分析结果"""
    tree: dict[str, Any]  # 树形结构
    clades: list[CladeInfo]  # 所有类群
    species_assignments: dict[str, list[str]]  # species_code -> [clade_names]
    stats: dict[str, Any]  # 统计信息


class TaxonomyService:
    """自动分类学服务
    
    使用 embedding 聚类自动生成生物分类树
    """
    
    # 分类等级定义
    RANKS = ["domain", "phylum", "class", "order", "family", "genus"]
    
    # 默认聚类参数
    DEFAULT_PARAMS = {
        "domain_clusters": 3,      # 域级类群数
        "phylum_clusters": 5,      # 门级类群数（每个域内）
        "min_cluster_size": 2,     # 最小类群大小
        "cohesion_threshold": 0.3, # 内聚度阈值
    }
    
    # 类群名称前缀（用于生成名称）
    RANK_PREFIXES = {
        "domain": "域",
        "phylum": "门",
        "class": "纲", 
        "order": "目",
        "family": "科",
        "genus": "属",
    }
    
    # 参考类群模板（用于命名）
    REFERENCE_TEMPLATES = {
        "vertebrate_like": {
            "keywords": ["脊柱", "脊椎", "骨骼", "内骨骼"],
            "name": "类脊椎动物",
            "latin": "Pseudovertebrata"
        },
        "arthropod_like": {
            "keywords": ["外骨骼", "节肢", "甲壳", "复眼"],
            "name": "类节肢动物",
            "latin": "Pseudoarthropoda"
        },
        "mollusk_like": {
            "keywords": ["软体", "贝壳", "腹足", "头足"],
            "name": "类软体动物",
            "latin": "Pseudomollusca"
        },
        "microbe_like": {
            "keywords": ["单细胞", "微生物", "细菌", "原生"],
            "name": "类原生生物",
            "latin": "Pseudoprotista"
        },
        "plant_like": {
            "keywords": ["光合", "叶绿体", "植物", "藻"],
            "name": "类植物",
            "latin": "Pseudoplantae"
        },
    }

    def __init__(
        self, 
        embedding_service: 'EmbeddingService',
        router: 'ModelRouter | None' = None
    ) -> None:
        self.embeddings = embedding_service
        self.router = router
        self._clade_counter = 0
        
    def build_taxonomy(
        self,
        species_list: Sequence['Species'],
        params: dict[str, Any] | None = None,
        current_turn: int = 0
    ) -> TaxonomyResult:
        """构建完整的分类树
        
        Args:
            species_list: 物种列表
            params: 聚类参数（可选）
            current_turn: 当前回合数
        
        Returns:
            TaxonomyResult: 分类结果
        """
        if len(species_list) < 2:
            logger.warning("物种数量不足，无法构建分类树")
            return TaxonomyResult(
                tree={},
                clades=[],
                species_assignments={},
                stats={"error": "insufficient_species"}
            )
        
        params = {**self.DEFAULT_PARAMS, **(params or {})}
        self._clade_counter = 0
        
        logger.info(f"开始构建分类树: {len(species_list)} 个物种")
        
        # 1. 批量获取所有物种的 embedding
        # 【优化】优先从索引获取已存在的向量
        species_codes = [sp.lineage_code for sp in species_list]
        indexed_vectors, indexed_codes = self.embeddings.get_species_vectors(species_codes)
        
        # 构建代码到向量的映射
        code_to_vector = dict(zip(indexed_codes, indexed_vectors))
        
        # 收集需要新生成向量的物种
        vectors_list = []
        missing_species = []
        missing_indices = []
        
        for i, sp in enumerate(species_list):
            if sp.lineage_code in code_to_vector:
                vectors_list.append(code_to_vector[sp.lineage_code])
            else:
                vectors_list.append(None)
                missing_species.append(sp)
                missing_indices.append(i)
        
        # 对未索引的物种生成向量
        if missing_species:
            from ..system.embedding import EmbeddingService
            descriptions = [
                EmbeddingService.build_species_text(sp, include_traits=True, include_names=True)
                for sp in missing_species
            ]
            new_vectors = self.embeddings.embed(descriptions)
            for i, idx in enumerate(missing_indices):
                vectors_list[idx] = new_vectors[i]
        
        vectors = np.array(vectors_list, dtype=np.float32)
        
        logger.info(f"已获取 {len(vectors)} 个 embedding 向量，维度: {vectors.shape[1]}（{len(indexed_codes)} 个来自索引）")
        
        # 2. 第一层聚类：域/门级大类
        domain_clades = self._cluster_top_level(
            vectors, 
            species_codes, 
            species_list,
            n_clusters=params["domain_clusters"]
        )
        
        # 3. 递归细分每个大类
        all_clades = []
        for domain_clade in domain_clades:
            subtree = self._recursive_cluster(
                domain_clade,
                vectors,
                species_codes,
                species_list,
                current_depth=1,
                max_depth=3,  # 最多3层细分
                params=params
            )
            all_clades.extend(subtree)
        
        all_clades = domain_clades + all_clades
        
        # 4. 构建树形结构
        tree = self._build_tree_structure(domain_clades)
        
        # 5. 生成物种分配映射
        species_assignments = self._build_species_assignments(all_clades)
        
        # 6. 统计信息
        stats = {
            "total_species": len(species_list),
            "total_clades": len(all_clades),
            "domain_count": len(domain_clades),
            "max_depth": max((c.depth for c in all_clades), default=0),
            "clustering_params": params,
            "turn_index": current_turn,
        }
        
        logger.info(f"分类树构建完成: {stats['total_clades']} 个类群, 最大深度 {stats['max_depth']}")
        
        return TaxonomyResult(
            tree=tree,
            clades=all_clades,
            species_assignments=species_assignments,
            stats=stats
        )

    def _cluster_top_level(
        self,
        vectors: np.ndarray,
        species_codes: list[str],
        species_list: Sequence['Species'],
        n_clusters: int = 3
    ) -> list[CladeInfo]:
        """顶层聚类（门级）"""
        from sklearn.cluster import KMeans
        
        # 限制聚类数量不超过样本数
        n_clusters = min(n_clusters, len(vectors))
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(vectors)
        
        clades = []
        for cluster_id in range(n_clusters):
            mask = labels == cluster_id
            if not np.any(mask):
                continue
            
            member_codes = [species_codes[i] for i in range(len(species_codes)) if mask[i]]
            member_species = [species_list[i] for i in range(len(species_list)) if mask[i]]
            centroid = kmeans.cluster_centers_[cluster_id]
            
            # 计算内聚度
            cohesion = self._compute_cohesion(vectors[mask], centroid)
            
            # 生成名称
            name, latin_name = self._generate_clade_name(
                member_species, 
                rank="phylum",
                cluster_id=cluster_id
            )
            
            # 提取定义特征
            defining_traits = self._extract_defining_traits(member_species)
            
            clade = CladeInfo(
                id=self._next_clade_id(),
                name=name,
                latin_name=latin_name,
                rank="phylum",
                parent_id=None,
                depth=0,
                centroid=centroid,
                member_codes=member_codes,
                defining_traits=defining_traits,
                cohesion=cohesion
            )
            clades.append(clade)
        
        logger.info(f"顶层聚类完成: {len(clades)} 个门级类群")
        return clades

    def _recursive_cluster(
        self,
        parent_clade: CladeInfo,
        all_vectors: np.ndarray,
        all_codes: list[str],
        all_species: Sequence['Species'],
        current_depth: int,
        max_depth: int,
        params: dict
    ) -> list[CladeInfo]:
        """递归聚类细分"""
        if current_depth >= max_depth:
            return []
        
        if len(parent_clade.member_codes) < params["min_cluster_size"] * 2:
            return []
        
        # 获取该类群的成员向量
        member_indices = [all_codes.index(code) for code in parent_clade.member_codes]
        member_vectors = all_vectors[member_indices]
        member_species = [all_species[i] for i in member_indices]
        
        # 尝试进一步聚类
        sub_clades = self._cluster_subclade(
            member_vectors,
            parent_clade.member_codes,
            member_species,
            parent_clade,
            current_depth,
            params
        )
        
        # 递归处理子类群
        all_sub_clades = list(sub_clades)
        for sub_clade in sub_clades:
            parent_clade.children.append(sub_clade)
            deeper_clades = self._recursive_cluster(
                sub_clade,
                all_vectors,
                all_codes,
                all_species,
                current_depth + 1,
                max_depth,
                params
            )
            all_sub_clades.extend(deeper_clades)
        
        return all_sub_clades

    def _cluster_subclade(
        self,
        vectors: np.ndarray,
        codes: list[str],
        species: Sequence['Species'],
        parent: CladeInfo,
        depth: int,
        params: dict
    ) -> list[CladeInfo]:
        """对子类群进行聚类"""
        if len(vectors) < 4:
            return []
        
        try:
            # 使用层次聚类
            from sklearn.cluster import AgglomerativeClustering
            
            n_clusters = min(3, len(vectors) // 2)
            if n_clusters < 2:
                return []
            
            clustering = AgglomerativeClustering(n_clusters=n_clusters)
            labels = clustering.fit_predict(vectors)
            
        except Exception as e:
            logger.warning(f"聚类失败: {e}")
            return []
        
        # 确定分类等级
        rank = self.RANKS[min(depth + 1, len(self.RANKS) - 1)]
        
        clades = []
        for cluster_id in np.unique(labels):
            mask = labels == cluster_id
            if np.sum(mask) < params["min_cluster_size"]:
                continue
            
            member_codes = [codes[i] for i in range(len(codes)) if mask[i]]
            member_species = [species[i] for i in range(len(species)) if mask[i]]
            centroid = vectors[mask].mean(axis=0)
            cohesion = self._compute_cohesion(vectors[mask], centroid)
            
            if cohesion < params["cohesion_threshold"]:
                continue
            
            name, latin_name = self._generate_clade_name(
                member_species,
                rank=rank,
                cluster_id=cluster_id,
                parent_name=parent.name
            )
            
            defining_traits = self._extract_defining_traits(member_species)
            
            clade = CladeInfo(
                id=self._next_clade_id(),
                name=name,
                latin_name=latin_name,
                rank=rank,
                parent_id=parent.id,
                depth=depth,
                centroid=centroid,
                member_codes=member_codes,
                defining_traits=defining_traits,
                cohesion=cohesion
            )
            clades.append(clade)
        
        return clades

    def _compute_cohesion(self, vectors: np.ndarray, centroid: np.ndarray) -> float:
        """计算类群内聚度（成员与中心的平均相似度）"""
        if len(vectors) == 0:
            return 0.0
        
        # 归一化
        centroid_norm = centroid / (np.linalg.norm(centroid) + 1e-8)
        
        similarities = []
        for vec in vectors:
            vec_norm = vec / (np.linalg.norm(vec) + 1e-8)
            sim = np.dot(vec_norm, centroid_norm)
            similarities.append(sim)
        
        return float(np.mean(similarities))

    def _generate_clade_name(
        self,
        member_species: Sequence['Species'],
        rank: str,
        cluster_id: int,
        parent_name: str = ""
    ) -> tuple[str, str]:
        """生成类群名称
        
        Returns:
            (中文名, 拉丁名)
        """
        # 收集所有描述文本
        all_text = " ".join([sp.description for sp in member_species])
        
        # 尝试匹配参考模板
        best_match = None
        best_score = 0
        
        for template_key, template in self.REFERENCE_TEMPLATES.items():
            score = sum(1 for kw in template["keywords"] if kw in all_text)
            if score > best_score:
                best_score = score
                best_match = template
        
        rank_suffix = self.RANK_PREFIXES.get(rank, "类群")
        
        if best_match and best_score >= 2:
            base_name = best_match["name"]
            latin_base = best_match["latin"]
        else:
            # 使用第一个物种名称作为基础
            if member_species:
                first_sp = member_species[0]
                base_name = f"类{first_sp.common_name[:2]}生物"
                latin_base = f"Pseudo{first_sp.latin_name.split()[0][:6] if first_sp.latin_name else 'species'}"
            else:
                base_name = f"类群{cluster_id + 1}"
                latin_base = f"Clade{cluster_id + 1}"
        
        # 添加层级区分
        if parent_name and rank != "phylum":
            name = f"{base_name}{rank_suffix}"
        else:
            name = f"{base_name}{rank_suffix}"
        
        latin_name = f"{latin_base}_{rank[:3]}"
        
        return name, latin_name

    def _extract_defining_traits(self, member_species: Sequence['Species']) -> dict[str, Any]:
        """提取类群的定义特征"""
        if not member_species:
            return {}
        
        # 收集共同特征
        all_traits = {}
        all_organs = {}
        all_capabilities = set()
        
        for sp in member_species:
            # 统计特征值
            for trait, value in sp.abstract_traits.items():
                if trait not in all_traits:
                    all_traits[trait] = []
                all_traits[trait].append(value)
            
            # 统计器官类型
            for organ_cat, organ_data in sp.organs.items():
                if organ_cat not in all_organs:
                    all_organs[organ_cat] = []
                if isinstance(organ_data, dict) and "type" in organ_data:
                    all_organs[organ_cat].append(organ_data["type"])
            
            # 收集能力
            all_capabilities.update(sp.capabilities)
        
        # 计算平均特征
        avg_traits = {k: float(np.mean(v)) for k, v in all_traits.items()}
        
        # 找出高于平均的特征
        high_traits = [k for k, v in avg_traits.items() if v > 5.0]
        
        # 找出共同器官
        common_organs = {}
        for organ_cat, types in all_organs.items():
            if types:
                from collections import Counter
                most_common = Counter(types).most_common(1)
                if most_common and most_common[0][1] > len(member_species) * 0.5:
                    common_organs[organ_cat] = most_common[0][0]
        
        return {
            "high_traits": high_traits,
            "common_organs": common_organs,
            "common_capabilities": list(all_capabilities)[:5],
            "avg_traits": {k: round(v, 1) for k, v in list(avg_traits.items())[:5]},
        }

    def _build_tree_structure(self, root_clades: list[CladeInfo]) -> dict[str, Any]:
        """构建树形结构字典"""
        def clade_to_dict(clade: CladeInfo) -> dict:
            return {
                "id": clade.id,
                "name": clade.name,
                "latin_name": clade.latin_name,
                "rank": clade.rank,
                "member_count": len(clade.member_codes),
                "cohesion": round(clade.cohesion, 3),
                "defining_traits": clade.defining_traits,
                "children": [clade_to_dict(c) for c in clade.children],
            }
        
        return {
            "root": {
                "name": "生命树",
                "latin_name": "Arbor Vitae",
                "children": [clade_to_dict(c) for c in root_clades]
            }
        }

    def _build_species_assignments(self, all_clades: list[CladeInfo]) -> dict[str, list[str]]:
        """构建物种到类群的映射"""
        assignments: dict[str, list[str]] = {}
        
        for clade in all_clades:
            for code in clade.member_codes:
                if code not in assignments:
                    assignments[code] = []
                assignments[code].append(clade.name)
        
        return assignments

    def _next_clade_id(self) -> int:
        """生成下一个类群ID"""
        self._clade_counter += 1
        return self._clade_counter

    def get_species_classification(
        self, 
        species_code: str,
        taxonomy_result: TaxonomyResult
    ) -> list[str]:
        """获取物种的完整分类路径"""
        return taxonomy_result.species_assignments.get(species_code, [])

    def find_related_species(
        self,
        species_code: str,
        taxonomy_result: TaxonomyResult,
        same_rank: str = "family"
    ) -> list[str]:
        """查找同一类群的物种"""
        for clade in taxonomy_result.clades:
            if clade.rank == same_rank and species_code in clade.member_codes:
                return [c for c in clade.member_codes if c != species_code]
        return []

    def export_for_save(self, result: TaxonomyResult) -> dict[str, Any]:
        """导出分类数据用于存档"""
        return {
            "version": "1.0",
            "tree": result.tree,
            "clades": [
                {
                    "id": c.id,
                    "name": c.name,
                    "latin_name": c.latin_name,
                    "rank": c.rank,
                    "parent_id": c.parent_id,
                    "depth": c.depth,
                    "centroid": c.centroid.tolist() if isinstance(c.centroid, np.ndarray) else c.centroid,
                    "member_codes": c.member_codes,
                    "defining_traits": c.defining_traits,
                    "cohesion": c.cohesion,
                }
                for c in result.clades
            ],
            "species_assignments": result.species_assignments,
            "stats": result.stats,
        }

    def import_from_save(self, data: dict[str, Any]) -> TaxonomyResult | None:
        """从存档导入分类数据"""
        if not data or "clades" not in data:
            return None
        
        clades = []
        for c_data in data["clades"]:
            clade = CladeInfo(
                id=c_data["id"],
                name=c_data["name"],
                latin_name=c_data["latin_name"],
                rank=c_data["rank"],
                parent_id=c_data.get("parent_id"),
                depth=c_data.get("depth", 0),
                centroid=np.array(c_data.get("centroid", [])),
                member_codes=c_data.get("member_codes", []),
                defining_traits=c_data.get("defining_traits", {}),
                cohesion=c_data.get("cohesion", 0.0),
            )
            clades.append(clade)
        
        # 重建父子关系
        id_to_clade = {c.id: c for c in clades}
        for clade in clades:
            if clade.parent_id and clade.parent_id in id_to_clade:
                id_to_clade[clade.parent_id].children.append(clade)
        
        return TaxonomyResult(
            tree=data.get("tree", {}),
            clades=clades,
            species_assignments=data.get("species_assignments", {}),
            stats=data.get("stats", {})
        )

