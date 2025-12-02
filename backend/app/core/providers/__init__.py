"""
服务提供者 - 按领域划分的服务工厂

此包包含按领域组织服务创建的提供者模块：
- repositories: 数据访问层（物种、环境、历史、属）
- core_services: 基础服务（嵌入、模型路由、配置）
- species_services: 物种相关服务（分化、生态位、分层等）
- simulation_services: 模拟引擎及相关服务
- analytics_services: 报告和分析服务

使用方式：
    这些提供者被 ServiceContainer 用来创建服务。
    每个提供者是一个 mixin 类，添加 cached_property 方法。
"""

from .repositories import RepositoryProvider
from .core_services import CoreServiceProvider
from .species_services import SpeciesServiceProvider
from .simulation_services import SimulationServiceProvider
from .analytics_services import AnalyticsServiceProvider

__all__ = [
    "RepositoryProvider",
    "CoreServiceProvider", 
    "SpeciesServiceProvider",
    "SimulationServiceProvider",
    "AnalyticsServiceProvider",
]

