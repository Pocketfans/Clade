"""
Simulation Engine - 模拟引擎（瘦中枢）

SimulationEngine 是模拟系统的核心调度器，负责：
1. 依赖注入：在构造函数中注入各类 service / repository / 配置
2. 模式管理：初始化 Pipeline、切换运行模式、加载 Stage
3. 回合调度：通过 run_turns_async() 驱动 Pipeline 执行回合

设计原则：
- 不承载具体业务逻辑，所有业务逻辑在 Stage 和 Service 中
- 作为"薄调度器"，只负责协调各组件
- 新业务规则应以 Stage 形式加入，不应直接在 Engine 中添加

遗留实现：
- 如需使用旧版回合逻辑进行回归测试，请使用 LegacyTurnRunner
- 参见: simulation/legacy_engine.py
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="ignore")
    except ValueError:
        pass

logger = logging.getLogger(__name__)

# 核心依赖
from .context import SimulationContext
from ..schemas.requests import TurnCommand
from ..schemas.responses import TurnReport

# 服务导入
from ..services.species.adaptation import AdaptationService
from ..services.species.ai_pressure_response import create_ai_pressure_service
from ..services.species.gene_activation import GeneActivationService
from ..services.species.gene_flow import GeneFlowService
from ..services.species.trophic_interaction import TrophicInteractionService
from ..services.species.food_web_manager import FoodWebManager

if TYPE_CHECKING:
    from ..services.species.background import BackgroundSpeciesManager

from ..services.analytics.critical_analyzer import CriticalAnalyzer
from ..services.analytics.exporter import ExportService
from ..services.system.embedding import EmbeddingService
from ..services.analytics.focus_processor import FocusBatchProcessor
from ..services.geo.map_evolution import MapEvolutionService
from ..services.geo.map_manager import MapStateManager
from ..services.species.migration import MigrationAdvisor
from ..services.species.reproduction import ReproductionService
from ..ai.model_router import ModelRouter
from ..services.species.niche import NicheAnalyzer
from ..services.system.pressure import PressureEscalationService
from ..services.analytics.report_builder import ReportBuilder
from ..services.species.speciation import SpeciationService
from ..services.species.tiering import SpeciesTieringService
from .environment import EnvironmentSystem
from .species import MortalityEngine
from .tile_based_mortality import TileBasedMortalityEngine
from ..services.analytics.embedding_integration import EmbeddingIntegrationService
from ..services.tectonic import TectonicIntegration, create_tectonic_integration


class SimulationEngine:
    """模拟引擎 - 负责模式选择与 Pipeline 调度
    
    SimulationEngine 是一个"瘦中枢"，不再承载具体业务逻辑。
    所有回合业务逻辑已迁移到 Stage 和 Service 中。
    
    核心方法：
    - set_mode(mode): 切换运行模式 (minimal/standard/full/debug)
    - run_turns_async(command): 执行多个回合（统一使用 Pipeline）
    - run_turn_with_pipeline(command): 执行单个回合
    - get_pipeline_metrics(): 获取执行性能指标
    
    服务属性（供 Stage 访问）：
    - trophic_service: 营养级互动服务
    - report_builder: 报告构建器
    - 其他注入的服务...
    
    扩展指南：
    - 新业务规则应以 Stage 形式加入（参见 stages.py, PLUGIN_GUIDE.md）
    - 新领域服务应加入 services/ 目录
    - 不应直接在 Engine 中添加业务逻辑
    """
    
    def __init__(
        self,
        environment: EnvironmentSystem,
        mortality: MortalityEngine,
        embeddings: EmbeddingService,
        router: ModelRouter,
        report_builder: ReportBuilder,
        exporter: ExportService,
        niche_analyzer: NicheAnalyzer,
        speciation: SpeciationService,
        background_manager: "BackgroundSpeciesManager",
        tiering: SpeciesTieringService,
        focus_processor: FocusBatchProcessor,
        critical_analyzer: CriticalAnalyzer,
        escalation_service: PressureEscalationService,
        map_evolution: MapEvolutionService,
        migration_advisor: MigrationAdvisor,
        map_manager: MapStateManager,
        reproduction_service: ReproductionService,
        adaptation_service: AdaptationService,
        gene_flow_service: GeneFlowService,
        embedding_integration: EmbeddingIntegrationService | None = None,
    ) -> None:
        # === 注入的服务 ===
        self.environment = environment
        self.mortality = mortality
        self.embeddings = embeddings
        self.router = router
        self.report_builder = report_builder
        self.exporter = exporter
        self.niche_analyzer = niche_analyzer
        self.speciation = speciation
        self.background_manager = background_manager
        self.tiering = tiering
        self.focus_processor = focus_processor
        self.critical_analyzer = critical_analyzer
        self.escalation_service = escalation_service
        self.map_evolution = map_evolution
        self.migration_advisor = migration_advisor
        self.map_manager = map_manager
        self.reproduction_service = reproduction_service
        self.adaptation_service = adaptation_service
        self.gene_flow_service = gene_flow_service
        
        # === 内部创建的服务 ===
        self.gene_activation_service = GeneActivationService()
        self.tile_mortality = TileBasedMortalityEngine()
        self.tile_mortality.set_embedding_service(embeddings)
        self.ai_pressure_service = create_ai_pressure_service(router)
        self.food_web_manager = FoodWebManager()
        self.trophic_service = TrophicInteractionService()
        
        # Embedding 集成服务
        self.embedding_integration = embedding_integration or EmbeddingIntegrationService(embeddings, router)
        
        # === 状态 ===
        self.turn_counter = 0
        self.watchlist: set[str] = set()
        self._event_callback = None
        
        # === 功能开关 ===
        self._use_tile_based_mortality = True
        self._use_ai_pressure_response = True
        self._use_embedding_integration = True
        self._use_tectonic_system = True
        
        # === 板块构造系统 ===
        self.tectonic: TectonicIntegration | None = None
        self._init_tectonic_system()
    
    def _init_tectonic_system(self) -> None:
        """初始化板块构造系统"""
        if not self._use_tectonic_system:
            return
        
        try:
            import random
            width = getattr(self.map_manager, "width", 128)
            height = getattr(self.map_manager, "height", 40)
            seed = random.randint(1, 999999)
            
            self.tectonic = create_tectonic_integration(
                width=width, height=height, seed=seed,
            )
            logger.info(f"[板块系统] 初始化成功: {width}x{height}")
        except Exception as e:
            logger.warning(f"[板块系统] 初始化失败: {e}, 将禁用板块系统")
            self._use_tectonic_system = False
            self.tectonic = None
    
    # =========================================================================
    # Pipeline 管理
    # =========================================================================
    
    def _init_pipeline(self, mode: str = "standard") -> None:
        """初始化流水线"""
        from .pipeline import Pipeline, PipelineConfig
        from .stage_config import StageLoader
        
        try:
            loader = StageLoader()
            stages = loader.load_stages_for_mode(mode, validate=True)
            
            config = PipelineConfig(
                continue_on_error=True,
                log_timing=True,
                emit_stage_events=True,
                validate_dependencies=False,
                debug_mode=(mode == "debug"),
            )
            
            self._pipeline = Pipeline(stages, config)
            self._pipeline_mode = mode
            self._last_pipeline_metrics = None
            
            logger.info(f"[Pipeline] 初始化完成，模式: {mode}，阶段数: {len(stages)}")
        except Exception as e:
            logger.error(f"[Pipeline] 初始化失败: {e}")
            self._pipeline = None
            self._pipeline_mode = None
    
    def set_mode(self, mode: str) -> None:
        """切换运行模式"""
        from .stage_config import AVAILABLE_MODES
        
        if mode not in AVAILABLE_MODES:
            raise ValueError(f"未知模式: {mode}。可用: {', '.join(AVAILABLE_MODES)}")
        
        self._init_pipeline(mode)
        logger.info(f"[Engine] 切换到模式: {mode}")
    
    async def run_turn_with_pipeline(
        self,
        command: TurnCommand,
        mode: str | None = None,
    ) -> TurnReport | None:
        """使用 Pipeline 执行单个回合"""
        from .pipeline import PipelineResult
        
        # 初始化 Pipeline（如果需要）
        if mode:
            self._init_pipeline(mode)
        elif not hasattr(self, '_pipeline') or self._pipeline is None:
            self._init_pipeline("standard")
        
        # 创建上下文
        ctx = SimulationContext(
            turn_index=self.turn_counter,
            command=command,
            event_callback=self._event_callback,
        )
        
        logger.info(f"[Pipeline] 执行回合 {self.turn_counter}")
        self._emit_event("turn_start", f"📅 开始回合 {self.turn_counter}", "系统")
        
        # 执行流水线
        result: PipelineResult = await self._pipeline.execute(ctx, self)
        
        # 保存性能指标
        self._last_pipeline_metrics = result.metrics
        
        # 处理结果
        if not result.success:
            logger.warning(f"[Pipeline] 回合 {self.turn_counter} 有 {len(result.failed_stages)} 个阶段失败")
            for stage_name in result.failed_stages:
                logger.warning(f"  - {stage_name}")
        
        # 增加回合计数器
                self.turn_counter += 1
        
        return ctx.report
    
    async def run_turns_async(
        self,
        command: TurnCommand,
        use_pipeline: bool = True,
        mode: str | None = None,
    ) -> list[TurnReport]:
        """执行多个回合
        
        统一使用 Pipeline 架构执行所有回合逻辑。
        use_pipeline 参数已废弃，始终使用 Pipeline 执行。
        """
        if not use_pipeline:
                logger.warning(
                "[SimulationEngine] use_pipeline=False 已废弃。"
                "如需使用遗留逻辑进行回归测试，请使用 LegacyTurnRunner。"
            )
        
        reports: list[TurnReport] = []
        for turn_num in range(command.rounds):
            logger.info(f"[Pipeline] 执行第 {turn_num + 1}/{command.rounds} 回合")
            report = await self.run_turn_with_pipeline(command, mode)
            if report:
                reports.append(report)
        return reports
    
    def run_turns(self, *args, **kwargs):
        """同步版本已废弃"""
        raise NotImplementedError("Use run_turns_async instead")
    
    def get_pipeline_metrics(self):
        """获取最近一次流水线执行的性能指标"""
        return getattr(self, '_last_pipeline_metrics', None)
    
    def get_pipeline_dependency_graph(self) -> str:
        """获取当前流水线的依赖关系图"""
        if hasattr(self, '_pipeline') and self._pipeline:
            return self._pipeline.get_dependency_graph()
        return "Pipeline 未初始化"
    
    # =========================================================================
    # 事件与状态
    # =========================================================================
    
    def _emit_event(self, event_type: str, message: str, category: str = "其他", **extra):
        """发送事件到前端"""
        if self._event_callback:
            try:
                self._event_callback(event_type, message, category, **extra)
            except Exception as e:
                logger.error(f"事件推送失败: {str(e)}")
    
    def update_watchlist(self, codes: set[str]) -> None:
        """更新关注列表"""
        self.watchlist = set(codes)
