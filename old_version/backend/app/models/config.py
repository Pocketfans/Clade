from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CapabilityModelConfig(BaseModel):
    """单个 AI 能力的模型配置"""
    model_config = ConfigDict(extra="ignore")
    
    provider: str = "local"
    model: str = "default"
    base_url: str | None = None
    api_key: str | None = None
    timeout: int = 60


class UIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # 全局默认配置（向后兼容）
    ai_provider: str | None = None
    ai_model: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_timeout: int = 60
    
    # 分功能配置（新增）
    capability_configs: dict[str, CapabilityModelConfig] | None = None
    
    # Embedding 配置（会根据配置完整性自动启用）
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
