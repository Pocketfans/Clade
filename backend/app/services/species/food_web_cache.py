"""食物网缓存服务 (Food Web Cache Service)

提供食物网数据的缓存和增量更新，优化性能。

核心功能：
1. 缓存 FoodWebAnalysis 结果
2. 缓存 predator→prey 关系映射
3. 分化/灭绝后局部增量更新
4. TTL 过期管理
5. 分页/裁剪查询支持

设计原则：
- 回合内复用缓存，减少重复计算
- 增量更新而非全量重算
- 支持多种查询模式（全局、局部、k-hop）
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ...models.species import Species
    from .food_web_manager import FoodWebAnalysis

logger = logging.getLogger(__name__)


@dataclass
class CachedFoodWebNode:
    """缓存的食物网节点（简化版）"""
    lineage_code: str
    common_name: str
    trophic_level: float
    population: int
    diet_type: str
    habitat_type: str
    prey_count: int
    predator_count: int
    is_keystone: bool = False
    status: str = "alive"


@dataclass
class CachedFoodWebLink:
    """缓存的食物网链接"""
    source: str  # 猎物
    target: str  # 捕食者
    preference: float


@dataclass
class FoodWebCache:
    """食物网缓存数据"""
    turn_index: int
    timestamp: float
    
    # 节点缓存
    nodes: dict[str, CachedFoodWebNode] = field(default_factory=dict)
    
    # 链接缓存
    links: list[CachedFoodWebLink] = field(default_factory=list)
    
    # 关系映射缓存
    predator_to_prey: dict[str, list[str]] = field(default_factory=dict)
    prey_to_predators: dict[str, list[str]] = field(default_factory=dict)
    
    # 营养级索引
    by_trophic_level: dict[int, list[str]] = field(default_factory=dict)
    
    # 关键物种缓存
    keystone_species: list[str] = field(default_factory=list)
    
    # FoodWebAnalysis 缓存
    analysis: "FoodWebAnalysis | None" = None
    
    # 统计信息
    total_nodes: int = 0
    total_links: int = 0


@dataclass
class FoodWebQueryOptions:
    """食物网查询选项"""
    # 分页
    max_nodes: int = 100
    max_links: int = 500
    offset: int = 0
    
    # 过滤
    trophic_levels: list[int] | None = None  # 只返回指定营养级
    center_species: str | None = None  # 中心物种（用于 k-hop）
    k_hop: int = 2  # 邻域跳数
    
    # 响应详细程度
    detail_level: str = "simple"  # simple, standard, full
    include_preferences: bool = False
    include_biomass: bool = False
    
    # 排序
    sort_by: str = "trophic_level"  # trophic_level, population, name
    sort_desc: bool = False


@dataclass
class PaginatedFoodWebResponse:
    """分页的食物网响应"""
    nodes: list[dict]
    links: list[dict]
    total_nodes: int
    total_links: int
    has_more_nodes: bool
    has_more_links: bool
    query_options: dict
    cache_hit: bool
    cache_age_seconds: float


class FoodWebCacheService:
    """食物网缓存服务
    
    提供食物网数据的缓存管理和查询优化。
    """
    
    # 默认 TTL（秒）
    DEFAULT_TTL = 300  # 5分钟
    
    def __init__(self, ttl_seconds: float = DEFAULT_TTL):
        self._cache: FoodWebCache | None = None
        self._ttl = ttl_seconds
        self._logger = logging.getLogger(__name__)
        
        # 增量更新队列
        self._pending_additions: list[str] = []
        self._pending_removals: list[str] = []
    
    @property
    def is_valid(self) -> bool:
        """检查缓存是否有效"""
        if self._cache is None:
            return False
        age = time.time() - self._cache.timestamp
        return age < self._ttl
    
    @property
    def cache_age(self) -> float:
        """获取缓存年龄（秒）"""
        if self._cache is None:
            return float('inf')
        return time.time() - self._cache.timestamp
    
    def invalidate(self):
        """使缓存失效"""
        self._cache = None
        self._pending_additions.clear()
        self._pending_removals.clear()
        self._logger.debug("[食物网缓存] 缓存已失效")
    
    def build_cache(
        self,
        all_species: Sequence[Species],
        turn_index: int,
        analysis: "FoodWebAnalysis | None" = None,
    ) -> FoodWebCache:
        """构建完整的食物网缓存
        
        Args:
            all_species: 所有物种
            turn_index: 当前回合
            analysis: 可选的 FoodWebAnalysis 结果
            
        Returns:
            构建的缓存对象
        """
        start_time = time.time()
        
        alive_species = [s for s in all_species if s.status == "alive"]
        alive_codes = {s.lineage_code for s in alive_species}
        
        cache = FoodWebCache(
            turn_index=turn_index,
            timestamp=time.time(),
            analysis=analysis,
        )
        
        # 统计被捕食次数
        predator_counts: dict[str, int] = {}
        
        # 构建节点和关系
        for sp in alive_species:
            # 节点
            node = CachedFoodWebNode(
                lineage_code=sp.lineage_code,
                common_name=sp.common_name,
                trophic_level=sp.trophic_level,
                population=sp.morphology_stats.get("population", 0),
                diet_type=sp.diet_type or "unknown",
                habitat_type=sp.habitat_type or "unknown",
                prey_count=len(sp.prey_species or []),
                predator_count=0,  # 稍后填充
                status=sp.status,
            )
            cache.nodes[sp.lineage_code] = node
            
            # 营养级索引
            level = int(sp.trophic_level)
            if level not in cache.by_trophic_level:
                cache.by_trophic_level[level] = []
            cache.by_trophic_level[level].append(sp.lineage_code)
            
            # 捕食关系
            prey_codes = sp.prey_species or []
            valid_prey = [c for c in prey_codes if c in alive_codes]
            cache.predator_to_prey[sp.lineage_code] = valid_prey
            
            for prey_code in valid_prey:
                # 反向索引
                if prey_code not in cache.prey_to_predators:
                    cache.prey_to_predators[prey_code] = []
                cache.prey_to_predators[prey_code].append(sp.lineage_code)
                
                # 统计被捕食次数
                predator_counts[prey_code] = predator_counts.get(prey_code, 0) + 1
                
                # 链接
                preference = (sp.prey_preferences or {}).get(prey_code, 0.5)
                cache.links.append(CachedFoodWebLink(
                    source=prey_code,
                    target=sp.lineage_code,
                    preference=preference,
                ))
        
        # 填充被捕食数量和关键物种
        for code, count in predator_counts.items():
            if code in cache.nodes:
                cache.nodes[code].predator_count = count
                if count >= 3:
                    cache.nodes[code].is_keystone = True
                    cache.keystone_species.append(code)
        
        cache.total_nodes = len(cache.nodes)
        cache.total_links = len(cache.links)
        
        self._cache = cache
        
        build_time = time.time() - start_time
        self._logger.info(
            f"[食物网缓存] 构建完成: {cache.total_nodes} 节点, "
            f"{cache.total_links} 链接, 耗时 {build_time*1000:.1f}ms"
        )
        
        return cache
    
    def update_on_speciation(
        self,
        new_species: Sequence[Species],
        parent_codes: list[str],
    ):
        """分化后增量更新缓存
        
        Args:
            new_species: 新分化的物种
            parent_codes: 父代物种代码
        """
        if self._cache is None:
            return
        
        for sp in new_species:
            self._pending_additions.append(sp.lineage_code)
        
        self._logger.debug(
            f"[食物网缓存] 标记增量更新: +{len(new_species)} 新物种"
        )
    
    def update_on_extinction(self, extinct_codes: list[str]):
        """灭绝后增量更新缓存
        
        Args:
            extinct_codes: 灭绝的物种代码
        """
        if self._cache is None:
            return
        
        for code in extinct_codes:
            self._pending_removals.append(code)
            
            # 从缓存中移除
            if code in self._cache.nodes:
                del self._cache.nodes[code]
            
            # 从关系中移除
            if code in self._cache.predator_to_prey:
                del self._cache.predator_to_prey[code]
            
            if code in self._cache.prey_to_predators:
                del self._cache.prey_to_predators[code]
            
            # 从其他捕食者的猎物列表中移除
            for pred_code in list(self._cache.predator_to_prey.keys()):
                prey_list = self._cache.predator_to_prey[pred_code]
                if code in prey_list:
                    prey_list.remove(code)
            
            # 从链接中移除
            self._cache.links = [
                link for link in self._cache.links
                if link.source != code and link.target != code
            ]
        
        self._cache.total_nodes = len(self._cache.nodes)
        self._cache.total_links = len(self._cache.links)
        
        self._logger.debug(
            f"[食物网缓存] 移除 {len(extinct_codes)} 个灭绝物种"
        )
    
    def apply_pending_updates(self, all_species: Sequence[Species]):
        """应用待处理的增量更新"""
        if self._cache is None:
            return
        
        if not self._pending_additions and not self._pending_removals:
            return
        
        species_map = {s.lineage_code: s for s in all_species if s.status == "alive"}
        alive_codes = set(species_map.keys())
        
        # 处理新增
        for code in self._pending_additions:
            sp = species_map.get(code)
            if not sp:
                continue
            
            # 添加节点
            node = CachedFoodWebNode(
                lineage_code=sp.lineage_code,
                common_name=sp.common_name,
                trophic_level=sp.trophic_level,
                population=sp.morphology_stats.get("population", 0),
                diet_type=sp.diet_type or "unknown",
                habitat_type=sp.habitat_type or "unknown",
                prey_count=len(sp.prey_species or []),
                predator_count=0,
                status=sp.status,
            )
            self._cache.nodes[code] = node
            
            # 添加营养级索引
            level = int(sp.trophic_level)
            if level not in self._cache.by_trophic_level:
                self._cache.by_trophic_level[level] = []
            if code not in self._cache.by_trophic_level[level]:
                self._cache.by_trophic_level[level].append(code)
            
            # 添加捕食关系
            prey_codes = sp.prey_species or []
            valid_prey = [c for c in prey_codes if c in alive_codes]
            self._cache.predator_to_prey[code] = valid_prey
            
            for prey_code in valid_prey:
                if prey_code not in self._cache.prey_to_predators:
                    self._cache.prey_to_predators[prey_code] = []
                if code not in self._cache.prey_to_predators[prey_code]:
                    self._cache.prey_to_predators[prey_code].append(code)
                
                preference = (sp.prey_preferences or {}).get(prey_code, 0.5)
                self._cache.links.append(CachedFoodWebLink(
                    source=prey_code,
                    target=code,
                    preference=preference,
                ))
        
        self._cache.total_nodes = len(self._cache.nodes)
        self._cache.total_links = len(self._cache.links)
        
        self._pending_additions.clear()
        self._pending_removals.clear()
        
        self._logger.debug("[食物网缓存] 增量更新已应用")
    
    def query(
        self,
        options: FoodWebQueryOptions | None = None,
    ) -> PaginatedFoodWebResponse:
        """查询食物网数据（支持分页/裁剪）
        
        Args:
            options: 查询选项
            
        Returns:
            分页的响应
        """
        options = options or FoodWebQueryOptions()
        cache_hit = self.is_valid and self._cache is not None
        
        if not cache_hit or self._cache is None:
            # 缓存未命中，返回空响应
            return PaginatedFoodWebResponse(
                nodes=[],
                links=[],
                total_nodes=0,
                total_links=0,
                has_more_nodes=False,
                has_more_links=False,
                query_options=self._options_to_dict(options),
                cache_hit=False,
                cache_age_seconds=0,
            )
        
        # 获取候选节点
        candidate_codes = self._get_candidate_nodes(options)
        
        # 排序
        sorted_codes = self._sort_nodes(candidate_codes, options)
        
        # 分页
        total_nodes = len(sorted_codes)
        paginated_codes = sorted_codes[options.offset:options.offset + options.max_nodes]
        has_more_nodes = options.offset + options.max_nodes < total_nodes
        
        # 构建节点响应
        nodes = [
            self._node_to_dict(self._cache.nodes[code], options)
            for code in paginated_codes
            if code in self._cache.nodes
        ]
        
        # 获取相关链接
        code_set = set(paginated_codes)
        relevant_links = [
            link for link in self._cache.links
            if link.source in code_set or link.target in code_set
        ]
        
        # 链接分页
        total_links = len(relevant_links)
        paginated_links = relevant_links[:options.max_links]
        has_more_links = len(relevant_links) > options.max_links
        
        # 构建链接响应
        links = [
            self._link_to_dict(link, options)
            for link in paginated_links
        ]
        
        return PaginatedFoodWebResponse(
            nodes=nodes,
            links=links,
            total_nodes=total_nodes,
            total_links=total_links,
            has_more_nodes=has_more_nodes,
            has_more_links=has_more_links,
            query_options=self._options_to_dict(options),
            cache_hit=True,
            cache_age_seconds=self.cache_age,
        )
    
    def query_species_neighborhood(
        self,
        center_code: str,
        k_hop: int = 2,
        options: FoodWebQueryOptions | None = None,
    ) -> PaginatedFoodWebResponse:
        """查询指定物种的 k-hop 邻域
        
        Args:
            center_code: 中心物种代码
            k_hop: 邻域跳数
            options: 其他查询选项
            
        Returns:
            邻域内的食物网数据
        """
        options = options or FoodWebQueryOptions()
        options.center_species = center_code
        options.k_hop = k_hop
        
        return self.query(options)
    
    def get_simple_summary(self) -> dict:
        """获取简化的食物网摘要（用于仪表盘）"""
        if not self.is_valid or self._cache is None:
            return {
                "total_species": 0,
                "total_links": 0,
                "by_trophic_level": {},
                "keystone_count": 0,
                "cache_valid": False,
            }
        
        return {
            "total_species": self._cache.total_nodes,
            "total_links": self._cache.total_links,
            "by_trophic_level": {
                str(k): len(v) for k, v in self._cache.by_trophic_level.items()
            },
            "keystone_count": len(self._cache.keystone_species),
            "cache_valid": True,
            "cache_age_seconds": round(self.cache_age, 1),
        }
    
    def _get_candidate_nodes(self, options: FoodWebQueryOptions) -> list[str]:
        """获取候选节点（根据过滤条件）"""
        if self._cache is None:
            return []
        
        # 如果指定了中心物种，使用 k-hop 邻域
        if options.center_species:
            return self._get_k_hop_neighborhood(
                options.center_species, options.k_hop
            )
        
        # 如果指定了营养级过滤
        if options.trophic_levels:
            candidates = []
            for level in options.trophic_levels:
                candidates.extend(
                    self._cache.by_trophic_level.get(level, [])
                )
            return candidates
        
        # 默认返回所有
        return list(self._cache.nodes.keys())
    
    def _get_k_hop_neighborhood(
        self,
        center_code: str,
        k: int,
    ) -> list[str]:
        """获取 k-hop 邻域内的所有物种"""
        if self._cache is None:
            return []
        
        visited = {center_code}
        frontier = {center_code}
        
        for _ in range(k):
            new_frontier = set()
            for code in frontier:
                # 向下（猎物）
                for prey in self._cache.predator_to_prey.get(code, []):
                    if prey not in visited:
                        new_frontier.add(prey)
                        visited.add(prey)
                
                # 向上（捕食者）
                for pred in self._cache.prey_to_predators.get(code, []):
                    if pred not in visited:
                        new_frontier.add(pred)
                        visited.add(pred)
            
            frontier = new_frontier
            if not frontier:
                break
        
        return list(visited)
    
    def _sort_nodes(
        self,
        codes: list[str],
        options: FoodWebQueryOptions,
    ) -> list[str]:
        """排序节点"""
        if self._cache is None:
            return codes
        
        def get_sort_key(code: str):
            node = self._cache.nodes.get(code)
            if not node:
                return (0, 0, "")
            
            if options.sort_by == "population":
                return node.population
            elif options.sort_by == "name":
                return node.common_name
            else:  # trophic_level
                return node.trophic_level
        
        return sorted(codes, key=get_sort_key, reverse=options.sort_desc)
    
    def _node_to_dict(
        self,
        node: CachedFoodWebNode,
        options: FoodWebQueryOptions,
    ) -> dict:
        """将节点转换为字典（根据详细程度）"""
        # 简版
        result = {
            "id": node.lineage_code,
            "name": node.common_name,
            "trophic_level": node.trophic_level,
            "status": node.status,
        }
        
        if options.detail_level in ("standard", "full"):
            result.update({
                "population": node.population,
                "diet_type": node.diet_type,
                "habitat_type": node.habitat_type,
                "prey_count": node.prey_count,
                "predator_count": node.predator_count,
                "is_keystone": node.is_keystone,
            })
        
        if options.detail_level == "full" and options.include_biomass:
            # 可以添加更多详细信息
            pass
        
        return result
    
    def _link_to_dict(
        self,
        link: CachedFoodWebLink,
        options: FoodWebQueryOptions,
    ) -> dict:
        """将链接转换为字典"""
        result = {
            "source": link.source,
            "target": link.target,
        }
        
        if options.include_preferences:
            result["preference"] = round(link.preference, 3)
        
        return result
    
    def _options_to_dict(self, options: FoodWebQueryOptions) -> dict:
        """将查询选项转换为字典"""
        return {
            "max_nodes": options.max_nodes,
            "max_links": options.max_links,
            "offset": options.offset,
            "trophic_levels": options.trophic_levels,
            "center_species": options.center_species,
            "k_hop": options.k_hop,
            "detail_level": options.detail_level,
        }


# 全局单例
_food_web_cache_service: FoodWebCacheService | None = None


def get_food_web_cache() -> FoodWebCacheService:
    """获取食物网缓存服务单例"""
    global _food_web_cache_service
    if _food_web_cache_service is None:
        _food_web_cache_service = FoodWebCacheService()
    return _food_web_cache_service












