"""
LLM Orchestrator - LLM 调用编排器

负责构建 prompt、选择模型、并行执行 A/B 批次请求、解析输出。
不负责打分、分档和规则集成。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .config import IntelligenceConfig, DEFAULT_CONFIG
from .schemas import (
    AssessmentBatch,
    AssessmentTier,
    BiologicalAssessment,
    EnvironmentSummary,
    SpeciesAssessmentInput,
)

if TYPE_CHECKING:
    from ...ai.model_router import ModelRouter

logger = logging.getLogger(__name__)


# Prompt 模板
SYSTEM_PROMPT_A = """你是一个专业的进化生态学家，正在评估物种在模拟器中的生存状况和演化潜力。

【重要背景】
- 每回合代表约 50 万年的演化时间
- 分化是演化的核心机制，50万年足以产生新物种
- 环境压力是分化的主要驱动力

【⚠️ 压力强度对死亡率的影响 - 必读】
压力强度范围 0-10，必须根据压力强度调整 mortality_modifier：
- 压力 0-2: 背景活动，mortality_modifier 应在 0.9-1.1
- 压力 3-4: 轻度压力，根据物种适应性给 0.8-1.3
- 压力 5-6: 中度压力，脆弱物种应给 1.3-1.6
- 压力 7-8: 重度压力，大多数物种应给 1.4-1.8
- 压力 9-10: 灾难级压力，不适应物种应给 1.8-2.5

【分化信号 speciation_signal 判断标准】（0~1，≥0.5 表示应该分化）
给予高分化信号（0.6~1.0）的条件（满足任一即可）：
1. 种群较大(>5000)且面临中等死亡压力(20%~60%) - 选择压力分化
2. 种群趋势持续下降但仍有较大基数 - 适应性分化
3. 环境发生剧变（温度变化>3°C 或 压力>5）- 环境驱动分化
4. 物种处于生态位边缘或面临资源竞争 - 生态位分化
5. 营养级处于中间位置(2.0~3.5)面临捕食压力 - 捕食者驱动分化

给予低分化信号（0~0.3）的条件：
1. 种群太小(<2000) - 缺乏遗传多样性
2. 死亡率极低(<10%)且环境稳定(压力<2) - 无选择压力
3. 已是特化物种(营养级>4.0或<1.5) - 演化空间有限

你需要为每个物种提供详细的生物学评估。请严格按照 JSON 格式输出。"""

SYSTEM_PROMPT_B = """你是进化生态学专家。每回合=50万年。请评估物种的生存状况和分化潜力。

【⚠️ 压力→死亡率修正】
- 压力<3: mortality_modifier给0.9-1.1
- 压力3-6: 根据适应性给0.8-1.5
- 压力>6: 脆弱物种必须给1.5-2.5！

【分化信号判断】speciation_signal 0~1：
- 高(0.6+): 种群>5000且死亡率20%~60%，或压力>5，或面临竞争
- 中(0.3~0.6): 有一定压力但条件不完全满足
- 低(<0.3): 种群小/环境稳定(压力<2)/无压力

严格按照 JSON 格式输出。"""


USER_PROMPT_TEMPLATE_A = """## 当前环境状况（回合 {turn_index}，约 {turn_years} 万年）
- 全球温度: {global_temperature:.1f}°C (变化: {temperature_change:+.1f}°C)
- 海平面: {sea_level:.1f}m (变化: {sea_level_change:+.1f}m)
- 活跃压力: {active_pressures}
- 重大事件: {major_events}

## 待评估物种

{species_details}

## 输出要求

请为每个物种返回 JSON 数组。

【⚠️ mortality_modifier 判断规则 - 必须遵循】
根据压力强度和物种适应性综合判断：
- 压力<3 且物种正常: 给 0.9-1.1
- 压力3-6 且物种脆弱: 给 1.2-1.5
- 压力>6 且物种不适应: 给 1.5-2.5（灾难级必须高修正！）
- 物种高度适应当前压力: 给 0.5-0.8

【speciation_signal 判断规则】
- 种群>5000 且 死亡率在20%~60%之间 → 给 0.6~0.9
- 环境剧变（温度变化>3°C 或 压力>5）→ 给 0.5~0.8
- 种群<2000 或 死亡率<10% → 给 0~0.3

```json
{{
  "lineage_code": "物种代码",
  "mortality_modifier": 0.5~2.5 死亡率乘数（压力大+不适应给>1.5，适应好给<0.8）,
  "r_adjust": -0.3~0.3 繁殖率调整（高压环境给负值）,
  "k_adjust": -0.4~0.4 承载力调整（灾难环境给负值）,
  "migration_bias": -1~1 迁徙倾向（高压力环境应给正值表示想逃离）,
  "speciation_signal": 0~1 【重要】分化信号，≥0.5表示应该产生新物种,
  "ecological_fate": "thriving/stable/declining/endangered",
  "evolution_direction": ["【重要】具体的演化方向，会传递给分化AI。例如：耐寒性+1.0、体型增大、深海适应、运动能力+0.5、防御性增强"],
  "narrative": "2-3句话描述物种当前状态和演化趋势",
  "headline": "简短标题",
  "mood": "positive/neutral/negative/critical",
  "confidence": 0~1 置信度
}}
```

只返回 JSON 数组，不要其他内容。"""


USER_PROMPT_TEMPLATE_B = """环境(回合{turn_index}): 温度{global_temperature:.0f}°C({temperature_change:+.1f}), 海平面{sea_level:.0f}m
压力: {active_pressures_brief}

物种(pop=种群, dr=死亡率, tl=营养级):
{species_brief}

【⚠️ 必须遵循】
- 压力>6 + 物种不适应 → mortality_modifier给1.5-2.5
- 压力<3 → mortality_modifier给0.9-1.1
- pop>5000且dr在20%~60%之间 → speciation_signal给0.6~0.9
- 压力>5的环境剧变 → speciation_signal给0.5~0.8

为每个物种返回JSON:
[{{"lineage_code":"代码","mortality_modifier":1.0,"r_adjust":0,"k_adjust":0,"migration_bias":0,"speciation_signal":0.5,"ecological_fate":"stable"}}]"""


@dataclass
class OrchestratorResult:
    """编排器执行结果"""
    assessments: Dict[str, BiologicalAssessment]
    batch_a_success: bool
    batch_b_success: bool
    errors: List[str]
    total_tokens: int = 0
    
    @property
    def success_count(self) -> int:
        return len(self.assessments)


class LLMOrchestrator:
    """LLM 调用编排器
    
    核心职责：
    1. 构建 prompt（A 档详细，B 档精简）
    2. 选择模型（A 档用大模型，B 档用小模型）
    3. 并行执行 A/B 两批次请求
    4. 解析 JSON 输出并转换为 BiologicalAssessment
    
    不负责：
    - 物种评分和分档
    - 数值修正应用
    """
    
    def __init__(
        self,
        router: "ModelRouter",
        config: IntelligenceConfig | None = None,
    ):
        self.router = router
        self.config = config or DEFAULT_CONFIG
        
        # 模型配置（可覆盖）
        self.model_a = "biological_assessment_a"  # A 档使用的 capability
        self.model_b = "biological_assessment_b"  # B 档使用的 capability
        
        logger.info("[LLMOrchestrator] 初始化完成")
    
    def _build_prompt_a(
        self,
        batch: AssessmentBatch,
    ) -> tuple[str, str]:
        """构建 A 档 prompt（详细版）"""
        env = batch.environment
        
        # 构建物种详情（添加分化建议）
        species_details = []
        for sp in batch.species_inputs:
            # 计算分化建议
            speciation_hint = self._get_speciation_hint(sp)
            
            detail = f"""### {sp.common_name} ({sp.lineage_code})
- 学名: {sp.latin_name or '未知'}
- 种群: {sp.population:,} {'【大种群，有分化基础】' if sp.population > 5000 else ''}
- 死亡率: {sp.death_rate:.1%} {'【中等压力，有分化潜力】' if 0.1 <= sp.death_rate <= 0.5 else ''}
- 营养级: {sp.trophic_level:.1f}
- 饮食: {sp.diet_type or '未知'}
- 气候耐受: {sp.climate_tolerance}
- 遗传多样性: {sp.genetic_diversity:.1%}
- 种群趋势: {sp.population_trend:+.1%}
- 近期事件: {', '.join(sp.recent_events) or '无'}
- 分化建议: {speciation_hint}
"""
            species_details.append(detail)
        
        # 格式化压力
        pressures_str = ", ".join(
            f"{k}: {v:+.1f}" for k, v in env.active_pressures.items()
            if abs(v) > 0.1
        ) or "无显著压力"
        
        events_str = ", ".join(env.major_events) or "无"
        
        # 计算演化年数（每回合50万年）
        turn_years = env.turn_index * 50
        
        user_prompt = USER_PROMPT_TEMPLATE_A.format(
            turn_index=env.turn_index,
            turn_years=turn_years,
            global_temperature=env.global_temperature,
            temperature_change=env.temperature_change,
            sea_level=env.sea_level,
            sea_level_change=env.sea_level_change,
            active_pressures=pressures_str,
            major_events=events_str,
            species_details="\n".join(species_details),
        )
        
        return SYSTEM_PROMPT_A, user_prompt
    
    def _get_speciation_hint(self, sp: SpeciesAssessmentInput) -> str:
        """生成分化建议提示"""
        hints = []
        
        # 检查种群条件
        if sp.population >= 5000:
            hints.append("种群足够大")
        elif sp.population >= 3000:
            hints.append("种群接近分化阈值")
        else:
            return "种群太小，不建议分化"
        
        # 检查死亡率条件
        if 0.1 <= sp.death_rate <= 0.5:
            hints.append("死亡率表明有选择压力")
        elif sp.death_rate > 0.5:
            hints.append("死亡率过高，濒临灭绝")
        else:
            hints.append("环境稳定，压力不足")
        
        # 检查趋势
        if sp.population_trend < -0.1:
            hints.append("种群下降可能触发适应性分化")
        
        # 综合建议
        if sp.population >= 5000 and 0.1 <= sp.death_rate <= 0.5:
            return f"【建议高分化信号0.6+】{', '.join(hints)}"
        elif sp.population >= 3000 and sp.death_rate > 0.05:
            return f"【建议中等分化信号0.4~0.6】{', '.join(hints)}"
        else:
            return f"【建议低分化信号<0.3】{', '.join(hints)}"
    
    def _build_prompt_b(
        self,
        batch: AssessmentBatch,
    ) -> tuple[str, str]:
        """构建 B 档 prompt（精简版）"""
        env = batch.environment
        
        # 精简的压力描述
        pressures_brief = ", ".join(
            f"{k[:3]}:{v:+.1f}" for k, v in env.active_pressures.items()
            if abs(v) > 0.1
        )[:50] or "稳定"
        
        # 精简的物种列表（添加分化提示）
        species_brief = []
        for sp in batch.species_inputs:
            # 添加简单的分化标记
            spec_hint = ""
            if sp.population >= 5000 and 0.1 <= sp.death_rate <= 0.5:
                spec_hint = " [建议分化0.6+]"
            elif sp.population >= 3000 and sp.death_rate > 0.05:
                spec_hint = " [可能分化0.4+]"
            
            brief = f"- {sp.lineage_code}: pop={sp.population:,}, dr={sp.death_rate:.0%}, tl={sp.trophic_level:.1f}{spec_hint}"
            species_brief.append(brief)
        
        user_prompt = USER_PROMPT_TEMPLATE_B.format(
            turn_index=env.turn_index,
            global_temperature=env.global_temperature,
            temperature_change=env.temperature_change,
            sea_level=env.sea_level,
            active_pressures_brief=pressures_brief,
            species_brief="\n".join(species_brief),
        )
        
        return SYSTEM_PROMPT_B, user_prompt
    
    def _parse_llm_response(
        self,
        raw_response: str,
        expected_codes: List[str],
        tier: AssessmentTier,
    ) -> Dict[str, BiologicalAssessment]:
        """解析 LLM 响应
        
        Args:
            raw_response: LLM 原始输出
            expected_codes: 预期的物种代码列表
            tier: 评估档次
            
        Returns:
            lineage_code -> BiologicalAssessment 映射
        """
        results = {}
        
        try:
            # 尝试解析 JSON
            content = raw_response.strip()
            
            # 清理可能的 markdown 代码块
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # 解析
            data = json.loads(content)
            
            # 确保是列表
            if isinstance(data, dict):
                data = [data]
            
            # 转换为 BiologicalAssessment
            code_to_id = {}  # 需要从外部获取 species_id
            
            for item in data:
                if not isinstance(item, dict):
                    continue
                
                lineage_code = item.get("lineage_code", "")
                if not lineage_code:
                    continue
                
                assessment = BiologicalAssessment.from_llm_output(
                    species_id=0,  # 后续填充
                    lineage_code=lineage_code,
                    raw_output=item,
                    tier=tier,
                )
                results[lineage_code] = assessment
            
            logger.info(
                f"[LLMOrchestrator] 解析 {tier.value} 档响应: "
                f"成功 {len(results)}/{len(expected_codes)}"
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"[LLMOrchestrator] JSON 解析失败: {e}")
            logger.debug(f"原始响应: {raw_response[:500]}")
        except Exception as e:
            logger.error(f"[LLMOrchestrator] 响应解析异常: {e}")
        
        return results
    
    async def _call_llm_batch(
        self,
        batch: AssessmentBatch,
        capability: str,
    ) -> Dict[str, BiologicalAssessment]:
        """执行单个批次的 LLM 调用
        
        Args:
            batch: 评估批次
            capability: 使用的模型 capability
            
        Returns:
            lineage_code -> BiologicalAssessment 映射
        """
        if batch.count == 0:
            return {}
        
        tier = batch.tier
        
        # 构建 prompt
        if tier == AssessmentTier.A:
            system_prompt, user_prompt = self._build_prompt_a(batch)
        else:
            system_prompt, user_prompt = self._build_prompt_b(batch)
        
        try:
            # 调用 LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            
            # 【优化】使用带心跳的调用
            from ...ai.streaming_helper import acall_with_heartbeat
            response = await acall_with_heartbeat(
                router=self.router,
                capability=capability,
                messages=messages,
                response_format={"type": "json_object"},
                task_name=f"生态评估[{tier.value}档×{len(batch.lineage_codes)}]",
                timeout=self.config.llm_timeout_seconds,
                heartbeat_interval=2.0,
            )
            
            # 解析响应
            return self._parse_llm_response(
                response,
                batch.lineage_codes,
                tier,
            )
            
        except asyncio.TimeoutError:
            logger.error(
                f"[LLMOrchestrator] {tier.value} 档调用超时 "
                f"(timeout={self.config.llm_timeout_seconds}s)"
            )
            return {}
        except Exception as e:
            logger.error(f"[LLMOrchestrator] {tier.value} 档调用失败: {e}")
            return {}
    
    async def execute(
        self,
        batch_a: AssessmentBatch,
        batch_b: AssessmentBatch,
        species_id_map: Dict[str, int] | None = None,
    ) -> OrchestratorResult:
        """执行 A/B 两个批次的并行评估
        
        Args:
            batch_a: A 档批次（高优先级）
            batch_b: B 档批次（中优先级）
            species_id_map: lineage_code -> species_id 映射
            
        Returns:
            OrchestratorResult 包含所有评估结果
        """
        if not self.config.enable_llm_calls:
            logger.info("[LLMOrchestrator] LLM 调用已禁用，返回空结果")
            return OrchestratorResult(
                assessments={},
                batch_a_success=False,
                batch_b_success=False,
                errors=["LLM 调用已禁用"],
            )
        
        errors = []
        results_a = {}
        results_b = {}
        
        logger.info(
            f"[LLMOrchestrator] 开始并行评估: "
            f"A={batch_a.count}, B={batch_b.count}"
        )
        
        # 根据配置决定是否并行
        if self.config.use_parallel_batches and batch_a.count > 0 and batch_b.count > 0:
            # 并行执行两个批次
            task_a = self._call_llm_batch(batch_a, self.model_a)
            task_b = self._call_llm_batch(batch_b, self.model_b)
            
            try:
                results_a, results_b = await asyncio.gather(
                    task_a, task_b,
                    return_exceptions=True,
                )
                
                if isinstance(results_a, Exception):
                    errors.append(f"A 档调用异常: {results_a}")
                    results_a = {}
                if isinstance(results_b, Exception):
                    errors.append(f"B 档调用异常: {results_b}")
                    results_b = {}
                    
            except Exception as e:
                errors.append(f"并行执行异常: {e}")
        else:
            # 串行执行
            if batch_a.count > 0:
                try:
                    results_a = await self._call_llm_batch(batch_a, self.model_a)
                except Exception as e:
                    errors.append(f"A 档调用异常: {e}")
            
            if batch_b.count > 0:
                try:
                    results_b = await self._call_llm_batch(batch_b, self.model_b)
                except Exception as e:
                    errors.append(f"B 档调用异常: {e}")
        
        # 合并结果
        all_assessments = {}
        
        # 填充 species_id
        id_map = species_id_map or {}
        
        for code, assessment in results_a.items():
            assessment.species_id = id_map.get(code, 0)
            all_assessments[code] = assessment
        
        for code, assessment in results_b.items():
            assessment.species_id = id_map.get(code, 0)
            all_assessments[code] = assessment
        
        logger.info(
            f"[LLMOrchestrator] 评估完成: "
            f"成功 {len(all_assessments)} (A={len(results_a)}, B={len(results_b)}), "
            f"错误 {len(errors)}"
        )
        
        return OrchestratorResult(
            assessments=all_assessments,
            batch_a_success=len(results_a) > 0 or batch_a.count == 0,
            batch_b_success=len(results_b) > 0 or batch_b.count == 0,
            errors=errors,
        )
    
    def create_default_assessments(
        self,
        lineage_codes: List[str],
        species_id_map: Dict[str, int] | None = None,
        tier: AssessmentTier = AssessmentTier.C,
    ) -> Dict[str, BiologicalAssessment]:
        """为物种创建默认评估（用于降级策略）
        
        Args:
            lineage_codes: 物种代码列表
            species_id_map: lineage_code -> species_id 映射
            tier: 评估档次
            
        Returns:
            lineage_code -> BiologicalAssessment 映射
        """
        id_map = species_id_map or {}
        results = {}
        
        for code in lineage_codes:
            results[code] = BiologicalAssessment.create_default(
                species_id=id_map.get(code, 0),
                lineage_code=code,
                tier=tier,
            )
        
        return results

