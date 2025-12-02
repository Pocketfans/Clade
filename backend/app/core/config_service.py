"""
配置服务 - 统一配置管理

此模块负责集中管理所有配置的读取和缓存：
1. UI 配置（data/settings.json）的唯一来源
2. 消除分散的 _load_*_config 函数
3. 避免重复读取配置文件
4. 支持缓存失效和热加载

使用方式（通过依赖注入）：
    from fastapi import Depends
    from app.api.dependencies import get_config
    
    @router.get("/settings")
    def get_settings(config: ConfigService = Depends(get_config)):
        return config.get_ecology_balance()
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Settings

logger = logging.getLogger(__name__)


class ConfigService:
    """统一配置服务
    
    负责：
    - 读取和缓存 UI 配置（data/settings.json）
    - 提供各类配置的访问接口
    - 支持配置更新和缓存失效
    - 线程安全的配置访问
    
    Attributes:
        settings: 全局静态配置（环境变量/默认值）
        _ui_config: 缓存的 UI 配置
        _lock: 线程锁
    """
    
    def __init__(self, settings: 'Settings') -> None:
        from .config import PROJECT_ROOT
        
        self.settings = settings
        self._ui_config_path = Path(settings.ui_config_path)
        self._project_root = PROJECT_ROOT
        self._ui_config = None
        self._ui_config_mtime: float = 0
        self._lock = RLock()
    
    def _load_ui_config_if_needed(self) -> None:
        """按需加载 UI 配置（带缓存）"""
        if not self._ui_config_path.exists():
            return
        
        try:
            current_mtime = self._ui_config_path.stat().st_mtime
            if self._ui_config is not None and current_mtime <= self._ui_config_mtime:
                return
            
            from ..models.config import UIConfig
            from ..repositories.environment_repository import environment_repository
            
            self._ui_config = environment_repository.load_ui_config(self._ui_config_path)
            self._ui_config_mtime = current_mtime
            logger.debug(f"[配置服务] 已加载 UI 配置: {self._ui_config_path}")
            
        except Exception as e:
            logger.warning(f"[配置服务] 加载 UI 配置失败: {e}")
    
    def invalidate_cache(self) -> None:
        """使配置缓存失效（配置更新后调用）"""
        with self._lock:
            self._ui_config = None
            self._ui_config_mtime = 0
            logger.debug("[配置服务] 配置缓存已失效")
    
    def get_ui_config(self) -> Any:
        """获取完整的 UI 配置
        
        Returns:
            UIConfig 对象，如果加载失败则返回默认值
        """
        from ..models.config import UIConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return UIConfig()
            return self._ui_config
    
    def get_ecology_balance(self) -> Any:
        """获取生态平衡配置
        
        Returns:
            EcologyBalanceConfig 对象
        """
        from ..models.config import EcologyBalanceConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return EcologyBalanceConfig()
            return self._ui_config.ecology_balance
    
    def get_mortality(self) -> Any:
        """获取死亡率配置
        
        Returns:
            MortalityConfig 对象
        """
        from ..models.config import MortalityConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return MortalityConfig()
            return self._ui_config.mortality
    
    def get_speciation(self) -> Any:
        """获取物种分化配置
        
        Returns:
            SpeciationConfig 对象
        """
        from ..models.config import SpeciationConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return SpeciationConfig()
            return self._ui_config.speciation
    
    def get_reproduction(self) -> Any:
        """获取繁殖配置
        
        Returns:
            ReproductionConfig 对象
        """
        from ..models.config import ReproductionConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return ReproductionConfig()
            return self._ui_config.reproduction
    
    def get_predation(self) -> Any:
        """获取捕食配置
        
        Returns:
            PredationConfig 对象
        """
        from ..models.config import PredationConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return PredationConfig()
            return self._ui_config.predation
    
    def get_plant_competition(self) -> Any:
        """获取植物竞争配置
        
        Returns:
            PlantCompetitionConfig 对象
        """
        from ..models.config import PlantCompetitionConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return PlantCompetitionConfig()
            return self._ui_config.plant_competition
    
    def get_ai_narrative(self) -> Any:
        """获取 AI 叙事配置
        
        Returns:
            AINarrativeConfig 对象
        """
        from ..models.config import AINarrativeConfig
        
        with self._lock:
            self._load_ui_config_if_needed()
            if self._ui_config is None:
                return AINarrativeConfig()
            return self._ui_config.ai_narrative
    
    # ========== 便捷方法 ==========
    
    def get_turn_years(self) -> int:
        """获取每回合代表的年数"""
        return self.settings.turn_years
    
    def get_global_carrying_capacity(self) -> int:
        """获取全球承载力"""
        return self.settings.global_carrying_capacity
    
    def is_generational_mortality_enabled(self) -> bool:
        """是否启用世代感知死亡率"""
        return self.settings.enable_generational_mortality
    
    def is_generational_growth_enabled(self) -> bool:
        """是否启用世代感知繁殖"""
        return self.settings.enable_generational_growth
    
    def is_dynamic_speciation_enabled(self) -> bool:
        """是否启用动态分化"""
        return self.settings.enable_dynamic_speciation


# ========== 已废弃：便捷函数 ==========

import warnings

_config_service_warned: bool = False


def get_config_service() -> ConfigService:
    """获取配置服务实例
    
    .. deprecated::
        请使用 ``api.dependencies`` 中的 ``Depends(get_config)``。
        此函数使用已废弃的全局容器单例。
        
    Warning:
        调用此函数会记录废弃警告。
    """
    global _config_service_warned
    
    if not _config_service_warned:
        warnings.warn(
            "get_config_service() 已废弃。请使用 api.dependencies 中的 Depends(get_config)，"
            "它会访问 app.state.container.config_service。",
            DeprecationWarning,
            stacklevel=2
        )
        _config_service_warned = True
    
    from .container import get_container
    return get_container().config_service

