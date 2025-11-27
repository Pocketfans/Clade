from __future__ import annotations

import uuid
from fastapi import FastAPI

from .api.routes import router as api_router, initialize_environment, set_backend_session_id
from .api.admin_routes import router as admin_router
from .api.embedding_routes import router as embedding_router
from .core.config import get_settings, setup_logging
from .core.database import init_db

settings = get_settings()

# 初始化日志系统
setup_logging(settings)

app = FastAPI(title=settings.app_name)


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
