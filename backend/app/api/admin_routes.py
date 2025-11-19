from __future__ import annotations

import shutil
import sys
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..core.database import session_scope, init_db, engine
from ..core.seed import A_SCENARIO, seed_defaults
from ..core.config import get_settings
from ..models.species import Species
from ..models.environment import MapTile, MapState, TerrainEvolutionHistory
from ..models.history import HistoryRecord, TurnLog
from ..repositories.species_repository import species_repository
from ..repositories.environment_repository import environment_repository
from ..services.terrain_evolution import TerrainEvolutionService
from ..services.map_evolution import MapEvolutionService
from ..ai.model_router import ModelRouter, ModelConfig
from ..simulation.environment import ParsedPressure
from sqlmodel import delete, select, Session

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()
logger = logging.getLogger(__name__)

class ResetRequest(BaseModel):
    keep_saves: bool = False
    keep_map: bool = False

class TerrainSimRequest(BaseModel):
    turns: int = 5
    width: int = 80
    height: int = 40

@router.get("/health")
def check_health() -> dict:
    """系统健康检查"""
    status = {
        "api": "online",
        "database": "unknown",
        "directories": {},
        "initial_species": "unknown"
    }
    
    # 1. 检查数据库
    try:
        with session_scope() as session:
            # 检查初始物种
            initial_codes = ['A1', 'B1', 'C1']
            missing = []
            for code in initial_codes:
                sp = species_repository.get_by_lineage(code)
                if not sp:
                    missing.append(code)
            
            if missing:
                status["initial_species"] = f"missing: {missing}"
                status["database"] = "degraded"
            else:
                status["initial_species"] = "ok"
                status["database"] = "ok"
    except Exception as e:
        status["database"] = f"error: {str(e)}"
    
    # 2. 检查目录
    required_dirs = ["data/db", "data/logs", "data/reports", "data/saves", "data/exports"]
    root_dir = Path(".").resolve()
    
    for d in required_dirs:
        path = root_dir / d
        if path.exists():
            status["directories"][d] = "ok"
        else:
            status["directories"][d] = "missing"
            
    return status

@router.post("/reset")
def reset_world(request: ResetRequest) -> dict:
    """重置世界状态"""
    try:
        # 1. 重置数据库
        with session_scope() as session:
            # 删除历史记录
            session.exec(delete(HistoryRecord))
            session.exec(delete(TurnLog))
            
            # 删除非初始物种
            initial_codes = {s['lineage_code'] for s in A_SCENARIO}
            all_species = session.exec(select(Species)).all()
            deleted_count = 0
            
            for sp in all_species:
                if sp.lineage_code not in initial_codes:
                    session.delete(sp)
                    deleted_count += 1
                else:
                    # 重置初始物种
                    scenario = next(s for s in A_SCENARIO if s['lineage_code'] == sp.lineage_code)
                    sp.population = 1000
                    sp.status = 'alive'
                    sp.created_turn = 0
                    sp.parent_code = None
                    sp.morphology_stats = scenario['morphology_stats']
                    sp.abstract_traits = scenario['abstract_traits']
                    sp.description = scenario['description']
                    session.add(sp)
            
            # 重置地图
            if not request.keep_map:
                session.exec(delete(TerrainEvolutionHistory))
                session.exec(delete(MapState))
                # 重置初始地图状态
                initial_state = MapState(
                    turn_index=0,
                    stage_name="稳定期",
                    stage_progress=0,
                    stage_duration=50,
                    sea_level=0.0,
                    global_avg_temperature=15.0
                )
                session.add(initial_state)
        
        # 2. 清理文件
        data_dir = Path("data")
        if not request.keep_saves:
            _clear_directory(data_dir / "saves")
            _clear_directory(data_dir / "exports")
        
        _clear_directory(data_dir / "reports")
        # 不清理 logs，因为当前正在写入日志
        
        return {"success": True, "message": f"重置完成。删除了 {deleted_count} 个演化物种。"}
        
    except Exception as e:
        logger.error(f"重置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _clear_directory(dir_path: Path):
    if not dir_path.exists():
        return
    for item in dir_path.glob("*"):
        if item.is_file():
            try:
                item.unlink()
            except Exception:
                pass
        elif item.is_dir():
            try:
                shutil.rmtree(item)
            except Exception:
                pass

@router.post("/simulate-terrain")
def simulate_terrain(request: TerrainSimRequest) -> dict:
    """运行地形演化模拟测试"""
    try:
        # 这是一个简化的同步运行版本，仅用于测试
        # 1. 初始化服务
        router = ModelRouter(
            {"terrain_evolution": ModelConfig(provider="openai", model=settings.report_model)},
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            timeout=settings.ai_request_timeout,
        )
        terrain_service = TerrainEvolutionService(router)
        map_evolution_service = MapEvolutionService(width=request.width, height=request.height)
        
        # 2. 生成临时测试地图（不保存到主数据库，以免覆盖游戏数据）
        # 这里我们复用 scripts/simulate_terrain.py 中的 create_test_map 逻辑
        # 但为了避免代码重复，我们简单生成一个
        tiles = _create_simple_test_map(request.width, request.height)
        
        current_state = MapState(
            turn_index=0,
            stage_name="稳定期",
            stage_progress=0,
            stage_duration=map_evolution_service.stage_duration,
            sea_level=0.0,
            global_avg_temperature=15.0,
        )
        
        logs = []
        logs.append(f"开始模拟 (Turns={request.turns}, Size={request.width}x{request.height})")
        
        for turn in range(1, request.turns + 1):
            prev_state = current_state.model_copy()
            
            # 推进阶段
            map_evolution_service.advance([], turn, {}, current_state)
            logs.append(f"Turn {turn}: {current_state.stage_name} ({current_state.stage_progress}/{current_state.stage_duration})")
            
            # 模拟压力
            pressures = []
            if turn % 5 == 0:
                pressures.append(ParsedPressure(kind="volcanic", intensity=7, affected_tiles=[], narrative="测试火山活动"))
            
            # 演化
            updated_tiles, events = terrain_service.evolve_terrain(
                tiles=tiles,
                pressures=pressures,
                map_state=current_state,
                prev_state=prev_state,
                turn_index=turn,
            )
            
            if updated_tiles:
                # 更新本地 tiles 列表
                tile_map = {t.id: t for t in tiles}
                for ut in updated_tiles:
                    tile_map[ut.id] = ut
                tiles = list(tile_map.values())
                logs.append(f"  -> 地形更新: {len(updated_tiles)} 地块")
            
            for evt in events:
                logs.append(f"  -> 事件: {evt.description}")
                
        return {
            "success": True,
            "logs": logs,
            "final_state": {
                "stage": current_state.stage_name,
                "sea_level": current_state.sea_level,
                "temperature": current_state.global_avg_temperature
            }
        }
        
    except Exception as e:
        logger.error(f"地形模拟失败: {e}")
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}

def _create_simple_test_map(width: int, height: int) -> list[MapTile]:
    """创建一个简单的平面地图用于测试"""
    tiles = []
    for y in range(height):
        for x in range(width):
            tile = MapTile(
                id=y * width + x + 1,
                x=x, y=y, q=x, r=y, # 简化坐标
                biome="草原",
                elevation=100.0,
                cover="草甸",
                temperature=20.0,
                humidity=0.5,
                resources=0.5,
                has_river=False,
                pressures={}
            )
            tiles.append(tile)
    return tiles

