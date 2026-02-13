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
        
        # 【修复】从持久化存储恢复回合数，防止服务器重启导致进度丢失
        try:
            map_state = self.environment_repository.get_state()
            if map_state and map_state.turn_index > 0:
                self.simulation_engine.turn_counter = map_state.turn_index
                logger.info(f"[容器] 已从数据库恢复回合数: {map_state.turn_index}")
            else:
                # 【新增】如果是首次启动（数据库为空或无进度），自动执行一次重置/初始化流程
                # 检查是否没有任何物种存在，作为判断“全新开局”的依据
                species_count = self.species_repository.count_species()
                if species_count == 0 and (not map_state or map_state.turn_index == 0):
                    logger.info("[容器] 检测到全新数据库，执行自动初始化流程...")
                    self._perform_initial_reset()
        except Exception as e:
            logger.warning(f"[容器] 恢复回合数或自动初始化失败: {e}")
        
        self._initialized = True
        logger.info("[容器] 服务容器初始化完成")

    def _perform_initial_reset(self) -> None:
        """执行初始重置流程（模拟 create_save 的部分逻辑）"""
        try:
            # 1. 清空可能存在的残留数据
            logger.info("[容器] 自动初始化：清理环境...")
            self.migration_advisor.clear_all_caches()
            self.habitat_manager.clear_all_caches()
            self.dispersal_engine.clear_caches()
            
            self.simulation_engine.speciation.clear_all_caches()
            self.embedding_integration.clear_all_caches()
            
            # 【新增】重置 ModelRouter 到初始状态（清除可能残留的配置）
            # 避免之前运行时的配置污染新会话
            if "model_router" in self.__dict__:
                # 重新触发 cached_property 的初始化逻辑
                del self.__dict__["model_router"]
                logger.info("[容器] ModelRouter 已重置为默认状态")
            
            # 2. 确保地图已生成（已有 ensure_initialized，这里再次确认或重新生成）
            # 注意：如果想强制重新生成地图，可以调用 map_manager.regenerate()
            # 但通常 ensure_initialized 已经够了。
            
            # 3. 重置引擎状态
            self.simulation_engine.turn_counter = 0
            logger.info("[容器] 自动初始化完成：系统已准备就绪，回合数=0")
            
        except Exception as e:
            logger.error(f"[容器] 自动初始化流程出错: {e}")



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
