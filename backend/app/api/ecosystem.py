"""
生态系统路由 - 食物网与生态健康分析

此模块负责：
- 食物网查询和分析
- 生态系统健康报告
- 物种灭绝影响分析
- 营养级分布
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query

from ..schemas.responses import (
    EcosystemHealthResponse,
    ExtinctionRiskItem,
    TrophicDistributionItem,
)
from .dependencies import get_container, get_species_repository

if TYPE_CHECKING:
    from ..core.container import ServiceContainer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["ecosystem"])


# ========== 生态健康 ==========

@router.get("/ecosystem/health", response_model=EcosystemHealthResponse, tags=["ecosystem"])
def get_ecosystem_health(
    container: 'ServiceContainer' = Depends(get_container),
) -> EcosystemHealthResponse:
    """获取生态系统健康报告"""
    from ..services.analytics.ecosystem_health import EcosystemHealthService
    
    species_repo = container.species_repository
    all_species = species_repo.list_species()
    
    health_service = EcosystemHealthService()
    report = health_service.analyze(all_species)
    
    return EcosystemHealthResponse(
        overall_health=report.get("overall_health", 0.5),
        biodiversity_index=report.get("biodiversity_index", 0.0),
        food_web_stability=report.get("food_web_stability", 0.5),
        trophic_balance=report.get("trophic_balance", 0.5),
        population_stability=report.get("population_stability", 0.5),
        extinction_risk=report.get("extinction_risk", 0.0),
        trophic_distribution=[
            TrophicDistributionItem(**item)
            for item in report.get("trophic_distribution", [])
        ],
        at_risk_species=[
            ExtinctionRiskItem(**item)
            for item in report.get("at_risk_species", [])
        ],
        recommendations=report.get("recommendations", []),
    )


# ========== 食物网 ==========

@router.get("/ecosystem/food-web", tags=["ecosystem"])
def get_food_web(
    max_nodes: int = Query(500, ge=1, le=1000, description="最大节点数"),
    include_extinct: bool = Query(False, description="是否包含已灭绝物种"),
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取食物网数据"""
    species_repo = container.species_repository
    all_species = species_repo.list_species()
    
    if not include_extinct:
        all_species = [sp for sp in all_species if sp.status == "alive"]
    
    if len(all_species) > max_nodes:
        # 按种群数量排序，保留最大的
        all_species = sorted(
            all_species,
            key=lambda sp: sp.morphology_stats.get("population", 0) or 0,
            reverse=True
        )[:max_nodes]
    
    # 构建物种映射
    species_map = {sp.lineage_code: sp for sp in all_species}
    alive_codes = set(species_map.keys())
    
    # 构建节点列表
    nodes = []
    prey_counts = {}  # 统计每个物种被多少物种捕食
    
    for sp in all_species:
        prey_codes = sp.prey_species or []
        valid_prey = [c for c in prey_codes if c in alive_codes]
        
        # 统计捕食者数量
        for prey_code in valid_prey:
            prey_counts[prey_code] = prey_counts.get(prey_code, 0) + 1
    
    for sp in all_species:
        nodes.append({
            "id": sp.lineage_code,
            "name": sp.common_name,
            "trophic_level": sp.trophic_level or 1.0,
            "population": int(sp.morphology_stats.get("population", 0) or 0),
            "diet_type": getattr(sp, 'diet_type', '') or '',
            "habitat_type": getattr(sp, 'habitat_type', '') or '',
            "prey_count": len([c for c in (sp.prey_species or []) if c in alive_codes]),
            "predator_count": prey_counts.get(sp.lineage_code, 0),
        })
    
    # 构建链接列表
    links = []
    for sp in all_species:
        prey_codes = sp.prey_species or []
        prey_prefs = sp.prey_preferences or {}
        
        for prey_code in prey_codes:
            if prey_code in alive_codes:
                prey_sp = species_map[prey_code]
                links.append({
                    "source": prey_code,  # 猎物
                    "target": sp.lineage_code,  # 捕食者
                    "value": prey_prefs.get(prey_code, 1.0 / max(len(prey_codes), 1)),
                    "predator_name": sp.common_name,
                    "prey_name": prey_sp.common_name,
                })
    
    # 识别关键物种（被3+物种依赖）
    keystone_species = [code for code, count in prey_counts.items() if count >= 3]
    
    # 按营养级分组
    trophic_levels = {}
    for sp in all_species:
        level = int(sp.trophic_level or 1)
        if level not in trophic_levels:
            trophic_levels[level] = []
        trophic_levels[level].append(sp.lineage_code)
    
    return {
        "nodes": nodes,
        "links": links,
        "keystone_species": keystone_species,
        "trophic_levels": trophic_levels,
        "total_species": len(nodes),
        "total_links": len(links),
    }


@router.get("/ecosystem/food-web/summary", tags=["ecosystem"])
def get_food_web_summary(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取食物网简版摘要（用于仪表盘）"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    all_species = [sp for sp in species_repo.list_species() if sp.status == "alive"]
    
    food_web_manager = FoodWebManager()
    analysis = food_web_manager.analyze_food_web(all_species)
    
    return {
        "total_species": analysis.total_species,
        "total_links": analysis.total_links,
        "health_score": analysis.health_score,
        "keystone_count": len(analysis.keystone_species),
        "warnings_count": len(analysis.bottleneck_warnings),
    }


@router.get("/ecosystem/food-web/cache-stats", tags=["ecosystem"])
def get_food_web_cache_stats(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取食物网缓存统计（调试用）"""
    # 缓存模块已移除，返回占位数据
    return {
        "cache_enabled": False,
        "message": "食物网缓存功能已禁用",
    }


@router.get("/ecosystem/food-web/analysis", tags=["ecosystem"])
def get_food_web_analysis(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取食物网分析报告"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    all_species = [sp for sp in species_repo.list_species() if sp.status == "alive"]
    
    food_web_manager = FoodWebManager()
    analysis = food_web_manager.analyze_food_web(all_species)
    
    # 转换为字典格式返回
    return {
        "total_species": analysis.total_species,
        "total_links": analysis.total_links,
        "orphaned_consumers": analysis.orphaned_consumers,
        "starving_species": analysis.starving_species,
        "keystone_species": analysis.keystone_species,
        "isolated_species": analysis.isolated_species,
        "avg_prey_per_consumer": analysis.avg_prey_per_consumer,
        "food_web_density": analysis.food_web_density,
        "bottleneck_warnings": analysis.bottleneck_warnings,
        "health_score": analysis.health_score,
    }


@router.post("/ecosystem/food-web/repair", tags=["ecosystem"])
def repair_food_web(
    container: 'ServiceContainer' = Depends(get_container),
):
    """修复食物网缺陷"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    all_species = species_repo.list_species()
    
    food_web_manager = FoodWebManager()
    
    # 使用 rebuild_food_web 修复食物网
    modified_count = food_web_manager.rebuild_food_web(
        all_species, 
        species_repo,
        preserve_valid_links=True
    )
    
    # 重新分析修复后的状态
    alive_species = [sp for sp in species_repo.list_species() if sp.status == "alive"]
    analysis = food_web_manager.analyze_food_web(alive_species)
    
    return {
        "modified_count": modified_count,
        "health_score": analysis.health_score,
        "remaining_issues": len(analysis.orphaned_consumers) + len(analysis.starving_species),
        "warnings": analysis.bottleneck_warnings,
    }


@router.get("/ecosystem/food-web/{lineage_code}", tags=["ecosystem"])
def get_species_food_chain(
    lineage_code: str,
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取特定物种的食物链
    
    返回该物种的上下游食物关系：
    - species: 物种基本信息
    - prey_chain: 猎物链（向下追溯）
    - predator_chain: 捕食者链（向上追溯）
    - food_dependency: 食物依赖满足度 (0-1)
    - predation_pressure: 被捕食压力 (0-1)
    """
    from ..services.species.predation import PredationService
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    all_species = species_repo.list_species()
    predation_service = PredationService()
    return predation_service.get_species_food_chain(species, all_species)


@router.get("/ecosystem/food-web/{lineage_code}/neighborhood", tags=["ecosystem"])
def get_species_neighborhood(
    lineage_code: str,
    depth: int = Query(2, ge=1, le=4, description="邻域深度"),
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取物种的食物网邻域
    
    返回以该物种为中心的 k-hop 邻域内的物种和捕食关系。
    """
    from ..services.species.predation import PredationService
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    all_species = species_repo.list_species()
    predation_service = PredationService()
    
    # 获取食物链数据
    food_chain = predation_service.get_species_food_chain(species, all_species, max_depth=depth)
    
    # 构建邻域节点和链接
    nodes = [{"id": species.lineage_code, "name": species.common_name, "trophic_level": species.trophic_level}]
    links = []
    
    def collect_nodes_from_chain(chain_items, direction):
        for item in chain_items:
            if item["code"] not in [n["id"] for n in nodes]:
                nodes.append({
                    "id": item["code"],
                    "name": item["name"],
                    "trophic_level": item["trophic_level"]
                })
            if direction == "prey":
                links.append({"source": item["code"], "target": species.lineage_code})
            else:  # predator
                links.append({"source": species.lineage_code, "target": item["code"]})
    
    collect_nodes_from_chain(food_chain.get("prey_chain", []), "prey")
    collect_nodes_from_chain(food_chain.get("predator_chain", []), "predator")
    
    return {
        "center": species.lineage_code,
        "depth": depth,
        "nodes": nodes,
        "links": links,
        "food_chain": food_chain
    }


@router.get("/ecosystem/extinction-impact/{lineage_code}", tags=["ecosystem"])
def analyze_extinction_impact(
    lineage_code: str,
    container: 'ServiceContainer' = Depends(get_container),
):
    """分析物种灭绝的影响
    
    返回格式兼容前端 ExtinctionImpact 类型：
    - extinct_species: 灭绝物种代码
    - directly_affected: 直接受影响的物种列表
    - indirectly_affected: 间接受影响的物种列表
    - food_chain_collapse_risk: 食物链崩溃风险 (0-1)
    - affected_biomass_percentage: 受影响生物量百分比
    """
    from ..services.species.predation import PredationService
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    predation_service = PredationService()
    all_species = species_repo.list_species()
    impact = predation_service.analyze_extinction_impact(species, all_species)
    
    # 返回符合前端 ExtinctionImpact 接口的结构
    return {
        "extinct_species": impact.extinct_species,
        "directly_affected": impact.directly_affected,
        "indirectly_affected": impact.indirectly_affected,
        "food_chain_collapse_risk": impact.food_chain_collapse_risk,
        "affected_biomass_percentage": impact.affected_biomass_percentage,
    }


