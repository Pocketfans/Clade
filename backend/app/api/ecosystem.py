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
    from ..services.species.food_web_manager import FoodWebManager
    
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
    
    food_web_manager = FoodWebManager(container.species_repository)
    web_data = food_web_manager.build_food_web(all_species)
    
    return web_data


@router.get("/ecosystem/food-web/summary", tags=["ecosystem"])
def get_food_web_summary(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取食物网简版摘要（用于仪表盘）"""
    from ..services.species.food_web_manager import FoodWebManager
    
    food_web_manager = FoodWebManager(container.species_repository)
    return food_web_manager.get_summary()


@router.get("/ecosystem/food-web/cache-stats", tags=["ecosystem"])
def get_food_web_cache_stats(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取食物网缓存统计（调试用）"""
    from ..services.species.food_web_cache import get_food_web_cache_stats
    return get_food_web_cache_stats()


@router.get("/ecosystem/food-web/analysis", tags=["ecosystem"])
def get_food_web_analysis(
    detail_level: str = Query("full", description="详细程度: simple, full"),
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取食物网分析报告"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    all_species = [sp for sp in species_repo.list_species() if sp.status == "alive"]
    
    food_web_manager = FoodWebManager(species_repo)
    analysis = food_web_manager.analyze_structure(all_species, detail_level=detail_level)
    
    return analysis


@router.post("/ecosystem/food-web/repair", tags=["ecosystem"])
def repair_food_web(
    container: 'ServiceContainer' = Depends(get_container),
):
    """修复食物网缺陷"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    all_species = [sp for sp in species_repo.list_species() if sp.status == "alive"]
    
    food_web_manager = FoodWebManager(species_repo)
    repair_report = food_web_manager.repair_food_web(all_species)
    
    # 保存修复后的物种
    for species in all_species:
        species_repo.upsert(species)
    
    return repair_report


@router.get("/ecosystem/food-web/{lineage_code}", tags=["ecosystem"])
def get_species_food_chain(
    lineage_code: str,
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取特定物种的食物链"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    food_web_manager = FoodWebManager(species_repo)
    return food_web_manager.get_species_chain(species)


@router.get("/ecosystem/food-web/{lineage_code}/neighborhood", tags=["ecosystem"])
def get_species_neighborhood(
    lineage_code: str,
    depth: int = Query(2, ge=1, le=4, description="邻域深度"),
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取物种的食物网邻域"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    food_web_manager = FoodWebManager(species_repo)
    return food_web_manager.get_neighborhood(species, depth=depth)


@router.get("/ecosystem/extinction-impact/{lineage_code}", tags=["ecosystem"])
def analyze_extinction_impact(
    lineage_code: str,
    container: 'ServiceContainer' = Depends(get_container),
):
    """分析物种灭绝的影响"""
    from ..services.species.food_web_manager import FoodWebManager
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {lineage_code} 不存在")
    
    food_web_manager = FoodWebManager(species_repo)
    impact = food_web_manager.analyze_extinction_impact(species)
    
    return {
        "lineage_code": lineage_code,
        "common_name": species.common_name,
        "impact": impact,
    }

