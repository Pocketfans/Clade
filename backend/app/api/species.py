"""
物种管理路由 - 物种增删改查、干预控制

此模块负责：
- 物种列表和详情查询
- 物种编辑和生成
- 物种干预（保护/压制）
- 杂交控制
- 系谱树和遗传关系
- 关注列表管理
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from ..schemas.requests import (
    GenerateSpeciesAdvancedRequest,
    GenerateSpeciesRequest,
    IntroduceSpeciesRequest,
    NicheCompareRequest,
    ProtectSpeciesRequest,
    SetSymbiosisRequest,
    SpeciesEditRequest,
    SuppressSpeciesRequest,
    WatchlistRequest,
)
from ..schemas.responses import (
    InterventionResponse,
    LineageNode,
    LineageTree,
    NicheCompareResult,
    SpeciesDetail,
    SpeciesList,
    SpeciesListItem,
)
from .dependencies import (
    get_container,
    get_embedding_service,
    get_genus_repository,
    get_model_router,
    get_session,
    get_species_generator,
    get_species_repository,
    require_not_running,
)

if TYPE_CHECKING:
    from ..core.container import ServiceContainer
    from ..core.session import SimulationSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["species"])


# ========== 关注列表（内存中，后续可移至 SessionManager）==========
_watchlist: set[str] = set()


def get_watchlist() -> set[str]:
    return _watchlist


def _invalidate_lineage_cache():
    """清除系谱树缓存"""
    _build_lineage_tree.cache_clear()


# ========== 辅助函数 ==========

def _serialize_species_detail(species) -> SpeciesDetail:
    """构建统一的 SpeciesDetail 响应"""
    morphology_stats = {
        k: v for k, v in (species.morphology_stats or {}).items()
        if isinstance(v, (int, float))
    }
    return SpeciesDetail(
        lineage_code=species.lineage_code,
        latin_name=species.latin_name,
        common_name=species.common_name,
        description=species.description,
        morphology_stats=morphology_stats,
        abstract_traits=species.abstract_traits,
        hidden_traits=species.hidden_traits,
        status=species.status,
        organs=species.organs,
        capabilities=species.capabilities,
        genus_code=species.genus_code,
        taxonomic_rank=species.taxonomic_rank,
        trophic_level=species.trophic_level,
        hybrid_parent_codes=species.hybrid_parent_codes,
        hybrid_fertility=species.hybrid_fertility,
        parent_code=species.parent_code,
        created_turn=species.created_turn,
        dormant_genes=species.dormant_genes,
        stress_exposure=species.stress_exposure,
    )


def _infer_ecological_role(species) -> str:
    """根据物种推断生态角色"""
    diet_type = getattr(species, 'diet_type', None)
    
    if diet_type == "detritivore":
        return "decomposer"
    if diet_type == "autotroph":
        return "producer"
    elif diet_type == "herbivore":
        return "herbivore"
    elif diet_type == "carnivore":
        return "carnivore"
    elif diet_type == "omnivore":
        return "omnivore"
    
    trophic = getattr(species, 'trophic_level', None)
    if trophic is None or not isinstance(trophic, (int, float)):
        trophic = 2.0
    
    if trophic < 1.5:
        return "producer"
    elif trophic < 2.0:
        return "mixotroph"
    elif trophic < 2.8:
        return "herbivore"
    elif trophic < 3.5:
        return "omnivore"
    else:
        return "carnivore"


@lru_cache(maxsize=1)
def _build_lineage_tree(cache_key: str, species_repo) -> LineageTree:
    """构建系谱树（带缓存）"""
    all_species = species_repo.list_species()
    nodes = []
    
    for sp in all_species:
        population = sp.morphology_stats.get("population", 0) or 0
        ecological_role = _infer_ecological_role(sp)
        
        nodes.append(LineageNode(
            lineage_code=sp.lineage_code,
            latin_name=sp.latin_name,
            common_name=sp.common_name,
            parent_code=sp.parent_code,
            status=sp.status,
            population=population,
            taxonomic_rank=sp.taxonomic_rank,
            ecological_role=ecological_role,
            created_turn=sp.created_turn,
            trophic_level=sp.trophic_level,
            hybrid_parent_codes=sp.hybrid_parent_codes,
        ))
    
    return LineageTree(
        nodes=nodes,
        total_species=len(nodes),
        alive_species=sum(1 for n in nodes if n.status == "alive"),
        extinct_species=sum(1 for n in nodes if n.status == "extinct"),
    )


# ========== 路由端点 ==========

@router.get("/species/list", response_model=SpeciesList)
def list_all_species(
    species_repo = Depends(get_species_repository)
) -> SpeciesList:
    """获取所有物种的简要列表"""
    all_species = species_repo.list_species()
    items = [
        SpeciesListItem(
            lineage_code=sp.lineage_code,
            latin_name=sp.latin_name,
            common_name=sp.common_name,
            status=sp.status,
            population=sp.morphology_stats.get("population", 0) or 0,
            genus_code=sp.genus_code,
            trophic_level=sp.trophic_level,
        )
        for sp in all_species
    ]
    return SpeciesList(
        items=items,
        total=len(items),
        alive=sum(1 for item in items if item.status == "alive"),
    )


@router.get("/species/{lineage_code}", response_model=SpeciesDetail)
def get_species_detail(
    lineage_code: str,
    species_repo = Depends(get_species_repository)
) -> SpeciesDetail:
    """获取物种详情"""
    species = species_repo.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail="Species not found")
    return _serialize_species_detail(species)


@router.post("/species/edit", response_model=SpeciesDetail)
def edit_species(
    request: SpeciesEditRequest,
    species_repo = Depends(get_species_repository),
    _: None = Depends(require_not_running),
) -> SpeciesDetail:
    """编辑物种属性（模拟运行时禁止）"""
    species = species_repo.get_by_lineage(request.lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail="Species not found")
    
    if request.description is not None:
        species.description = request.description
    if request.abstract_traits is not None:
        species.abstract_traits.update(request.abstract_traits)
    
    species_repo.upsert(species)
    _invalidate_lineage_cache()
    
    return _serialize_species_detail(species)


@router.get("/watchlist")
def get_watchlist_route() -> dict[str, list[str]]:
    """获取当前玩家关注的物种列表"""
    return {"watchlist": list(_watchlist)}


@router.post("/watchlist")
def update_watchlist(
    request: WatchlistRequest,
    species_repo = Depends(get_species_repository)
) -> dict[str, list[str]]:
    """更新玩家关注的物种列表"""
    global _watchlist
    
    # 验证物种存在
    for code in request.lineage_codes:
        if not species_repo.get_by_lineage(code):
            raise HTTPException(status_code=404, detail=f"Species {code} not found")
    
    _watchlist = set(request.lineage_codes)
    return {"watchlist": list(_watchlist)}


@router.get("/lineage")
def get_lineage_tree(
    request: Request,
    species_repo = Depends(get_species_repository),
) -> LineageTree:
    """获取完整系谱树"""
    all_species = species_repo.list_species()
    cache_key = f"{len(all_species)}_{sum(1 for s in all_species if s.status=='alive')}"
    return _build_lineage_tree(cache_key, species_repo)


@router.post("/species/generate")
def generate_species(
    request: GenerateSpeciesRequest,
    species_repo = Depends(get_species_repository),
    generator = Depends(get_species_generator),
    _: None = Depends(require_not_running),
) -> dict:
    """使用AI生成物种（模拟运行时禁止）"""
    try:
        existing = species_repo.list_species()
        used_codes = {sp.lineage_code for sp in existing}
        
        base_codes = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P"]
        lineage_code = None
        
        for base in base_codes:
            for suffix in range(1, 100):
                candidate = f"{base}{suffix}"
                if candidate not in used_codes:
                    lineage_code = candidate
                    break
            if lineage_code:
                break
        
        if not lineage_code:
            raise HTTPException(status_code=400, detail="无法生成唯一的物种编码")
        
        species = generator.generate_from_prompt(request.prompt, lineage_code)
        species_repo.upsert(species)
        _invalidate_lineage_cache()
        
        return {
            "success": True,
            "species": _serialize_species_detail(species).model_dump(),
        }
        
    except Exception as e:
        logger.error(f"[物种生成错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成物种失败: {str(e)}")


@router.post("/species/generate/advanced")
def generate_species_advanced(
    request: GenerateSpeciesAdvancedRequest,
    species_repo = Depends(get_species_repository),
    generator = Depends(get_species_generator),
    _: None = Depends(require_not_running),
) -> dict:
    """增强版物种生成 - 支持完整参数"""
    try:
        species = generator.generate_from_prompt_advanced(
            prompt=request.prompt,
            lineage_code=request.lineage_code,
            trophic_level=request.trophic_level,
            diet_type=request.diet_type,
            population=request.population,
            parent_code=request.parent_code,
        )
        species_repo.upsert(species)
        _invalidate_lineage_cache()
        
        return {
            "success": True,
            "species": _serialize_species_detail(species).model_dump(),
        }
        
    except Exception as e:
        logger.error(f"[高级物种生成错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"生成物种失败: {str(e)}")


@router.post("/niche/compare", response_model=NicheCompareResult)
def compare_niche(
    request: NicheCompareRequest,
    species_repo = Depends(get_species_repository),
    embedding_service = Depends(get_embedding_service),
) -> NicheCompareResult:
    """对比两个物种的生态位"""
    from ..services.species.niche_compare import NicheCompareService
    
    species_a = species_repo.get_by_lineage(request.code_a)
    species_b = species_repo.get_by_lineage(request.code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {request.code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {request.code_b} 不存在")
    
    compare_service = NicheCompareService(embedding_service)
    result = compare_service.compare(species_a, species_b)
    
    return result


@router.get("/species/{code1}/can_hybridize/{code2}", tags=["species"])
def check_hybridization(
    code1: str,
    code2: str,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """检查两个物种能否杂交"""
    species_repo = container.species_repository
    hybridization_service = container.hybridization_service
    
    sp1 = species_repo.get_by_lineage(code1)
    sp2 = species_repo.get_by_lineage(code2)
    
    if not sp1:
        raise HTTPException(status_code=404, detail=f"物种 {code1} 不存在")
    if not sp2:
        raise HTTPException(status_code=404, detail=f"物种 {code2} 不存在")
    
    can_hybrid, fertility = hybridization_service.can_hybridize(sp1, sp2)
    
    return {
        "can_hybridize": can_hybrid,
        "fertility": round(fertility, 3) if can_hybrid else 0,
        "species_a": {"lineage_code": sp1.lineage_code, "common_name": sp1.common_name},
        "species_b": {"lineage_code": sp2.lineage_code, "common_name": sp2.common_name},
    }


@router.get("/genus/{code}/relationships", tags=["species"])
def get_genetic_relationships(
    code: str,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取属内遗传关系"""
    species_repo = container.species_repository
    genus_repo = container.genus_repository
    genetic_calculator = container.genetic_distance_calculator
    
    genus = genus_repo.get_by_code(code)
    if not genus:
        raise HTTPException(status_code=404, detail=f"属 {code} 不存在")
    
    # 获取属内所有物种
    all_species = species_repo.list_species()
    genus_species = [sp for sp in all_species if sp.genus_code == code]
    
    relationships = []
    for i, sp1 in enumerate(genus_species):
        for sp2 in genus_species[i + 1:]:
            distance = genetic_calculator.calculate_distance(sp1, sp2)
            relationships.append({
                "species_a": sp1.lineage_code,
                "species_b": sp2.lineage_code,
                "distance": round(distance, 3),
            })
    
    return {
        "genus_code": code,
        "species_count": len(genus_species),
        "relationships": relationships,
    }


# ========== 干预控制 ==========

@router.post("/intervention/protect", response_model=InterventionResponse, tags=["intervention"])
def protect_species(
    request: ProtectSpeciesRequest,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> InterventionResponse:
    """保护指定物种（模拟运行时禁止）"""
    from ..services.system.divine_energy import energy_service
    from ..services.species.intervention import InterventionService
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(request.lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    if species.status != "alive":
        raise HTTPException(status_code=400, detail="物种已灭绝")
    
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    
    # 检查能量
    can_afford, cost = energy_service.can_afford("protect", turns=request.turns)
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！保护需要 {cost} 能量"
        )
    
    # 消耗能量
    success, msg = energy_service.spend(
        "protect",
        current_turn,
        details=f"保护 {species.common_name}",
        turns=request.turns
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    # 应用保护
    intervention_service = InterventionService()
    intervention_service.protect_species(species, request.turns)
    species_repo.upsert(species)
    _invalidate_lineage_cache()
    
    return InterventionResponse(
        success=True,
        lineage_code=request.lineage_code,
        intervention_type="protect",
        duration=request.turns,
        message=f"已保护 {species.common_name}，持续 {request.turns} 回合",
        energy_spent=cost,
    )


@router.post("/intervention/suppress", response_model=InterventionResponse, tags=["intervention"])
def suppress_species(
    request: SuppressSpeciesRequest,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> InterventionResponse:
    """压制指定物种（模拟运行时禁止）"""
    from ..services.system.divine_energy import energy_service
    from ..services.species.intervention import InterventionService
    
    species_repo = container.species_repository
    species = species_repo.get_by_lineage(request.lineage_code)
    
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    if species.status != "alive":
        raise HTTPException(status_code=400, detail="物种已灭绝")
    
    engine = container.simulation_engine
    current_turn = engine.turn_counter
    
    can_afford, cost = energy_service.can_afford("suppress", turns=request.turns)
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！压制需要 {cost} 能量"
        )
    
    success, msg = energy_service.spend(
        "suppress",
        current_turn,
        details=f"压制 {species.common_name}",
        turns=request.turns
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    
    intervention_service = InterventionService()
    intervention_service.suppress_species(species, request.turns)
    species_repo.upsert(species)
    _invalidate_lineage_cache()
    
    return InterventionResponse(
        success=True,
        lineage_code=request.lineage_code,
        intervention_type="suppress",
        duration=request.turns,
        message=f"已压制 {species.common_name}，持续 {request.turns} 回合",
        energy_spent=cost,
    )


@router.post("/intervention/cancel/{lineage_code}", response_model=InterventionResponse, tags=["intervention"])
def cancel_intervention(
    lineage_code: str,
    species_repo = Depends(get_species_repository),
    _: None = Depends(require_not_running),
) -> InterventionResponse:
    """取消对指定物种的所有干预（模拟运行时禁止）"""
    from ..services.species.intervention import InterventionService
    
    species = species_repo.get_by_lineage(lineage_code)
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    
    intervention_service = InterventionService()
    intervention_service.cancel_intervention(species)
    species_repo.upsert(species)
    _invalidate_lineage_cache()
    
    return InterventionResponse(
        success=True,
        lineage_code=lineage_code,
        intervention_type="cancel",
        duration=0,
        message=f"已取消对 {species.common_name} 的所有干预",
    )


@router.post("/intervention/introduce", response_model=InterventionResponse, tags=["intervention"])
async def introduce_species(
    request: IntroduceSpeciesRequest,
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> InterventionResponse:
    """引入新物种（模拟运行时禁止）"""
    from ..services.system.divine_energy import energy_service
    
    engine = container.simulation_engine
    species_repo = container.species_repository
    generator = container.species_generator
    current_turn = engine.turn_counter
    
    can_afford, cost = energy_service.can_afford("introduce")
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！引入物种需要 {cost} 能量"
        )
    
    # 生成物种
    existing = species_repo.list_species()
    used_codes = {sp.lineage_code for sp in existing}
    
    base_codes = ["A", "B", "C", "D", "E", "F", "G", "H"]
    lineage_code = None
    for base in base_codes:
        for suffix in range(1, 100):
            candidate = f"{base}{suffix}"
            if candidate not in used_codes:
                lineage_code = candidate
                break
        if lineage_code:
            break
    
    if not lineage_code:
        raise HTTPException(status_code=400, detail="无法生成唯一编码")
    
    try:
        species = generator.generate_from_prompt(request.description, lineage_code)
        species.created_turn = current_turn
        
        success, msg = energy_service.spend(
            "introduce",
            current_turn,
            details=f"引入 {species.common_name}"
        )
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        
        species_repo.upsert(species)
        _invalidate_lineage_cache()
        
        return InterventionResponse(
            success=True,
            lineage_code=species.lineage_code,
            intervention_type="introduce",
            duration=0,
            message=f"已引入新物种: {species.common_name}",
            energy_spent=cost,
        )
        
    except Exception as e:
        logger.error(f"[引入物种错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"引入物种失败: {str(e)}")


@router.post("/intervention/symbiosis", response_model=InterventionResponse, tags=["intervention"])
def set_symbiosis(
    request: SetSymbiosisRequest,
    species_repo = Depends(get_species_repository),
    _: None = Depends(require_not_running),
) -> InterventionResponse:
    """设置物种间的共生关系"""
    from ..services.system.divine_energy import energy_service
    
    species_a = species_repo.get_by_lineage(request.species_a)
    species_b = species_repo.get_by_lineage(request.species_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_b} 不存在")
    
    can_afford, cost = energy_service.can_afford("symbiosis")
    if not can_afford:
        raise HTTPException(
            status_code=400,
            detail=f"能量不足！建立共生关系需要 {cost} 能量"
        )
    
    # 设置共生关系
    if not hasattr(species_a, 'symbiotic_partners') or not species_a.symbiotic_partners:
        species_a.symbiotic_partners = []
    if not hasattr(species_b, 'symbiotic_partners') or not species_b.symbiotic_partners:
        species_b.symbiotic_partners = []
    
    if request.species_b not in species_a.symbiotic_partners:
        species_a.symbiotic_partners.append(request.species_b)
    if request.species_a not in species_b.symbiotic_partners:
        species_b.symbiotic_partners.append(request.species_a)
    
    species_repo.upsert(species_a)
    species_repo.upsert(species_b)
    _invalidate_lineage_cache()
    
    return InterventionResponse(
        success=True,
        lineage_code=request.species_a,
        intervention_type="symbiosis",
        duration=0,
        message=f"已建立 {species_a.common_name} 与 {species_b.common_name} 的共生关系",
        energy_spent=cost,
    )


@router.get("/intervention/status", tags=["intervention"])
def get_intervention_status(
    species_repo = Depends(get_species_repository),
) -> dict:
    """获取所有干预状态"""
    all_species = species_repo.list_species()
    
    protected = []
    suppressed = []
    
    for sp in all_species:
        if getattr(sp, 'is_protected', False) and sp.status == "alive":
            protected.append({
                "lineage_code": sp.lineage_code,
                "common_name": sp.common_name,
                "turns_remaining": getattr(sp, 'protection_turns', 0),
            })
        if getattr(sp, 'is_suppressed', False) and sp.status == "alive":
            suppressed.append({
                "lineage_code": sp.lineage_code,
                "common_name": sp.common_name,
                "turns_remaining": getattr(sp, 'suppression_turns', 0),
            })
    
    return {
        "protected": protected,
        "suppressed": suppressed,
        "total_interventions": len(protected) + len(suppressed),
    }

