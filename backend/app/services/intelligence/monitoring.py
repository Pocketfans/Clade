"""
Monitoring - 生态智能体监控

提供智能体流水线的监控、指标收集和降级策略。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class StageMetrics:
    """单个阶段的指标"""
    stage_name: str
    
    # 时间指标
    duration_ms: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 处理数量
    items_processed: int = 0
    items_failed: int = 0
    
    # 错误信息
    errors: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        if self.items_processed == 0:
            return 1.0
        return 1.0 - (self.items_failed / self.items_processed)


@dataclass
class TurnMetrics:
    """单个回合的指标"""
    turn_index: int
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    # 物种统计
    total_species: int = 0
    tier_a_count: int = 0
    tier_b_count: int = 0
    tier_c_count: int = 0
    
    # LLM 调用
    llm_calls_attempted: int = 0
    llm_calls_succeeded: int = 0
    llm_calls_failed: int = 0
    llm_total_tokens: int = 0
    
    # 阶段指标
    stage_metrics: Dict[str, StageMetrics] = field(default_factory=dict)
    
    # 状态
    status: HealthStatus = HealthStatus.HEALTHY
    fallback_used: bool = False
    errors: List[str] = field(default_factory=list)
    
    @property
    def duration_ms(self) -> float:
        if self.completed_at is None:
            return (datetime.now() - self.started_at).total_seconds() * 1000
        return (self.completed_at - self.started_at).total_seconds() * 1000
    
    @property
    def llm_success_rate(self) -> float:
        if self.llm_calls_attempted == 0:
            return 1.0
        return self.llm_calls_succeeded / self.llm_calls_attempted


class IntelligenceMonitor:
    """智能体监控器
    
    职责：
    1. 收集和存储各阶段的指标
    2. 跟踪 LLM 调用统计
    3. 检测异常并触发降级
    4. 提供健康状态查询
    """
    
    def __init__(
        self,
        history_size: int = 100,
        llm_failure_threshold: float = 0.5,  # 50% 失败率触发降级
        timeout_threshold_ms: float = 30000,  # 30秒超时警告
    ):
        self.history_size = history_size
        self.llm_failure_threshold = llm_failure_threshold
        self.timeout_threshold_ms = timeout_threshold_ms
        
        # 回合历史
        self._turn_history: List[TurnMetrics] = []
        self._current_turn: Optional[TurnMetrics] = None
        
        # 全局统计
        self._total_turns: int = 0
        self._total_llm_calls: int = 0
        self._total_llm_failures: int = 0
        self._consecutive_failures: int = 0
        
        # 阶段计时
        self._stage_start_times: Dict[str, float] = {}
        
        logger.info("[IntelligenceMonitor] 初始化完成")
    
    # =========================================================================
    # 回合生命周期
    # =========================================================================
    
    def start_turn(self, turn_index: int, total_species: int) -> TurnMetrics:
        """开始新回合"""
        if self._current_turn is not None:
            logger.warning("[Monitor] 上一回合未正常结束，强制完成")
            self.end_turn()
        
        self._current_turn = TurnMetrics(
            turn_index=turn_index,
            total_species=total_species,
        )
        
        logger.debug(f"[Monitor] 开始回合 {turn_index}")
        return self._current_turn
    
    def end_turn(self, success: bool = True) -> Optional[TurnMetrics]:
        """结束当前回合"""
        if self._current_turn is None:
            return None
        
        self._current_turn.completed_at = datetime.now()
        
        # 确定状态
        if not success or self._current_turn.fallback_used:
            self._current_turn.status = HealthStatus.DEGRADED
        
        if self._current_turn.llm_success_rate < 0.5:
            self._current_turn.status = HealthStatus.UNHEALTHY
        
        # 存入历史
        self._turn_history.append(self._current_turn)
        if len(self._turn_history) > self.history_size:
            self._turn_history.pop(0)
        
        # 更新全局统计
        self._total_turns += 1
        
        result = self._current_turn
        self._current_turn = None
        
        logger.info(
            f"[Monitor] 回合 {result.turn_index} 完成: "
            f"耗时 {result.duration_ms:.0f}ms, "
            f"状态 {result.status.value}"
        )
        
        return result
    
    # =========================================================================
    # 阶段跟踪
    # =========================================================================
    
    def start_stage(self, stage_name: str) -> None:
        """开始阶段计时"""
        self._stage_start_times[stage_name] = time.time()
        
        if self._current_turn is not None:
            self._current_turn.stage_metrics[stage_name] = StageMetrics(
                stage_name=stage_name,
                started_at=datetime.now(),
            )
    
    def end_stage(
        self,
        stage_name: str,
        items_processed: int = 0,
        items_failed: int = 0,
        errors: List[str] | None = None,
    ) -> Optional[StageMetrics]:
        """结束阶段计时"""
        start_time = self._stage_start_times.pop(stage_name, None)
        
        if self._current_turn is None:
            return None
        
        metrics = self._current_turn.stage_metrics.get(stage_name)
        if metrics is None:
            metrics = StageMetrics(stage_name=stage_name)
            self._current_turn.stage_metrics[stage_name] = metrics
        
        if start_time is not None:
            metrics.duration_ms = (time.time() - start_time) * 1000
        
        metrics.completed_at = datetime.now()
        metrics.items_processed = items_processed
        metrics.items_failed = items_failed
        
        if errors:
            metrics.errors = errors
        
        # 超时警告
        if metrics.duration_ms > self.timeout_threshold_ms:
            logger.warning(
                f"[Monitor] 阶段 {stage_name} 耗时过长: "
                f"{metrics.duration_ms:.0f}ms"
            )
        
        return metrics
    
    # =========================================================================
    # LLM 调用跟踪
    # =========================================================================
    
    def record_llm_call(
        self,
        success: bool,
        tokens: int = 0,
        error: str | None = None,
    ) -> None:
        """记录 LLM 调用"""
        self._total_llm_calls += 1
        
        if self._current_turn is not None:
            self._current_turn.llm_calls_attempted += 1
            
            if success:
                self._current_turn.llm_calls_succeeded += 1
                self._current_turn.llm_total_tokens += tokens
                self._consecutive_failures = 0
            else:
                self._current_turn.llm_calls_failed += 1
                self._total_llm_failures += 1
                self._consecutive_failures += 1
                
                if error:
                    self._current_turn.errors.append(error)
    
    def record_tier_distribution(
        self,
        tier_a: int,
        tier_b: int,
        tier_c: int,
    ) -> None:
        """记录分档分布"""
        if self._current_turn is not None:
            self._current_turn.tier_a_count = tier_a
            self._current_turn.tier_b_count = tier_b
            self._current_turn.tier_c_count = tier_c
    
    def record_fallback_used(self) -> None:
        """记录使用了降级策略"""
        if self._current_turn is not None:
            self._current_turn.fallback_used = True
            logger.warning("[Monitor] 触发降级策略")
    
    # =========================================================================
    # 健康检查
    # =========================================================================
    
    def get_health_status(self) -> HealthStatus:
        """获取当前健康状态"""
        # 连续失败检查
        if self._consecutive_failures >= 3:
            return HealthStatus.UNHEALTHY
        
        # 最近成功率检查
        recent_turns = self._turn_history[-10:]
        if recent_turns:
            unhealthy_count = sum(
                1 for t in recent_turns
                if t.status == HealthStatus.UNHEALTHY
            )
            if unhealthy_count >= 3:
                return HealthStatus.UNHEALTHY
            if unhealthy_count >= 1:
                return HealthStatus.DEGRADED
        
        # LLM 失败率检查
        if self._total_llm_calls > 10:
            failure_rate = self._total_llm_failures / self._total_llm_calls
            if failure_rate > self.llm_failure_threshold:
                return HealthStatus.DEGRADED
        
        return HealthStatus.HEALTHY
    
    def should_fallback(self) -> bool:
        """是否应该使用降级策略"""
        return (
            self._consecutive_failures >= 2 or
            self.get_health_status() == HealthStatus.UNHEALTHY
        )
    
    # =========================================================================
    # 统计查询
    # =========================================================================
    
    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要"""
        recent = self._turn_history[-20:] if self._turn_history else []
        
        avg_duration = 0.0
        avg_llm_success_rate = 1.0
        if recent:
            avg_duration = sum(t.duration_ms for t in recent) / len(recent)
            avg_llm_success_rate = sum(t.llm_success_rate for t in recent) / len(recent)
        
        return {
            "health_status": self.get_health_status().value,
            "total_turns": self._total_turns,
            "total_llm_calls": self._total_llm_calls,
            "total_llm_failures": self._total_llm_failures,
            "consecutive_failures": self._consecutive_failures,
            "recent_avg_duration_ms": avg_duration,
            "recent_avg_llm_success_rate": avg_llm_success_rate,
            "should_fallback": self.should_fallback(),
        }
    
    def get_turn_history(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取回合历史"""
        recent = self._turn_history[-limit:]
        
        return [
            {
                "turn_index": t.turn_index,
                "duration_ms": t.duration_ms,
                "status": t.status.value,
                "tier_a": t.tier_a_count,
                "tier_b": t.tier_b_count,
                "tier_c": t.tier_c_count,
                "llm_success_rate": t.llm_success_rate,
                "fallback_used": t.fallback_used,
            }
            for t in recent
        ]
    
    def reset_stats(self) -> None:
        """重置统计（用于测试）"""
        self._turn_history.clear()
        self._current_turn = None
        self._total_turns = 0
        self._total_llm_calls = 0
        self._total_llm_failures = 0
        self._consecutive_failures = 0
        self._stage_start_times.clear()


# 全局监控器实例
_global_monitor: Optional[IntelligenceMonitor] = None


def get_monitor() -> IntelligenceMonitor:
    """获取全局监控器实例"""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = IntelligenceMonitor()
    return _global_monitor


def reset_monitor() -> None:
    """重置全局监控器（用于测试）"""
    global _global_monitor
    _global_monitor = None


