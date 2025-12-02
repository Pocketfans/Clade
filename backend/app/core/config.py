from __future__ import annotations

import logging
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


# Calculate project root (3 levels up from config.py: core -> app -> backend -> E-game)
# config.py is in backend/app/core/config.py
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Global configuration for the evolutionary sandbox."""

    app_name: str = "Clade"
    # 服务端口配置
    backend_port: int = Field(default=8022, alias="BACKEND_PORT")
    frontend_port: int = Field(default=5188, alias="FRONTEND_PORT")
    database_url: str = Field(default=f"sqlite:///{PROJECT_ROOT.as_posix()}/data/db/egame.db", alias="DATABASE_URL")
    embedding_provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    report_model: str = Field(default="gpt-large", alias="REPORT_MODEL")
    lineage_model: str = Field(default="gpt-medium", alias="LINEAGE_MODEL")
    speciation_model: str = Field(default="", alias="SPECIATION_MODEL")  # 空表示使用 UI 配置的默认模型
    species_gen_model: str = Field(default="", alias="SPECIES_GEN_MODEL")  # 空表示使用 UI 配置的默认模型
    batch_rule_limit: int = 50
    map_width: int = 128
    map_height: int = 40
    data_dir: str = str(PROJECT_ROOT / "data")
    reports_dir: str = str(PROJECT_ROOT / "data/reports")
    exports_dir: str = str(PROJECT_ROOT / "data/exports")
    saves_dir: str = str(PROJECT_ROOT / "data/saves")
    cache_dir: str = str(PROJECT_ROOT / "data/cache")
    # 全球承载力：使用JavaScript安全整数上限，让生态因素决定实际软上限
    # 9_007_199_254_740_991 ≈ 9千万亿，远超地球生物量，但数值安全
    global_carrying_capacity: int = 9_007_199_254_740_991
    background_population_threshold: int = 50_000
    mass_extinction_threshold: float = 0.6
    background_promotion_quota: int = 3
    critical_species_limit: int = 3
    focus_batch_size: int = 4  # 【优化】减小批量大小，提高并发数
    focus_batch_limit: int = 3
    use_report_v2: bool = Field(default=True, alias="USE_REPORT_V2")  # 使用并行化报告生成器
    minor_pressure_window: int = 10
    escalation_threshold: int = 80
    high_event_cooldown: int = 5
    ai_base_url: str | None = Field(default=None, alias="AI_BASE_URL")
    ai_api_key: str | None = Field(default=None, alias="AI_API_KEY")
    ai_request_timeout: int = Field(default=60, alias="AI_TIMEOUT")
    ai_concurrency_limit: int = Field(default=15, alias="AI_CONCURRENCY_LIMIT")
    ui_config_path: str = Field(default=str(PROJECT_ROOT / "data/settings.json"))
    
    # ========== 演化时间尺度配置 ==========
    # 控制是否启用世代感知的演化模型（50万年/回合的精确模拟）
    enable_generational_mortality: bool = Field(default=True, alias="ENABLE_GENERATIONAL_MORTALITY")
    enable_generational_growth: bool = Field(default=True, alias="ENABLE_GENERATIONAL_GROWTH")
    enable_dynamic_speciation: bool = Field(default=True, alias="ENABLE_DYNAMIC_SPECIATION")
    
    # 回合代表的年数（默认50万年）
    turn_years: int = Field(default=500_000, alias="TURN_YEARS")
    
    # 世代数缩放参数（用于调节快速繁殖生物的演化速率）
    generation_scale_factor: float = Field(default=8.0, alias="GENERATION_SCALE_FACTOR")
    
    # ========== 物种分化平衡参数 ==========
    # 分化冷却期（回合数）：分化后多少回合内不能再次分化
    # 【早期分化优化】改为 0，允许连续分化（代码中 turn<5 时额外跳过冷却）
    speciation_cooldown_turns: int = Field(default=0, alias="SPECIATION_COOLDOWN_TURNS")
    # 物种密度软上限：超过此数量后分化概率开始衰减
    species_soft_cap: int = Field(default=60, alias="SPECIES_SOFT_CAP")
    # 基础分化概率（0-1）- 50万年/回合尺度下应很高
    base_speciation_rate: float = Field(default=0.50, alias="BASE_SPECIATION_RATE")
    # 最大子种数量
    max_offspring_count: int = Field(default=6, alias="MAX_OFFSPRING_COUNT")
    
    # ========== 遗传距离与基因交流平衡参数 ==========
    # 时间分化分母（N回合达到最大时间距离）：30表示30回合(1500万年)完全分化
    time_divergence_scale: int = Field(default=30, alias="TIME_DIVERGENCE_SCALE")
    # 每回合遗传漂变增量（模拟突变积累）- 提高以加速遗传分化
    genetic_drift_per_turn: float = Field(default=0.012, alias="GENETIC_DRIFT_PER_TURN")
    # 基因交流遗传距离阈值（超过此值停止交流）- 略微放宽
    gene_flow_distance_threshold: float = Field(default=0.32, alias="GENE_FLOW_DISTANCE_THRESHOLD")
    # 基因交流地理重叠阈值（低于此值视为隔离）
    gene_flow_overlap_threshold: float = Field(default=0.10, alias="GENE_FLOW_OVERLAP_THRESHOLD")
    # 自动杂交检测概率（每回合检测同属近缘物种杂交的概率）- 提高以增加杂交事件
    auto_hybridization_chance: float = Field(default=0.18, alias="AUTO_HYBRIDIZATION_CHANCE")
    # 杂交遗传距离上限（超过此值无法杂交）- 略微放宽允许更多杂交
    hybridization_distance_max: float = Field(default=0.50, alias="HYBRIDIZATION_DISTANCE_MAX")
    
    # ========== AI 功能开关 ==========
    # 回合报告 LLM 叙事开关（与 AI 物种叙事分开控制）
    # True: 使用 LLM 生成每回合的整体总结/叙事
    # False: 使用简单模板生成回合报告，节省 Token
    enable_turn_report_llm: bool = Field(default=True, alias="ENABLE_TURN_REPORT_LLM")
    
    # 日志配置
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: str = Field(default=str(PROJECT_ROOT / "data/logs"))
    log_to_file: bool = Field(default=True, alias="LOG_TO_FILE")
    log_to_console: bool = Field(default=True, alias="LOG_TO_CONSOLE")

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",  # 明确指定UTF-8编码
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
    # 关闭 uvicorn 访问日志
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    root_logger.info(f"日志系统初始化完成 - 级别: {settings.log_level}, 目录: {settings.log_dir}")


def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
