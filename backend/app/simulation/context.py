"""
SimulationContext - 回合内数据共享上下文

该模块定义了 SimulationContext 类，用于在单个回合的各个阶段之间共享数据。
所有阶段都通过读写 context 的字段来交换信息，避免了大量的局部变量传递。

设计原则：
1. 每个回合创建一个新的 SimulationContext 实例
2. 各阶段通过 context 读取输入、写入输出
3. 字段按功能分组，便于理解和维护
4. 使用 Optional 类型表示可能未初始化的字段
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from ..models.species import Species
    from ..models.environment import MapState, Tile, Habitat
    from ..schemas.requests import PressureConfig, TurnCommand
    from ..schemas.responses import (
        BackgroundSummary,
        BranchingEvent,
        EcosystemMetrics,
        MajorPressureEvent,
        MapChange,
        MigrationEvent,
        ReemergenceEvent,
        SpeciesSnapshot,
        TurnReport,
    )
    from ..services.species.niche import NicheMetrics
    from ..services.species.tiering import TieringResult
    from ..services.species.ai_pressure_response import SpeciesStatusEval
    from ..services.tectonic import TectonicStepResult
    from ..services.ecology.resource_manager import ResourceSnapshot
    from .species import MortalityResult


@dataclass
class SimulationContext:
    """回合内数据共享上下文
    
    该类承载单个回合内需要在各阶段之间共享的所有数据。
    字段按功能分组，每个阶段根据需要读取和写入相应字段。
    
    Attributes:
        # === 回合基础信息 ===
        turn_index: 当前回合索引
        command: 回合命令（包含压力配置和回合数）
        
        # === 压力与事件 ===
        pressures: 解析后的压力配置列表
        modifiers: 环境修正系数字典 {压力类型: 修正值}
        major_events: 本回合的重大事件列表
        pressure_context: 压力上下文字符串（用于AI评估）
        
        # === 地图与环境状态 ===
        current_map_state: 当前地图状态
        map_changes: 地图变化事件列表
        temp_delta: 温度变化量
        sea_delta: 海平面变化量
        tectonic_result: 板块构造运动结果
        
        # === 物种数据 ===
        all_species: 所有物种（含灭绝）
        species_batch: 存活物种列表
        extinct_codes: 已灭绝物种编码集合
        tiered: 物种分层结果
        
        # === 栖息地与地块 ===
        all_habitats: 所有栖息地记录
        all_tiles: 所有地块列表
        
        # === 生态分析结果 ===
        niche_metrics: 生态位分析结果
        trophic_interactions: 营养级互动数据
        food_web_analysis: 食物网分析结果
        
        # === 死亡率评估 ===
        preliminary_mortality: 初步死亡率结果（迁徙前）
        critical_results: Critical层死亡率结果
        focus_results: Focus层死亡率结果
        background_results: Background层死亡率结果
        combined_results: 合并后的最终死亡率结果
        
        # === 迁徙相关 ===
        migration_events: 迁徙事件列表
        migration_count: 成功迁徙数量
        symbiotic_follow_count: 共生物种追随数量
        cooldown_species: 处于迁徙冷却期的物种编码集合
        
        # === 种群更新 ===
        new_populations: 更新后的种群数量 {lineage_code: population}
        reproduction_results: 繁殖计算结果
        
        # === AI评估相关 ===
        ai_status_evals: AI状态评估结果 {lineage_code: SpeciesStatusEval}
        emergency_responses: 紧急响应信息列表
        narrative_results: AI叙事生成结果
        
        # === 基因与演化 ===
        activation_events: 基因激活事件列表
        gene_flow_count: 基因流动对数
        drift_count: 遗传漂变更新数
        auto_hybrids: 自动杂交产生的新物种
        adaptation_events: 适应性演化事件列表
        branching_events: 分化事件列表
        
        # === 背景物种管理 ===
        background_summary: 背景物种汇总
        mass_extinction: 是否检测到大灭绝
        reemergence_events: 重现事件列表
        
        # === 报告与输出 ===
        species_snapshots: 物种快照列表
        ecosystem_metrics: 生态系统指标
        report: 最终回合报告
        
        # === 插件数据 ===
        plugin_data: 插件间共享数据 {"plugin_name": {"key": value}}
        
        # === 回调函数 ===
        event_callback: 事件回调函数（用于发送SSE事件）
    """
    
    # === 回合基础信息 ===
    turn_index: int = 0
    command: TurnCommand | None = None
    
    # === 压力与事件 ===
    pressures: list[PressureConfig] = field(default_factory=list)
    modifiers: dict[str, float] = field(default_factory=dict)
    major_events: list[MajorPressureEvent] = field(default_factory=list)
    pressure_context: str = ""
    
    # === 地图与环境状态 ===
    current_map_state: MapState | None = None
    map_changes: list[MapChange] = field(default_factory=list)
    temp_delta: float = 0.0
    sea_delta: float = 0.0
    tectonic_result: TectonicStepResult | None = None
    
    # === 物种数据 ===
    all_species: list[Species] = field(default_factory=list)
    species_batch: list[Species] = field(default_factory=list)
    extinct_codes: set[str] = field(default_factory=set)
    tiered: TieringResult | None = None
    
    # === 栖息地与地块 ===
    all_habitats: list[Habitat] = field(default_factory=list)
    all_tiles: list[Tile] = field(default_factory=list)
    
    # === 生态分析结果 ===
    niche_metrics: dict[str, NicheMetrics] = field(default_factory=dict)
    trophic_interactions: dict[str, float] = field(default_factory=dict)
    food_web_analysis: Any = None  # FoodWebAnalysis 类型
    resource_snapshot: "ResourceSnapshot | None" = None  # 资源系统快照（NPP/承载力）
    
    # === 死亡率评估 ===
    preliminary_mortality: list[MortalityResult] = field(default_factory=list)
    critical_results: list[MortalityResult] = field(default_factory=list)
    focus_results: list[MortalityResult] = field(default_factory=list)
    background_results: list[MortalityResult] = field(default_factory=list)
    combined_results: list[MortalityResult] = field(default_factory=list)
    
    # === 迁徙相关 ===
    migration_events: list[MigrationEvent] = field(default_factory=list)
    migration_count: int = 0
    symbiotic_follow_count: int = 0
    cooldown_species: set[str] = field(default_factory=set)
    
    # === 种群更新 ===
    new_populations: dict[str, int] = field(default_factory=dict)
    reproduction_results: dict[str, int] = field(default_factory=dict)
    
    # === AI评估相关 ===
    ai_status_evals: dict[str, SpeciesStatusEval] = field(default_factory=dict)
    emergency_responses: list[dict] = field(default_factory=list)
    narrative_results: list[Any] = field(default_factory=list)
    
    # === 基因与演化 ===
    activation_events: list[dict] = field(default_factory=list)
    gene_flow_count: int = 0
    drift_count: int = 0
    auto_hybrids: list[Species] = field(default_factory=list)
    adaptation_events: list[dict] = field(default_factory=list)
    branching_events: list[BranchingEvent] = field(default_factory=list)
    
    # === 背景物种管理 ===
    background_summary: list[BackgroundSummary] = field(default_factory=list)
    mass_extinction: bool = False
    reemergence_events: list[ReemergenceEvent] = field(default_factory=list)
    
    # === 报告与输出 ===
    species_snapshots: list[SpeciesSnapshot] = field(default_factory=list)
    ecosystem_metrics: EcosystemMetrics | None = None
    report: TurnReport | None = None
    
    # === Embedding 集成 ===
    embedding_turn_data: dict = field(default_factory=dict)
    
    # === 插件数据共享 ===
    # 用于插件之间的数据交换，避免动态属性
    # 结构: {"plugin_name": {"key": value, ...}, ...}
    plugin_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    
    # === 生态智能体评估 ===
    biological_assessment_results: dict = field(default_factory=dict)  # {lineage_code: BiologicalAssessment}
    species_priority_partition: Any = None  # PartitionResult
    modifier_applicator: Any = None  # ModifierApplicator 实例
    
    # === 回调函数 ===
    event_callback: Callable[[str, str, str], None] | None = None
    
    def emit_event(self, event_type: str, message: str, category: str = "其他", **extra) -> None:
        """发送事件到前端
        
        Args:
            event_type: 事件类型（如 "stage", "info", "warning" 等）
            message: 事件消息
            category: 事件分类
            **extra: 额外数据
        """
        if self.event_callback:
            try:
                self.event_callback(event_type, message, category, **extra)
            except Exception:
                pass  # 忽略回调错误
    
    def get_alive_species_count(self) -> int:
        """获取存活物种数量"""
        return len(self.species_batch)
    
    def get_total_population(self) -> int:
        """获取总种群数量"""
        return sum(
            sp.morphology_stats.get("population", 0) or 0
            for sp in self.species_batch
        )
    
    def has_critical_species(self) -> bool:
        """是否有Critical层物种"""
        return self.tiered is not None and len(self.tiered.critical) > 0
    
    def get_pressure_summary(self) -> str:
        """获取压力摘要字符串"""
        if not self.modifiers:
            return "环境稳定"
        return "; ".join([
            f"{k}: {v:.1f}" for k, v in self.modifiers.items() if abs(v) > 0.1
        ])

