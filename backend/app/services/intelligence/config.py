"""
Ecological Intelligence Configuration - 生态智能体配置

所有可调参数集中管理，便于调优和覆盖。
"""

from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class IntelligenceConfig:
    """生态智能体配置
    
    Attributes:
        top_a_count: A 档（高优先级）物种数量
        top_b_count: B 档（中优先级）物种数量
        risk_weight: 风险权重（用于 priority 计算）
        impact_weight: 生态影响权重
        potential_weight: 潜力权重
        priority_threshold: 进入 LLM 评估的最低优先级阈值
        mortality_mod_range: 死亡率调节因子范围
        r_adjust_range: 繁殖率调节范围
        k_adjust_range: 承载力调节范围（相对于基础值的比例）
        migration_bias_range: 迁徙偏向范围
        enable_llm_calls: 是否启用 LLM 调用
        max_llm_tokens_per_turn: 每回合最大 LLM token 数
        llm_timeout_seconds: LLM 调用超时时间
        use_parallel_batches: 是否并行执行 A/B 批次
    """
    # === 分档参数 ===
    top_a_count: int = 5
    top_b_count: int = 15
    
    # === 优先级权重 ===
    risk_weight: float = 0.5
    impact_weight: float = 0.3
    potential_weight: float = 0.2
    
    # === 阈值 ===
    priority_threshold: float = 0.4
    
    # === 数值修正范围 ===
    mortality_mod_range: Tuple[float, float] = (0.3, 1.8)
    r_adjust_range: Tuple[float, float] = (-0.3, 0.3)
    k_adjust_range: Tuple[float, float] = (-0.5, 0.5)
    migration_bias_range: Tuple[float, float] = (-1.0, 1.0)
    
    # === LLM 控制 ===
    enable_llm_calls: bool = True
    max_llm_tokens_per_turn: int = 50000
    llm_timeout_seconds: float = 60.0
    use_parallel_batches: bool = True
    
    # === 降级策略 ===
    fallback_mortality_modifier: float = 1.0
    fallback_r_adjust: float = 0.0
    fallback_k_adjust: float = 0.0
    
    # === 评分参数 ===
    death_rate_critical_threshold: float = 0.5  # 死亡率超过此值视为高风险
    death_rate_warning_threshold: float = 0.3   # 死亡率超过此值视为警告
    population_critical_threshold: int = 100    # 种群低于此值视为濒危
    biomass_high_impact_threshold: float = 0.1  # 生物量占比超过此值视为高影响
    
    # === Embedding 参数 ===
    use_embedding_scoring: bool = True
    embedding_fitness_weight: float = 0.4  # fitness 在评分中的权重


# 默认配置实例
DEFAULT_CONFIG = IntelligenceConfig()


def load_config_from_yaml(yaml_path: str | None = None) -> IntelligenceConfig:
    """从 YAML 文件加载配置
    
    Args:
        yaml_path: YAML 配置文件路径，如果为 None 则返回默认配置
        
    Returns:
        配置实例
    """
    if yaml_path is None:
        return DEFAULT_CONFIG
    
    try:
        import yaml
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # 从 YAML 中提取 intelligence 配置部分
        intel_config = data.get('intelligence', {})
        
        # 合并到默认配置
        config_dict = {}
        for key, value in intel_config.items():
            if hasattr(DEFAULT_CONFIG, key):
                config_dict[key] = value
        
        return IntelligenceConfig(**config_dict)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"加载配置失败: {e}，使用默认配置")
        return DEFAULT_CONFIG


