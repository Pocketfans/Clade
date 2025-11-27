"""Embedding 扩展功能 API 路由

提供以下功能的 API 接口：
1. 自动分类学 (Taxonomy)
2. 向量演化预测 (Evolution Prediction)
3. 叙事生成 (Narrative)
4. 智能百科 (Encyclopedia)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/embedding", tags=["Embedding Services"])


# ==================== 请求/响应模型 ====================

class TaxonomyRequest(BaseModel):
    """分类学请求"""
    rebuild: bool = Field(default=False, description="是否强制重建分类树")
    params: dict[str, Any] | None = Field(default=None, description="聚类参数")


class TaxonomyResponse(BaseModel):
    """分类学响应"""
    success: bool
    tree: dict[str, Any]
    stats: dict[str, Any]
    species_assignments: dict[str, list[str]]


class EvolutionPredictionRequest(BaseModel):
    """演化预测请求"""
    species_code: str = Field(..., description="物种代码")
    pressure_types: list[str] = Field(..., description="压力类型列表")
    pressure_strengths: list[float] | None = Field(default=None, description="压力强度列表")
    generate_description: bool = Field(default=False, description="是否生成LLM描述")


class EvolutionPredictionResponse(BaseModel):
    """演化预测响应"""
    success: bool
    species_code: str
    species_name: str
    applied_pressures: list[str]
    predicted_trait_changes: dict[str, float]
    reference_species: list[dict[str, Any]]
    confidence: float
    predicted_description: str = ""


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(..., description="搜索查询")
    search_types: list[str] | None = Field(default=None, description="搜索类型")
    top_k: int = Field(default=10, description="返回数量")


class SearchResponse(BaseModel):
    """搜索响应"""
    success: bool
    results: list[dict[str, Any]]
    query: str


class QARequest(BaseModel):
    """问答请求"""
    question: str = Field(..., description="问题")


class QAResponse(BaseModel):
    """问答响应"""
    success: bool
    question: str
    answer: str
    sources: list[dict[str, Any]]
    confidence: float
    follow_up_questions: list[str]


class SpeciesExplanationRequest(BaseModel):
    """物种解释请求"""
    species_code: str = Field(..., description="物种代码")


class SpeciesExplanationResponse(BaseModel):
    """物种解释响应"""
    success: bool
    species_code: str
    species_name: str
    explanation: str
    key_factors: list[str]
    trait_explanations: dict[str, str]


class SpeciesCompareRequest(BaseModel):
    """物种对比请求"""
    species_code_a: str
    species_code_b: str


class SpeciesCompareResponse(BaseModel):
    """物种对比响应"""
    success: bool
    similarity: float
    relationship: str
    details: dict[str, Any]


class PressureListResponse(BaseModel):
    """压力列表响应"""
    pressures: list[dict[str, str]]


class HintsRequest(BaseModel):
    """提示请求"""
    species_code: str


class HintsResponse(BaseModel):
    """提示响应"""
    hints: list[dict[str, Any]]


class EmbeddingStatsResponse(BaseModel):
    """Embedding 统计响应"""
    cache_stats: dict[str, Any]
    index_stats: dict[str, Any]


# ==================== 服务实例（延迟初始化）====================

_taxonomy_service = None
_evolution_predictor = None
_narrative_engine = None
_encyclopedia_service = None
_services_initialized = False


def _get_services():
    """获取服务实例（延迟初始化）"""
    global _taxonomy_service, _evolution_predictor, _narrative_engine
    global _encyclopedia_service, _services_initialized
    
    if _services_initialized:
        return {
            "taxonomy": _taxonomy_service,
            "evolution": _evolution_predictor,
            "narrative": _narrative_engine,
            "encyclopedia": _encyclopedia_service
        }
    
    # 尝试从主路由获取依赖
    try:
        from . import routes
        
        embedding_service = getattr(routes, 'embedding_service', None)
        model_router = getattr(routes, 'model_router', None)  # 使用正确的变量名
        
        if embedding_service is None:
            logger.warning("Embedding 服务未初始化")
            return {}
        
        from ..services.analytics.taxonomy import TaxonomyService
        from ..services.analytics.evolution_predictor import EvolutionPredictor, PressureVectorLibrary
        from ..services.analytics.narrative_engine import NarrativeEngine
        from ..services.analytics.encyclopedia import EncyclopediaService
        
        _taxonomy_service = TaxonomyService(embedding_service, model_router)
        
        pressure_library = PressureVectorLibrary(embedding_service)
        _evolution_predictor = EvolutionPredictor(embedding_service, pressure_library, model_router)
        
        _narrative_engine = NarrativeEngine(embedding_service, model_router)
        _encyclopedia_service = EncyclopediaService(embedding_service, model_router)
        
        _services_initialized = True
        logger.info("Embedding 扩展服务初始化完成")
        
    except Exception as e:
        logger.error(f"初始化 Embedding 服务失败: {e}")
        import traceback
        traceback.print_exc()
        return {}
    
    return {
        "taxonomy": _taxonomy_service,
        "evolution": _evolution_predictor,
        "narrative": _narrative_engine,
        "encyclopedia": _encyclopedia_service
    }


def _get_species_list():
    """获取物种列表"""
    from ..repositories.species_repository import species_repository
    return species_repository.list_species()


def _get_species_by_code(code: str):
    """根据代码获取物种"""
    from ..repositories.species_repository import species_repository
    return species_repository.get_by_code(code)


# ==================== 分类学 API ====================

@router.post("/taxonomy/build", response_model=TaxonomyResponse)
async def build_taxonomy(request: TaxonomyRequest) -> TaxonomyResponse:
    """构建/重建分类树"""
    services = _get_services()
    taxonomy = services.get("taxonomy")
    
    if not taxonomy:
        raise HTTPException(status_code=503, detail="分类学服务不可用")
    
    species_list = _get_species_list()
    if not species_list:
        raise HTTPException(status_code=404, detail="没有可用的物种数据")
    
    try:
        result = taxonomy.build_taxonomy(
            species_list,
            params=request.params
        )
        
        return TaxonomyResponse(
            success=True,
            tree=result.tree,
            stats=result.stats,
            species_assignments=result.species_assignments
        )
    except Exception as e:
        logger.error(f"构建分类树失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/taxonomy/species/{species_code}")
async def get_species_taxonomy(species_code: str) -> dict[str, Any]:
    """获取物种的分类信息"""
    services = _get_services()
    taxonomy = services.get("taxonomy")
    
    if not taxonomy:
        raise HTTPException(status_code=503, detail="分类学服务不可用")
    
    # 需要先构建分类树
    species_list = _get_species_list()
    result = taxonomy.build_taxonomy(species_list)
    
    classification = taxonomy.get_species_classification(species_code, result)
    related = taxonomy.find_related_species(species_code, result)
    
    return {
        "species_code": species_code,
        "classification": classification,
        "related_species": related[:10]
    }


# ==================== 演化预测 API ====================

@router.get("/evolution/pressures", response_model=PressureListResponse)
async def list_evolution_pressures() -> PressureListResponse:
    """列出所有可用的演化压力类型"""
    services = _get_services()
    predictor = services.get("evolution")
    
    if not predictor:
        raise HTTPException(status_code=503, detail="演化预测服务不可用")
    
    pressures = predictor.pressures.list_pressures()
    return PressureListResponse(pressures=pressures)


@router.post("/evolution/predict", response_model=EvolutionPredictionResponse)
async def predict_evolution(request: EvolutionPredictionRequest) -> EvolutionPredictionResponse:
    """预测物种的演化方向"""
    services = _get_services()
    predictor = services.get("evolution")
    
    if not predictor:
        raise HTTPException(status_code=503, detail="演化预测服务不可用")
    
    species = _get_species_by_code(request.species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code} 不存在")
    
    try:
        # 构建物种索引
        species_list = _get_species_list()
        predictor.build_species_index(species_list)
        
        # 预测
        result = predictor.predict_evolution(
            species,
            request.pressure_types,
            request.pressure_strengths
        )
        
        # 可选生成描述
        description = ""
        if request.generate_description:
            description = await predictor.generate_prediction_description(result, species)
        
        return EvolutionPredictionResponse(
            success=True,
            species_code=result.species_code,
            species_name=result.species_name,
            applied_pressures=result.applied_pressures,
            predicted_trait_changes=result.predicted_trait_changes,
            reference_species=[
                {"code": code, "name": name, "similarity": round(sim, 3)}
                for code, name, sim in result.reference_species
            ],
            confidence=round(result.confidence, 3),
            predicted_description=description
        )
    except Exception as e:
        logger.error(f"演化预测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 搜索 API ====================

@router.post("/search", response_model=SearchResponse)
async def semantic_search(request: SearchRequest) -> SearchResponse:
    """语义搜索"""
    services = _get_services()
    encyclopedia = services.get("encyclopedia")
    
    if not encyclopedia:
        raise HTTPException(status_code=503, detail="百科服务不可用")
    
    try:
        # 确保物种索引已构建
        species_list = _get_species_list()
        encyclopedia.build_species_index(species_list)
        
        results = encyclopedia.search(
            request.query,
            search_types=request.search_types,
            top_k=request.top_k
        )
        
        return SearchResponse(
            success=True,
            results=[
                {
                    "type": r.result_type,
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "similarity": round(r.similarity, 3),
                    "metadata": r.metadata
                }
                for r in results
            ],
            query=request.query
        )
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/quick")
async def quick_search(
    q: str = Query(..., description="搜索查询"),
    limit: int = Query(5, description="返回数量")
) -> dict[str, Any]:
    """快速搜索（GET 方式）"""
    request = SearchRequest(query=q, top_k=limit)
    response = await semantic_search(request)
    return response.model_dump()


# ==================== 问答 API ====================

@router.post("/qa", response_model=QAResponse)
async def ask_question(request: QARequest) -> QAResponse:
    """智能问答"""
    services = _get_services()
    encyclopedia = services.get("encyclopedia")
    
    if not encyclopedia:
        raise HTTPException(status_code=503, detail="百科服务不可用")
    
    try:
        # 确保索引已构建
        species_list = _get_species_list()
        encyclopedia.build_species_index(species_list)
        
        result = await encyclopedia.answer_question(request.question)
        
        return QAResponse(
            success=True,
            question=result.question,
            answer=result.answer,
            sources=[
                {
                    "type": s.result_type,
                    "title": s.title,
                    "similarity": round(s.similarity, 3)
                }
                for s in result.sources
            ],
            confidence=round(result.confidence, 3),
            follow_up_questions=result.follow_up_questions
        )
    except Exception as e:
        logger.error(f"问答失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 物种解释 API ====================

@router.post("/explain/species", response_model=SpeciesExplanationResponse)
async def explain_species(request: SpeciesExplanationRequest) -> SpeciesExplanationResponse:
    """解释物种的演化原因"""
    services = _get_services()
    encyclopedia = services.get("encyclopedia")
    
    if not encyclopedia:
        raise HTTPException(status_code=503, detail="百科服务不可用")
    
    species = _get_species_by_code(request.species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code} 不存在")
    
    try:
        result = await encyclopedia.explain_species_evolution(species)
        
        return SpeciesExplanationResponse(
            success=True,
            species_code=result.species_code,
            species_name=result.species_name,
            explanation=result.explanation,
            key_factors=result.key_factors,
            trait_explanations=result.trait_explanations
        )
    except Exception as e:
        logger.error(f"生成解释失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare/species", response_model=SpeciesCompareResponse)
async def compare_species(request: SpeciesCompareRequest) -> SpeciesCompareResponse:
    """对比两个物种"""
    services = _get_services()
    encyclopedia = services.get("encyclopedia")
    
    if not encyclopedia:
        raise HTTPException(status_code=503, detail="百科服务不可用")
    
    species_a = _get_species_by_code(request.species_code_a)
    species_b = _get_species_by_code(request.species_code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code_b} 不存在")
    
    try:
        # 确保索引已构建
        species_list = _get_species_list()
        encyclopedia.build_species_index(species_list)
        
        result = encyclopedia.compare_species(species_a, species_b)
        
        return SpeciesCompareResponse(
            success=True,
            similarity=round(result["similarity"], 3),
            relationship=result["relationship"],
            details=result
        )
    except Exception as e:
        logger.error(f"物种对比失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 提示 API ====================

@router.post("/hints", response_model=HintsResponse)
async def get_species_hints(request: HintsRequest) -> HintsResponse:
    """获取物种的游戏提示"""
    services = _get_services()
    encyclopedia = services.get("encyclopedia")
    
    if not encyclopedia:
        raise HTTPException(status_code=503, detail="百科服务不可用")
    
    species = _get_species_by_code(request.species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code} 不存在")
    
    try:
        hints = encyclopedia.generate_hints(species)
        
        return HintsResponse(
            hints=[
                {
                    "type": h.hint_type,
                    "message": h.message,
                    "priority": h.priority,
                    "related_species": h.related_species,
                    "suggested_actions": h.suggested_actions
                }
                for h in hints
            ]
        )
    except Exception as e:
        logger.error(f"生成提示失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 统计 API ====================

@router.get("/stats", response_model=EmbeddingStatsResponse)
async def get_embedding_stats() -> EmbeddingStatsResponse:
    """获取 Embedding 系统统计信息"""
    try:
        from . import routes
        embedding_service = getattr(routes, 'embedding_service', None)
        
        cache_stats = {}
        if embedding_service:
            cache_stats = embedding_service.get_cache_stats()
        
        services = _get_services()
        encyclopedia = services.get("encyclopedia")
        
        index_stats = {}
        if encyclopedia:
            index_stats = encyclopedia.get_index_stats()
        
        return EmbeddingStatsResponse(
            cache_stats=cache_stats,
            index_stats=index_stats
        )
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 叙事 API ====================

@router.get("/narrative/turn/{turn_index}")
async def get_turn_narrative(turn_index: int) -> dict[str, Any]:
    """获取指定回合的叙事"""
    services = _get_services()
    narrative = services.get("narrative")
    
    if not narrative:
        raise HTTPException(status_code=503, detail="叙事服务不可用")
    
    try:
        result = await narrative.generate_turn_narrative(turn_index)
        
        return {
            "success": True,
            "turn_index": turn_index,
            "narrative": result.narrative,
            "key_events": [
                {"title": e.title, "description": e.description}
                for e in result.key_events
            ],
            "related_species": result.related_species,
            "novelty_info": result.novelty_info
        }
    except Exception as e:
        logger.error(f"生成叙事失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/narrative/eras")
async def get_evolution_eras(
    start_turn: int = Query(0, description="开始回合"),
    end_turn: int | None = Query(None, description="结束回合")
) -> dict[str, Any]:
    """获取演化时代划分"""
    services = _get_services()
    narrative = services.get("narrative")
    
    if not narrative:
        raise HTTPException(status_code=503, detail="叙事服务不可用")
    
    try:
        eras = narrative.identify_eras(start_turn, end_turn)
        
        return {
            "success": True,
            "eras": [
                {
                    "name": era.name,
                    "start_turn": era.start_turn,
                    "end_turn": era.end_turn,
                    "event_count": len(era.key_events),
                    "summary": era.summary
                }
                for era in eras
            ]
        }
    except Exception as e:
        logger.error(f"获取时代失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/narrative/species/{species_code}/biography")
async def get_species_biography(species_code: str) -> dict[str, Any]:
    """获取物种传记"""
    services = _get_services()
    narrative = services.get("narrative")
    
    if not narrative:
        raise HTTPException(status_code=503, detail="叙事服务不可用")
    
    species = _get_species_by_code(species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {species_code} 不存在")
    
    try:
        biography = await narrative.generate_species_biography(species)
        
        return {
            "success": True,
            "species_code": species_code,
            "species_name": species.common_name,
            "biography": biography
        }
    except Exception as e:
        logger.error(f"生成传记失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

