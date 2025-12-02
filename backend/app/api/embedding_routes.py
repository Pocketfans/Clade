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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .dependencies import get_container

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

# 服务实例缓存（按 container 实例缓存，避免重复创建）
_services_cache: dict[int, dict] = {}


def _get_services_from_container(container):
    """从容器获取服务实例（延迟初始化并缓存）
    
    Args:
        container: ServiceContainer 实例
        
    Returns:
        服务字典
    """
    # 使用 container id 作为缓存键
    cache_key = id(container)
    
    if cache_key in _services_cache:
        return _services_cache[cache_key]
    
    try:
        embedding_service = container.embedding_service
        model_router = container.model_router
        
        if embedding_service is None:
            logger.warning("Embedding 服务未初始化")
            return {}
        
        from ..services.analytics.taxonomy import TaxonomyService
        from ..services.analytics.evolution_predictor import EvolutionPredictor, PressureVectorLibrary
        from ..services.analytics.narrative_engine import NarrativeEngine
        from ..services.analytics.encyclopedia import EncyclopediaService
        
        taxonomy_service = TaxonomyService(embedding_service, model_router)
        
        pressure_library = PressureVectorLibrary(embedding_service)
        evolution_predictor = EvolutionPredictor(embedding_service, pressure_library, model_router)
        
        narrative_engine = NarrativeEngine(embedding_service, model_router)
        encyclopedia_service = EncyclopediaService(embedding_service, model_router)
        
        services = {
            "taxonomy": taxonomy_service,
            "evolution": evolution_predictor,
            "narrative": narrative_engine,
            "encyclopedia": encyclopedia_service
        }
        
        _services_cache[cache_key] = services
        logger.info("Embedding 扩展服务初始化完成")
        return services
        
    except Exception as e:
        logger.error(f"初始化 Embedding 服务失败: {e}")
        import traceback
        traceback.print_exc()
        return {}


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
async def build_taxonomy(request: TaxonomyRequest, container = Depends(get_container)) -> TaxonomyResponse:
    """构建/重建分类树"""
    services = _get_services_from_container(container)
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
async def get_species_taxonomy(species_code: str, container = Depends(get_container)) -> dict[str, Any]:
    """获取物种的分类信息"""
    services = _get_services_from_container(container)
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
async def list_evolution_pressures(container = Depends(get_container)) -> PressureListResponse:
    """列出所有可用的演化压力类型"""
    services = _get_services_from_container(container)
    predictor = services.get("evolution")
    
    if not predictor:
        raise HTTPException(status_code=503, detail="演化预测服务不可用")
    
    pressures = predictor.pressures.list_pressures()
    return PressureListResponse(pressures=pressures)


@router.post("/evolution/predict", response_model=EvolutionPredictionResponse)
async def predict_evolution(request: EvolutionPredictionRequest, container = Depends(get_container)) -> EvolutionPredictionResponse:
    """预测物种的演化方向"""
    services = _get_services_from_container(container)
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
async def semantic_search(request: SearchRequest, container = Depends(get_container)) -> SearchResponse:
    """语义搜索"""
    services = _get_services_from_container(container)
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
async def ask_question(request: QARequest, container = Depends(get_container)) -> QAResponse:
    """智能问答"""
    services = _get_services_from_container(container)
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
async def explain_species(request: SpeciesExplanationRequest, container = Depends(get_container)) -> SpeciesExplanationResponse:
    """解释物种的演化原因"""
    services = _get_services_from_container(container)
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
async def compare_species(request: SpeciesCompareRequest, container = Depends(get_container)) -> SpeciesCompareResponse:
    """对比两个物种"""
    services = _get_services_from_container(container)
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
async def get_species_hints(request: HintsRequest, container = Depends(get_container)) -> HintsResponse:
    """获取物种的游戏提示"""
    services = _get_services_from_container(container)
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
async def get_embedding_stats(container = Depends(get_container)) -> EmbeddingStatsResponse:
    """获取 Embedding 系统统计信息"""
    try:
        embedding_service = container.embedding_service
        
        cache_stats = {}
        if embedding_service:
            cache_stats = embedding_service.get_cache_stats()
        
        services = _get_services_from_container(container)
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
async def get_turn_narrative(turn_index: int, container = Depends(get_container)) -> dict[str, Any]:
    """获取指定回合的叙事"""
    services = _get_services_from_container(container)
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
    end_turn: int | None = Query(None, description="结束回合"),
    container = Depends(get_container)
) -> dict[str, Any]:
    """获取演化时代划分"""
    services = _get_services_from_container(container)
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
async def get_species_biography(species_code: str, container = Depends(get_container)) -> dict[str, Any]:
    """获取物种传记"""
    services = _get_services_from_container(container)
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


# ==================== 插件 API ====================

_plugin_manager = None

def _get_plugin_manager():
    """获取插件管理器（延迟初始化）"""
    global _plugin_manager
    
    if _plugin_manager is not None:
        return _plugin_manager
    
    try:
        from . import routes
        from pathlib import Path
        
        embedding_service = getattr(routes, 'embedding_service', None)
        
        if embedding_service is None:
            logger.warning("[PluginAPI] EmbeddingService 不可用，插件功能已禁用")
            return None
        
        from ..services.embedding_plugins import (
            EmbeddingPluginManager,
            load_all_plugins
        )
        
        load_all_plugins()
        
        # 获取当前模式（从 simulation_engine）
        simulation_engine = getattr(routes, 'simulation_engine', None)
        mode = "full"  # 默认值
        if simulation_engine:
            mode = getattr(simulation_engine, '_pipeline_mode', None) or \
                   getattr(simulation_engine, '_stage_mode', None) or 'full'
        
        # 获取配置文件路径
        config_path = Path(__file__).parent.parent / "simulation" / "stage_config.yaml"
        
        _plugin_manager = EmbeddingPluginManager(
            embedding_service, 
            mode=mode,
            config_path=config_path
        )
        count = _plugin_manager.load_plugins()
        
        if count == 0:
            logger.info(f"[PluginAPI] 模式 {mode} 无启用的插件")
        else:
            logger.info(f"[PluginAPI] 模式 {mode} 已加载 {count} 个插件")
        
        return _plugin_manager
    except Exception as e:
        logger.error(f"[PluginAPI] 初始化插件管理器失败: {e}")
        return None


def _check_plugin_available(plugin_name: str):
    """检查插件是否可用，返回错误响应或 None"""
    manager = _get_plugin_manager()
    if not manager:
        raise HTTPException(
            status_code=503, 
            detail={
                "error": "插件管理器不可用",
                "reason": "EmbeddingService 未初始化或配置错误",
                "suggestion": "请确保 embedding 功能已启用"
            }
        )
    
    plugin = manager.get_plugin(plugin_name)
    if not plugin:
        raise HTTPException(
            status_code=503,
            detail={
                "error": f"插件 {plugin_name} 不可用",
                "reason": "该插件未启用或加载失败",
                "enabled_plugins": manager.list_plugins()
            }
        )
    
    return plugin


def _check_index_not_empty(plugin, plugin_name: str):
    """检查插件索引是否为空"""
    store = plugin._get_vector_store(create=False)
    if not store or store.size == 0:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "索引为空",
                "plugin": plugin_name,
                "reason": "索引尚未构建或无数据",
                "suggestion": "请等待至少一个回合结束后重试",
                "last_update_turn": plugin._last_update_turn
            }
        )


@router.get("/plugins/status")
async def get_plugins_status() -> dict[str, Any]:
    """获取所有插件状态"""
    manager = _get_plugin_manager()
    if not manager:
        return {
            "success": False, 
            "error": "插件管理器不可用",
            "reason": "EmbeddingService 未初始化",
            "plugins": []
        }
    
    return {
        "success": True,
        "plugins": manager.list_plugins(),
        "stats": manager.get_all_stats(),
    }


# ==================== 行为策略插件 API ====================

@router.get("/behavior/profile/{species_code}")
async def get_behavior_profile(species_code: str) -> dict[str, Any]:
    """获取物种行为档案"""
    plugin = _check_plugin_available("behavior_strategy")
    
    species = _get_species_by_code(species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {species_code} 不存在")
    
    try:
        profile = plugin.infer_behavior_profile(species)
        stats = plugin.get_stats()
        
        return {
            "success": True,
            "species_code": species_code,
            "profile": {
                "predation_strategy": profile.predation_strategy,
                "defense_strategy": profile.defense_strategy,
                "reproduction_strategy": profile.reproduction_strategy,
                "activity_pattern": profile.activity_pattern,
                "social_behavior": profile.social_behavior,
            },
            "text": profile.to_text(),
            "degraded_mode": stats.get("degraded_mode", False),
        }
    except Exception as e:
        logger.error(f"获取行为档案失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/behavior/similar/{species_code}")
async def get_similar_behaviors(species_code: str, top_k: int = 5) -> dict[str, Any]:
    """查找行为相似的物种"""
    plugin = _check_plugin_available("behavior_strategy")
    _check_index_not_empty(plugin, "behavior_strategy")
    
    species = _get_species_by_code(species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {species_code} 不存在")
    
    try:
        similar = plugin.find_similar_species(species, top_k=top_k)
        return {"success": True, "species_code": species_code, "similar": similar}
    except Exception as e:
        logger.error(f"查找相似物种失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BehaviorConflictRequest(BaseModel):
    """行为冲突检测请求"""
    species_code_a: str
    species_code_b: str


@router.post("/behavior/conflicts")
async def check_behavior_conflicts(request: BehaviorConflictRequest) -> dict[str, Any]:
    """检测两个物种的行为冲突"""
    plugin = _check_plugin_available("behavior_strategy")
    
    species_a = _get_species_by_code(request.species_code_a)
    species_b = _get_species_by_code(request.species_code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code_b} 不存在")
    
    try:
        conflicts = plugin.find_behavior_conflicts(species_a, species_b)
        return {
            "success": True,
            "species_a": request.species_code_a,
            "species_b": request.species_code_b,
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
        }
    except Exception as e:
        logger.error(f"检测行为冲突失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/behavior/summary")
async def get_behavior_summary() -> dict[str, Any]:
    """获取行为分布摘要"""
    plugin = _check_plugin_available("behavior_strategy")
    
    try:
        summary = plugin.get_behavior_summary()
        stats = plugin.get_stats()
        return {
            "success": True, 
            "degraded_mode": stats.get("degraded_mode", False),
            **summary
        }
    except Exception as e:
        logger.error(f"获取行为摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 生态网络插件 API ====================

@router.get("/food-web/keystone")
async def get_keystone_species(top_k: int = 5) -> dict[str, Any]:
    """获取关键物种"""
    plugin = _check_plugin_available("food_web")
    
    try:
        keystones = plugin.find_keystone_species(top_k=top_k)
        stats = plugin.get_stats()
        return {
            "success": True, 
            "keystones": keystones,
            "index_size": stats.get("index_size", 0),
            "degraded_mode": stats.get("degraded_mode", False),
        }
    except Exception as e:
        logger.error(f"获取关键物种失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/food-web/stability")
async def get_ecosystem_stability() -> dict[str, Any]:
    """获取生态稳定性指标"""
    plugin = _check_plugin_available("food_web")
    
    try:
        stability = plugin.calculate_ecosystem_stability()
        return {"success": True, **stability}
    except Exception as e:
        logger.error(f"获取稳定性失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ReplacementRequest(BaseModel):
    """补位物种请求"""
    extinct_code: str
    top_k: int = 3


@router.post("/food-web/replacement")
async def find_replacement_candidates(request: ReplacementRequest) -> dict[str, Any]:
    """为灭绝物种寻找补位候选"""
    plugin = _check_plugin_available("food_web")
    _check_index_not_empty(plugin, "food_web")
    
    try:
        candidates = plugin.find_replacement_candidates(request.extinct_code, request.top_k)
        return {
            "success": True,
            "extinct_code": request.extinct_code,
            "candidates": candidates,
        }
    except Exception as e:
        logger.error(f"查找补位候选失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/food-web/summary")
async def get_food_web_summary() -> dict[str, Any]:
    """获取食物网摘要"""
    plugin = _check_plugin_available("food_web")
    
    try:
        summary = plugin.get_network_summary()
        stats = plugin.get_stats()
        return {
            "success": True, 
            "degraded_mode": stats.get("degraded_mode", False),
            **summary
        }
    except Exception as e:
        logger.error(f"获取食物网摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 地块向量插件 API ====================

@router.get("/tiles/hotspots")
async def get_ecological_hotspots(top_k: int = 10) -> dict[str, Any]:
    """获取生态热点区域"""
    plugin = _check_plugin_available("tile_biome")
    
    try:
        hotspots = plugin.find_ecological_hotspots(top_k=top_k)
        stats = plugin.get_stats()
        return {
            "success": True, 
            "hotspots": hotspots,
            "index_size": stats.get("index_size", 0),
        }
    except Exception as e:
        logger.error(f"获取热点区域失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SpeciesTileMatchRequest(BaseModel):
    """物种地块匹配请求"""
    species_code: str
    top_k: int = 5


@router.post("/tiles/species-match")
async def match_species_to_tiles(request: SpeciesTileMatchRequest) -> dict[str, Any]:
    """为物种找最佳地块"""
    plugin = _check_plugin_available("tile_biome")
    
    species = _get_species_by_code(request.species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code} 不存在")
    
    try:
        matches = plugin.find_best_tiles_for_species(species, top_k=request.top_k)
        return {
            "success": True,
            "species_code": request.species_code,
            "matches": matches,
        }
    except Exception as e:
        logger.error(f"匹配地块失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tiles/summary")
async def get_tile_summary() -> dict[str, Any]:
    """获取地块摘要"""
    plugin = _check_plugin_available("tile_biome")
    
    try:
        summary = plugin.get_tile_summary()
        if not summary:
            return {
                "success": True, 
                "message": "地块索引为空，请等待回合结束后重试",
                "total_tiles": 0
            }
        return {"success": True, **summary}
    except Exception as e:
        logger.error(f"获取地块摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 演化空间插件 API ====================

@router.get("/evolution/trends")
async def get_evolution_trends(top_k: int = 5) -> dict[str, Any]:
    """获取演化趋势"""
    plugin = _check_plugin_available("evolution_space")
    
    try:
        trends = plugin.get_current_trends(top_k=top_k)
        stats = plugin.get_stats()
        return {
            "success": True, 
            "trends": trends,
            "total_events": stats.get("index_size", 0),
        }
    except Exception as e:
        logger.error(f"获取演化趋势失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evolution/convergent")
async def detect_convergent_evolution(min_species: int = 3) -> dict[str, Any]:
    """检测收敛演化"""
    plugin = _check_plugin_available("evolution_space")
    
    try:
        convergences = plugin.detect_convergent_evolution(min_species=min_species)
        return {"success": True, "convergent_evolutions": convergences}
    except Exception as e:
        logger.error(f"检测收敛演化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evolution/trajectory/{species_code}")
async def predict_species_trajectory(species_code: str) -> dict[str, Any]:
    """预测物种演化轨迹"""
    plugin = _check_plugin_available("evolution_space")
    
    species = _get_species_by_code(species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {species_code} 不存在")
    
    try:
        predictions = plugin.predict_species_trajectory(species)
        return {
            "success": True,
            "species_code": species_code,
            "predictions": predictions if predictions else [],
            "message": "无历史演化数据" if not predictions else None,
        }
    except Exception as e:
        logger.error(f"预测演化轨迹失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/evolution/summary")
async def get_evolution_summary() -> dict[str, Any]:
    """获取演化空间摘要"""
    plugin = _check_plugin_available("evolution_space")
    
    try:
        summary = plugin.get_evolution_summary()
        return {"success": True, **summary}
    except Exception as e:
        logger.error(f"获取演化摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 血统向量插件 API ====================

@router.get("/ancestry/{species_code}")
async def get_ancestry_info(species_code: str) -> dict[str, Any]:
    """获取物种血统信息"""
    plugin = _check_plugin_available("ancestry")
    
    species = _get_species_by_code(species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {species_code} 不存在")
    
    try:
        ancestry = plugin._ancestry_cache.get(species_code)
        if not ancestry:
            return {
                "success": True,
                "species_code": species_code,
                "ancestry": None,
                "message": "血统信息尚未计算，请等待回合结束后重试",
            }
        
        return {
            "success": True,
            "species_code": species_code,
            "ancestry": {
                "generation": ancestry.generation,
                "ancestor_codes": ancestry.ancestor_codes,
                "has_trait_history": len(ancestry.trait_history) > 0,
            },
        }
    except Exception as e:
        logger.error(f"获取血统信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ancestry/inertia/{species_code}/{trait}")
async def get_genetic_inertia(species_code: str, trait: str) -> dict[str, Any]:
    """获取遗传惯性"""
    plugin = _check_plugin_available("ancestry")
    
    species = _get_species_by_code(species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {species_code} 不存在")
    
    try:
        inertia = plugin.predict_genetic_inertia(species, trait)
        return {
            "success": True,
            "species_code": species_code,
            "trait": trait,
            **inertia,
        }
    except Exception as e:
        logger.error(f"获取遗传惯性失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ancestry/speciation/{species_code}")
async def should_species_speciate(species_code: str, threshold: float = 0.6) -> dict[str, Any]:
    """判断是否应该分化"""
    plugin = _check_plugin_available("ancestry")
    
    species = _get_species_by_code(species_code)
    if not species:
        raise HTTPException(status_code=404, detail=f"物种 {species_code} 不存在")
    
    try:
        result = plugin.should_speciate(species, threshold=threshold)
        return {"success": True, "species_code": species_code, **result}
    except Exception as e:
        logger.error(f"判断分化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class DivergenceRequest(BaseModel):
    """分化程度请求"""
    species_code_a: str
    species_code_b: str


@router.post("/ancestry/divergence")
async def calculate_divergence(request: DivergenceRequest) -> dict[str, Any]:
    """计算两个物种的分化程度"""
    plugin = _check_plugin_available("ancestry")
    
    species_a = _get_species_by_code(request.species_code_a)
    species_b = _get_species_by_code(request.species_code_b)
    
    if not species_a:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code_a} 不存在")
    if not species_b:
        raise HTTPException(status_code=404, detail=f"物种 {request.species_code_b} 不存在")
    
    try:
        result = plugin.calculate_divergence_score(species_a, species_b)
        return {
            "success": True,
            "species_a": request.species_code_a,
            "species_b": request.species_code_b,
            **result,
        }
    except Exception as e:
        logger.error(f"计算分化程度失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ancestry/summary")
async def get_ancestry_summary() -> dict[str, Any]:
    """获取血统摘要"""
    plugin = _check_plugin_available("ancestry")
    
    try:
        summary = plugin.get_ancestry_summary()
        if not summary:
            return {
                "success": True,
                "message": "血统索引为空，请等待回合结束后重试",
                "total_species": 0
            }
        return {"success": True, **summary}
    except Exception as e:
        logger.error(f"获取血统摘要失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))