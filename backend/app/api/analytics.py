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

import json
import logging
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError

from ..security import OutboundRequestError, SafeProbeClient
from ..security.admin_token import AdminTokenValidationError, validate_admin_token
from ..security.config_secrets import (
    UIConfigUpdateRequest,
    merge_ui_config_secrets,
    public_ui_config,
    resolve_provider_credentials,
)
from ..schemas.responses import ExportRecord
from .dependencies import get_container, get_history_repository, get_session
from ..core.ai_router_config import configure_model_router
from ..simulation.constants import get_time_config

if TYPE_CHECKING:
    from ..core.container import ServiceContainer
    from ..core.session import SimulationSessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["analytics"])
_UI_CONFIG_UPDATE_LOCK = RLock()
_SAFE_PROBE_CLIENT = SafeProbeClient()


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
    """获取当前游戏状态
    
    返回格式兼容前端期望的顶层字段结构
    """
    engine = container.simulation_engine
    species_repo = container.species_repository
    env_repo = container.environment_repository
    
    all_species = species_repo.list_species()
    alive_species = [sp for sp in all_species if sp.status == "alive"]
    
    map_state = env_repo.get_state()
    
    # 【动态时间流】获取当前时间配置
    time_config = get_time_config(engine.turn_counter)
    
    # 前端期望的顶层字段
    return {
        "turn_index": engine.turn_counter,
        "species_count": len(alive_species),  # 前端期望的：存活物种数
        "total_species_count": len(all_species),  # 前端期望的：总物种数（含灭绝）
        "sea_level": map_state.sea_level if map_state else 0.0,  # 前端期望的顶层字段
        "global_temperature": map_state.global_avg_temperature if map_state else 15.0,  # 前端期望的顶层字段
        "tectonic_stage": map_state.stage_name if map_state else "稳定期",  # 前端期望的顶层字段
        # 【动态时间流】年份信息
        "current_year": time_config["current_year"],
        "years_per_turn": time_config["years_per_turn"],
        "era_name": time_config["era_name"],
        # 额外字段（保持兼容）
        "running": session.is_running,
        "current_save": session.current_save_name,
        "backend_session_id": str(id(session)),
        # 嵌套格式也保留（向后兼容）
        "species_count_detail": {
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
    import json
    from fastapi.responses import StreamingResponse
    
    async def event_generator():
        # 【修复】发送连接确认事件，让前端从 "连接中" 切换到 "已连接"
        yield f"data: {json.dumps({'type': 'connected', 'message': '已连接到事件流'}, ensure_ascii=False)}\n\n"
        
        while True:
            events = session.get_pending_events(max_count=10)
            
            if events:
                for event in events:
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
) -> dict:
    """获取 UI 配置"""
    return public_ui_config(container.config_service.get_ui_config())


def _inline_local_schema_definitions(schema: dict[str, Any]) -> dict[str, Any]:
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        raise ValueError("Schema definitions must be an object")

    def expand(value: Any, active_references: frozenset[str]) -> Any:
        if isinstance(value, list):
            return [expand(item, active_references) for item in value]
        if not isinstance(value, dict):
            return value

        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            if reference in active_references:
                raise ValueError(f"Recursive schema reference: {reference}")

            definition_name = reference.removeprefix("#/$defs/")
            definition = definitions.get(definition_name)
            if not isinstance(definition, dict):
                raise ValueError(f"Unknown local schema reference: {reference}")

            next_references = active_references | {reference}
            expanded_reference = expand(definition, next_references)
            siblings = {
                key: expand(item, active_references)
                for key, item in value.items()
                if key not in {"$ref", "$defs"}
            }
            if siblings:
                return {"allOf": [expanded_reference], **siblings}
            return expanded_reference

        return {
            key: expand(item, active_references)
            for key, item in value.items()
            if key != "$defs"
        }

    expanded = expand(schema, frozenset())
    if not isinstance(expanded, dict):
        raise ValueError("Schema root must be an object")
    return expanded


def _is_json_media_type(content_type: str | None) -> bool:
    if not content_type:
        return False

    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type == "application/json":
        return True
    if not media_type.startswith("application/"):
        return False

    subtype = media_type.removeprefix("application/")
    token_characters = frozenset(
        "!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyz"
    )
    return (
        subtype.endswith("+json")
        and bool(subtype.removesuffix("+json"))
        and "*" not in subtype
        and all(character in token_characters for character in subtype)
    )


async def _parse_ui_config_update(request: Request) -> UIConfigUpdateRequest:
    raw_request = await _parse_safe_json_object(request)

    try:
        return UIConfigUpdateRequest.model_validate(raw_request)
    except ValidationError:
        raise HTTPException(
            status_code=422,
            detail="Invalid configuration payload",
        ) from None


async def _parse_safe_json_object(request: Request) -> dict[str, Any]:
    if not _is_json_media_type(request.headers.get("content-type")):
        raise HTTPException(
            status_code=422,
            detail="Invalid configuration payload",
        )

    try:
        raw_request = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=422,
            detail="Invalid configuration payload",
        ) from None

    if not isinstance(raw_request, dict):
        raise HTTPException(
            status_code=422,
            detail="Invalid configuration payload",
        )

    return raw_request


def _json_object_request_openapi() -> dict[str, Any]:
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                },
            },
        },
    }


@router.post(
    "/config/ui",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _inline_local_schema_definitions(
                        UIConfigUpdateRequest.model_json_schema()
                    ),
                },
            },
        },
    },
)
def update_ui_config(
    request: UIConfigUpdateRequest = Depends(_parse_ui_config_update),
    x_clade_admin_token: str | None = Header(
        default=None, alias="X-Clade-Admin-Token"
    ),
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    with _UI_CONFIG_UPDATE_LOCK:
        return _update_ui_config(request, container, x_clade_admin_token)


def _update_ui_config(
    request: UIConfigUpdateRequest,
    container: 'ServiceContainer',
    x_clade_admin_token: str | None,
) -> dict:
    """更新 UI 配置"""
    env_repo = container.environment_repository
    config_service = container.config_service

    current = config_service.get_ui_config()
    if request.config.allow_local_ai_endpoints != current.allow_local_ai_endpoints:
        try:
            validate_admin_token(
                x_clade_admin_token,
                container.settings.clade_admin_token,
            )
        except AdminTokenValidationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.public_message},
            ) from None

    merged = merge_ui_config_secrets(
        current,
        request.config,
        request.clear_provider_api_keys,
    )
    
    # 保存配置
    saved = env_repo.save_ui_config(
        Path(container.settings.ui_config_path),
        merged,
    )
    
    # 使缓存失效
    try:
        config_service.invalidate_cache()
    except Exception as exc:
        logger.warning(
            "[config] Cache invalidation failed (error_type=%s)",
            type(exc).__name__,
        )
    
    # 应用配置到容器级 ModelRouter
    try:
        configure_model_router(saved, container.model_router, container.embedding_service, container.settings)
        logger.info("[配置] 容器 ModelRouter 已更新")
    except Exception as exc:
        logger.warning(
            "[配置] 更新容器 ModelRouter 失败 (error_type=%s)",
            type(exc).__name__,
        )
    
    # 【修复】刷新 SimulationEngine 及子服务的配置（分化、死亡率、生态平衡等）
    try:
        # 获取最新配置
        new_configs = {
            "ecology": config_service.get_ecology_balance(),
            "mortality": config_service.get_mortality(),
            "speciation": config_service.get_speciation(),
            "food_web": getattr(saved, 'food_web', None),
        }
        container.simulation_engine.reload_configs(new_configs)
        logger.info("[配置] 游戏参数配置已刷新到引擎")
    except Exception as exc:
        logger.warning(
            "[配置] 刷新引擎配置失败（将在下次推演时自动加载） "
            "(error_type=%s)",
            type(exc).__name__,
        )
    
    return public_ui_config(saved)


@router.post("/config/test-api", openapi_extra=_json_object_request_openapi())
def test_api_connection(
    request: dict[str, Any] = Depends(_parse_safe_json_object),
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """测试 API 连接是否有效"""
    current = container.config_service.get_ui_config()
    try:
        credentials = resolve_provider_credentials(request, current)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    base_url = credentials.base_url or ""
    api_key = credentials.api_key
    provider_type = credentials.provider_type
    
    if not base_url or not api_key:
        return {"success": False, "error": "缺少必要参数"}
    
    headers = {"Authorization": f"Bearer {api_key}"}
    endpoint = "models"

    if provider_type == "anthropic":
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        endpoint = "messages"

    try:
        status_code = _SAFE_PROBE_CLIENT.probe_status(
            base_url,
            endpoint=endpoint,
            headers=headers,
            allow_local=current.allow_local_ai_endpoints,
        )
    except OutboundRequestError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.public_message},
        ) from None

    if status_code == 200:
        return {"success": True, "message": "连接成功"}
    return {"success": False, "error": "API 返回非成功状态"}


@router.post("/config/fetch-models", openapi_extra=_json_object_request_openapi())
def fetch_models(
    request: dict[str, Any] = Depends(_parse_safe_json_object),
    container: 'ServiceContainer' = Depends(get_container),
) -> dict:
    """获取服务商的可用模型列表"""
    current = container.config_service.get_ui_config()
    try:
        credentials = resolve_provider_credentials(request, current)
    except ValueError as exc:
        return {"success": False, "error": str(exc), "models": []}

    base_url = credentials.base_url or ""
    api_key = credentials.api_key
    provider_type = credentials.provider_type
    
    if not base_url or not api_key:
        return {"success": False, "error": "缺少必要参数", "models": []}
    
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

    try:
        response = _SAFE_PROBE_CLIENT.fetch_json_response(
            base_url,
            endpoint="models",
            headers=headers,
            allow_local=current.allow_local_ai_endpoints,
        )
    except OutboundRequestError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.public_message},
        ) from None

    if response.status_code != 200:
        return {
            "success": False,
            "error": "API 返回非成功状态",
            "models": [],
        }

    data = response.data
    models = data.get("data") if isinstance(data, dict) else None
    if not isinstance(models, list) or any(
        not isinstance(model, dict) or not isinstance(model.get("id"), str)
        for model in models
    ):
        raise HTTPException(
            status_code=502,
            detail={
                "code": "outbound_bad_response",
                "message": "外部服务响应无效",
            },
        )

    return {
        "success": True,
        "models": [
            {"id": model["id"], "name": model["id"]}
            for model in models
            if model["id"]
        ],
    }


# ========== 地图 ==========

@router.get("/map")
def get_map_overview(
    limit_tiles: int = 0,
    limit_habitats: int = 0,
    view_mode: str = "terrain",
    species_id: int | None = None,
    species_code: str | None = None,
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取地图概览
    
    Args:
        limit_tiles: 限制返回的地块数量（0=不限制）
        limit_habitats: 限制返回的栖息地数量（0=不限制）
        view_mode: 视图模式（terrain/terrain_type/elevation/biodiversity/climate/suitability）
        species_id: 可选，聚焦特定物种的分布（通过ID）
        species_code: 可选，聚焦特定物种的分布（通过lineage_code，兼容前端）
    """
    from ..services.geo.map_coloring import ViewMode
    
    map_manager = container.map_manager
    species_repo = container.species_repository
    
    # 确保地图已初始化
    map_manager.ensure_initialized()
    
    # 【v14】预初始化 embedding 相关服务
    try:
        from ..services.geo.suitability_service import get_suitability_service
        from ..services.species.prey_affinity import get_prey_affinity_service
        get_suitability_service(container.embedding_service)
        get_prey_affinity_service(container.embedding_service)
    except Exception:
        pass  # 非阻塞，失败时回退到旧方法
    
    # 如果提供了 species_code，转换为 species_id
    resolved_species_id = species_id
    if species_code and not species_id:
        species = species_repo.get_by_lineage(species_code)
        if species:
            resolved_species_id = species.id
    
    # 直接使用 map_manager 的 get_overview，它包含完整的颜色计算逻辑
    return map_manager.get_overview(
        tile_limit=limit_tiles if limit_tiles > 0 else None,
        habitat_limit=limit_habitats if limit_habitats > 0 else None,
        view_mode=view_mode,  # type: ignore
        species_id=resolved_species_id,
    )


# ========== 渲染数据 ==========

@router.get("/render/heightmap")
def get_heightmap(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取高度图（二进制 Float32Array）
    
    返回所有地块的高度数据，按地块ID顺序排列
    """
    import struct
    from starlette.responses import Response
    
    env_repo = container.environment_repository
    tiles = env_repo.list_tiles()
    
    if not tiles:
        return Response(content=b"", media_type="application/octet-stream")
    
    # 按 ID 排序
    tiles.sort(key=lambda t: t.id)
    
    # 打包为 Float32Array
    data = struct.pack(f"{len(tiles)}f", *[t.elevation for t in tiles])
    
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Length": str(len(data))}
    )


@router.get("/render/watermask")
def get_watermask(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取水域遮罩（二进制 Float32Array）
    
    返回每个地块的水域深度，陆地为0，水域为正值
    """
    import struct
    from starlette.responses import Response
    
    env_repo = container.environment_repository
    tiles = env_repo.list_tiles()
    map_state = env_repo.get_state()
    sea_level = map_state.sea_level if map_state else 0.0
    
    if not tiles:
        return Response(content=b"", media_type="application/octet-stream")
    
    # 按 ID 排序
    tiles.sort(key=lambda t: t.id)
    
    # 计算水深：海平面以下为正值，以上为0
    water_depths = []
    for t in tiles:
        depth = max(0.0, sea_level - t.elevation)
        water_depths.append(depth)
    
    data = struct.pack(f"{len(tiles)}f", *water_depths)
    
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Length": str(len(data))}
    )


@router.get("/render/erosionmap")
def get_erosionmap(
    container: 'ServiceContainer' = Depends(get_container),
):
    """获取侵蚀图（二进制 Float32Array）
    
    返回每个地块的侵蚀程度（基于相邻高度差计算）
    """
    import struct
    from starlette.responses import Response
    
    env_repo = container.environment_repository
    tiles = env_repo.list_tiles()
    
    if not tiles:
        return Response(content=b"", media_type="application/octet-stream")
    
    # 按 ID 排序并建立索引
    tiles.sort(key=lambda t: t.id)
    tile_map = {t.id: t for t in tiles}
    
    # 计算侵蚀值（基于与邻居的高度差）
    erosion_values = []
    for t in tiles:
        if not t.neighbors:
            erosion_values.append(0.0)
            continue
        
        # 计算与所有邻居的平均高度差
        height_diffs = []
        for neighbor_id in t.neighbors:
            neighbor = tile_map.get(neighbor_id)
            if neighbor:
                height_diffs.append(abs(t.elevation - neighbor.elevation))
        
        if height_diffs:
            avg_diff = sum(height_diffs) / len(height_diffs)
            # 归一化到 0-1 范围（假设最大高度差为 2000m）
            erosion = min(1.0, avg_diff / 2000.0)
        else:
            erosion = 0.0
        
        erosion_values.append(erosion)
    
    data = struct.pack(f"{len(tiles)}f", *erosion_values)
    
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Length": str(len(data))}
    )

