from __future__ import annotations

import sys
import time
import uuid
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from .api.routes import router as api_router, initialize_environment, set_backend_session_id
from .api.admin_routes import router as admin_router
from .api.embedding_routes import router as embedding_router
from .core.config import get_settings, setup_logging
from .core.database import init_db


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件 - 记录所有请求的 URL、方法、状态码等信息，便于调试 404 等问题"""
    
    # 忽略的高频轮询路径（不打印日志）
    IGNORED_PATHS = {
        "/api/queue",
        "/api/energy", 
        "/api/hints",
        "/api/health",
    }
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # 获取客户端信息
        client_host = request.client.host if request.client else "unknown"
        method = request.method
        url = str(request.url)
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""
        
        # 执行请求
        response = await call_next(request)
        
        # 计算耗时
        duration_ms = (time.time() - start_time) * 1000
        status_code = response.status_code
        
        # 跳过高频轮询请求的日志（除非出错）
        if path in self.IGNORED_PATHS and status_code < 400:
            return response
        
        # 根据状态码选择日志级别和颜色
        if status_code >= 500:
            level = "❌ ERROR"
        elif status_code >= 400:
            level = "⚠️ WARN "
        elif status_code >= 300:
            level = "↗️ REDIR"
        else:
            level = "✅ OK   "
        
        # 打印请求日志
        log_line = f"[{level}] {status_code} | {method:6} | {path}"
        if query:
            log_line += f"?{query}"
        log_line += f" | {duration_ms:.0f}ms | {client_host}"
        
        # 对于 404 错误，打印更详细的信息
        if status_code == 404:
            print(f"\n{'='*60}")
            print(f"[404 详细信息]")
            print(f"  完整 URL: {url}")
            print(f"  路径: {path}")
            print(f"  方法: {method}")
            print(f"  客户端: {client_host}")
            print(f"  查询参数: {query or '无'}")
            print(f"{'='*60}\n")
        
        print(log_line)
        
        return response


def disable_windows_quickedit() -> None:
    """禁用 Windows 控制台的快速编辑模式
    
    快速编辑模式会导致：当用户点击控制台窗口时，程序会暂停输出，
    直到按键才继续。这在 LLM 调用等长时间运行的任务中会造成"卡住"假象。
    
    此函数通过 Windows API 禁用该功能，让程序可以持续运行。
    """
    if sys.platform != "win32":
        return
    
    try:
        import ctypes
        from ctypes import wintypes
        
        kernel32 = ctypes.windll.kernel32
        
        # 控制台模式标志
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080
        
        # 获取标准输入句柄
        STD_INPUT_HANDLE = -10
        handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        
        if handle == -1:
            return
        
        # 获取当前控制台模式
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return
        
        # 禁用快速编辑模式，启用扩展标志
        new_mode = (mode.value | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE
        kernel32.SetConsoleMode(handle, new_mode)
        
        print("[系统] 已禁用 Windows 控制台快速编辑模式（防止点击窗口导致程序暂停）")
    except Exception as e:
        # 静默失败，不影响程序运行
        print(f"[系统] 禁用快速编辑模式失败（不影响功能）: {e}")


# 在导入阶段就禁用快速编辑模式，确保最早生效
disable_windows_quickedit()

settings = get_settings()

# 初始化日志系统
setup_logging(settings)

app = FastAPI(title=settings.app_name)

# 添加请求日志中间件（帮助调试 404 等连接问题）
app.add_middleware(RequestLoggingMiddleware)


@app.on_event("startup")
def on_startup() -> None:
    # 生成后端会话ID（每次后端启动都会生成新的）
    # 这用于让前端检测后端是否重启
    backend_session_id = str(uuid.uuid4())
    set_backend_session_id(backend_session_id)
    print(f"[后端启动] 会话ID: {backend_session_id[:8]}...")
    
    init_db()
    # 注意：不再在启动时调用 seed_defaults()
    # 初始物种应该在创建存档时根据剧本类型生成
    initialize_environment()


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(embedding_router)  # 已包含 /api/embedding 前缀
