from __future__ import annotations

import logging
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Global configuration for the evolutionary sandbox."""

    app_name: str = "EvoSandbox"
    database_url: str = Field(default="sqlite:///data/db/egame.db", alias="DATABASE_URL")
    embedding_provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    report_model: str = Field(default="gpt-large", alias="REPORT_MODEL")
    lineage_model: str = Field(default="gpt-medium", alias="LINEAGE_MODEL")
    batch_rule_limit: int = 50
    map_width: int = 80
    map_height: int = 40
    reports_dir: str = "data/reports"
    exports_dir: str = "data/exports"
    saves_dir: str = "data/saves"
    cache_dir: str = "data/cache"
    global_carrying_capacity: int = 100_000_000  # 全球承载力1亿（适应微生物大种群）
    background_population_threshold: int = 50_000
    mass_extinction_threshold: float = 0.6
    background_promotion_quota: int = 3
    critical_species_limit: int = 3
    focus_batch_size: int = 8
    focus_batch_limit: int = 3
    minor_pressure_window: int = 10
    escalation_threshold: int = 80
    high_event_cooldown: int = 5
    ai_base_url: str | None = Field(default=None, alias="AI_BASE_URL")
    ai_api_key: str | None = Field(default=None, alias="AI_API_KEY")
    ai_request_timeout: int = Field(default=60, alias="AI_TIMEOUT")
    ui_config_path: str = Field(default="data/settings.json")
    
    # 日志配置
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: str = Field(default="data/logs")
    log_to_file: bool = Field(default=True, alias="LOG_TO_FILE")
    log_to_console: bool = Field(default=True, alias="LOG_TO_CONSOLE")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def setup_logging(settings: Settings) -> None:
    """配置全局日志系统
    
    Args:
        settings: 应用配置对象
    """
    # 创建日志目录
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取日志级别
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # 配置根logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除已存在的handlers，避免重复输出
    root_logger.handlers.clear()
    
    # 日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 文件handler
    if settings.log_to_file:
        file_handler = logging.FileHandler(
            log_dir / "simulation.log",
            encoding='utf-8',
            mode='a'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # 控制台handler
    if settings.log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # 设置第三方库日志级别（避免干扰）
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    
    root_logger.info(f"日志系统初始化完成 - 级别: {settings.log_level}, 目录: {settings.log_dir}")


def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
