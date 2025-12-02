"""
FastAPI 依赖注入 - Depends 工厂

此模块提供用于 FastAPI 路由的依赖注入函数。
所有依赖通过 Depends() 注入到路由处理函数中。

架构：
- 依赖项优先使用 app.state 中的实例（在 lifespan 中设置）
- 不再回退到全局单例（已移除）
- 所有新代码使用基于 Request 的注入

使用方式：
    from fastapi import Depends, Request
    from .dependencies import get_species_repository, get_session
    
    @router.get("/species")
    def list_species(
        repo: SpeciesRepository = Depends(get_species_repository),
        session: SimulationSessionManager = Depends(get_session)
    ):
        return repo.get_all()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request

if TYPE_CHECKING:
    from ..core.container import ServiceContainer
    from ..core.session import SimulationSessionManager
    from ..core.config_service import ConfigService
    from ..repositories.species_repository import SpeciesRepository
    from ..repositories.environment_repository import EnvironmentRepository
    from ..repositories.history_repository import HistoryRepository
    from ..repositories.genus_repository import GenusRepository
    from ..ai.model_router import ModelRouter
    from ..services.system.embedding import EmbeddingService
    from ..services.system.save_manager import SaveManager
    from ..services.species.species_generator import SpeciesGenerator
    from ..services.analytics.exporter import ExportService
    from ..simulation.engine import SimulationEngine
    from ..simulation.environment import EnvironmentSystem


# ========== 核心依赖 ==========

def get_container(request: Request) -> 'ServiceContainer':
    """从 app.state 获取服务容器
    
    容器在 lifespan 中实例化并存储到 app.state。
    这确保了显式的依赖注入，不使用全局单例。
    
    Raises:
        RuntimeError: 如果容器未初始化（lifespan 未启动）
    """
    if not hasattr(request.app.state, 'container'):
        raise RuntimeError(
            "ServiceContainer 未初始化。"
            "请确保应用 lifespan 已启动。"
        )
    return request.app.state.container


def get_session(request: Request) -> 'SimulationSessionManager':
    """从 app.state 获取会话管理器
    
    会话在 lifespan 中实例化并存储到 app.state。
    这确保了显式的依赖注入，不使用全局单例。
    
    Raises:
        RuntimeError: 如果会话未初始化（lifespan 未启动）
    """
    if not hasattr(request.app.state, 'session'):
        raise RuntimeError(
            "SimulationSessionManager 未初始化。"
            "请确保应用 lifespan 已启动。"
        )
    return request.app.state.session


def get_config(request: Request) -> 'ConfigService':
    """获取配置服务"""
    container = get_container(request)
    return container.config_service


# ========== 仓储依赖 ==========

def get_species_repository(request: Request) -> 'SpeciesRepository':
    """获取物种仓储"""
    return get_container(request).species_repository


def get_environment_repository(request: Request) -> 'EnvironmentRepository':
    """获取环境仓储"""
    return get_container(request).environment_repository


def get_history_repository(request: Request) -> 'HistoryRepository':
    """获取历史仓储"""
    return get_container(request).history_repository


def get_genus_repository(request: Request) -> 'GenusRepository':
    """获取属仓储"""
    return get_container(request).genus_repository


# ========== 服务依赖 ==========

def get_model_router(request: Request) -> 'ModelRouter':
    """获取模型路由"""
    return get_container(request).model_router


def get_embedding_service(request: Request) -> 'EmbeddingService':
    """获取嵌入服务"""
    return get_container(request).embedding_service


def get_save_manager(request: Request) -> 'SaveManager':
    """获取存档管理器"""
    return get_container(request).save_manager


def get_species_generator(request: Request) -> 'SpeciesGenerator':
    """获取物种生成器"""
    return get_container(request).species_generator


def get_export_service(request: Request) -> 'ExportService':
    """获取导出服务"""
    return get_container(request).export_service


def get_resource_manager(request: Request):
    """获取资源管理器"""
    return get_container(request).resource_manager


# ========== 模拟依赖 ==========

def get_simulation_engine(request: Request) -> 'SimulationEngine':
    """获取模拟引擎"""
    return get_container(request).simulation_engine


def get_environment_system(request: Request) -> 'EnvironmentSystem':
    """获取环境系统"""
    return get_container(request).environment_system


# ========== 状态检查依赖 ==========

def require_not_running(
    request: Request,
    session: 'SimulationSessionManager' = Depends(get_session)
) -> None:
    """要求模拟未运行
    
    用于需要模拟停止的操作（如加载存档）。
    
    Raises:
        HTTPException: 如果模拟正在运行
    """
    if session.is_running:
        raise HTTPException(
            status_code=400,
            detail="操作失败：模拟正在运行，请等待或先中止"
        )


def require_save_loaded(
    request: Request,
    session: 'SimulationSessionManager' = Depends(get_session)
) -> str:
    """要求已加载存档
    
    Returns:
        当前存档名称
        
    Raises:
        HTTPException: 如果未加载存档
    """
    save_name = session.current_save_name
    if not save_name:
        raise HTTPException(
            status_code=400,
            detail="操作失败：请先创建或加载存档"
        )
    return save_name
