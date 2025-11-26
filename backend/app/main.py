from __future__ import annotations

from fastapi import FastAPI

from .api.routes import router as api_router, initialize_environment
from .api.admin_routes import router as admin_router
from .core.config import get_settings, setup_logging
from .core.database import init_db
from .core.seed import seed_defaults

settings = get_settings()

# 初始化日志系统
setup_logging(settings)

app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    seed_defaults()
    initialize_environment()


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
