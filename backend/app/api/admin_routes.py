from __future__ import annotations

import shutil
import sys
import logging
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import SQLModel, delete, select, Session

from ..core.database import session_scope, init_db, engine
from ..core.seed import A_SCENARIO, seed_defaults
from ..core.config import get_settings
from ..models.species import Species
from ..models.environment import MapState
from ..models.history import TurnLog
from ..repositories.species_repository import species_repository
from ..repositories.environment_repository import environment_repository
from ..security.admin_token import require_admin_token

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)
settings = get_settings()
logger = logging.getLogger(__name__)

class ResetRequest(BaseModel):
    keep_saves: bool = False
    keep_map: bool = False

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
    
    # 2. 检查目录 (使用 Settings 中的配置)
    current_settings = get_settings()
    required_dirs = {
        "db": Path(current_settings.database_url.replace("sqlite:///", "")).parent,
        "logs": Path(current_settings.log_dir),
        "reports": Path(current_settings.reports_dir),
        "saves": Path(current_settings.saves_dir),
        "exports": Path(current_settings.exports_dir)
    }
    
    for name, path in required_dirs.items():
        if path.exists():
            status["directories"][name] = "ok"
        else:
            status["directories"][name] = "missing"
            
    return status

@router.post("/reset")
def reset_world(request: ResetRequest) -> dict:
    """重置世界状态"""
    try:
        # 1. 重置数据库
        with session_scope() as session:
            # 删除历史记录
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
        current_settings = get_settings()
        if not request.keep_saves:
            _clear_directory(Path(current_settings.saves_dir))
            _clear_directory(Path(current_settings.exports_dir))
        
        _clear_directory(Path(current_settings.reports_dir))
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


class DropDatabaseRequest(BaseModel):
    confirm: bool = False  # 必须确认


@router.post("/drop-database")
def drop_and_recreate_database(request: DropDatabaseRequest) -> dict:
    """完全清空数据库并重新创建所有表
    
    ⚠️ 危险操作：这将删除所有数据！
    """
    if not request.confirm:
        raise HTTPException(status_code=400, detail="必须设置 confirm=true 才能执行此操作")
    
    try:
        logger.warning("⚠️ 开始清空数据库...")
        
        # 1. 删除所有表
        SQLModel.metadata.drop_all(engine)
        logger.info("✓ 已删除所有表")
        
        # 2. 重新创建所有表
        init_db()
        logger.info("✓ 已重新创建所有表")
        
        # 3. 重新填充初始数据
        seed_defaults()
        logger.info("✓ 已重新填充初始数据")
        
        # 4. 清理所有数据目录
        current_settings = get_settings()
        _clear_directory(Path(current_settings.saves_dir))
        _clear_directory(Path(current_settings.exports_dir))
        _clear_directory(Path(current_settings.reports_dir))
        
        # 清理embedding缓存
        cache_dir = Path(current_settings.embedding_cache_dir) if hasattr(current_settings, 'embedding_cache_dir') else Path("data/cache/embeddings")
        _clear_directory(cache_dir)
        logger.info("✓ 已清理数据目录")
        
        return {
            "success": True, 
            "message": "数据库已完全重置。所有表已删除并重新创建，初始数据已重新填充。"
        }
        
    except Exception as e:
        logger.error(f"清空数据库失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空数据库失败: {str(e)}")


# ==================== 性能优化 API ====================

class OptimizeRequest(BaseModel):
    """优化请求参数"""
    create_indexes: bool = True
    vacuum: bool = True
    cleanup_history: bool = False
    keep_turns: int = 3


class CleanupRequest(BaseModel):
    """清理请求参数"""
    keep_turns: int = 3
    confirm: bool = False


@router.get("/storage-stats")
def get_storage_stats() -> dict:
    """获取存储统计信息
    
    返回数据库和存档的使用情况统计
    """
    try:
        result = {
            "habitat_stats": {},
            "save_stats": {},
        }
        
        # 栖息地统计
        if hasattr(environment_repository, 'get_habitat_stats'):
            result["habitat_stats"] = environment_repository.get_habitat_stats()
        
        # 存档统计
        from ..services.system.save_manager import SaveManager
        saves_dir = Path(settings.saves_dir)
        if saves_dir.exists():
            save_manager = SaveManager(saves_dir)
            result["save_stats"] = save_manager.get_storage_stats()
        
        return result
        
    except Exception as e:
        logger.error(f"获取存储统计失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize-database")
def optimize_database(request: OptimizeRequest) -> dict:
    """优化数据库性能
    
    【功能】
    1. 创建必要的索引（加速查询 10-100x）
    2. 执行 VACUUM（回收空间）
    3. 执行 ANALYZE（更新查询优化器统计）
    4. 可选：清理历史栖息地数据
    
    【建议】
    - 在加载大型存档后执行
    - 在数据库膨胀时执行
    """
    try:
        result = {
            "success": True,
            "indexes": {},
            "vacuum": False,
            "analyze": False,
            "cleanup": None,
        }
        
        # 创建索引
        if request.create_indexes:
            if hasattr(environment_repository, 'ensure_indexes'):
                result["indexes"] = environment_repository.ensure_indexes()
                logger.info(f"[Admin] 索引创建完成: {result['indexes']}")
        
        # VACUUM 和 ANALYZE
        if request.vacuum:
            if hasattr(environment_repository, 'optimize_database'):
                opt_result = environment_repository.optimize_database()
                result["vacuum"] = opt_result.get("vacuum", False)
                result["analyze"] = opt_result.get("analyze", False)
                logger.info(f"[Admin] 数据库优化完成: VACUUM={result['vacuum']}, ANALYZE={result['analyze']}")
        
        # 清理历史数据
        if request.cleanup_history:
            if hasattr(environment_repository, 'cleanup_old_habitats'):
                deleted = environment_repository.cleanup_old_habitats(request.keep_turns)
                result["cleanup"] = {
                    "deleted_records": deleted,
                    "keep_turns": request.keep_turns,
                }
                logger.info(f"[Admin] 历史数据清理完成: 删除 {deleted} 条")
        
        return result
        
    except Exception as e:
        logger.error(f"数据库优化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup-habitat-history")
def cleanup_habitat_history(request: CleanupRequest) -> dict:
    """清理栖息地历史数据
    
    ⚠️ 此操作不可逆！只保留最近 N 回合的数据。
    
    【适用场景】
    - 数据库文件过大
    - 加载存档过慢
    - 内存占用过高
    """
    if not request.confirm:
        raise HTTPException(
            status_code=400, 
            detail="必须设置 confirm=true 才能执行此操作。此操作将删除历史数据，不可恢复！"
        )
    
    try:
        # 获取清理前统计
        stats_before = {}
        if hasattr(environment_repository, 'get_habitat_stats'):
            stats_before = environment_repository.get_habitat_stats()
        
        # 执行清理
        deleted = 0
        if hasattr(environment_repository, 'cleanup_old_habitats'):
            deleted = environment_repository.cleanup_old_habitats(request.keep_turns)
        
        # 获取清理后统计
        stats_after = {}
        if hasattr(environment_repository, 'get_habitat_stats'):
            stats_after = environment_repository.get_habitat_stats()
        
        return {
            "success": True,
            "deleted_records": deleted,
            "keep_turns": request.keep_turns,
            "before": stats_before,
            "after": stats_after,
        }
        
    except Exception as e:
        logger.error(f"清理历史数据失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-indexes")
def create_database_indexes() -> dict:
    """创建数据库索引
    
    【性能提升】
    - 栖息地查询: 10-100x
    - 地块查询: 5-20x
    - 物种查询: 5-10x
    
    【安全性】
    - 此操作是幂等的，可以重复执行
    - 不会删除任何数据
    """
    try:
        if not hasattr(environment_repository, 'ensure_indexes'):
            raise HTTPException(
                status_code=501, 
                detail="环境仓储不支持索引管理"
            )
        
        results = environment_repository.ensure_indexes()
        
        created = sum(1 for v in results.values() if v)
        existing = sum(1 for v in results.values() if not v)
        
        return {
            "success": True,
            "created_count": created,
            "existing_count": existing,
            "details": results,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建索引失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
