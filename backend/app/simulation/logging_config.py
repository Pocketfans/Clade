"""
Logging Configuration - 日志配置与标签化系统

提供 Stage 级别的结构化日志，支持：
- 按 Stage 名称过滤
- 按类别（环境/地质/物种/迁徙/AI/性能）过滤
- debug 模式下的阶段汇总日志
- 统一的日志格式
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, List, Dict, Set, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# 日志类别
# ============================================================================

class LogCategory(Enum):
    """日志类别枚举"""
    SYSTEM = "系统"
    ENVIRONMENT = "环境"
    GEOLOGY = "地质"
    SPECIES = "物种"
    MIGRATION = "迁徙"
    MORTALITY = "死亡"
    REPRODUCTION = "繁殖"
    SPECIATION = "分化"
    AI = "AI"
    PERFORMANCE = "性能"
    PIPELINE = "流水线"
    SNAPSHOT = "快照"
    OTHER = "其他"
    
    @classmethod
    def from_string(cls, s: str) -> "LogCategory":
        """从字符串解析类别"""
        for cat in cls:
            if cat.value == s or cat.name.lower() == s.lower():
                return cat
        return cls.OTHER


# Stage 到默认类别的映射
STAGE_CATEGORY_MAP = {
    "回合初始化": LogCategory.SYSTEM,
    "解析环境压力": LogCategory.ENVIRONMENT,
    "地图演化": LogCategory.GEOLOGY,
    "板块构造运动": LogCategory.GEOLOGY,
    "获取物种列表": LogCategory.SPECIES,
    "食物网维护": LogCategory.SPECIES,
    "物种分层与生态位": LogCategory.SPECIES,
    "初步死亡率": LogCategory.MORTALITY,
    "猎物分布更新": LogCategory.MIGRATION,
    "迁徙规划与执行": LogCategory.MIGRATION,
    "被动扩散": LogCategory.MIGRATION,
    "饥饿迁徙": LogCategory.MIGRATION,
    "后迁徙生态位": LogCategory.SPECIES,
    "最终死亡率": LogCategory.MORTALITY,
    "AI状态评估": LogCategory.AI,
    "种群更新": LogCategory.REPRODUCTION,
    "基因激活": LogCategory.SPECIATION,
    "基因流动": LogCategory.SPECIATION,
    "遗传漂变": LogCategory.SPECIATION,
    "自动杂交": LogCategory.SPECIATION,
    "亚种晋升": LogCategory.SPECIATION,
    "AI并行任务": LogCategory.AI,
    "背景物种管理": LogCategory.SPECIES,
    "构建报告": LogCategory.SYSTEM,
    "保存地图快照": LogCategory.SNAPSHOT,
    "植被覆盖更新": LogCategory.ENVIRONMENT,
    "保存种群快照": LogCategory.SNAPSHOT,
    "Embedding钩子": LogCategory.AI,
    "保存历史记录": LogCategory.SYSTEM,
    "导出数据": LogCategory.SYSTEM,
    "最终化": LogCategory.SYSTEM,
}


# ============================================================================
# 结构化日志记录
# ============================================================================

@dataclass
class StageLogEntry:
    """阶段日志条目"""
    timestamp: str
    stage_name: str
    category: LogCategory
    level: str
    message: str
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "stage": self.stage_name,
            "category": self.category.value,
            "level": self.level,
            "message": self.message,
            **self.extra,
        }
    
    def format(self, include_timestamp: bool = True) -> str:
        """格式化为可读字符串"""
        parts = []
        if include_timestamp:
            parts.append(f"[{self.timestamp}]")
        parts.append(f"[{self.category.value}]")
        parts.append(f"[{self.stage_name}]")
        parts.append(self.message)
        return " ".join(parts)


@dataclass
class StageSummary:
    """阶段执行汇总"""
    stage_name: str
    category: LogCategory
    duration_ms: float
    success: bool
    error_message: str = ""
    # 关键指标
    species_affected: int = 0
    migrations: int = 0
    extinctions: int = 0
    speciations: int = 0
    ai_calls: int = 0
    custom_stats: Dict[str, Any] = field(default_factory=dict)
    
    def format(self) -> str:
        """格式化为汇总文本"""
        status = "✅" if self.success else "❌"
        lines = [
            f"{status} [{self.category.value}] {self.stage_name}: {self.duration_ms:.1f}ms"
        ]
        
        stats = []
        if self.species_affected > 0:
            stats.append(f"物种: {self.species_affected}")
        if self.migrations > 0:
            stats.append(f"迁徙: {self.migrations}")
        if self.extinctions > 0:
            stats.append(f"灭绝: {self.extinctions}")
        if self.speciations > 0:
            stats.append(f"分化: {self.speciations}")
        if self.ai_calls > 0:
            stats.append(f"AI调用: {self.ai_calls}")
        
        for key, value in self.custom_stats.items():
            stats.append(f"{key}: {value}")
        
        if stats:
            lines.append(f"    {', '.join(stats)}")
        
        if not self.success and self.error_message:
            lines.append(f"    错误: {self.error_message}")
        
        return "\n".join(lines)


# ============================================================================
# 日志过滤器
# ============================================================================

@dataclass
class LogFilter:
    """日志过滤器配置"""
    # 允许的阶段名称（空=全部）
    allowed_stages: Set[str] = field(default_factory=set)
    # 排除的阶段名称
    excluded_stages: Set[str] = field(default_factory=set)
    # 允许的类别（空=全部）
    allowed_categories: Set[LogCategory] = field(default_factory=set)
    # 排除的类别
    excluded_categories: Set[LogCategory] = field(default_factory=set)
    # 最低日志级别
    min_level: str = "DEBUG"
    
    def should_log(
        self,
        stage_name: str,
        category: LogCategory,
        level: str,
    ) -> bool:
        """判断是否应该记录此日志"""
        # 级别检查
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
        if level_order.get(level.upper(), 0) < level_order.get(self.min_level.upper(), 0):
            return False
        
        # 阶段检查
        if self.excluded_stages and stage_name in self.excluded_stages:
            return False
        if self.allowed_stages and stage_name not in self.allowed_stages:
            return False
        
        # 类别检查
        if self.excluded_categories and category in self.excluded_categories:
            return False
        if self.allowed_categories and category not in self.allowed_categories:
            return False
        
        return True


# ============================================================================
# Stage Logger
# ============================================================================

class StageLogger:
    """Stage 专用日志记录器
    
    提供结构化、可过滤的日志功能。
    """
    
    def __init__(
        self,
        stage_name: str,
        category: LogCategory | None = None,
        log_filter: LogFilter | None = None,
    ):
        """初始化 Stage Logger
        
        Args:
            stage_name: 阶段名称
            category: 日志类别（如果不指定则从映射表查找）
            log_filter: 日志过滤器
        """
        self.stage_name = stage_name
        self.category = category or STAGE_CATEGORY_MAP.get(stage_name, LogCategory.OTHER)
        self.log_filter = log_filter or LogFilter()
        self._entries: List[StageLogEntry] = []
        self._underlying_logger = logging.getLogger(f"simulation.stages.{stage_name}")
    
    def _create_entry(self, level: str, message: str, **extra) -> StageLogEntry:
        """创建日志条目"""
        return StageLogEntry(
            timestamp=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            stage_name=self.stage_name,
            category=self.category,
            level=level,
            message=message,
            extra=extra,
        )
    
    def _log(self, level: str, message: str, **extra) -> None:
        """内部日志方法"""
        if not self.log_filter.should_log(self.stage_name, self.category, level):
            return
        
        entry = self._create_entry(level, message, **extra)
        self._entries.append(entry)
        
        # 同时输出到底层 logger
        formatted = entry.format(include_timestamp=False)
        log_method = getattr(self._underlying_logger, level.lower(), self._underlying_logger.info)
        log_method(formatted)
    
    def debug(self, message: str, **extra) -> None:
        """记录 DEBUG 日志"""
        self._log("DEBUG", message, **extra)
    
    def info(self, message: str, **extra) -> None:
        """记录 INFO 日志"""
        self._log("INFO", message, **extra)
    
    def warning(self, message: str, **extra) -> None:
        """记录 WARNING 日志"""
        self._log("WARNING", message, **extra)
    
    def error(self, message: str, **extra) -> None:
        """记录 ERROR 日志"""
        self._log("ERROR", message, **extra)
    
    def get_entries(self) -> List[StageLogEntry]:
        """获取所有日志条目"""
        return self._entries.copy()
    
    def clear(self) -> None:
        """清除日志条目"""
        self._entries.clear()


# ============================================================================
# 全局日志管理器
# ============================================================================

class SimulationLogManager:
    """模拟日志管理器
    
    管理所有 Stage 的日志，提供全局过滤和汇总功能。
    """
    
    def __init__(self, log_filter: LogFilter | None = None):
        self.log_filter = log_filter or LogFilter()
        self._stage_loggers: Dict[str, StageLogger] = {}
        self._summaries: List[StageSummary] = []
        self._debug_mode = False
    
    def set_debug_mode(self, enabled: bool) -> None:
        """设置调试模式"""
        self._debug_mode = enabled
        if enabled:
            self.log_filter.min_level = "DEBUG"
    
    def get_logger(self, stage_name: str, category: LogCategory | None = None) -> StageLogger:
        """获取或创建 Stage Logger"""
        if stage_name not in self._stage_loggers:
            self._stage_loggers[stage_name] = StageLogger(
                stage_name,
                category,
                self.log_filter,
            )
        return self._stage_loggers[stage_name]
    
    def add_summary(self, summary: StageSummary) -> None:
        """添加阶段汇总"""
        self._summaries.append(summary)
        
        if self._debug_mode:
            logger.info(summary.format())
    
    def get_all_entries(self) -> List[StageLogEntry]:
        """获取所有日志条目"""
        entries = []
        for stage_logger in self._stage_loggers.values():
            entries.extend(stage_logger.get_entries())
        return sorted(entries, key=lambda e: e.timestamp)
    
    def get_summaries(self) -> List[StageSummary]:
        """获取所有阶段汇总"""
        return self._summaries.copy()
    
    def format_summaries_table(self) -> str:
        """格式化汇总表格"""
        if not self._summaries:
            return "No summaries available"
        
        lines = [
            "┌" + "─" * 30 + "┬" + "─" * 10 + "┬" + "─" * 10 + "┬" + "─" * 6 + "┐",
            "│ {:^28} │ {:^8} │ {:^8} │ {:^4} │".format("Stage", "Category", "Time(ms)", "OK"),
            "├" + "─" * 30 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┼" + "─" * 6 + "┤",
        ]
        
        total_time = 0.0
        for s in self._summaries:
            status = "✅" if s.success else "❌"
            name = s.stage_name[:28]
            cat = s.category.value[:8]
            lines.append(
                "│ {:28} │ {:8} │ {:>8.1f} │ {:^4} │".format(
                    name, cat, s.duration_ms, status
                )
            )
            total_time += s.duration_ms
        
        lines.append("├" + "─" * 30 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┼" + "─" * 6 + "┤")
        lines.append("│ {:28} │ {:8} │ {:>8.1f} │      │".format("TOTAL", "", total_time))
        lines.append("└" + "─" * 30 + "┴" + "─" * 10 + "┴" + "─" * 10 + "┴" + "─" * 6 + "┘")
        
        return "\n".join(lines)
    
    def format_category_breakdown(self) -> str:
        """按类别分解统计"""
        category_stats: Dict[LogCategory, dict] = {}
        
        for s in self._summaries:
            if s.category not in category_stats:
                category_stats[s.category] = {
                    "count": 0,
                    "total_time": 0.0,
                    "errors": 0,
                }
            category_stats[s.category]["count"] += 1
            category_stats[s.category]["total_time"] += s.duration_ms
            if not s.success:
                category_stats[s.category]["errors"] += 1
        
        lines = ["类别统计:", "=" * 40]
        for cat, stats in sorted(category_stats.items(), key=lambda x: x[1]["total_time"], reverse=True):
            error_str = f" ({stats['errors']} 错误)" if stats["errors"] > 0 else ""
            lines.append(
                f"  {cat.value}: {stats['count']} 阶段, {stats['total_time']:.1f}ms{error_str}"
            )
        
        return "\n".join(lines)
    
    def clear(self) -> None:
        """清除所有日志数据"""
        for stage_logger in self._stage_loggers.values():
            stage_logger.clear()
        self._summaries.clear()


# ============================================================================
# 便捷函数
# ============================================================================

# 全局日志管理器实例
_global_log_manager: SimulationLogManager | None = None


def get_log_manager() -> SimulationLogManager:
    """获取全局日志管理器"""
    global _global_log_manager
    if _global_log_manager is None:
        _global_log_manager = SimulationLogManager()
    return _global_log_manager


def get_stage_logger(stage_name: str, category: LogCategory | None = None) -> StageLogger:
    """获取 Stage Logger 的便捷函数"""
    return get_log_manager().get_logger(stage_name, category)


def configure_log_filter(
    allowed_stages: Set[str] | None = None,
    excluded_stages: Set[str] | None = None,
    allowed_categories: Set[LogCategory] | None = None,
    excluded_categories: Set[LogCategory] | None = None,
    min_level: str = "DEBUG",
) -> None:
    """配置日志过滤器"""
    manager = get_log_manager()
    manager.log_filter = LogFilter(
        allowed_stages=allowed_stages or set(),
        excluded_stages=excluded_stages or set(),
        allowed_categories=allowed_categories or set(),
        excluded_categories=excluded_categories or set(),
        min_level=min_level,
    )


def enable_debug_logging() -> None:
    """启用调试日志"""
    get_log_manager().set_debug_mode(True)


def disable_debug_logging() -> None:
    """禁用调试日志"""
    get_log_manager().set_debug_mode(False)



