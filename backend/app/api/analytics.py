"""
分析与导出路由 - 报表、导出、系统诊断

此模块负责：
- 导出功能
- 系统日志
- AI 诊断
- 游戏状态
- 任务控制
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from ..schemas.responses import ExportRecord
from .dependencies import get_container, get_history_repository, get_session

if TYPE_CHECKING:
    from ..core.container import ServiceContainer
    from ..core.session import SimulationSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["analytics"])


# ========== 导出 ==========

@router.get("/exports", response_model=list[ExportRecord])
def list_exports(
    container: 'ServiceContainer' = Depends(get_container),
) -> list[ExportRecord]:
    """列出所有导出记录"""
    records = container.export_service.list_records()
    return [ExportRecord(**r) for r in records]


# ========== 系统日志 ==========

@router.get("/system/logs")
def get_system_logs(
    lines: int = 200,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取系统日志"""
    log_path = Path(container.settings.log_dir) / "simulation.log"
    
    if not log_path.exists():
        return {"logs": [], "path": str(log_path)}
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]
        return {"logs": recent_lines, "path": str(log_path)}
    except Exception as e:
        logger.error(f"[日志读取错误] {e}")
        return {"logs": [], "error": str(e)}


# ========== AI 诊断 ==========

@router.get("/system/ai-diagnostics", tags=["system"])
def get_ai_diagnostics(
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取 AI 模型调用诊断信息"""
    model_router = container.model_router
    
    stats = model_router.get_call_stats()
    
    return {
        "enabled": True,
        "provider": model_router.api_base_url,
        "total_calls": stats.get("total_calls", 0),
        "successful_calls": stats.get("successful_calls", 0),
        "failed_calls": stats.get("failed_calls", 0),
        "average_latency_ms": stats.get("average_latency_ms", 0),
        "capability_stats": stats.get("by_capability", {}),
        "recent_errors": stats.get("recent_errors", []),
    }


@router.post("/system/ai-diagnostics/reset", tags=["system"])
def reset_ai_diagnostics(
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """重置 AI 诊断统计"""
    model_router = container.model_router
    model_router.reset_stats()
    
    return {"success": True, "message": "AI 诊断统计已重置"}


# ========== 游戏状态 ==========

@router.get("/game/state", tags=["game"])
def get_game_state(
    container: 'ServiceContainer' = Depends(get_container),
    session: 'SimulationSessionManager' = Depends(get_session),
) -> dict:
    """获取当前游戏状态"""
    engine = container.simulation_engine
    species_repo = container.species_repository
    env_repo = container.environment_repository
    
    all_species = species_repo.list_species()
    alive_species = [sp for sp in all_species if sp.status == "alive"]
    
    map_state = env_repo.get_state()
    
    return {
        "turn_index": engine.turn_counter,
        "running": session.is_running,
        "current_save": session.current_save_name,
        "species_count": {
            "total": len(all_species),
            "alive": len(alive_species),
            "extinct": len(all_species) - len(alive_species),
        },
        "total_population": sum(
            sp.morphology_stats.get("population", 0) or 0
            for sp in alive_species
        ),
        "environment": {
            "sea_level": map_state.sea_level if map_state else 0.0,
            "global_temperature": map_state.global_avg_temperature if map_state else 15.0,
            "tectonic_stage": map_state.stage_name if map_state else "稳定期",
        },
    }


# ========== 任务控制 ==========

@router.post("/tasks/abort", tags=["system"])
async def abort_current_tasks(
    session: 'SimulationSessionManager' = Depends(get_session),
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """重置 AI 连接，解除卡住状态"""
    model_router = container.model_router
    
    session.request_abort()
    
    # 重置 HTTP 客户端
    if hasattr(model_router, 'reset_client'):
        model_router.reset_client()
    
    session.clear_abort()
    
    return {
        "success": True,
        "message": "已重置 AI 连接",
    }


@router.post("/tasks/skip-ai-step", tags=["system"])
async def skip_current_ai_step(
    session: 'SimulationSessionManager' = Depends(get_session),
) -> dict:
    """跳过当前 AI 步骤，使用 fallback 规则"""
    current_step = session.current_ai_step
    
    session.request_skip_ai()
    
    return {
        "success": True,
        "skipped_step": current_step,
        "message": f"已请求跳过当前 AI 步骤: {current_step}",
    }


@router.get("/tasks/diagnostics", tags=["system"])
def get_task_diagnostics(
    session: 'SimulationSessionManager' = Depends(get_session),
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取当前 AI 任务的诊断信息"""
    model_router = container.model_router
    
    return {
        "running": session.is_running,
        "current_step": session.current_ai_step,
        "abort_requested": session.abort_requested,
        "skip_requested": session.skip_ai_step,
        "concurrency_stats": model_router.get_concurrency_stats() if hasattr(model_router, 'get_concurrency_stats') else {},
    }


# ========== 事件流 ==========

@router.get("/events/stream")
async def stream_simulation_events(
    session: 'SimulationSessionManager' = Depends(get_session),
):
    """Server-Sent Events 端点，实时推送演化事件"""
    import asyncio
    from fastapi.responses import StreamingResponse
    
    async def event_generator():
        while True:
            events = session.get_pending_events(max_count=10)
            
            if events:
                for event in events:
                    import json
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            else:
                yield ": keepalive\n\n"
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ========== 配置 ==========

@router.get("/config/ui")
def get_ui_config(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取 UI 配置"""
    return container.config_service.get_ui_config()


@router.post("/config/ui")
def update_ui_config(
    config: dict,
    container: 'ServiceContainer' = Depends(get_container),
):
    """更新 UI 配置"""
    from ..models.config import UIConfig
    
    env_repo = container.environment_repository
    config_service = container.config_service
    
    ui_config = UIConfig(**config)
    
    # 保存配置
    saved = env_repo.save_ui_config(
        Path(container.settings.ui_config_path),
        ui_config
    )
    
    # 使缓存失效
    config_service.invalidate_cache()
    
    return saved


@router.post("/config/test-api")
def test_api_connection(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """测试 API 连接是否有效"""
    import httpx
    
    base_url = request.get("base_url", "")
    api_key = request.get("api_key", "")
    provider_type = request.get("provider_type", "openai")
    
    if not base_url or not api_key:
        return {"success": False, "error": "缺少必要参数"}
    
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        
        if provider_type == "anthropic":
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
            test_url = f"{base_url.rstrip('/')}/messages"
        else:
            test_url = f"{base_url.rstrip('/')}/models"
        
        with httpx.Client(timeout=10) as client:
            response = client.get(test_url, headers=headers)
        
        if response.status_code == 200:
            return {"success": True, "message": "连接成功"}
        else:
            return {
                "success": False,
                "error": f"API 返回状态码: {response.status_code}",
                "detail": response.text[:500] if response.text else "",
            }
            
    except httpx.TimeoutException:
        return {"success": False, "error": "连接超时"}
    except httpx.ConnectError as e:
        return {"success": False, "error": f"连接失败: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/config/fetch-models")
def fetch_models(
    request: dict,
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取服务商的可用模型列表"""
    import httpx
    
    base_url = request.get("base_url", "")
    api_key = request.get("api_key", "")
    provider_type = request.get("provider_type", "openai")
    
    if not base_url or not api_key:
        return {"success": False, "error": "缺少必要参数", "models": []}
    
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        
        if provider_type == "anthropic":
            # Anthropic 没有 models API，返回硬编码列表
            return {
                "success": True,
                "models": [
                    {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus"},
                    {"id": "claude-3-sonnet-20240229", "name": "Claude 3 Sonnet"},
                    {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku"},
                    {"id": "claude-3-5-sonnet-20240620", "name": "Claude 3.5 Sonnet"},
                ],
            }
        
        models_url = f"{base_url.rstrip('/')}/models"
        
        with httpx.Client(timeout=15) as client:
            response = client.get(models_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            models = data.get("data", [])
            
            return {
                "success": True,
                "models": [
                    {"id": m.get("id", ""), "name": m.get("id", "")}
                    for m in models
                    if m.get("id")
                ],
            }
        else:
            return {
                "success": False,
                "error": f"获取模型列表失败: {response.status_code}",
                "models": [],
            }
            
    except Exception as e:
        return {"success": False, "error": str(e), "models": []}


# ========== 地图 ==========

@router.get("/map")
def get_map_overview(
    limit_tiles: int = 0,
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取地图概览"""
    from ..schemas.responses import MapOverview, MapTileInfo, HabitatEntry
    from ..services.species.habitat_manager import habitat_manager
    
    env_repo = container.environment_repository
    map_manager = container.map_manager
    species_repo = container.species_repository
    
    # 确保地图已初始化
    map_manager.ensure_initialized()
    
    # 获取地图全局状态
    map_state = env_repo.get_state()
    sea_level = map_state.sea_level if map_state else 0.0
    
    # 获取地块列表
    db_tiles = env_repo.list_tiles(limit=limit_tiles if limit_tiles > 0 else None)
    
    if not db_tiles:
        raise HTTPException(status_code=404, detail="地图未初始化")
    
    # 转换为 MapTileInfo
    tiles = []
    for t in db_tiles:
        # 计算地形类型
        relative_elev = t.elevation - sea_level
        if relative_elev < -3000:
            terrain_type = "海沟"
        elif relative_elev < -200:
            terrain_type = "深海"
        elif relative_elev < 0:
            terrain_type = "浅海"
        elif relative_elev < 50:
            terrain_type = "海岸" if t.biome in ("浅海", "海岸") else "平原"
        elif relative_elev < 500:
            terrain_type = "平原"
        elif relative_elev < 1500:
            terrain_type = "丘陵"
        elif relative_elev < 3000:
            terrain_type = "山地"
        elif relative_elev < 5000:
            terrain_type = "高山"
        else:
            terrain_type = "极高山"
        
        # 计算气候带
        if t.temperature > 20:
            climate_zone = "热带"
        elif t.temperature > 10:
            climate_zone = "亚热带"
        elif t.temperature > 0:
            climate_zone = "温带"
        elif t.temperature > -10:
            climate_zone = "寒带"
        else:
            climate_zone = "极地"
        
        tiles.append(MapTileInfo(
            id=t.id,
            x=t.x,
            y=t.y,
            q=t.q,
            r=t.r,
            biome=t.biome,
            cover=t.cover,
            temperature=t.temperature,
            humidity=t.humidity,
            resources=t.resources,
            neighbors=[],  # 简化，不计算邻居
            elevation=relative_elev,
            terrain_type=terrain_type,
            climate_zone=climate_zone,
            color="#808080",  # 默认灰色
            salinity=t.salinity,
            is_lake=t.is_lake,
        ))
    
    # 获取栖息地数据
    habitats = []
    try:
        all_species = species_repo.list_species()
        species_map = {sp.id: sp for sp in all_species}
        
        habitat_data = habitat_manager.get_all_habitats()
        for (tile_id, species_id), pop in habitat_data.items():
            sp = species_map.get(species_id)
            if sp and pop > 0:
                habitats.append(HabitatEntry(
                    species_id=species_id,
                    lineage_code=sp.lineage_code,
                    common_name=sp.common_name,
                    latin_name=sp.latin_name,
                    tile_id=tile_id,
                    population=pop,
                    suitability=0.5,  # 简化
                ))
    except Exception as e:
        logger.warning(f"获取栖息地数据失败: {e}")
    
    return MapOverview(
        tiles=tiles,
        habitats=habitats,
        sea_level=sea_level,
        global_avg_temperature=map_state.global_avg_temperature if map_state else 15.0,
        turn_index=map_state.turn_index if map_state else 0,
    )

