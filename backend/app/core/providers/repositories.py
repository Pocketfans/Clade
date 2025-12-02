"""
仓储提供者 - 数据访问层服务

提供对仓储实例的缓存访问：
- species_repository: 物种数据访问
- environment_repository: 环境/地图数据访问
- history_repository: 回合历史数据访问
- genus_repository: 属/分类数据访问

架构：
- 每个容器实例获取自己的仓储实例
- 这使得在测试和多实例场景中能够正确隔离
- 仓储是无状态的，共享是安全的，但隔离更佳
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ...repositories.species_repository import SpeciesRepository
    from ...repositories.environment_repository import EnvironmentRepository
    from ...repositories.history_repository import HistoryRepository
    from ...repositories.genus_repository import GenusRepository


class RepositoryProvider:
    """Mixin providing repository access
    
    Creates new repository instances per container for proper isolation.
    Override via container.override() for testing.
    """
    
    _overrides: dict[str, Any]
    
    def _get_or_override(self, name: str, factory: Callable[[], Any]) -> Any:
        """Get service instance, preferring override if set"""
        if name in self._overrides:
            return self._overrides[name]
        return factory()
    
    @cached_property
    def species_repository(self) -> 'SpeciesRepository':
        """Get species repository (new instance per container)"""
        from ...repositories.species_repository import SpeciesRepository
        return self._get_or_override('species_repository', SpeciesRepository)
    
    @cached_property
    def environment_repository(self) -> 'EnvironmentRepository':
        """Get environment repository (new instance per container)"""
        from ...repositories.environment_repository import EnvironmentRepository
        return self._get_or_override('environment_repository', EnvironmentRepository)
    
    @cached_property
    def history_repository(self) -> 'HistoryRepository':
        """Get history repository (new instance per container)"""
        from ...repositories.history_repository import HistoryRepository
        return self._get_or_override('history_repository', HistoryRepository)
    
    @cached_property
    def genus_repository(self) -> 'GenusRepository':
        """Get genus repository (new instance per container)"""
        from ...repositories.genus_repository import GenusRepository
        return self._get_or_override('genus_repository', GenusRepository)

