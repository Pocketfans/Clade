"""生态学服务模块

提供生态系统模拟的核心服务：
- ResourceManager: 资源管理（NPP、承载力）
- SemanticAnchorService: 语义锚点（embedding语义匹配）
- EcologicalRealismService: 生态拟真（高级生态学机制）
"""

from .resource_manager import (
    ResourceManager,
    TileResourceState,
    ResourceSnapshot,
    get_resource_manager,
)

from .semantic_anchors import (
    SemanticAnchorService,
    SemanticAnchor,
    SEMANTIC_ANCHORS,
    get_semantic_anchor_service,
)

from .ecological_realism import (
    EcologicalRealismService,
    EcologicalRealismConfig,
    AlleeEffectResult,
    DiseaseResult,
    VerticalNicheResult,
    MutualismLink,
    get_ecological_realism_service,
)

__all__ = [
    # Resource Manager
    "ResourceManager",
    "TileResourceState",
    "ResourceSnapshot",
    "get_resource_manager",
    # Semantic Anchors
    "SemanticAnchorService",
    "SemanticAnchor",
    "SEMANTIC_ANCHORS",
    "get_semantic_anchor_service",
    # Ecological Realism
    "EcologicalRealismService",
    "EcologicalRealismConfig",
    "AlleeEffectResult",
    "DiseaseResult",
    "VerticalNicheResult",
    "MutualismLink",
    "get_ecological_realism_service",
]






