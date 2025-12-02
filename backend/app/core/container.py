"""
服务容器 - 组合根

此模块实现依赖注入模式，管理所有服务实例的创建和生命周期。

架构：
- 容器通过多继承从领域特定的 Provider 获取功能
- 每个 Provider 贡献其领域的 cached_property 方法
- 服务在首次访问时延迟初始化
- 支持通过 override() 方法进行测试替换

Provider 列表：
- RepositoryProvider: 数据访问层（物种、环境、历史、属）
- CoreServiceProvider: 基础服务（嵌入、模型路由、配置）
- SpeciesServiceProvider: 物种相关服务
- SimulationServiceProvider: 模拟引擎及相关服务
- AnalyticsServiceProvider: 报告和分析服务

使用方式：
    # 在 lifespan 中（main.py）
    container = ServiceContainer()
    app.state.container = container
    
    # 在依赖中（通过 Depends）
    def get_species_repository(request: Request):
        return request.app.state.container.species_repository
"""

from __future__ import annotations

import logging
from typing import Any

from .config import get_settings
from .providers import (
    RepositoryProvider,
    CoreServiceProvider,
    SpeciesServiceProvider,
    SimulationServiceProvider,
    AnalyticsServiceProvider,
)

logger = logging.getLogger(__name__)


class ServiceContainer(
    RepositoryProvider,
    CoreServiceProvider,
    SpeciesServiceProvider,
    AnalyticsServiceProvider,
    SimulationServiceProvider,  # 最后，因为它依赖其他服务
):
    """服务容器 - 管理所有服务实例的生命周期
    
    所有服务通过 cached_property 延迟初始化，
    仅在首次访问时创建。
    
    Attributes:
        settings: 全局配置
        _overrides: 测试用服务替换
        _initialized: 容器是否已初始化
    """
    
    def __init__(self) -> None:
        self.settings = get_settings()
        self._overrides: dict[str, Any] = {}
        self._initialized = False
    
    def override(self, name: str, instance: Any) -> None:
        """替换服务实例（用于测试）
        
        Args:
            name: 服务名称（属性名）
            instance: 替换的实例
        """
        self._overrides[name] = instance
        # 清除缓存属性（如果存在）
        if name in self.__dict__:
            del self.__dict__[name]
    
    def reset_overrides(self) -> None:
        """重置所有替换"""
        for name in list(self._overrides.keys()):
            if name in self.__dict__:
                del self.__dict__[name]
        self._overrides.clear()
    
    def _get_or_override(self, name: str, factory: Any) -> Any:
        """获取服务实例，优先使用替换的实例"""
        if name in self._overrides:
            return self._overrides[name]
        return factory()
    
    def initialize(self) -> None:
        """初始化容器（启动时调用）
        
        执行必要的预热和环境初始化。
        """
        if self._initialized:
            return
        
        # 确保地图初始化
        self.map_manager.ensure_initialized()
        logger.info("[容器] 地图初始化完成")
        
        self._initialized = True
        logger.info("[容器] 服务容器初始化完成")


# ========== 已废弃：全局实例 ==========
# 这些函数已废弃，将在未来版本中移除。
# 所有新代码请使用 app.state.container 并通过 Depends() 访问。

import warnings

_container: ServiceContainer | None = None
_global_access_warned: bool = False


def get_container() -> ServiceContainer:
    """获取全局服务容器实例
    
    .. deprecated::
        请使用 ``Depends(get_container)`` 从 ``request.app.state.container`` 获取。
        全局单例会在多 Worker 部署时导致状态隔离问题。
        
    Warning:
        调用此函数会记录废弃警告。当所有代码路径迁移到
        基于 lifespan 的注入后，此函数将被移除。
    """
    global _container, _global_access_warned
    
    if not _global_access_warned:
        warnings.warn(
            "get_container() 已废弃。请使用 api.dependencies 中的 Depends(get_container)，"
            "它会访问 app.state.container。此全局单例将被移除。",
            DeprecationWarning,
            stacklevel=2
        )
        logger.warning(
            "[已废弃] get_container() 被调用。请迁移到 api.dependencies 中的 "
            "Depends(get_container) 以获得正确的生命周期管理。"
        )
        _global_access_warned = True
    
    if _container is None:
        _container = ServiceContainer()
    return _container


def reset_container() -> None:
    """重置容器（仅用于测试）
    
    .. deprecated::
        请直接创建新的 ServiceContainer 实例。
    """
    global _container, _global_access_warned
    if _container is not None:
        _container.reset_overrides()
    _container = None
    _global_access_warned = False
