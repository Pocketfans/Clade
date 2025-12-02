"""
Clade 后端入口

此模块是 FastAPI 应用的入口点，负责：
1. 初始化依赖注入容器
2. 配置中间件
3. 注册路由
4. 应用生命周期管理

架构说明：
- 服务实例化: core/container.py (ServiceContainer)
- 会话状态管理: core/session.py (SimulationSessionManager)
- 配置管理: core/config_service.py (ConfigService)
- 路由拆分: api/*.py (simulation/species/divine/ecosystem/analytics)

生命周期：
- 容器和会话在 lifespan 上下文中实例化
- 存储在 app.state 中供显式依赖注入使用
- 依赖项通过 Depends() 访问，不使用全局单例
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .core.config import get_settings, setup_logging
from .core.database import init_db

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件 - 使用结构化日志记录请求信息"""
    
    IGNORED_PATHS = {
        "/api/queue",
        "/api/energy", 
        "/api/hints",
        "/api/health",
        "/health",
    }
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # 提取请求信息
        client_host = request.client.host if request.client else "unknown"
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""
        
        # 获取会话 ID（用于日志关联，启动期间可能不存在）
        session_id = ""
        if hasattr(request.app.state, 'session'):
            session = request.app.state.session
            session_id = session.session_id[:8] if session.session_id else ""
        
        # 执行请求
        response = await call_next(request)
        
        duration_ms = (time.time() - start_time) * 1000
        status_code = response.status_code
        
        # 跳过高频轮询的正常响应
        if path in self.IGNORED_PATHS and status_code < 400:
            return response
        
        # 结构化日志
        log_extra = {
            "method": method,
            "path": path,
            "status": status_code,
            "duration_ms": round(duration_ms, 1),
            "client": client_host,
            "session": session_id,
        }
        if query:
            log_extra["query"] = query
        
        # 根据状态码选择日志级别
        if status_code >= 500:
            logger.error(f"HTTP {status_code} {method} {path}", extra=log_extra)
        elif status_code >= 400:
            logger.warning(f"HTTP {status_code} {method} {path}", extra=log_extra)
        else:
            logger.debug(f"HTTP {status_code} {method} {path}", extra=log_extra)
        
        return response


def _disable_windows_quickedit() -> None:
    """禁用 Windows 控制台的快速编辑模式
    
    快速编辑模式会导致点击控制台窗口时程序暂停。
    包装在 try/except 中避免阻塞导入。
    """
    if sys.platform != "win32":
        return
    
    try:
        import ctypes
        from ctypes import wintypes
        
        kernel32 = ctypes.windll.kernel32
        
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080
        STD_INPUT_HANDLE = -10
        
        handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        if handle == -1:
            return
        
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return
        
        new_mode = (mode.value | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE
        kernel32.SetConsoleMode(handle, new_mode)
        
        logger.info("[系统] 已禁用 Windows 控制台快速编辑模式")
    except Exception as e:
        logger.debug(f"[系统] 禁用快速编辑模式失败（不影响功能）: {e}")


# 初始化日志系统（在任何其他操作之前）
settings = get_settings()
setup_logging(settings)

# 禁用 Windows 快速编辑模式
_disable_windows_quickedit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期上下文管理器
    
    替代已废弃的 @app.on_event("startup") 模式。
    容器和会话在此实例化并存储到 app.state 中，
    用于显式依赖注入。
    
    优势：
    - 显式生命周期管理
    - 容器/会话通过 app.state 访问（不使用全局单例）
    - 更容易使用隔离实例进行测试
    - 清晰的启动/关闭边界
    """
    from .core.container import ServiceContainer
    from .core.session import SimulationSessionManager
    
    # 创建实例（不使用全局单例）
    session = SimulationSessionManager()
    container = ServiceContainer()
    
    # 生成会话 ID
    backend_session_id = session.generate_session_id()
    logger.info(f"[启动] 会话ID: {backend_session_id[:8]}...")
    
    # 初始化数据库
    init_db()
    
    # 初始化服务容器
    container.initialize()
    
    # 存储到 app.state 供依赖注入使用
    app.state.container = container
    app.state.session = session
    
    logger.info("[启动] 服务容器初始化完成")
    
    yield  # 应用在此运行
    
    # 关闭时清理（如需要）
    logger.info("[关闭] 应用正在关闭")


# 创建 FastAPI 应用（使用 lifespan）
app = FastAPI(title=settings.app_name, lifespan=lifespan)

# 添加请求日志中间件
app.add_middleware(RequestLoggingMiddleware)


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, str]:
    """基础健康检查"""
    return {"status": "ok"}


@app.get("/api/health", tags=["system"])
def api_healthcheck(request: Request) -> dict[str, str]:
    """API 健康检查（带会话信息）
    
    使用 app.state.session 获取 lifespan 管理的实例。
    """
    session_id = ""
    if hasattr(request.app.state, 'session'):
        session = request.app.state.session
        session_id = session.session_id[:8] + "..." if session.session_id else ""
    
    return {
        "status": "ok",
        "session_id": session_id,
    }


# ========== 路由注册 ==========

# 主 API 路由（聚合 simulation/species/divine/ecosystem/analytics）
from .api.router import router as api_router
app.include_router(api_router, prefix="/api")

# 其他路由
from .api.admin_routes import router as admin_router
from .api.embedding_routes import router as embedding_router

app.include_router(admin_router, prefix="/api")
app.include_router(embedding_router)  # 已包含 /api/embedding 前缀
