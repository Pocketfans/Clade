"""AI压力响应服务：让AI参与物种对压力的响应决策

【优化后】实现四大核心功能：
1. 综合状态评估 - 评估物种状态、应对能力、是否需要紧急响应（合并了压力评估+紧急响应）
2. 物种叙事生成 - 为Critical/Focus物种生成叙事描述（合并了Critical增润+Focus增润）
3. 种群博弈仲裁 - 模拟物种间的互动博弈
4. 迁徙决策参谋 - 智能规划迁徙路线（保留用于特殊情况）

【兼容性】保留旧接口（assess_pressure_response、generate_emergency_response），内部调用新方法

【可观测性】
- 所有 AI 调用都记录耗时和计数
- 使用 logger.info 输出结构化日志（含 method/duration_ms/count）
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Sequence, Callable, Awaitable, TYPE_CHECKING

from ...models.species import Species
from ...models.environment import HabitatPopulation, MapTile
from ...ai.model_router import ModelRouter, staggered_gather
from ...ai.prompts.pressure_response import PRESSURE_RESPONSE_PROMPTS
from ...schemas.responses import MigrationEvent

if TYPE_CHECKING:
    from ...simulation.species import MortalityResult

logger = logging.getLogger(__name__)


@dataclass
class PressureAssessmentResult:
    """压力评估结果"""
    lineage_code: str
    survival_modifier: float  # 死亡率修正系数 (0.5-1.5)
    response_strategy: str  # 应对策略
    key_survival_factors: list[str] = field(default_factory=list)
    key_risk_factors: list[str] = field(default_factory=list)
    population_behavior: str = "normal"
    narrative: str = ""
    
    def apply_to_death_rate(self, base_death_rate: float) -> float:
        """应用修正系数到基础死亡率"""
        modified = base_death_rate * self.survival_modifier
        # 限制在合理范围
        return max(0.0, min(0.95, modified))


@dataclass
class InteractionResult:
    """物种互动结果"""
    species_a_code: str
    species_b_code: str
    interaction_type: str
    outcome: str  # a_wins/b_wins/draw/mutual_benefit/mutual_harm
    a_mortality_delta: float
    b_mortality_delta: float
    narrative: str = ""


@dataclass
class EmergencyResponse:
    """紧急响应计划"""
    lineage_code: str
    primary_strategy: str
    survival_probability: float
    mortality_reduction: float
    immediate_actions: list[str] = field(default_factory=list)
    trait_changes: dict[str, float] = field(default_factory=dict)
    narrative: str = ""


@dataclass
class MigrationAdvice:
    """迁徙建议"""
    lineage_code: str
    recommended_destination: int  # tile_id
    destination_score: float
    expected_mortality_change: float
    journey_mortality: float
    reasoning: str = ""
    narrative: str = ""


@dataclass
class SpeciesStatusEval:
    """【新】综合状态评估结果（合并了压力评估+紧急响应）"""
    lineage_code: str
    survival_modifier: float  # 死亡率修正系数 (0.5-1.5)
    response_strategy: str  # 应对策略
    key_factors: list[str] = field(default_factory=list)
    population_behavior: str = "normal"
    
    # 紧急状态信息
    is_emergency: bool = False
    emergency_level: str = "stable"  # critical/warning/stable
    emergency_action: dict = field(default_factory=dict)
    
    # 迁徙建议
    should_migrate: bool = False
    migration_urgency: str = "none"  # immediate/next_turn/optional/none
    
    narrative: str = ""
    
    def apply_to_death_rate(self, base_death_rate: float) -> float:
        """应用修正系数到基础死亡率"""
        modified = base_death_rate * self.survival_modifier
        # 如果有紧急措施，额外降低死亡率
        if self.is_emergency and self.emergency_action:
            benefit = self.emergency_action.get("expected_benefit", 0)
            modified = modified * (1 - benefit)
        return max(0.0, min(0.95, modified))


@dataclass
class SpeciesNarrativeResult:
    """【新】物种叙事结果"""
    lineage_code: str
    tier: str  # critical/focus
    headline: str
    narrative: str
    mood: str  # thriving/struggling/adapting/declining/critical
    highlight_event: str = ""


@dataclass
class NarrativeBatchResult:
    """【新】批量叙事结果（包含物种间互动故事）"""
    narratives: list[SpeciesNarrativeResult]
    cross_species_story: str = ""  # 物种间互动或生态系统整体变化描述


class AIPressureResponseService:
    """AI压力响应服务
    
    核心理念：规则引擎计算基础值，AI提供智能修正
    
    调用策略：
    - Critical物种：每回合都调用AI
    - Focus物种：高压力时调用AI
    - Background物种：仅紧急情况调用AI
    """
    
    # 触发阈值
    HIGH_PRESSURE_THRESHOLD = 5.0
    EMERGENCY_DEATH_RATE = 0.70
    CONSECUTIVE_DANGER_THRESHOLD = 3
    
    # 并发控制
    MAX_ASSESSMENTS_PER_TURN = 20
    MAX_INTERACTIONS_PER_TURN = 10
    MAX_EMERGENCY_PER_TURN = 5
    
    def __init__(self, router: ModelRouter):
        self.router = router
        self.enable_ai_assessment = True
        self.enable_ai_interaction = True
        self.enable_emergency_response = True
        self.enable_migration_advice = True
        
        # 缓存：物种连续高危回合数
        self._consecutive_danger: dict[str, int] = {}
        # 缓存：本回合已处理的物种
        self._processed_this_turn: set[str] = set()
        
        # 【新增】事件回调（用于发送流式心跳到前端）
        self._event_callback: Callable[[str, str, str], None] | None = None
        # 【新增】是否使用流式传输
        self.use_streaming = True
        
        # 【可观测性】AI 调用计时统计
        self._ai_metrics = {
            "species_status_eval": {"count": 0, "total_ms": 0.0},
            "narrative_generation": {"count": 0, "total_ms": 0.0},
            "batch_eval": {"count": 0, "total_ms": 0.0},
            "emergency_response": {"count": 0, "total_ms": 0.0},
        }
    
    def get_ai_metrics(self) -> dict:
        """获取 AI 调用统计指标"""
        return {
            method: {
                "count": stats["count"],
                "total_ms": round(stats["total_ms"], 1),
                "avg_ms": round(stats["total_ms"] / stats["count"], 1) if stats["count"] > 0 else 0,
            }
            for method, stats in self._ai_metrics.items()
        }
    
    def reset_ai_metrics(self) -> None:
        """重置 AI 调用统计（每回合开始时调用）"""
        for stats in self._ai_metrics.values():
            stats["count"] = 0
            stats["total_ms"] = 0.0
    
    def _record_ai_call(self, method: str, duration_ms: float) -> None:
        """记录一次 AI 调用"""
        if method in self._ai_metrics:
            self._ai_metrics[method]["count"] += 1
            self._ai_metrics[method]["total_ms"] += duration_ms
    
    def set_event_callback(self, callback: Callable[[str, str, str], None] | None) -> None:
        """设置事件回调函数
        
        Args:
            callback: 回调函数，签名为 (event_type, message, category, **extra)
        """
        self._event_callback = callback
    
    def _emit_event(self, event_type: str, message: str, category: str = "AI", **extra) -> None:
        """发送事件到前端"""
        if self._event_callback:
            try:
                self._event_callback(event_type, message, category, **extra)
            except Exception as e:
                logger.debug(f"[AI服务] 发送事件失败: {e}")
    
    def clear_turn_cache(self) -> None:
        """清空回合缓存（每回合开始时调用）"""
        self._processed_this_turn.clear()
    
    def clear_all_caches(self) -> None:
        """清空所有缓存（存档切换时调用）
        
        【重要】切换存档时必须调用此方法，否则旧存档的
        连续危险回合数会影响新存档的物种状态判断。
        """
        self._consecutive_danger.clear()
        self._processed_this_turn.clear()
    
    def _generate_rule_based_fallback(
        self,
        species: 'Species',
        base_death_rate: float,
        environment_pressure: dict[str, float],
    ) -> SpeciesStatusEval:
        """【优化】AI调用失败时，基于规则生成合理的评估结果
        
        这个智能fallback确保即使AI失败，物种也能获得合理的评估，
        而不是直接使用未修正的规则引擎结果。
        
        Args:
            species: 目标物种
            base_death_rate: 规则引擎计算的基础死亡率
            environment_pressure: 环境压力字典
            
        Returns:
            基于规则生成的评估结果
        """
        traits = species.abstract_traits or {}
        consecutive = self._consecutive_danger.get(species.lineage_code, 0)
        
        # ========== 1. 计算智能修正系数 ==========
        # 基于物种特质与环境压力的匹配度
        modifier = 1.0
        key_factors = []
        
        # 【新增】灾难类压力的强制惩罚
        volcano_pressure = environment_pressure.get("volcano", 0) + environment_pressure.get("volcanic", 0)
        sulfide_pressure = environment_pressure.get("sulfide", 0)
        mortality_spike = environment_pressure.get("mortality_spike", 0)
        wildfire_pressure = environment_pressure.get("wildfire", 0)
        
        # 火山喷发高强度时的惩罚
        if volcano_pressure >= 7:
            heat_resist = traits.get("耐热性", 5) / 15.0
            if heat_resist < 0.4:  # 无耐热性
                modifier *= 1.6
                key_factors.append("对火山喷发高度脆弱")
            elif heat_resist < 0.7:
                modifier *= 1.3
                key_factors.append("难以承受火山压力")
        elif volcano_pressure >= 4:
            modifier *= 1.15
            key_factors.append("受火山活动影响")
        
        # 硫化事件惩罚
        if sulfide_pressure >= 5:
            modifier *= 1.5
            key_factors.append("硫化毒气威胁严重")
        
        # 野火惩罚（主要影响陆生物种）
        if wildfire_pressure >= 6:
            habitat = getattr(species, 'habitat_type', 'terrestrial')
            if habitat in ('terrestrial', 'aerial'):
                mobility = traits.get("运动能力", 5) / 15.0
                if mobility < 0.4:
                    modifier *= 1.5
                    key_factors.append("无法逃离野火")
                else:
                    modifier *= 1.2
                    key_factors.append("野火威胁")
        
        # 直接死亡率压力
        if mortality_spike > 0:
            modifier *= (1.0 + mortality_spike * 0.1)
            key_factors.append("环境灾害直接影响")
        
        # 温度适应性
        temp_pressure = environment_pressure.get("temperature", 0)
        if temp_pressure < -2:  # 寒冷
            cold_resist = traits.get("耐寒性", 5) / 15.0
            if cold_resist > 0.6:
                modifier *= 0.75  # 从0.85增强到0.75
                key_factors.append(f"耐寒能力强({traits.get('耐寒性', 5):.0f})")
            elif cold_resist < 0.3:
                modifier *= 1.25  # 从1.15增强到1.25
                key_factors.append("对寒冷敏感")
        elif temp_pressure > 2:  # 炎热
            heat_resist = traits.get("耐热性", 5) / 15.0
            if heat_resist > 0.6:
                modifier *= 0.75
                key_factors.append(f"耐热能力强({traits.get('耐热性', 5):.0f})")
            elif heat_resist < 0.3:
                modifier *= 1.25
                key_factors.append("对高温敏感")
        
        # 干旱/湿度适应性
        drought_pressure = environment_pressure.get("drought", 0)
        if drought_pressure > 2:
            drought_resist = traits.get("耐旱性", 5) / 15.0
            if drought_resist > 0.6:
                modifier *= 0.85
                key_factors.append("抗旱能力强")
            elif drought_resist < 0.3:
                modifier *= 1.30  # 从1.20增强到1.30
                key_factors.append("对干旱敏感")
        
        # 运动能力影响逃避能力
        mobility = traits.get("运动能力", 5) / 15.0
        if mobility > 0.7 and base_death_rate > 0.3:
            modifier *= 0.90  # 从0.95增强到0.90
            key_factors.append("高机动性有助于逃避")
        
        # 繁殖速度提供恢复潜力
        repro_speed = traits.get("繁殖速度", 5) / 15.0
        if repro_speed > 0.7:
            modifier *= 0.95
            key_factors.append("快速繁殖有助于恢复")
        
        # 【扩大范围】限制修正系数范围到0.3-2.0
        modifier = max(0.3, min(2.0, modifier))
        
        # ========== 2. 判断紧急状态 ==========
        if base_death_rate > 0.70 or consecutive >= 4:
            is_emergency = True
            emergency_level = "critical"
        elif base_death_rate > 0.50 or consecutive >= 2:
            is_emergency = True
            emergency_level = "warning"
        else:
            is_emergency = False
            emergency_level = "stable"
        
        # ========== 3. 确定应对策略 ==========
        if base_death_rate > 0.60:
            if mobility > 0.5:
                strategy = "逃避"
            elif repro_speed > 0.6:
                strategy = "忍耐"
            else:
                strategy = "衰退"
        elif base_death_rate > 0.30:
            strategy = "适应"
        else:
            strategy = "对抗" if mobility > 0.5 else "适应"
        
        # ========== 4. 判断是否需要迁徙 ==========
        should_migrate = base_death_rate > 0.50 and mobility > 0.4
        migration_urgency = "none"
        if should_migrate:
            if base_death_rate > 0.70:
                migration_urgency = "immediate"
            elif base_death_rate > 0.50:
                migration_urgency = "next_turn"
            else:
                migration_urgency = "optional"
        
        # ========== 5. 生成简短叙事 ==========
        if is_emergency:
            narrative = f"{species.common_name}正面临{emergency_level}级生存危机，采取{strategy}策略应对。"
        elif base_death_rate > 0.30:
            narrative = f"{species.common_name}在当前环境压力下表现出{strategy}倾向。"
        else:
            narrative = f"{species.common_name}种群状态相对稳定。"
        
        logger.info(
            f"[规则Fallback] {species.common_name}: "
            f"modifier={modifier:.2f}, strategy={strategy}, emergency={emergency_level}"
        )
        
        return SpeciesStatusEval(
            lineage_code=species.lineage_code,
            survival_modifier=modifier,
            response_strategy=strategy,
            key_factors=key_factors[:3],  # 最多3个关键因素
            population_behavior="迁徙准备" if should_migrate else "normal",
            is_emergency=is_emergency,
            emergency_level=emergency_level,
            emergency_action={
                "primary_strategy": "migration" if should_migrate else "behavior_change",
                "action_detail": f"基于规则评估的{strategy}策略",
                "expected_benefit": 0.1 if is_emergency else 0.0,
            },
            should_migrate=should_migrate,
            migration_urgency=migration_urgency,
            narrative=narrative,
        )
    
    # ==================== 【新】综合状态评估 ====================
    
    async def _stream_call_with_heartbeat(
        self,
        capability: str,
        messages: list[dict[str, str]],
        response_format: dict | None = None,
        task_name: str = "AI处理",
        timeout: float | None = None,
    ) -> str:
        """【增强】使用流式传输调用 AI，智能超时 + chunk心跳
        
        智能超时机制：
        - 只要持续收到 chunk，就不会触发超时
        - 只有在 idle_timeout 秒内没有收到任何 chunk 才触发超时
        - 这样即使 AI 思考+输出很长时间，只要在输出就不会超时
        
        Args:
            capability: AI 能力名称
            messages: 消息列表
            response_format: 响应格式
            task_name: 任务名称（用于心跳消息）
            timeout: 空闲超时秒数（两个chunk之间的最大间隔），None则使用默认
            
        Returns:
            完整的 AI 响应内容
        """
        chunks: list[str] = []
        chunk_count = 0
        last_heartbeat_time = asyncio.get_event_loop().time()
        last_chunk_time = asyncio.get_event_loop().time()  # 上次收到 chunk 的时间
        heartbeat_interval = 1.5  # 每 1.5 秒发送一次 chunk 心跳
        
        # 空闲超时：两个 chunk 之间的最大允许间隔
        # 这个超时只在"没有收到任何输出"时才触发
        idle_timeout = timeout or float(self.SPECIES_EVAL_TIMEOUT)
        
        async def iter_with_idle_timeout():
            """带空闲超时的迭代器包装"""
            nonlocal last_chunk_time
            
            async for item in self.router.astream_capability(
                capability=capability,
                messages=messages,
                response_format=response_format,
            ):
                last_chunk_time = asyncio.get_event_loop().time()  # 重置空闲计时
                yield item
        
        try:
            # 启动流式迭代
            stream_iter = iter_with_idle_timeout()
            
            while True:
                try:
                    # 计算剩余空闲超时时间
                    elapsed_idle = asyncio.get_event_loop().time() - last_chunk_time
                    remaining_timeout = max(1.0, idle_timeout - elapsed_idle)
                    
                    # 尝试获取下一个 item，带超时保护
                    item = await asyncio.wait_for(
                        stream_iter.__anext__(),
                        timeout=remaining_timeout
                    )
                    
                except StopAsyncIteration:
                    # 流结束
                    break
                except asyncio.TimeoutError:
                    # 空闲超时：在 idle_timeout 秒内没有收到任何输出
                    elapsed_total = asyncio.get_event_loop().time() - (last_chunk_time - elapsed_idle)
                    self._emit_event(
                        "ai_idle_timeout",
                        f"⏰ {task_name} 空闲超时 ({idle_timeout:.0f}s无输出)",
                        "AI",
                        task=task_name,
                        chunks_received=chunk_count,
                        idle_seconds=idle_timeout
                    )
                    logger.warning(
                        f"[流式调用] {task_name} 空闲超时 "
                        f"(已收到{chunk_count}个chunks, 空闲{idle_timeout}秒)"
                    )
                    # 如果已经收到一些内容，尝试返回；否则抛出异常
                    if chunks:
                        logger.info(f"[流式调用] {task_name} 使用已接收的部分内容 ({len(''.join(chunks))} chars)")
                        break
                    raise asyncio.TimeoutError(f"空闲超时: {idle_timeout}秒内无输出")
                
                # 处理状态事件
                if isinstance(item, dict):
                    state = item.get("state", "")
                    if state == "connected":
                        self._emit_event(
                            "ai_stream_start", 
                            f"🔗 {task_name} 已连接",
                            "AI",
                            task=task_name
                        )
                    elif state == "receiving":
                        self._emit_event(
                            "ai_stream_receiving",
                            f"📥 {task_name} 正在接收...",
                            "AI", 
                            task=task_name
                        )
                    elif state == "completed":
                        self._emit_event(
                            "ai_stream_complete",
                            f"✅ {task_name} 接收完成",
                            "AI",
                            task=task_name,
                            chunks=chunk_count
                        )
                    elif item.get("type") == "error":
                        error_msg = item.get("message", "未知错误")
                        self._emit_event(
                            "ai_stream_error",
                            f"❌ {task_name} 错误: {error_msg}",
                            "AI",
                            task=task_name,
                            error=error_msg
                        )
                else:
                    # 这是文本 chunk
                    chunks.append(str(item))
                    chunk_count += 1
                    
                    # 发送 chunk 心跳（限制频率）
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_heartbeat_time >= heartbeat_interval:
                        self._emit_event(
                            "ai_chunk_heartbeat",
                            f"💓 {task_name} 输出中 ({chunk_count} chunks)",
                            "AI",
                            task=task_name,
                            chunks=chunk_count,
                            preview=chunks[-1][:30] if chunks else ""
                        )
                        last_heartbeat_time = current_time
            
            full_content = "".join(chunks)
            logger.debug(f"[流式调用] {task_name} 完成，共 {chunk_count} chunks, 总长度 {len(full_content)}")
            return full_content
            
        except Exception as e:
            logger.error(f"[流式调用] {task_name} 失败: {e}")
            self._emit_event(
                "ai_stream_error",
                f"❌ {task_name} 流式调用失败",
                "AI",
                task=task_name,
                error=str(e)
            )
            raise
    
    async def evaluate_species_status(
        self,
        species: Species,
        base_death_rate: float,
        environment_pressure: dict[str, float],
        pressure_context: str,
        death_causes: str = "",
        competitors: list[Species] = None,
        prey_info: str = "",
        predator_info: str = "",
        habitat_status: str = "",
    ) -> SpeciesStatusEval | None:
        """【新】综合评估物种状态（合并了压力评估+紧急响应）
        
        这是优化后的主要评估方法，一次AI调用完成：
        1. 评估物种对压力的应对能力（survival_modifier）
        2. 判断是否处于紧急状态
        3. 如处于紧急状态，给出应急策略
        4. 给出迁徙建议
        
        Args:
            species: 目标物种
            base_death_rate: 规则引擎计算的基础死亡率
            environment_pressure: 环境压力字典
            pressure_context: 压力上下文描述
            death_causes: 主要死因描述
            competitors: 竞争者列表
            prey_info: 猎物信息
            predator_info: 捕食者信息
            habitat_status: 栖息地状态
            
        Returns:
            综合状态评估结果
        """
        if not self.enable_ai_assessment or not self.router:
            return None
        
        if species.lineage_code in self._processed_this_turn:
            return None
        
        start_time = time.perf_counter()
        
        try:
            # 获取连续高危回合数
            consecutive = self._consecutive_danger.get(species.lineage_code, 0)
            
            # 准备prompt参数
            params = self._prepare_status_eval_params(
                species, base_death_rate, environment_pressure,
                pressure_context, death_causes, consecutive,
                competitors, prey_info, predator_info, habitat_status
            )
            
            prompt = PRESSURE_RESPONSE_PROMPTS["species_status_eval"].format(**params)
            
            # 【改进】使用流式传输调用 AI，可以发送心跳 + 智能超时
            if self.use_streaming and self._event_callback:
                full_content = await self._stream_call_with_heartbeat(
                    capability="species_status_eval",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    task_name=f"评估[{species.common_name}]",
                    timeout=float(self.SPECIES_EVAL_TIMEOUT)
                )
            else:
                # 非流式调用（fallback）
                full_content = await self.router.acall_capability(
                    capability="species_status_eval",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
            
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_ai_call("species_status_eval", duration_ms)
            logger.info(
                f"[AI计时] species_status_eval 完成",
                extra={
                    "method": "evaluate_species_status",
                    "species": species.lineage_code,
                    "duration_ms": round(duration_ms, 1),
                }
            )
            
            # 解析结果
            result = self._parse_status_eval_result(species.lineage_code, full_content)
            
            if result:
                self._processed_this_turn.add(species.lineage_code)
                logger.info(
                    f"[综合评估] {species.common_name}: "
                    f"修正={result.survival_modifier:.2f}, "
                    f"策略={result.response_strategy}, "
                    f"紧急={result.emergency_level}"
                )
            
            return result
            
        except Exception as e:
            logger.warning(f"[综合评估] {species.common_name} AI评估失败: {e}，使用规则fallback")
            # 【优化】AI失败时使用智能规则fallback，确保物种仍能获得评估
            fallback_result = self._generate_rule_based_fallback(
                species, base_death_rate, environment_pressure
            )
            self._processed_this_turn.add(species.lineage_code)
            return fallback_result
    
    # 状态评估批次大小（每批最多处理几个物种）
    STATUS_EVAL_BATCH_SIZE = 3
    
    # 超时配置（可通过 set_timeout_config 方法动态设置）
    SPECIES_EVAL_TIMEOUT = 60  # 单物种评估超时（秒）
    BATCH_EVAL_TIMEOUT = 180   # 整体批量评估超时（秒）
    NARRATIVE_TIMEOUT = 60     # 叙事生成超时（秒）
    
    def set_timeout_config(
        self,
        species_eval_timeout: int = 90,
        batch_eval_timeout: int = 180,
        narrative_timeout: int = 90,
    ) -> None:
        """设置超时配置（从UIConfig读取）"""
        self.SPECIES_EVAL_TIMEOUT = species_eval_timeout
        self.BATCH_EVAL_TIMEOUT = batch_eval_timeout
        self.NARRATIVE_TIMEOUT = narrative_timeout
        logger.info(
            f"[AI压力响应] 超时配置已更新: "
            f"单物种={species_eval_timeout}s, 批量={batch_eval_timeout}s, 叙事={narrative_timeout}s"
        )
    
    async def batch_evaluate_species_status(
        self,
        species_list: Sequence[Species],
        mortality_results: dict[str, float],
        environment_pressure: dict[str, float],
        pressure_context: str,
    ) -> dict[str, SpeciesStatusEval]:
        """【优化】批量综合评估物种状态（全并行模式）
        
        改进策略：
        1. 将所有物种分成小批次（每批4个）
        2. 使用 staggered_gather 并行执行多个批次
        3. 每个批次内部也是并行的
        4. 单个物种超时30秒后快速降级到规则fallback
        
        Returns:
            {lineage_code: SpeciesStatusEval}
        """
        if not self.enable_ai_assessment or not self.router:
            return {}
        
        # 筛选需要评估的物种
        species_to_eval = [
            sp for sp in species_list
            if sp.status == "alive"
            and not sp.is_background
            and sp.lineage_code in mortality_results
            and sp.lineage_code not in self._processed_this_turn
        ][:self.MAX_ASSESSMENTS_PER_TURN]
        
        if not species_to_eval:
            return {}
        
        logger.info(f"[综合评估] 开始并行评估 {len(species_to_eval)} 个物种")
        
        # 单个物种的评估协程（带超时保护）
        async def eval_single_with_fallback(sp: Species) -> tuple[str, SpeciesStatusEval]:
            """评估单个物种，超时则使用规则fallback"""
            base_dr = mortality_results.get(sp.lineage_code, 0.0)
            try:
                # 使用配置的超时时间
                result = await asyncio.wait_for(
                    self.evaluate_species_status(
                        sp, base_dr, environment_pressure, pressure_context
                    ),
                    timeout=float(self.SPECIES_EVAL_TIMEOUT)
                )
                if result:
                    return (sp.lineage_code, result)
            except asyncio.TimeoutError:
                logger.warning(f"[综合评估] {sp.common_name} AI超时(30s)，使用规则fallback")
            except Exception as e:
                logger.warning(f"[综合评估] {sp.common_name} AI失败: {e}，使用规则fallback")
            
            # 降级到规则fallback
            fallback = self._generate_rule_based_fallback(sp, base_dr, environment_pressure)
            return (sp.lineage_code, fallback)
        
        # 如果物种很少（≤4个），直接并行评估所有
        if len(species_to_eval) <= self.STATUS_EVAL_BATCH_SIZE:
            parallel_results = await asyncio.gather(
                *[eval_single_with_fallback(sp) for sp in species_to_eval],
                return_exceptions=True
            )
            
            results = {}
            for item in parallel_results:
                if isinstance(item, Exception):
                    logger.warning(f"[综合评估] 并行评估异常: {item}")
                    continue
                code, result = item
                results[code] = result
                self._processed_this_turn.add(code)
            
            logger.info(f"[综合评估] 并行评估完成: {len(results)}/{len(species_to_eval)} 个物种")
            return results
        
        # 物种较多时，分批并行处理
        batches = []
        for i in range(0, len(species_to_eval), self.STATUS_EVAL_BATCH_SIZE):
            batches.append(species_to_eval[i:i + self.STATUS_EVAL_BATCH_SIZE])
        
        logger.info(f"[综合评估] 分 {len(batches)} 批并行处理（每批最多 {self.STATUS_EVAL_BATCH_SIZE} 个物种）")
        
        # 为每个批次创建协程
        async def process_batch(batch: list[Species]) -> list[tuple[str, SpeciesStatusEval]]:
            """并行处理一个批次"""
            batch_results = await asyncio.gather(
                *[eval_single_with_fallback(sp) for sp in batch],
                return_exceptions=True
            )
            valid_results = []
            for item in batch_results:
                if isinstance(item, Exception):
                    continue
                valid_results.append(item)
            return valid_results
        
        # 使用 staggered_gather 并行执行所有批次
        batch_results = await staggered_gather(
            [process_batch(batch) for batch in batches],
            interval=0.5,  # 批次间隔0.5秒
            max_concurrent=4,  # 最多同时4个批次（即12个并发评估）
            task_name="状态评估批次",
            task_timeout=60.0,  # 单批次超时60秒
            event_callback=self._emit_event if self._event_callback else None,  # 【新增】传递心跳回调
        )
        
        # 合并结果
        results = {}
        for i, batch_result in enumerate(batch_results):
            if isinstance(batch_result, Exception):
                logger.warning(f"[综合评估] 批次{i+1}失败: {batch_result}")
                # 为失败批次的物种生成fallback
                for sp in batches[i]:
                    base_dr = mortality_results.get(sp.lineage_code, 0.0)
                    fallback = self._generate_rule_based_fallback(sp, base_dr, environment_pressure)
                    results[sp.lineage_code] = fallback
                    self._processed_this_turn.add(sp.lineage_code)
                continue
            
            if batch_result:
                for code, result in batch_result:
                    results[code] = result
                    self._processed_this_turn.add(code)
        
        logger.info(f"[综合评估] 分批并行评估完成: {len(results)}/{len(species_to_eval)} 个物种")
        return results
    
    def _prepare_status_eval_params(
        self,
        species: Species,
        base_death_rate: float,
        environment_pressure: dict[str, float],
        pressure_context: str,
        death_causes: str,
        consecutive_danger: int,
        competitors: list[Species] = None,
        prey_info: str = "",
        predator_info: str = "",
        habitat_status: str = "",
    ) -> dict:
        """准备综合状态评估的prompt参数"""
        
        # 特质摘要
        traits_summary = "\n".join([
            f"- {name}: {value:.1f}"
            for name, value in species.abstract_traits.items()
        ])
        
        # 器官摘要
        organs = getattr(species, 'organs', {})
        if organs:
            organs_summary = "\n".join([
                f"- {cat}: {info.get('type', '未知')} (阶段 {info.get('stage', 0)})"
                for cat, info in organs.items()
            ])
        else:
            organs_summary = "无特殊器官系统"
        
        # 营养级分类
        trophic_categories = {
            1: "生产者", 2: "初级消费者", 3: "次级消费者",
            4: "三级消费者", 5: "顶级捕食者"
        }
        trophic_category = trophic_categories.get(int(species.trophic_level), "消费者")
        
        # 压力来源
        pressure_sources = ", ".join([
            f"{k}: {v:.1f}" for k, v in environment_pressure.items() if abs(v) > 0.1
        ]) or "环境稳定"
        
        # 死因分解
        death_breakdown = death_causes or f"环境压力导致约{base_death_rate:.1%}的死亡率"
        
        # 竞争者
        if competitors:
            comp_str = ", ".join([c.common_name for c in competitors[:5]])
        else:
            comp_str = "未检测到直接竞争者"
        
        total_pressure = sum(abs(v) for v in environment_pressure.values())
        population = species.morphology_stats.get("population", 10000) if species.morphology_stats else 10000
        
        # 获取食性类型
        diet_type = getattr(species, 'diet_type', 'omnivore')
        diet_type_cn = {
            "autotroph": "自养生物（化能/光合）",
            "herbivore": "草食动物",
            "carnivore": "肉食动物",
            "omnivore": "杂食动物",
            "detritivore": "腐食/分解者",
        }.get(diet_type, diet_type)
        
        # 提取关键适应性特质（用于快速判断）
        key_traits = []
        traits = species.abstract_traits or {}
        if traits.get("耐热性", 0) >= 8:
            key_traits.append("🔥高耐热")
        if traits.get("耐寒性", 0) >= 8:
            key_traits.append("❄️高耐寒")
        if traits.get("耐盐性", 0) >= 8:
            key_traits.append("🧂高耐盐")
        if traits.get("耐旱性", 0) >= 8:
            key_traits.append("🏜️高耐旱")
        if traits.get("光照需求", 0) <= 2:
            key_traits.append("🌑无需光照")
        if traits.get("氧气需求", 0) <= 2:
            key_traits.append("💨低氧适应")
        key_traits_str = ", ".join(key_traits) if key_traits else "无特殊适应性"
        
        return {
            "latin_name": species.latin_name,
            "common_name": species.common_name,
            "lineage_code": species.lineage_code,
            "trophic_level": species.trophic_level,
            "trophic_category": trophic_category,
            "habitat_type": species.habitat_type or "terrestrial",
            "diet_type": diet_type_cn,
            "key_adaptations": key_traits_str,
            "population": int(population),
            "description": (species.description or "")[:200],
            "traits_summary": traits_summary,
            "organs_summary": organs_summary,
            "total_pressure": total_pressure,
            "pressure_sources": pressure_sources,
            "major_events": pressure_context,
            "base_death_rate": base_death_rate,
            "death_causes_breakdown": death_breakdown,
            "consecutive_danger_turns": consecutive_danger,
            "competitors": comp_str,
            "prey_info": prey_info or "根据营养级自动匹配",
            "predator_info": predator_info or "未检测到直接捕食者",
            "habitat_status": habitat_status or "栖息地状态稳定",
        }
    
    def _parse_status_eval_result(self, lineage_code: str, content: str) -> SpeciesStatusEval | None:
        """解析综合状态评估结果"""
        try:
            data = self.router._parse_content(content)
            if not data:
                return None
            
            # 【扩大范围】验证和限制修正系数：0.3-2.0
            # 允许AI对高压力情况给出更极端的惩罚
            modifier = float(data.get("survival_modifier", 1.0))
            modifier = max(0.3, min(2.0, modifier))
            
            # 解析紧急措施
            emergency_action = data.get("emergency_action", {})
            if isinstance(emergency_action, str):
                emergency_action = {"action_detail": emergency_action}
            
            return SpeciesStatusEval(
                lineage_code=lineage_code,
                survival_modifier=modifier,
                response_strategy=data.get("response_strategy", "适应"),
                key_factors=data.get("key_factors", []),
                population_behavior=data.get("population_behavior", "normal"),
                is_emergency=data.get("is_emergency", False),
                emergency_level=data.get("emergency_level", "stable"),
                emergency_action=emergency_action,
                should_migrate=data.get("should_migrate", False),
                migration_urgency=data.get("migration_urgency", "none"),
                narrative=data.get("brief_narrative", data.get("narrative", "")),
            )
        except Exception as e:
            logger.warning(f"[综合评估] 解析失败: {e}")
            return None
    
    def _parse_batch_status_eval(
        self, 
        content: str, 
        mortality_data: dict[str, float] | None = None
    ) -> dict[str, SpeciesStatusEval]:
        """解析批量综合评估结果
        
        Args:
            content: AI返回的JSON内容
            mortality_data: 物种死亡率数据 {lineage_code: death_rate}，用于推断紧急状态
        """
        results = {}
        if mortality_data is None:
            mortality_data = {}
        
        try:
            data = self.router._parse_content(content)
            if not data:
                return results
            
            assessments = data.get("assessments", [])
            for item in assessments:
                code = item.get("lineage_code")
                if not code:
                    continue
                
                # 【扩大范围】修正系数：0.3-2.0
                modifier = float(item.get("survival_modifier", 1.0))
                modifier = max(0.3, min(2.0, modifier))
                
                # 【修复】基于死亡率自动推断紧急状态
                death_rate = mortality_data.get(code, 0.0)
                consecutive = self._consecutive_danger.get(code, 0)
                
                # 判断紧急状态：
                # - critical: 死亡率>70% 或 连续4+回合高危
                # - warning: 死亡率50-70% 或 连续2-3回合高危
                # - stable: 其他情况
                if death_rate > 0.70 or consecutive >= 4:
                    is_emergency = True
                    emergency_level = "critical"
                elif death_rate > 0.50 or consecutive >= 2:
                    is_emergency = True
                    emergency_level = "warning"
                else:
                    is_emergency = False
                    emergency_level = "stable"
                
                results[code] = SpeciesStatusEval(
                    lineage_code=code,
                    survival_modifier=modifier,
                    response_strategy=item.get("response_strategy", "适应"),
                    key_factors=[item.get("key_factor", "")],
                    population_behavior=item.get("population_behavior", "normal"),
                    is_emergency=is_emergency,
                    emergency_level=emergency_level,
                    narrative=item.get("brief_narrative", ""),
                )
        except Exception as e:
            logger.warning(f"[综合评估] 批量解析失败: {e}")
        
        return results
    
    # ==================== 【新】物种叙事生成 ====================
    
    # 叙事生成批次大小阈值
    NARRATIVE_BATCH_SIZE = 3  # 【优化】减小批量，降低超时风险
    
    # 【优化】叙事物种数量上限（节省tokens）
    MAX_CRITICAL_NARRATIVES = 3   # Critical物种最多3个
    MAX_FOCUS_NARRATIVES = 2      # Focus物种最多4个
    
    async def generate_species_narratives(
        self,
        species_data: list[dict],
        turn_index: int,
        global_environment: str,
        major_events: str,
    ) -> list[SpeciesNarrativeResult]:
        """【优化v2】批量生成物种叙事（节省tokens版）
        
        优化策略：
        1. 限制叙事物种数量：Critical最多3个，Focus最多4个
        2. 优先选择死亡率高或有重要事件的物种
        3. 大幅压缩叙事字数要求
        
        Args:
            species_data: 物种数据列表
            turn_index: 当前回合
            global_environment: 全球环境描述
            major_events: 重大事件描述
            
        Returns:
            叙事结果列表
        """
        if not self.router or not species_data:
            return []
        
        # 【优化】按tier分类并限制数量
        critical_species = [d for d in species_data if d.get("tier") == "critical"]
        focus_species = [d for d in species_data if d.get("tier") == "focus"]
        
        # 按死亡率排序（优先叙述高危物种）
        critical_species.sort(key=lambda x: x.get("death_rate", 0), reverse=True)
        focus_species.sort(key=lambda x: x.get("death_rate", 0), reverse=True)
        
        # 限制数量
        selected_critical = critical_species[:self.MAX_CRITICAL_NARRATIVES]
        selected_focus = focus_species[:self.MAX_FOCUS_NARRATIVES]
        
        filtered_data = selected_critical + selected_focus
        
        if not filtered_data:
            return []
        
        original_count = len(species_data)
        if len(filtered_data) < original_count:
            logger.info(
                f"[物种叙事] 从 {original_count} 个物种中筛选 {len(filtered_data)} 个"
                f" (Critical: {len(selected_critical)}/{len(critical_species)}, "
                f"Focus: {len(selected_focus)}/{len(focus_species)})"
            )
        
        # 如果物种数量不多，直接单次请求
        if len(filtered_data) <= self.NARRATIVE_BATCH_SIZE:
            return await self._generate_narrative_batch(
                filtered_data, turn_index, global_environment, major_events
            )
        
        # 【优化】物种数量较多时，分批并行处理
        logger.info(f"[物种叙事] 物种数量 {len(filtered_data)} > {self.NARRATIVE_BATCH_SIZE}，启用分批并行")
        
        # 分批
        batches = []
        for i in range(0, len(filtered_data), self.NARRATIVE_BATCH_SIZE):
            batches.append(filtered_data[i:i + self.NARRATIVE_BATCH_SIZE])
        
        # 为每个批次创建协程
        async def process_batch(batch: list[dict]) -> list[SpeciesNarrativeResult]:
            return await self._generate_narrative_batch(
                batch, turn_index, global_environment, major_events
            )
        
        # 使用 staggered_gather 并行处理
        batch_results = await staggered_gather(
            [process_batch(batch) for batch in batches],
            interval=1.5,  
            max_concurrent=4,  
            task_name="叙事批次",
            task_timeout=60.0,  # 单批次超时60秒
            event_callback=self._emit_event if self._event_callback else None,  # 【新增】传递心跳回调
        )
        
        # 合并结果
        all_results = []
        failed_batches_data = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.warning(f"[物种叙事] 批次{i+1}失败: {result}")
                failed_batches_data.extend(batches[i])  # 收集失败批次的数据
                continue
            if result:
                all_results.extend(result)
        
        # 【优化】为失败批次的物种生成规则fallback叙事
        if failed_batches_data:
            fallback_narratives = self._generate_rule_based_narratives(failed_batches_data)
            all_results.extend(fallback_narratives)
            logger.info(f"[物种叙事] 为 {len(fallback_narratives)} 个物种生成规则fallback叙事")
        
        logger.info(f"[物种叙事] 分批并行完成: {len(all_results)} 个叙事 ({len(batches)} 批次)")
        return all_results
    
    def _generate_rule_based_narratives(
        self,
        species_data: list[dict],
    ) -> list[SpeciesNarrativeResult]:
        """【优化】为AI失败的物种生成规则基础叙事
        
        确保即使AI不可用，重要物种仍能获得叙事描述。
        """
        results = []
        
        for item in species_data:
            sp = item["species"]
            tier = item.get("tier", "focus")
            dr = item.get("death_rate", 0.0)
            status_eval = item.get("status_eval")
            
            # 根据死亡率确定情绪
            if dr > 0.70:
                mood = "critical"
                headline = "危在旦夕"
            elif dr > 0.50:
                mood = "declining"
                headline = "艰难求存"
            elif dr > 0.30:
                mood = "struggling"
                headline = "应对压力"
            elif dr < 0.10:
                mood = "thriving"
                headline = "繁荣发展"
            else:
                mood = "adapting"
                headline = "稳步适应"
            
            # 生成基本叙事
            if status_eval:
                strategy = status_eval.response_strategy
                narrative = f"{sp.common_name}正采取{strategy}策略应对当前环境。本回合死亡率{dr:.1%}。"
            else:
                narrative = f"{sp.common_name}在当前回合死亡率为{dr:.1%}，种群状态{mood}。"
            
            results.append(SpeciesNarrativeResult(
                lineage_code=sp.lineage_code,
                tier=tier,
                headline=headline,
                narrative=narrative,
                mood=mood,
                highlight_event="",
            ))
        
        return results
    
    async def _generate_narrative_batch(
        self,
        species_data: list[dict],
        turn_index: int,
        global_environment: str,
        major_events: str,
    ) -> list[SpeciesNarrativeResult]:
        """生成单批次叙事（精简版）- 支持流式传输"""
        try:
            # 【优化】构建精简的物种列表字符串
            species_info_list = []
            species_names = []
            for item in species_data:
                sp = item["species"]
                tier = item.get("tier", "focus")
                dr = item.get("death_rate", 0.0)
                
                species_names.append(sp.common_name)
                
                # 精简格式：一行包含所有关键信息
                info = f"[{sp.lineage_code}] {sp.common_name}, {tier}, 死亡率{dr:.0%}, T{sp.trophic_level:.1f}"
                species_info_list.append(info)
            
            prompt = PRESSURE_RESPONSE_PROMPTS["species_narrative"].format(
                turn_index=turn_index,
                global_environment=global_environment,
                major_events=major_events,
                species_list="\n\n".join(species_info_list)
            )
            
            # 【改进】使用流式传输 + 智能超时
            task_name = f"叙事[{', '.join(species_names[:3])}{'...' if len(species_names) > 3 else ''}]"
            
            if self.use_streaming and self._event_callback:
                full_content = await self._stream_call_with_heartbeat(
                    capability="species_narrative",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    task_name=task_name,
                    timeout=float(self.NARRATIVE_TIMEOUT)
                )
            else:
                full_content = await self.router.acall_capability(
                    capability="species_narrative",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"}
                )
            
            # 解析结果
            return self._parse_narrative_results(full_content)
            
        except Exception as e:
            logger.warning(f"[物种叙事] 批次生成失败: {e}")
            return []
    
    def _parse_narrative_results(self, content: str) -> list[SpeciesNarrativeResult]:
        """解析物种叙事结果（精简版）"""
        results = []
        try:
            data = self.router._parse_content(content)
            if not data:
                return results
            
            narratives = data.get("narratives", [])
            for item in narratives:
                code = item.get("lineage_code")
                if not code:
                    continue
                
                results.append(SpeciesNarrativeResult(
                    lineage_code=code,
                    tier=item.get("tier", "focus"),
                    headline=item.get("headline", ""),
                    narrative=item.get("narrative", ""),
                    mood=item.get("mood", "adapting"),
                    highlight_event="",  # 精简版不再生成此字段
                ))
            
            logger.info(f"[物种叙事] 生成了 {len(results)} 个叙事")
        except Exception as e:
            logger.warning(f"[物种叙事] 解析失败: {e}")
        
        return results
    
    def get_last_cross_species_story(self) -> str:
        """获取最近一次生成的物种间互动故事"""
        return getattr(self, '_last_cross_species_story', "")
    
    # ==================== 旧接口兼容性 ====================
    
    def update_danger_tracking(self, lineage_code: str, death_rate: float) -> int:
        """更新物种的危险追踪
        
        Returns:
            连续高危回合数
        """
        if death_rate >= 0.5:
            self._consecutive_danger[lineage_code] = \
                self._consecutive_danger.get(lineage_code, 0) + 1
        else:
            self._consecutive_danger[lineage_code] = 0
        
        return self._consecutive_danger.get(lineage_code, 0)
    
    # ==================== 方案A：压力评估顾问 ====================
    
    async def assess_pressure_response(
        self,
        species: Species,
        base_death_rate: float,
        environment_pressure: dict[str, float],
        pressure_context: str,
        competitors: list[Species] = None,
        prey_info: str = "",
        predator_info: str = "",
        habitat_status: str = "",
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> PressureAssessmentResult | None:
        """评估物种对压力的应对能力
        
        Args:
            species: 目标物种
            base_death_rate: 规则引擎计算的基础死亡率
            environment_pressure: 环境压力字典
            pressure_context: 压力上下文描述
            competitors: 竞争者列表
            prey_info: 猎物信息
            predator_info: 捕食者信息
            habitat_status: 栖息地状态
            
        Returns:
            压力评估结果，包含修正系数
        """
        if not self.enable_ai_assessment or not self.router:
            return None
        
        if species.lineage_code in self._processed_this_turn:
            return None
        
        try:
            # 准备prompt参数
            prompt_params = self._prepare_assessment_params(
                species, base_death_rate, environment_pressure, 
                pressure_context, competitors, prey_info, predator_info, habitat_status
            )
            
            prompt = PRESSURE_RESPONSE_PROMPTS["pressure_assessment"].format(**prompt_params)
            
            # 【优化】使用带心跳的调用
            from ...ai.streaming_helper import acall_with_heartbeat
            full_content = await acall_with_heartbeat(
                router=self.router,
                capability="pressure_adaptation",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"压力评估[{species.common_name[:8]}]",
                timeout=60,
                heartbeat_interval=2.0,
                event_callback=self._emit_event if self._event_callback else None,
            )
            
            if stream_callback and full_content:
                await stream_callback(full_content)
            
            # 解析结果
            result = self._parse_assessment_result(species.lineage_code, full_content)
            
            if result:
                self._processed_this_turn.add(species.lineage_code)
                logger.info(
                    f"[AI压力评估] {species.common_name}: "
                    f"修正系数={result.survival_modifier:.2f}, "
                    f"策略={result.response_strategy}"
                )
            
            return result
            
        except Exception as e:
            logger.warning(f"[AI压力评估] {species.common_name} 评估失败: {e}")
            return None
    
    async def batch_assess_pressure(
        self,
        species_list: Sequence[Species],
        mortality_results: dict[str, float],  # {lineage_code: base_death_rate}
        environment_pressure: dict[str, float],
        pressure_context: str,
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> dict[str, PressureAssessmentResult]:
        """批量评估多个物种的压力响应
        
        Returns:
            {lineage_code: PressureAssessmentResult}
        """
        if not self.enable_ai_assessment or not self.router:
            return {}
        
        # 筛选需要评估的物种（非背景，且有死亡率数据）
        species_to_assess = [
            sp for sp in species_list
            if sp.status == "alive" 
            and not sp.is_background
            and sp.lineage_code in mortality_results
            and sp.lineage_code not in self._processed_this_turn
        ][:self.MAX_ASSESSMENTS_PER_TURN]
        
        if not species_to_assess:
            return {}
        
        try:
            # 准备批量prompt
            species_info_list = []
            for sp in species_to_assess:
                base_dr = mortality_results.get(sp.lineage_code, 0.0)
                info = (
                    f"【{sp.lineage_code}】{sp.common_name}\n"
                    f"  营养级: T{sp.trophic_level:.1f}, 栖息地: {sp.habitat_type}\n"
                    f"  基础死亡率: {base_dr:.1%}\n"
                    f"  关键特质: 耐寒{sp.abstract_traits.get('耐寒性', 5):.0f}, "
                    f"耐热{sp.abstract_traits.get('耐热性', 5):.0f}, "
                    f"耐旱{sp.abstract_traits.get('耐旱性', 5):.0f}"
                )
                species_info_list.append(info)
            
            total_pressure = sum(abs(v) for v in environment_pressure.values())
            
            prompt = PRESSURE_RESPONSE_PROMPTS["pressure_assessment_batch"].format(
                total_pressure=total_pressure,
                pressure_sources=pressure_context,
                major_events="",
                species_list="\n\n".join(species_info_list)
            )
            
            # 【优化】使用带心跳的调用
            from ...ai.streaming_helper import acall_with_heartbeat
            full_content = await acall_with_heartbeat(
                router=self.router,
                capability="pressure_adaptation",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"批量压力评估[{len(species_to_assess)}物种]",
                timeout=90,
                heartbeat_interval=2.0,
                event_callback=self._emit_event if self._event_callback else None,
            )
            
            if stream_callback and full_content:
                await stream_callback(full_content)
            
            # 解析批量结果
            results = self._parse_batch_assessment(full_content)
            
            for code in results:
                self._processed_this_turn.add(code)
            
            logger.info(f"[AI压力评估] 批量评估完成: {len(results)} 个物种")
            return results
            
        except Exception as e:
            logger.warning(f"[AI压力评估] 批量评估失败: {e}")
            return {}
    
    def _prepare_assessment_params(
        self,
        species: Species,
        base_death_rate: float,
        environment_pressure: dict[str, float],
        pressure_context: str,
        competitors: list[Species] = None,
        prey_info: str = "",
        predator_info: str = "",
        habitat_status: str = "",
    ) -> dict:
        """准备压力评估的prompt参数"""
        
        # 特质摘要
        traits_summary = "\n".join([
            f"- {name}: {value:.1f}"
            for name, value in species.abstract_traits.items()
        ])
        
        # 器官摘要
        organs = getattr(species, 'organs', {})
        if organs:
            organs_summary = "\n".join([
                f"- {cat}: {info.get('type', '未知')} (阶段 {info.get('stage', 0)})"
                for cat, info in organs.items()
            ])
        else:
            organs_summary = "无特殊器官系统"
        
        # 营养级分类
        trophic_categories = {
            1: "生产者", 2: "初级消费者", 3: "次级消费者",
            4: "三级消费者", 5: "顶级捕食者"
        }
        trophic_category = trophic_categories.get(int(species.trophic_level), "消费者")
        
        # 历史高光
        highlights = getattr(species, 'history_highlights', [])
        history_str = "; ".join(highlights[-3:]) if highlights else "无记录"
        
        # 压力来源
        pressure_sources = ", ".join([
            f"{k}: {v:.1f}" for k, v in environment_pressure.items() if abs(v) > 0.1
        ]) or "环境稳定"
        
        # 死因分解
        death_causes = f"环境压力导致约{base_death_rate:.1%}的死亡率"
        
        # 竞争者
        if competitors:
            comp_str = ", ".join([c.common_name for c in competitors[:5]])
        else:
            comp_str = "未检测到直接竞争者"
        
        total_pressure = sum(abs(v) for v in environment_pressure.values())
        
        return {
            "latin_name": species.latin_name,
            "common_name": species.common_name,
            "lineage_code": species.lineage_code,
            "trophic_level": species.trophic_level,
            "trophic_category": trophic_category,
            "habitat_type": species.habitat_type or "terrestrial",
            "description": species.description[:200],
            "traits_summary": traits_summary,
            "organs_summary": organs_summary,
            "history_highlights": history_str,
            "total_pressure": total_pressure,
            "pressure_sources": pressure_sources,
            "major_events": pressure_context,
            "base_death_rate": base_death_rate,
            "death_causes_breakdown": death_causes,
            "competitors": comp_str,
            "prey_info": prey_info or "根据营养级自动匹配",
            "predator_info": predator_info or "未检测到直接捕食者",
            "habitat_status": habitat_status or "栖息地状态稳定",
        }
    
    def _parse_assessment_result(self, lineage_code: str, content: str) -> PressureAssessmentResult | None:
        """解析AI返回的评估结果"""
        try:
            data = self.router._parse_content(content)
            if not data:
                return None
            
            # 【扩大范围】验证和限制修正系数：0.3-2.0
            modifier = float(data.get("survival_modifier", 1.0))
            modifier = max(0.3, min(2.0, modifier))
            
            return PressureAssessmentResult(
                lineage_code=lineage_code,
                survival_modifier=modifier,
                response_strategy=data.get("response_strategy", "适应"),
                key_survival_factors=data.get("key_survival_factors", []),
                key_risk_factors=data.get("key_risk_factors", []),
                population_behavior=data.get("population_behavior", "normal"),
                narrative=data.get("narrative", ""),
            )
        except Exception as e:
            logger.warning(f"[AI压力评估] 解析失败: {e}")
            return None
    
    def _parse_batch_assessment(self, content: str) -> dict[str, PressureAssessmentResult]:
        """解析批量评估结果"""
        results = {}
        try:
            data = self.router._parse_content(content)
            if not data:
                return results
            
            assessments = data.get("assessments", [])
            for item in assessments:
                code = item.get("lineage_code")
                if not code:
                    continue
                
                # 【扩大范围】修正系数：0.3-2.0
                modifier = float(item.get("survival_modifier", 1.0))
                modifier = max(0.3, min(2.0, modifier))
                
                results[code] = PressureAssessmentResult(
                    lineage_code=code,
                    survival_modifier=modifier,
                    response_strategy=item.get("response_strategy", "适应"),
                    key_survival_factors=[item.get("key_factor", "")],
                    population_behavior=item.get("population_behavior", "normal"),
                    narrative=item.get("brief_narrative", ""),
                )
        except Exception as e:
            logger.warning(f"[AI压力评估] 批量解析失败: {e}")
        
        return results
    
    # ==================== 方案B：种群博弈仲裁 ====================
    
    async def arbitrate_interaction(
        self,
        species_a: Species,
        species_b: Species,
        interaction_type: str,
        habitat_overlap: float,
        environment_context: str,
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> InteractionResult | None:
        """仲裁两个物种间的互动
        
        Args:
            species_a: 物种A
            species_b: 物种B
            interaction_type: 互动类型 (predation/competition/mutualism/parasitism)
            habitat_overlap: 栖息地重叠度 (0-1)
            environment_context: 环境背景
        """
        if not self.enable_ai_interaction or not self.router:
            return None
        
        try:
            # 确定互动角色
            if interaction_type == "predation":
                if species_a.trophic_level > species_b.trophic_level:
                    role_a, role_b = "捕食者", "猎物"
                else:
                    role_a, role_b = "猎物", "捕食者"
            elif interaction_type == "competition":
                role_a, role_b = "竞争者", "竞争者"
            else:
                role_a, role_b = "参与方", "参与方"
            
            # 特质摘要
            def trait_summary(sp: Species) -> str:
                traits = sp.abstract_traits
                return (
                    f"耐寒{traits.get('耐寒性', 5):.0f}, "
                    f"运动{traits.get('运动能力', 5):.0f}, "
                    f"繁殖{traits.get('繁殖速度', 5):.0f}"
                )
            
            prompt = PRESSURE_RESPONSE_PROMPTS["species_interaction"].format(
                interaction_role_a=role_a,
                species_a_latin=species_a.latin_name,
                species_a_common=species_a.common_name,
                species_a_trophic=species_a.trophic_level,
                species_a_traits=trait_summary(species_a),
                species_a_population=10000,  # 简化
                interaction_role_b=role_b,
                species_b_latin=species_b.latin_name,
                species_b_common=species_b.common_name,
                species_b_trophic=species_b.trophic_level,
                species_b_traits=trait_summary(species_b),
                species_b_population=10000,
                interaction_type=interaction_type,
                habitat_overlap=habitat_overlap,
                resource_competition=habitat_overlap * 10,
                interaction_history="首次记录的互动",
                environment_context=environment_context,
            )
            
            # 【优化】使用带心跳的调用
            from ...ai.streaming_helper import acall_with_heartbeat
            full_content = await acall_with_heartbeat(
                router=self.router,
                capability="pressure_adaptation",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"互动[{species_a.common_name[:5]}↔{species_b.common_name[:5]}]",
                timeout=60,
                heartbeat_interval=2.0,
                event_callback=self._emit_event if self._event_callback else None,
            )
            
            if stream_callback and full_content:
                await stream_callback(full_content)
            
            return self._parse_interaction_result(
                species_a.lineage_code, species_b.lineage_code, 
                interaction_type, full_content
            )
            
        except Exception as e:
            logger.warning(f"[AI博弈] 仲裁失败: {e}")
            return None
    
    def _parse_interaction_result(
        self, code_a: str, code_b: str, 
        interaction_type: str, content: str
    ) -> InteractionResult | None:
        """解析互动仲裁结果"""
        try:
            data = self.router._parse_content(content)
            if not data:
                return None
            
            a_effects = data.get("a_effects", {})
            b_effects = data.get("b_effects", {})
            
            # 限制死亡率变化范围
            a_delta = float(a_effects.get("mortality_delta", 0))
            b_delta = float(b_effects.get("mortality_delta", 0))
            a_delta = max(-0.15, min(0.25, a_delta))
            b_delta = max(-0.15, min(0.25, b_delta))
            
            return InteractionResult(
                species_a_code=code_a,
                species_b_code=code_b,
                interaction_type=interaction_type,
                outcome=data.get("interaction_outcome", "draw"),
                a_mortality_delta=a_delta,
                b_mortality_delta=b_delta,
                narrative=data.get("narrative", ""),
            )
        except Exception as e:
            logger.warning(f"[AI博弈] 解析失败: {e}")
            return None
    
    # ==================== 方案C：紧急响应系统 ====================
    
    def should_trigger_emergency(
        self,
        species: Species,
        death_rate: float,
        is_major_event: bool = False
    ) -> tuple[bool, str]:
        """判断是否应该触发紧急响应
        
        Returns:
            (是否触发, 触发原因)
        """
        consecutive = self._consecutive_danger.get(species.lineage_code, 0)
        
        # 触发条件
        if death_rate >= self.EMERGENCY_DEATH_RATE:
            return True, f"死亡率达到{death_rate:.1%}，处于濒危状态"
        
        if consecutive >= self.CONSECUTIVE_DANGER_THRESHOLD:
            return True, f"连续{consecutive}回合死亡率超过50%"
        
        if is_major_event and death_rate >= 0.5:
            return True, "重大环境事件导致高死亡率"
        
        return False, ""
    
    async def generate_emergency_response(
        self,
        species: Species,
        death_rate: float,
        trigger_reason: str,
        environment_context: str,
        potential_destinations: str = "",
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> EmergencyResponse | None:
        """生成紧急响应计划"""
        if not self.enable_emergency_response or not self.router:
            return None
        
        try:
            consecutive = self._consecutive_danger.get(species.lineage_code, 0)
            extinction_eta = max(1, int((1 - death_rate) / max(0.1, death_rate - 0.3) * 2))
            
            # 关键特质
            key_traits = "\n".join([
                f"- {name}: {value:.1f}"
                for name, value in sorted(
                    species.abstract_traits.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]
            ])
            
            # 器官摘要
            organs = getattr(species, 'organs', {})
            organs_summary = ", ".join([
                f"{cat}({info.get('type', '?')})"
                for cat, info in organs.items()
            ]) or "无特殊器官"
            
            # 可调整特质
            adjustable_traits = ", ".join(species.abstract_traits.keys())
            
            prompt = PRESSURE_RESPONSE_PROMPTS["emergency_response"].format(
                trigger_reason=trigger_reason,
                current_death_rate=death_rate,
                consecutive_danger_turns=consecutive,
                extinction_eta=extinction_eta,
                latin_name=species.latin_name,
                common_name=species.common_name,
                trophic_level=species.trophic_level,
                population=10000,
                habitat_type=species.habitat_type or "terrestrial",
                key_traits=key_traits,
                organs_summary=organs_summary,
                past_crises="; ".join(getattr(species, 'history_highlights', [])[-2:]) or "无记录",
                survival_history="该物种尚无重大危机记录",
                threat_details=environment_context,
                potential_destinations=potential_destinations or "需要根据物种能力搜索",
                adjustable_traits=adjustable_traits,
                alternative_food="根据营养级自动搜索",
            )
            
            # 【优化】使用带心跳的调用
            from ...ai.streaming_helper import acall_with_heartbeat
            full_content = await acall_with_heartbeat(
                router=self.router,
                capability="pressure_adaptation",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"紧急响应[{species.common_name[:8]}]",
                timeout=60,
                heartbeat_interval=2.0,
                event_callback=self._emit_event if self._event_callback else None,
            )
            
            if stream_callback and full_content:
                await stream_callback(full_content)
            
            return self._parse_emergency_response(species.lineage_code, full_content)
            
        except Exception as e:
            logger.warning(f"[紧急响应] {species.common_name} 生成失败: {e}")
            return None
    
    def _parse_emergency_response(self, lineage_code: str, content: str) -> EmergencyResponse | None:
        """解析紧急响应结果"""
        try:
            data = self.router._parse_content(content)
            if not data:
                return None
            
            # 解析特质变化
            trait_changes = {}
            strategy_details = data.get("strategy_details", {})
            if "trait_changes" in strategy_details:
                for name, change in strategy_details["trait_changes"].items():
                    try:
                        if isinstance(change, str):
                            delta = float(change.replace("+", ""))
                        else:
                            delta = float(change)
                        trait_changes[name] = max(-1.0, min(1.0, delta))
                    except:
                        pass
            
            return EmergencyResponse(
                lineage_code=lineage_code,
                primary_strategy=data.get("primary_strategy", "accept_extinction"),
                survival_probability=float(data.get("survival_probability", 0.5)),
                mortality_reduction=max(0, min(0.5, float(data.get("mortality_reduction", 0)))),
                immediate_actions=data.get("immediate_actions", []),
                trait_changes=trait_changes,
                narrative=data.get("narrative", ""),
            )
        except Exception as e:
            logger.warning(f"[紧急响应] 解析失败: {e}")
            return None
    
    # ==================== 方案D：迁徙决策参谋 ====================
    
    async def advise_migration(
        self,
        species: Species,
        migration_trigger: str,
        current_mortality: float,
        candidate_destinations: list[dict],  # [{tile_id, coords, biome, suitability, prey_density, distance}]
        stream_callback: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> MigrationAdvice | None:
        """为物种提供迁徙建议"""
        if not self.enable_migration_advice or not self.router:
            return None
        
        if not candidate_destinations:
            return None
        
        try:
            # 格式化候选目的地
            dest_list = []
            for dest in candidate_destinations[:10]:
                dest_str = (
                    f"- 地块{dest.get('tile_id')}: "
                    f"坐标({dest.get('x', 0)}, {dest.get('y', 0)}), "
                    f"生物群落={dest.get('biome', '未知')}, "
                    f"适宜度={dest.get('suitability', 0):.2f}, "
                    f"猎物密度={dest.get('prey_density', 0):.2f}, "
                    f"距离={dest.get('distance', 0):.0f}格"
                )
                dest_list.append(dest_str)
            
            # 迁徙能力
            organs = getattr(species, 'organs', {})
            locomotion = organs.get('locomotion', {})
            locomotion_type = locomotion.get('type', 'walking')
            
            if locomotion_type in ('wings', 'flight'):
                migration_cap = "高（飞行）"
                migration_range = "10-15格"
            elif locomotion_type in ('fins', 'swimming'):
                migration_cap = "中等（游泳）"
                migration_range = "5-8格"
            else:
                migration_cap = "低-中等（陆地移动）"
                migration_range = "3-5格"
            
            prompt = PRESSURE_RESPONSE_PROMPTS["migration_advisor"].format(
                latin_name=species.latin_name,
                common_name=species.common_name,
                trophic_level=species.trophic_level,
                habitat_type=species.habitat_type or "terrestrial",
                migration_capability=migration_cap,
                migration_range=migration_range,
                temp_preference=f"耐寒{species.abstract_traits.get('耐寒性', 5):.0f}, 耐热{species.abstract_traits.get('耐热性', 5):.0f}",
                humidity_requirement=f"耐旱{species.abstract_traits.get('耐旱性', 5):.0f}",
                food_requirement=f"T{species.trophic_level:.0f}营养级所需食物",
                migration_trigger=migration_trigger,
                current_region="当前栖息地",
                current_mortality=current_mortality,
                current_problems=migration_trigger,
                candidate_destinations="\n".join(dest_list),
            )
            
            # 【优化】使用带心跳的调用
            from ...ai.streaming_helper import acall_with_heartbeat
            full_content = await acall_with_heartbeat(
                router=self.router,
                capability="pressure_adaptation",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                task_name=f"迁徙建议[{species.common_name[:8]}]",
                timeout=60,
                heartbeat_interval=2.0,
                event_callback=self._emit_event if self._event_callback else None,
            )
            
            if stream_callback and full_content:
                await stream_callback(full_content)
            
            return self._parse_migration_advice(species.lineage_code, full_content)
            
        except Exception as e:
            logger.warning(f"[迁徙建议] {species.common_name} 生成失败: {e}")
            return None
    
    def _parse_migration_advice(self, lineage_code: str, content: str) -> MigrationAdvice | None:
        """解析迁徙建议"""
        try:
            data = self.router._parse_content(content)
            if not data:
                return None
            
            # 获取推荐目的地
            dest = data.get("recommended_destination")
            if dest is None:
                return None
            
            try:
                dest_id = int(dest)
            except:
                return None
            
            expected = data.get("expected_outcomes", {})
            cost = data.get("migration_cost", {})
            
            return MigrationAdvice(
                lineage_code=lineage_code,
                recommended_destination=dest_id,
                destination_score=float(data.get("destination_score", 0.5)),
                expected_mortality_change=float(expected.get("mortality_change", 0)),
                journey_mortality=float(cost.get("journey_mortality", 0.1)),
                reasoning=data.get("selection_reasoning", ""),
                narrative=data.get("narrative", ""),
            )
        except Exception as e:
            logger.warning(f"[迁徙建议] 解析失败: {e}")
            return None


# 工厂函数
def create_ai_pressure_service(router: ModelRouter) -> AIPressureResponseService:
    """创建AI压力响应服务实例"""
    return AIPressureResponseService(router)

