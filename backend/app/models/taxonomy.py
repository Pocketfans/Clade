"""分类学模型 - 支持自动生成的类群分类树

【用途】
- 存储通过 embedding 聚类自动生成的生物分类
- 支持门-纲-目-科-属等多层级分类
- 记录类群的定义特征和成员物种
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Column, Field, JSON, SQLModel


class Clade(SQLModel, table=True):
    """类群（分支）- 通过 embedding 聚类生成的分类单元
    
    分类等级:
    - domain: 域（最高级，如"类真核生物"）
    - phylum: 门（如"类脊椎动物门"）
    - class_: 纲（如"类哺乳纲"）
    - order: 目（如"类食肉目"）
    - family: 科（如"类猫科"）
    - genus: 属（如"类虎属"）
    """
    __tablename__ = "clades"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # 基本信息
    name: str = Field(index=True)  # 类群名称（如"类脊椎动物门"）
    latin_name: str = ""  # 拉丁名风格名称
    rank: str = Field(index=True)  # 分类等级: domain/phylum/class/order/family/genus
    
    # 层级关系
    parent_clade_id: int | None = Field(default=None, index=True)  # 父类群ID
    depth: int = Field(default=0)  # 在分类树中的深度（0=根）
    
    # 聚类信息
    centroid_vector: list[float] = Field(default=[], sa_column=Column(JSON))  # 聚类中心向量
    cluster_id: int = 0  # 聚类算法分配的ID
    cohesion_score: float = 0.0  # 类群内聚度（0-1，越高越紧密）
    
    # 定义特征
    defining_traits: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    # 示例: {"主要特征": ["有脊柱", "恒温"], "典型器官": ["心脏四腔"]}
    
    description: str = ""  # LLM 生成的类群描述
    
    # 成员信息
    member_species_codes: list[str] = Field(default=[], sa_column=Column(JSON))  # 成员物种代码列表
    member_count: int = 0  # 成员物种数量
    
    # 元数据
    created_turn: int = 0  # 创建时的回合数
    last_updated_turn: int = 0  # 最后更新的回合数
    is_auto_generated: bool = True  # 是否自动生成（vs 手动定义）
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TaxonomyTree(SQLModel, table=True):
    """分类树快照 - 记录完整的分类树结构
    
    用于快速加载和展示分类树，避免每次都重新聚类
    """
    __tablename__ = "taxonomy_trees"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # 树信息
    name: str = "default"  # 分类树名称
    version: int = 1  # 版本号（每次重新聚类递增）
    turn_index: int = 0  # 生成时的回合数
    
    # 聚类参数
    clustering_params: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    # 示例: {"algorithm": "hierarchical", "n_clusters": [4, 8, 16], "threshold": 0.5}
    
    # 统计信息
    total_species: int = 0
    total_clades: int = 0
    max_depth: int = 0
    
    # 树结构（用于快速序列化/反序列化）
    tree_structure: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    # 示例: {"root": {"children": [{"id": 1, "name": "...", "children": [...]}]}}
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EmbeddedEvent(SQLModel, table=True):
    """带 embedding 的事件记录 - 用于事件相似度检索和叙事生成
    
    存储游戏中发生的各类事件及其向量表示
    """
    __tablename__ = "embedded_events"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # 事件基本信息
    event_type: str = Field(index=True)  # 事件类型
    # 类型包括: speciation(分化), extinction(灭绝), adaptation(适应), 
    #          migration(迁徙), mass_extinction(大灭绝), climate_change(气候变化)
    
    turn_index: int = Field(index=True)  # 发生回合
    
    # 事件描述
    title: str = ""  # 事件标题
    description: str = ""  # 事件详细描述
    
    # 向量表示
    embedding_vector: list[float] = Field(default=[], sa_column=Column(JSON))
    
    # 关联实体
    related_species_codes: list[str] = Field(default=[], sa_column=Column(JSON))  # 相关物种代码
    related_clade_ids: list[int] = Field(default=[], sa_column=Column(JSON))  # 相关类群ID
    affected_regions: list[int] = Field(default=[], sa_column=Column(JSON))  # 影响的区域ID
    
    # 事件属性
    severity: float = 0.0  # 严重程度 (0-1)
    novelty_score: float = 0.0  # 新颖度分数（与历史事件的差异）
    
    # 额外数据
    payload: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    # 可存储事件特定数据，如灭绝的物种数、气候变化幅度等
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvolutionPrediction(SQLModel, table=True):
    """演化预测记录 - 存储向量演化预测结果
    
    记录对物种未来演化方向的预测，用于验证和分析
    """
    __tablename__ = "evolution_predictions"
    
    id: int | None = Field(default=None, primary_key=True)
    
    # 预测对象
    species_code: str = Field(index=True)  # 被预测的物种代码
    species_name: str = ""  # 物种名称（快照）
    
    # 预测参数
    prediction_turn: int = Field(index=True)  # 预测发起的回合
    target_turn: int = 0  # 预测目标回合（预计多少回合后）
    
    # 压力向量
    applied_pressures: list[str] = Field(default=[], sa_column=Column(JSON))
    # 示例: ["cold_adaptation", "predation_pressure"]
    pressure_strengths: list[float] = Field(default=[], sa_column=Column(JSON))
    
    # 预测结果
    predicted_vector: list[float] = Field(default=[], sa_column=Column(JSON))  # 预测的未来向量
    predicted_traits: dict[str, float] = Field(default={}, sa_column=Column(JSON))  # 预测的特征变化
    predicted_description: str = ""  # LLM 生成的预测描述
    
    # 参考物种（向量空间中的近邻）
    reference_species_codes: list[str] = Field(default=[], sa_column=Column(JSON))
    reference_similarities: list[float] = Field(default=[], sa_column=Column(JSON))
    
    # 预测置信度
    confidence: float = 0.0  # 预测置信度 (0-1)
    
    # 验证结果（后续填充）
    actual_outcome: str = ""  # 实际结果描述
    accuracy_score: float | None = None  # 准确度评分
    verified_turn: int | None = None  # 验证时的回合数
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

