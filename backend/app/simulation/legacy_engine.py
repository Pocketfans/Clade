"""
Legacy Turn Runner - 遗留回合运行器

用于回归测试的旧版回合逻辑。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import SimulationEngine
    from ..schemas.requests import TurnCommand
    from ..schemas.responses import TurnReport

logger = logging.getLogger(__name__)


class LegacyTurnRunner:
    """遗留回合运行器
    
    保留旧版的回合逻辑，用于回归测试。
    正常使用请使用 Pipeline 架构。
    """
    
    def __init__(self, engine: "SimulationEngine"):
        self.engine = engine
    
    async def run_turn(self, command: "TurnCommand") -> "TurnReport | None":
        """运行单个回合（遗留逻辑）
        
        Args:
            command: 回合命令
            
        Returns:
            回合报告
        """
        logger.warning(
            "[LegacyTurnRunner] 使用遗留回合逻辑，建议使用 Pipeline 架构"
        )
        
        # 遗留逻辑占位
        # 实际实现应该调用旧版的回合处理流程
        
        from ..schemas.responses import TurnReport
        
        return TurnReport(
            turn_index=self.engine.turn_counter,
            narrative="遗留模式运行",
            pressures_summary="",
            species=[],
            branching_events=[],
            major_events=[],
        )


