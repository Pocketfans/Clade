from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# 服务商 API 类型常量
PROVIDER_TYPE_OPENAI = "openai"       # OpenAI 兼容格式（包括DeepSeek、硅基流动等）
PROVIDER_TYPE_ANTHROPIC = "anthropic"  # Claude 原生 API
PROVIDER_TYPE_GOOGLE = "google"        # Gemini 原生 API


class ProviderConfig(BaseModel):
    """AI 服务商配置"""
    model_config = ConfigDict(extra="ignore")
    
    id: str  # 唯一标识符，如 "provider_123" 或 "openai_main"
    name: str # 显示名称，如 "My OpenAI"
    type: str = "openai"  # 兼容旧字段，实际使用 provider_type
    provider_type: str = PROVIDER_TYPE_OPENAI  # API 类型：openai, anthropic, google
    base_url: str | None = None
    api_key: str | None = None
    
    # 预设模型列表（可选，用于前端自动补全）
    models: list[str] = []
    # 用户选择保存的模型列表
    selected_models: list[str] = []


class CapabilityRouteConfig(BaseModel):
    """功能路由配置"""
    model_config = ConfigDict(extra="ignore")
    
    provider_id: str | None = None  # 引用 ProviderConfig.id（单服务商模式）
    provider_ids: list[str] | None = None  # 多服务商池（负载均衡模式）
    model: str | None = None        # 具体模型名称
    timeout: int = 60
    enable_thinking: bool = False   # 是否开启思考模式（如DeepSeek-R1/SiliconFlow）


class UIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 1. 服务商库 (Provider Library)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    
    # 2. 全局默认设置
    default_provider_id: str | None = None
    default_model: str | None = None
    ai_concurrency_limit: int = 15  # AI 并发限制
    
    # 3. 功能路由表 (Routing Table)
    # Key: capability_name (e.g., "turn_report", "speciation")
    capability_routes: dict[str, CapabilityRouteConfig] = Field(default_factory=dict)
    
    # 4. Embedding 配置
    embedding_provider_id: str | None = None
    embedding_model: str | None = None
    
    # 5. 自动保存配置
    autosave_enabled: bool = True  # 是否启用自动保存
    autosave_interval: int = 1     # 每N回合自动保存一次
    autosave_max_slots: int = 5    # 最大自动保存槽位数
    
    # 6. AI 推演超时配置
    ai_species_eval_timeout: int = 60    # 单物种AI评估超时（秒）
    ai_batch_eval_timeout: int = 180     # 整体批量评估超时（秒）
    ai_narrative_timeout: int = 60       # 物种叙事生成超时（秒）
    ai_speciation_timeout: int = 120     # 物种分化评估超时（秒）
    
    # 7. 负载均衡配置
    load_balance_enabled: bool = False   # 是否启用多服务商负载均衡
    load_balance_strategy: str = "round_robin"  # 负载均衡策略: round_robin, random, least_latency
    
    # 8. AI 叙事开关
    ai_narrative_enabled: bool = False   # 是否启用 AI 生成物种叙事（默认关闭，节省 API 调用）
    
    # 9. 回合报告 LLM 开关（与物种叙事分开）
    turn_report_llm_enabled: bool = True  # 是否启用 LLM 生成回合总结（默认开启）
    
    # --- Legacy Fields (Keep for migration) ---
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_timeout: int = 60
    # 旧版 capability_configs (dict[str, CapabilityModelConfig])
    capability_configs: dict | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
