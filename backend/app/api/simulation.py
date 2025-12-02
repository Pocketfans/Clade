"""
Simulation Control Routes - Turn execution and save management

This module handles:
- Turn execution control (run_turns)
- Pressure queue management
- Save creation/save/load/delete
- Auto-save

Uses dependency injection to get service instances, no module-level globals.
"""

from __future__ import annotations

import json
import logging
import time as time_module
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlmodel import select
from starlette.responses import Response

from ..schemas.requests import (
    CreateSaveRequest,
    LoadGameRequest,
    PressureConfig,
    QueueRequest,
    SaveGameRequest,
    TurnCommand,
)
from ..schemas.responses import (
    ActionQueueStatus,
    PressureTemplate,
    SpeciesSnapshot,
    TurnReport,
)
from .dependencies import (
    get_config,
    get_container,
    get_environment_repository,
    get_history_repository,
    get_session,
    get_species_repository,
    require_not_running,
)
from .pressure_templates import PRESSURE_TEMPLATES

if TYPE_CHECKING:
    from ..core.container import ServiceContainer
    from ..core.session import SimulationSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["simulation"])


# ========== 辅助函数 ==========

def _infer_ecological_role(species) -> str:
    """根据物种营养级推断生态角色"""
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


def _perform_autosave(
    turn_index: int,
    session: 'SimulationSessionManager',
    container: 'ServiceContainer'
) -> bool:
    """执行自动保存
    
    Returns:
        是否成功保存
    """
    save_name = session.current_save_name
    if not save_name:
        return False
    
    # 获取配置
    config = container.config_service.get_ui_config()
    if not config.autosave_enabled:
        return False
    
    # 检查是否需要保存（按间隔）
    counter = session.increment_autosave_counter()
    if counter % config.autosave_interval != 0:
        return False
    
    try:
        # 执行保存
        autosave_name = f"{save_name}_autosave_{counter // config.autosave_interval}"
        container.save_manager.save_game(autosave_name, turn_index=turn_index)
        logger.info(f"[自动保存] 成功保存: {autosave_name}")
        
        # 清理旧的自动保存
        _cleanup_old_autosaves(save_name, config.autosave_slots, container)
        return True
    except Exception as e:
        logger.error(f"[自动保存] 保存失败: {e}")
        return False


def _cleanup_old_autosaves(
    base_save_name: str, 
    max_slots: int,
    container: 'ServiceContainer'
) -> None:
    """清理旧的自动保存，只保留最新的N个"""
    try:
        saves = container.save_manager.list_saves()
        autosaves = [s for s in saves if s["name"].startswith(f"{base_save_name}_autosave_")]
        autosaves.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
        
        for old_save in autosaves[max_slots:]:
            container.save_manager.delete_save(old_save["name"])
            logger.debug(f"[自动保存] 删除旧存档: {old_save['name']}")
    except Exception as e:
        logger.warning(f"[自动保存] 清理旧存档失败: {e}")


# ========== 路由端点 ==========

@router.get("/pressures/templates", response_model=list[PressureTemplate])
def list_pressure_templates() -> list[PressureTemplate]:
    """获取所有压力模板"""
    return PRESSURE_TEMPLATES


@router.get("/queue", response_model=ActionQueueStatus)
def get_queue_status(
    session: 'SimulationSessionManager' = Depends(get_session)
) -> ActionQueueStatus:
    """获取压力队列状态"""
    queue = session.pressure_queue
    preview = session.get_queue_preview()
    
    return ActionQueueStatus(
        queued_rounds=len(queue),
        running=session.is_running,
        preview=preview,
    )


@router.post("/queue/add", response_model=ActionQueueStatus)
def add_to_queue(
    request: QueueRequest,
    session: 'SimulationSessionManager' = Depends(get_session)
) -> ActionQueueStatus:
    """添加压力到队列"""
    for _ in range(request.rounds):
        session.add_pressure(request.pressures)
    
    queue = session.pressure_queue
    preview = session.get_queue_preview()
    
    return ActionQueueStatus(
        queued_rounds=len(queue),
        running=session.is_running,
        preview=preview,
    )


@router.post("/queue/clear", response_model=ActionQueueStatus)
def clear_queue(
    session: 'SimulationSessionManager' = Depends(get_session)
) -> ActionQueueStatus:
    """清空压力队列"""
    session.clear_pressure_queue()
    
    return ActionQueueStatus(
        queued_rounds=0,
        running=session.is_running,
        preview=[],
    )


@router.post("/turns/run")
async def run_turns(
    command: TurnCommand,
    background_tasks: BackgroundTasks,
    session: 'SimulationSessionManager' = Depends(get_session),
    container: 'ServiceContainer' = Depends(get_container),
):
    """执行回合推演"""
    from ..services.system.divine_energy import energy_service
    
    start_time = time_module.time()
    
    try:
        logger.info(f"[推演开始] 回合数: {command.rounds}, 压力数: {len(command.pressures)}")
        
        # 检查是否已在运行
        if session.is_running:
            raise HTTPException(status_code=400, detail="模拟已在运行中")
        
        session.set_running(True)
        
        # 清空事件队列中的旧事件
        session.get_pending_events(max_count=9999)
        
        session.push_event("start", f"开始推演 {command.rounds} 回合", "系统")
        
        # 处理压力队列
        engine = container.simulation_engine
        engine.update_watchlist(container.species_repository.get_watchlist())
        
        pressures = list(command.pressures)
        if not pressures:
            queued = session.pop_pressure()
            if queued:
                pressures = queued
        command.pressures = pressures
        
        logger.info(f"[推演执行] 应用压力: {[p.kind for p in pressures]}")
        
        current_turn = engine.turn_counter
        
        # 能量系统检查
        if pressures and energy_service.enabled:
            pressure_dicts = [{"kind": p.kind, "intensity": p.intensity} for p in pressures]
            total_cost = energy_service.get_pressure_cost(pressure_dicts)
            current_energy = energy_service.get_state().current
            
            if current_energy < total_cost:
                session.set_running(False)
                raise HTTPException(
                    status_code=400,
                    detail=f"能量不足！施加压力需要 {total_cost} 能量，当前只有 {current_energy}"
                )
            
            success, msg = energy_service.spend(
                "pressure",
                current_turn,
                details=f"压力: {', '.join([p.kind for p in pressures])}",
                intensity=sum(p.intensity for p in pressures) / len(pressures) if pressures else 0
            )
            if success:
                session.push_event("energy", f"⚡ 消耗 {total_cost} 能量（环境压力）", "系统")
        
        session.push_event(
            "pressure",
            f"应用压力: {', '.join([p.kind for p in pressures]) if pressures else '自然演化'}",
            "环境"
        )
        
        # 设置事件回调
        engine._event_callback = lambda t, m, c="其他", **kw: session.push_event(t, m, c, **kw)
        
        # 配置 AI 超时
        config = container.config_service.get_ui_config()
        if hasattr(engine, 'ai_pressure_service') and engine.ai_pressure_service:
            engine.ai_pressure_service.set_timeout_config(
                species_eval_timeout=config.ai_species_eval_timeout,
                batch_eval_timeout=config.ai_batch_eval_timeout,
                narrative_timeout=config.ai_narrative_timeout,
            )
            engine.ai_pressure_service.set_event_callback(
                lambda t, m, c="其他", **kw: session.push_event(t, m, c, **kw)
            )
        
        # 执行推演
        reports = await engine.run_turns_async(command)
        
        elapsed = time_module.time() - start_time
        logger.info(f"[推演完成] 生成了 {len(reports)} 个报告, 耗时 {elapsed:.1f}秒")
        
        # 能量回复
        final_turn = engine.turn_counter
        regen = energy_service.regenerate(final_turn)
        if regen > 0:
            session.push_event("energy", f"⚡ 神力恢复 +{regen}", "系统")
        
        session.push_event("complete", f"推演完成！生成了 {len(reports)} 个报告", "系统")
        session.push_event("turn_complete", "回合推演完成", "系统")
        
        session.set_running(False)
        
        # 后台执行自动保存
        latest_turn = reports[-1].turn_index if reports else 0
        background_tasks.add_task(
            _perform_autosave, 
            latest_turn, 
            session, 
            container
        )
        
        # 序列化响应
        logger.info("[HTTP响应] 开始序列化响应...")
        try:
            response_data = [r.model_dump(mode="json") for r in reports]
            json_str = json.dumps(response_data, ensure_ascii=False, default=str)
            logger.info(f"[HTTP响应] 序列化完成，数据大小: {len(json_str)} 字节")
            return Response(
                content=json_str,
                media_type="application/json",
                headers={"Content-Length": str(len(json_str.encode('utf-8')))}
            )
        except Exception as e:
            logger.error(f"[HTTP响应] 序列化失败: {e}")
            return JSONResponse(content={"error": str(e), "reports_count": len(reports)})
        
    except HTTPException:
        session.set_running(False)
        raise
    except Exception as e:
        elapsed = time_module.time() - start_time
        logger.error(f"[推演错误] {str(e)}, 耗时 {elapsed:.1f}秒")
        logger.error(traceback.format_exc())
        
        session.push_event("error", f"推演失败: {str(e)}", "错误", force=True)
        session.set_running(False)
        
        raise HTTPException(status_code=500, detail=f"推演执行失败: {str(e)}")


@router.get("/history", response_model=list[TurnReport])
def list_history(
    limit: int = 10,
    history_repo = Depends(get_history_repository)
) -> list[TurnReport]:
    """获取历史回合记录"""
    logs = history_repo.list_turns(limit=limit)
    return [TurnReport.model_validate(log.record_data) for log in logs]


@router.get("/saves/list")
def list_saves(container: 'ServiceContainer' = Depends(get_container)) -> list[dict]:
    """列出所有存档"""
    try:
        saves = container.save_manager.list_saves()
        for save in saves:
            if "created_at" not in save and "timestamp" in save:
                save["created_at"] = save["timestamp"]
        return saves
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"列出存档失败: {str(e)}")


@router.post("/saves/create")
async def create_save(
    request: CreateSaveRequest,
    session: 'SimulationSessionManager' = Depends(get_session),
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """创建新存档"""
    from ..services.system.divine_energy import energy_service
    from ..services.system.divine_progression import divine_progression_service
    from ..services.analytics.achievements import achievement_service
    from ..services.analytics.game_hints import game_hints_service
    from ..services.analytics.embedding_integration import EmbeddingIntegrationService
    from ..services.species.habitat_manager import habitat_manager
    from ..services.species.dispersal_engine import dispersal_engine
    from ..core.database import session_scope
    from ..models.species import Species, PopulationSnapshot
    from ..models.environment import MapTile, MapState, HabitatPopulation
    from ..models.history import TurnLog
    from ..models.genus import Genus
    
    try:
        logger.info(f"[存档API] 创建存档: {request.save_name}, 剧本: {request.scenario}")
        
        engine = container.simulation_engine
        species_repo = container.species_repository
        env_repo = container.environment_repository
        history_repo = container.history_repository
        save_manager = container.save_manager
        map_manager = container.map_manager
        migration_advisor = container.migration_advisor
        species_generator = container.species_generator
        
        # 重置引擎和服务状态
        engine.turn_counter = 0
        energy_service.reset()
        divine_progression_service.reset()
        achievement_service.reset()
        game_hints_service.clear_cooldown()
        
        session.set_save_name(request.save_name)
        session.reset_autosave_counter()
        
        # 清空数据库
        logger.info("[存档API] 清空当前数据...")
        with session_scope() as db_session:
            for sp in db_session.exec(select(Species)).all():
                db_session.delete(sp)
            for tile in db_session.exec(select(MapTile)).all():
                db_session.delete(tile)
            for state in db_session.exec(select(MapState)).all():
                db_session.delete(state)
            for hab in db_session.exec(select(HabitatPopulation)).all():
                db_session.delete(hab)
            for log in db_session.exec(select(TurnLog)).all():
                db_session.delete(log)
            for genus in db_session.exec(select(Genus)).all():
                db_session.delete(genus)
        
        # 清除服务缓存
        migration_advisor.clear_all_caches()
        habitat_manager.clear_all_caches()
        dispersal_engine.clear_caches()
        session.clear_pressure_queue()
        
        if hasattr(engine, 'ai_pressure_service') and engine.ai_pressure_service:
            engine.ai_pressure_service.clear_all_caches()
        engine.speciation.clear_all_caches()
        
        embedding_integration = EmbeddingIntegrationService(container.embedding_service)
        embedding_integration.clear_all_caches()
        
        # 初始化地图
        logger.info(f"[存档API] 初始化地图，种子: {request.map_seed if request.map_seed else '随机'}")
        map_manager.ensure_initialized(map_seed=request.map_seed)
        
        # 初始化物种
        if request.scenario == "空白剧本" and request.species_prompts:
            logger.info(f"[存档API] 空白剧本，生成 {len(request.species_prompts)} 个物种")
            base_codes = ["A", "B", "C", "D", "E", "F", "G", "H"]
            existing_species = species_repo.list_species()
            used_codes = {sp.lineage_code[:1] for sp in existing_species}
            available_codes = [code for code in base_codes if code not in used_codes]
            
            if len(available_codes) < len(request.species_prompts):
                raise HTTPException(
                    status_code=400,
                    detail=f"物种数量过多，最多支持 {len(available_codes)} 个初始物种"
                )
            
            for i, prompt in enumerate(request.species_prompts):
                lineage_code = f"{available_codes[i]}1"
                species = species_generator.generate_from_prompt(prompt, lineage_code)
                species_repo.upsert(species)
        else:
            from ..core.seed import seed_defaults
            seed_defaults()
        
        # 初始化栖息地分布
        all_species = species_repo.list_species()
        if all_species:
            map_manager.snapshot_habitats(all_species, turn_index=0, force_recalculate=True)
        
        # 创建初始人口快照
        MAX_SAFE_POPULATION = 9_007_199_254_740_991
        if all_species:
            snapshots = []
            for species in all_species:
                raw_pop = species.morphology_stats.get("population", 0) or 0
                population = max(0, min(int(raw_pop), MAX_SAFE_POPULATION))
                if population > 0:
                    snapshots.append(PopulationSnapshot(
                        species_id=species.id or 0,
                        turn_index=0,
                        region_id=0,
                        count=population,
                        death_count=0,
                        survivor_count=population,
                        population_share=1.0 / len(all_species),
                        ecological_pressure={}
                    ))
            if snapshots:
                species_repo.add_population_snapshots(snapshots)
        
        # 创建初始回合报告
        if all_species:
            def safe_population(sp):
                raw = sp.morphology_stats.get("population", 0) or 0
                return max(0, min(int(raw), MAX_SAFE_POPULATION))
            
            total_population = sum(safe_population(sp) for sp in all_species)
            initial_species = []
            
            for species in all_species:
                population = safe_population(species)
                population_share = (population / total_population) if total_population > 0 else 0.0
                ecological_role = _infer_ecological_role(species)
                
                initial_species.append(SpeciesSnapshot(
                    lineage_code=species.lineage_code,
                    latin_name=species.latin_name,
                    common_name=species.common_name,
                    population=population,
                    population_share=population_share,
                    deaths=0,
                    death_rate=0.0,
                    niche_overlap=0.0,
                    tier="T1.0",
                    notes=[f"初始物种，投放到{request.scenario}"],
                    status=species.status,
                    ecological_role=ecological_role,
                    total_tiles=0,
                    healthy_tiles=0,
                    warning_tiles=0,
                    critical_tiles=0,
                    best_tile_rate=0.0,
                    worst_tile_rate=0.0,
                    has_refuge=True,
                    distribution_status="初始",
                ))
            
            map_state = env_repo.get_state()
            
            initial_report = TurnReport(
                turn_index=0,
                pressures_summary="初始状态，无环境压力",
                narrative=f"世界诞生！{len(all_species)}个物种在{request.scenario}开始了它们的演化之旅。",
                species=initial_species,
                branching_events=[],
                background_summary=[],
                reemergence_events=[],
                major_events=[],
                map_changes=[],
                migration_events=[],
                sea_level=map_state.sea_level if map_state else 0.0,
                global_temperature=map_state.global_avg_temperature if map_state else 15.0,
                tectonic_stage=map_state.stage_name if map_state else "稳定期"
            )
            
            history_repo.log_turn(
                TurnLog(
                    turn_index=0,
                    pressures_summary=initial_report.pressures_summary,
                    narrative=initial_report.narrative,
                    record_data=initial_report.model_dump(mode="json")
                )
            )
        
        # 创建存档元数据
        metadata = save_manager.create_save(request.save_name, request.scenario)
        
        # 切换向量索引目录
        save_dir = save_manager.get_save_dir(request.save_name)
        if save_dir:
            embedding_integration.switch_to_save_context(save_dir)
        
        # 保存初始状态
        save_manager.save_game(request.save_name, turn_index=0)
        
        species_count = len(species_repo.list_species())
        metadata["species_count"] = species_count
        
        logger.info(f"[存档API] 存档创建完成，物种数: {species_count}")
        return metadata
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"创建存档失败: {str(e)}")


@router.post("/saves/save")
async def save_game(
    request: SaveGameRequest,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """保存当前游戏状态"""
    try:
        history_repo = container.history_repository
        logs = history_repo.list_turns(limit=1)
        turn_index = logs[0].turn_index if logs else 0
        
        container.save_manager.save_game(request.save_name, turn_index=turn_index)
        
        return {
            "success": True,
            "save_name": request.save_name,
            "turn_index": turn_index,
        }
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存游戏失败: {str(e)}")


@router.post("/saves/load")
async def load_game(
    request: LoadGameRequest,
    session: 'SimulationSessionManager' = Depends(get_session),
    container: 'ServiceContainer' = Depends(get_container),
    _: None = Depends(require_not_running),
) -> dict:
    """加载游戏存档"""
    from ..services.system.divine_energy import energy_service
    from ..services.system.divine_progression import divine_progression_service
    from ..services.analytics.achievements import achievement_service
    from ..services.analytics.game_hints import game_hints_service
    from ..services.analytics.embedding_integration import EmbeddingIntegrationService
    from ..services.species.habitat_manager import habitat_manager
    from ..services.species.dispersal_engine import dispersal_engine
    
    try:
        logger.info(f"[存档API] 加载存档: {request.save_name}")
        
        save_manager = container.save_manager
        engine = container.simulation_engine
        map_manager = container.map_manager
        migration_advisor = container.migration_advisor
        
        # 重置服务状态
        energy_service.reset()
        divine_progression_service.reset()
        achievement_service.reset()
        game_hints_service.clear_cooldown()
        session.clear_pressure_queue()
        
        # 清除缓存
        migration_advisor.clear_all_caches()
        habitat_manager.clear_all_caches()
        dispersal_engine.clear_caches()
        
        if hasattr(engine, 'ai_pressure_service') and engine.ai_pressure_service:
            engine.ai_pressure_service.clear_all_caches()
        engine.speciation.clear_all_caches()
        
        # 加载存档
        result = save_manager.load_game(request.save_name)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "加载失败"))
        
        # 恢复回合计数器
        engine.turn_counter = result.get("turn_index", 0)
        
        # 设置会话状态
        session.set_save_name(request.save_name)
        session.reset_autosave_counter()
        
        # 重新初始化地图状态
        env_repo = container.environment_repository
        map_state = env_repo.get_state()
        if map_state:
            map_manager.load_state(map_state)
        
        # 切换向量索引
        save_dir = save_manager.get_save_dir(request.save_name)
        if save_dir:
            embedding_integration = EmbeddingIntegrationService(container.embedding_service)
            embedding_integration.switch_to_save_context(save_dir)
        
        # 恢复能量状态
        if "energy" in result:
            energy_service.load_state(result["energy"])
        if "divine_progression" in result:
            divine_progression_service.load_state(result["divine_progression"])
        
        logger.info(f"[存档API] 存档加载完成: turn={engine.turn_counter}")
        
        return {
            "success": True,
            "save_name": request.save_name,
            "turn_index": engine.turn_counter,
            "species_count": result.get("species_count", 0),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"加载存档失败: {str(e)}")


@router.delete("/saves/{save_name}")
def delete_save(
    save_name: str,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """删除存档"""
    try:
        container.save_manager.delete_save(save_name)
        return {"success": True, "deleted": save_name}
    except Exception as e:
        logger.error(f"[存档API错误] {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除存档失败: {str(e)}")

