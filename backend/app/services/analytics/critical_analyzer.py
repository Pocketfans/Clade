from __future__ import annotations

import asyncio
import logging

from ...ai.model_router import ModelRouter
from ...simulation.species import MortalityResult

logger = logging.getLogger(__name__)


class CriticalAnalyzer:
    """针对玩家关注的物种（Critical 层）逐个调用 AI 模型补充细化叙事。
    
    这是最高级别的 AI 处理，为每个 critical 物种提供详细的个性化分析。
    通常 critical 层最多包含3个玩家主动标记的物种。
    
    【优化】使用顺序执行队列，避免并发请求过多导致API卡死。
    """

    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    async def enhance_async(self, results: list[MortalityResult]) -> None:
        """为 critical 层物种的死亡率结果添加 AI 生成的详细叙事（顺序执行队列）。"""
        if not results:
            return
        
        logger.info(f"[Critical增润] 开始处理 {len(results)} 个物种（顺序队列）")
        
        # 【修改】顺序执行，逐个处理，避免并发
        for idx, item in enumerate(results):
            logger.info(f"[Critical增润] 处理 {idx + 1}/{len(results)}: {item.species.common_name}")
            
            payload = {
                "lineage_code": item.species.lineage_code,
                "population": item.survivors,
                "deaths": item.deaths,
                "traits": item.species.description,
                "niche": {
                    "overlap": item.niche_overlap,
                    "saturation": item.resource_pressure,
                },
            }
            
            try:
                response = await self.router.ainvoke("critical_detail", payload)
                
                # 从响应中提取 content
                content = response.get("content") if isinstance(response, dict) else None
                if isinstance(content, dict):
                    summary = content.get("summary") or content.get("text") or "重要物种细化完成"
                elif isinstance(content, str):
                    summary = content
                else:
                    summary = "重要物种细化完成"
                item.notes.append(str(summary))
                
            except Exception as e:
                logger.warning(f"[Critical增润] {item.species.common_name} 处理失败: {e}")
                item.notes.append("重要物种细化完成")
                continue
            
            # 持久化高光时刻到物种历史
            if summary and len(str(summary)) > 10:
                timestamp = f"Turn {item.species.morphology_stats.get('extinction_turn', 'Current')}"
                highlight = f"[{timestamp}] {summary}"
                if not item.species.history_highlights:
                    item.species.history_highlights = []
                item.species.history_highlights.append(highlight)
                # 保持历史记录不超过5条，避免Prompt过长
                if len(item.species.history_highlights) > 5:
                    item.species.history_highlights = item.species.history_highlights[-5:]
                
                # 注意：这里不直接调用upsert，因为SimulationEngine后续会统一处理，或者依赖ORM对象的引用更新
                # 但为了保险，SimulationEngine最好在CriticalAnalyzer之后有一次save操作

    
    def enhance(self, results: list[MortalityResult]) -> None:
        """同步方法已废弃，请使用 enhance_async"""
        raise NotImplementedError("Use enhance_async instead")
