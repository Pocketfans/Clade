"""
张量系统监控指标

提供张量计算系统的性能监控和统计功能：
- 执行耗时追踪
- 分化触发命中率
- 回退频次统计
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class TensorMetrics:
    """张量系统监控指标
    
    记录单个回合或累计的张量系统性能数据。
    
    Attributes:
        mortality_time_ms: 死亡率计算耗时（毫秒）
        speciation_detection_time_ms: 分化检测耗时（毫秒）
        tradeoff_time_ms: 代价计算耗时（毫秒）
            migration_time_ms: 迁徙计算耗时（毫秒）
        tensor_triggers: 张量检测产生的分化触发数
        ai_fallback_count: AI 回退次数
        isolation_detections: 地理隔离检测次数
        divergence_detections: 环境分歧检测次数
    """
    
    mortality_time_ms: float = 0.0
    speciation_detection_time_ms: float = 0.0
    tradeoff_time_ms: float = 0.0
    migration_time_ms: float = 0.0
    tensor_triggers: int = 0
    ai_fallback_count: int = 0
    isolation_detections: int = 0
    divergence_detections: int = 0
    
    def total_time_ms(self) -> float:
        """总张量计算耗时"""
        return (
            self.mortality_time_ms
            + self.speciation_detection_time_ms
            + self.tradeoff_time_ms
            + self.migration_time_ms
        )
    
    def trigger_hit_rate(self, total_speciations: int) -> float:
        """分化触发命中率
        
        Args:
            total_speciations: 本回合实际发生的分化总数
        
        Returns:
            张量检测触发占总分化的比例 (0.0-1.0)
        """
        if total_speciations == 0:
            return 0.0
        return min(1.0, self.tensor_triggers / total_speciations)
    
    def to_dict(self) -> Dict[str, float | int]:
        """转换为字典（用于日志和导出）"""
        return {
            "mortality_time_ms": round(self.mortality_time_ms, 2),
            "speciation_detection_time_ms": round(self.speciation_detection_time_ms, 2),
            "tradeoff_time_ms": round(self.tradeoff_time_ms, 2),
            "migration_time_ms": round(self.migration_time_ms, 2),
            "total_time_ms": round(self.total_time_ms(), 2),
            "tensor_triggers": self.tensor_triggers,
            "ai_fallback_count": self.ai_fallback_count,
            "isolation_detections": self.isolation_detections,
            "divergence_detections": self.divergence_detections,
        }
    
    def log_summary(self, turn: int = 0) -> None:
        """记录性能摘要到日志"""
        logger.info(
            f"[张量监控] 回合{turn}: "
            f"死亡率={self.mortality_time_ms:.1f}ms, "
            f"迁徙={self.migration_time_ms:.1f}ms, "
            f"分化检测={self.speciation_detection_time_ms:.1f}ms, "
            f"代价计算={self.tradeoff_time_ms:.1f}ms, "
            f"触发数={self.tensor_triggers}, "
            f"回退数={self.ai_fallback_count}"
        )


@dataclass
class TensorMetricsCollector:
    """张量系统指标收集器
    
    跨回合累积和统计张量系统的性能数据。
    
    使用方式：
        collector = TensorMetricsCollector()
        
        # 在每个回合中
        with collector.track_mortality():
            # 执行死亡率计算
            ...
        
        collector.record_tensor_trigger(count=3)
        
        # 回合结束
        collector.end_turn()
        
        # 查看统计
        stats = collector.get_statistics()
    """
    
    # 当前回合指标
    current: TensorMetrics = field(default_factory=TensorMetrics)
    
    # 历史指标（最近 N 回合）
    history: List[TensorMetrics] = field(default_factory=list)
    max_history: int = 100
    
    # 累计统计
    total_turns: int = 0
    total_tensor_triggers: int = 0
    total_ai_fallbacks: int = 0
    total_time_ms: float = 0.0
    
    def reset_current(self) -> None:
        """重置当前回合指标"""
        self.current = TensorMetrics()
    
    def end_turn(self, turn: int = 0) -> TensorMetrics:
        """结束当前回合，保存指标
        
        Args:
            turn: 当前回合数
        
        Returns:
            本回合的指标
        """
        metrics = self.current
        
        # 更新累计统计
        self.total_turns += 1
        self.total_tensor_triggers += metrics.tensor_triggers
        self.total_ai_fallbacks += metrics.ai_fallback_count
        self.total_time_ms += metrics.total_time_ms()
        
        # 保存到历史
        self.history.append(metrics)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        
        # 记录日志
        metrics.log_summary(turn)
        
        # 重置当前
        self.reset_current()
        
        return metrics
    
    class _Timer:
        """内部计时器上下文管理器"""
        
        def __init__(self, callback):
            self.callback = callback
            self.start_time = 0.0
        
        def __enter__(self):
            self.start_time = time.perf_counter()
            return self
        
        def __exit__(self, *args):
            elapsed_ms = (time.perf_counter() - self.start_time) * 1000
            self.callback(elapsed_ms)
    
    def track_mortality(self) -> _Timer:
        """追踪死亡率计算耗时"""
        def callback(ms):
            self.current.mortality_time_ms += ms
        return self._Timer(callback)
    
    def track_speciation_detection(self) -> _Timer:
        """追踪分化检测耗时"""
        def callback(ms):
            self.current.speciation_detection_time_ms += ms
        return self._Timer(callback)
    
    def track_tradeoff(self) -> _Timer:
        """追踪代价计算耗时"""
        def callback(ms):
            self.current.tradeoff_time_ms += ms
        return self._Timer(callback)
    
    def record_tensor_trigger(self, count: int = 1) -> None:
        """记录张量触发的分化"""
        self.current.tensor_triggers += count
    
    def record_ai_fallback(self, count: int = 1) -> None:
        """记录 AI 回退"""
        self.current.ai_fallback_count += count
    
    def record_isolation_detection(self, count: int = 1) -> None:
        """记录地理隔离检测"""
        self.current.isolation_detections += count
    
    def record_divergence_detection(self, count: int = 1) -> None:
        """记录环境分歧检测"""
        self.current.divergence_detections += count
    
    def get_statistics(self) -> Dict[str, float | int]:
        """获取累计统计
        
        Returns:
            包含平均值和累计值的统计字典
        """
        if self.total_turns == 0:
            return {
                "total_turns": 0,
                "avg_time_ms": 0.0,
                "avg_tensor_triggers": 0.0,
                "total_tensor_triggers": 0,
                "total_ai_fallbacks": 0,
                "tensor_vs_ai_ratio": 0.0,
            }
        
        total_triggers = self.total_tensor_triggers + self.total_ai_fallbacks
        tensor_ratio = (
            self.total_tensor_triggers / total_triggers if total_triggers > 0 else 0.0
        )
        
        return {
            "total_turns": self.total_turns,
            "avg_time_ms": round(self.total_time_ms / self.total_turns, 2),
            "avg_tensor_triggers": round(self.total_tensor_triggers / self.total_turns, 2),
            "total_tensor_triggers": self.total_tensor_triggers,
            "total_ai_fallbacks": self.total_ai_fallbacks,
            "tensor_vs_ai_ratio": round(tensor_ratio, 3),
        }
    
    def get_recent_average(self, n: int = 10) -> Dict[str, float]:
        """获取最近 N 回合的平均指标
        
        Args:
            n: 回合数
        
        Returns:
            平均指标字典
        """
        if not self.history:
            return {
                "avg_mortality_ms": 0.0,
                "avg_speciation_detection_ms": 0.0,
                "avg_tradeoff_ms": 0.0,
                "avg_total_ms": 0.0,
            }
        
        recent = self.history[-n:]
        count = len(recent)
        
        return {
            "avg_mortality_ms": round(
                sum(m.mortality_time_ms for m in recent) / count, 2
            ),
            "avg_speciation_detection_ms": round(
                sum(m.speciation_detection_time_ms for m in recent) / count, 2
            ),
            "avg_tradeoff_ms": round(
                sum(m.tradeoff_time_ms for m in recent) / count, 2
            ),
            "avg_total_ms": round(
                sum(m.total_time_ms() for m in recent) / count, 2
            ),
        }


# 全局收集器实例（可选使用）
_global_collector: TensorMetricsCollector | None = None


def get_global_collector() -> TensorMetricsCollector:
    """获取全局指标收集器"""
    global _global_collector
    if _global_collector is None:
        _global_collector = TensorMetricsCollector()
    return _global_collector


def reset_global_collector() -> None:
    """重置全局指标收集器"""
    global _global_collector
    _global_collector = TensorMetricsCollector()









