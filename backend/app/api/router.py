"""
API 路由聚合器

此模块负责聚合所有子路由模块，并提供公共依赖。
重构后的路由结构：
- simulation.py: 回合推演、存档管理
- species.py: 物种管理、干预控制
- divine.py: 能量系统、成就、杂交
- ecosystem.py: 食物网、生态健康
- analytics.py: 导出、诊断、配置

原 routes.py 的职责现在分散到：
- 服务实例化 -> core/container.py (ServiceContainer)
- 全局状态 -> core/session.py (SimulationSessionManager)
- 配置管理 -> core/config_service.py (ConfigService)
- 业务路由 -> api/*.py (各子模块)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from . import analytics, divine, ecosystem, simulation, species

logger = logging.getLogger(__name__)

# 创建主路由器
router = APIRouter()

# 聚合所有子路由
router.include_router(simulation.router)
router.include_router(species.router)
router.include_router(divine.router)
router.include_router(ecosystem.router)
router.include_router(analytics.router)


def get_all_routers() -> list[APIRouter]:
    """获取所有子路由器（用于测试或文档生成）"""
    return [
        simulation.router,
        species.router,
        divine.router,
        ecosystem.router,
        analytics.router,
    ]


# 导出供 main.py 使用
__all__ = ["router", "get_all_routers"]



