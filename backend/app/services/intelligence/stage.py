"""
Ecological Intelligence Stage - 生态智能体阶段

该阶段集成了生态智能体模块，在回合中执行：
1. 物种评分与分档
2. 构建 LLM 输入 DTO
3. 并行执行 A/B 批次 LLM 评估
4. 将结果写入 Context 供后续 Stage 使用

位置：在初步死亡率评估(50)之后、迁徙(60)之前
这样 AI 生成的 migration_bias 可以影响迁徙决策
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...simulation.context import SimulationContext
    from ...simulation.engine import SimulationEngine

logger = logging.getLogger(__name__)


class EcologicalIntelligenceStage:
    """生态智能体阶段
    
    该阶段负责：
    1. 使用 EcologicalIntelligence 对物种进行评分和分档
    2. 构建 A/B 两批次的评估输入
    3. 使用 LLMOrchestrator 并行执行评估
    4. 将 BiologicalAssessment 结果和 ModifierApplicator 写入 Context
    
    后续 Stage 可通过 ctx.modifier_applicator.apply() 获取修正值。
    """
    
    # Stage 属性
    ORDER = 52  # 在初步死亡率(50)之后，迁徙(60)之前，使 AI 能影响迁徙决策
    
    def __init__(self):
        self._order = self.ORDER
        self._name = "生态智能体评估"
        self._is_async = True
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def order(self) -> int:
        return self._order
    
    @property
    def is_async(self) -> bool:
        return self._is_async
    
    def get_dependency(self):
        """获取阶段依赖声明"""
        from ...simulation.stages import StageDependency
        
        return StageDependency(
            requires_stages={"初步死亡率评估"},
            requires_fields={"preliminary_mortality", "species_batch", "modifiers", "niche_metrics"},
            writes_fields={"biological_assessment_results", "species_priority_partition", "modifier_applicator"},
        )
    
    async def execute(
        self,
        ctx: "SimulationContext",
        engine: "SimulationEngine",
    ) -> None:
        """执行生态智能体评估"""
        from .ecological_intelligence import EcologicalIntelligence
        from .llm_orchestrator import LLMOrchestrator
        from .modifier_applicator import ModifierApplicator
        from .config import load_config_from_yaml
        
        logger.info("开始生态智能体评估...")
        ctx.emit_event("stage", "🧠 生态智能体评估", "AI")
        
        # 检查是否有物种需要评估
        # 注意：此阶段在初步死亡率(50)之后、最终死亡率之前运行
        # 所以应检查 preliminary_mortality 而非 combined_results
        mortality_available = getattr(ctx, 'combined_results', None) or getattr(ctx, 'preliminary_mortality', None)
        if not ctx.species_batch:
            logger.info("[生态智能体] 无物种需要评估")
            ctx.biological_assessment_results = {}
            ctx.modifier_applicator = ModifierApplicator()
            return
        
        if not mortality_available:
            logger.warning("[生态智能体] 没有死亡率数据，跳过评估")
            ctx.biological_assessment_results = {}
            ctx.modifier_applicator = ModifierApplicator()
            return
        
        try:
            # 加载配置
            config = load_config_from_yaml()
            
            # 初始化组件
            intelligence = EcologicalIntelligence(
                config=config,
                embedding_service=engine.embeddings if hasattr(engine, 'embeddings') else None,
            )
            
            orchestrator = LLMOrchestrator(
                router=engine.router,
                config=config,
            )
            
            modifier = ModifierApplicator(config=config)
            
            # Step 1: 分档
            # 优先使用 combined_results（最终死亡率），如果不可用则使用 preliminary_mortality（初步死亡率）
            mortality_data = getattr(ctx, 'combined_results', None) or getattr(ctx, 'preliminary_mortality', [])
            using_combined = bool(getattr(ctx, 'combined_results', None))
            logger.info(f"[生态智能体] Step 1: 物种分档... (使用 {'combined_results' if using_combined else 'preliminary_mortality'})")
            partition = intelligence.partition_species(
                species_list=ctx.species_batch,
                mortality_results=mortality_data,
                niche_metrics=ctx.niche_metrics,
                food_web_analysis=ctx.food_web_analysis,
            )
            ctx.species_priority_partition = partition
            
            ctx.emit_event(
                "info",
                f"🎯 分档完成: A={len(partition.tier_a)}, B={len(partition.tier_b)}, C={len(partition.tier_c)}",
                "AI",
            )
            
            # Step 2: 构建环境摘要
            logger.info("[生态智能体] Step 2: 构建评估输入...")
            environment = intelligence.build_environment_summary(
                turn_index=ctx.turn_index,
                modifiers=ctx.modifiers,
                major_events=ctx.major_events,
                map_state=ctx.current_map_state,
                species_count=len(ctx.species_batch),
            )
            
            # 构建物种映射
            species_map = {sp.lineage_code: sp for sp in ctx.species_batch}
            species_id_map = {sp.lineage_code: sp.id or 0 for sp in ctx.species_batch}
            
            # 构建批次
            batch_a, batch_b = intelligence.build_assessment_batches(
                partition=partition,
                species_map=species_map,
                environment=environment,
            )
            
            # Step 3: 执行 LLM 评估
            if config.enable_llm_calls and (batch_a.count > 0 or batch_b.count > 0):
                logger.info("[生态智能体] Step 3: 执行 LLM 评估...")
                ctx.emit_event("info", "🤖 开始 LLM 并行评估...", "AI")
                
                result = await orchestrator.execute(
                    batch_a=batch_a,
                    batch_b=batch_b,
                    species_id_map=species_id_map,
                )
                
                ctx.biological_assessment_results = result.assessments
                
                if result.errors:
                    for error in result.errors:
                        logger.warning(f"[生态智能体] {error}")
                
                ctx.emit_event(
                    "info",
                    f"✅ LLM 评估完成: {result.success_count} 个物种",
                    "AI",
                )
            else:
                logger.info("[生态智能体] LLM 调用已禁用或无需评估")
                ctx.biological_assessment_results = {}
            
            # Step 4: 为 C 档创建默认评估
            c_codes = [p.lineage_code for p in partition.tier_c]
            if c_codes:
                from .schemas import AssessmentTier
                defaults = orchestrator.create_default_assessments(
                    lineage_codes=c_codes,
                    species_id_map=species_id_map,
                    tier=AssessmentTier.C,
                )
                # 只添加还没有评估结果的
                for code, assessment in defaults.items():
                    if code not in ctx.biological_assessment_results:
                        ctx.biological_assessment_results[code] = assessment
            
            # Step 5: 设置 ModifierApplicator
            modifier.set_assessments(ctx.biological_assessment_results)
            ctx.modifier_applicator = modifier
            
            # 输出统计
            stats = modifier.get_stats()
            logger.info(
                f"[生态智能体] 评估完成: "
                f"总计 {stats['count']} 个物种, "
                f"分化候选 {stats.get('speciation_candidates', 0)} 个"
            )
            
            if stats.get('fates'):
                fate_str = ", ".join(f"{k}:{v}" for k, v in stats['fates'].items())
                logger.info(f"[生态智能体] 生态命运分布: {fate_str}")
            
        except Exception as e:
            logger.error(f"[生态智能体] 评估失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 降级：使用空结果
            ctx.biological_assessment_results = {}
            ctx.modifier_applicator = ModifierApplicator()
            ctx.emit_event("warning", f"⚠️ 生态智能体评估失败: {e}", "AI")


# 工厂函数，用于 Stage 加载器
def create_ecological_intelligence_stage():
    """创建生态智能体阶段实例"""
    return EcologicalIntelligenceStage()

