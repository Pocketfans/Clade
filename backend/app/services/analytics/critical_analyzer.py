from __future__ import annotations

import asyncio
import logging

from typing import Callable

from ...ai.model_router import ModelRouter, staggered_gather
from ...simulation.species import MortalityResult

logger = logging.getLogger(__name__)


class CriticalAnalyzer:
    """针对玩家关注的物种（Critical 层）逐个调用 AI 模型补充细化叙事。
    
    这是最高级别的 AI 处理，为每个 critical 物种提供详细的个性化分析。
    通常 critical 层最多包含3个玩家主动标记的物种。
    
    【优化】使用间隔并行执行，兼顾效率和稳定性。
    """

    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    async def _process_item(self, item: MortalityResult) -> dict:
        """处理单个物种（带超时保护）"""
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
        
        # 【优化】使用带心跳的调用
        from ...ai.streaming_helper import invoke_with_heartbeat
        
        try:
            response = await invoke_with_heartbeat(
                router=self.router,
                capability="critical_detail",
                payload=payload,
                task_name=f"Critical分析[{item.species.common_name[:8]}]",
                timeout=60,
                heartbeat_interval=2.0,
            )
            return response
        except asyncio.TimeoutError:
            logger.error(f"[Critical] {item.species.common_name} AI调用超时")
            return {"error": "timeout", "content": {"summary": "分析超时，请稍后重试"}}

    async def enhance_async(
        self, 
        results: list[MortalityResult],
        event_callback: Callable[[str, str, str], None] | None = None
    ) -> None:
        """为 critical 层物种的死亡率结果添加 AI 生成的详细叙事（间隔并行执行）。"""
        if not results:
            return
        
        logger.info(f"[Critical增润] 开始处理 {len(results)} 个物种（间隔并行）")
        
        # 【优化】间隔并行执行，每1秒启动一个，最多同时2个
        coroutines = [self._process_item(item) for item in results]
        responses = await staggered_gather(
            coroutines,
            interval=1.0,  # Critical 物种较少，间隔1秒即可
            max_concurrent=2,
            task_name="Critical分析",
            event_callback=event_callback  # 【新增】传递心跳回调
        )
        
        # 处理结果
        for idx, (item, response) in enumerate(zip(results, responses)):
            if isinstance(response, Exception):
                logger.warning(f"[Critical增润] {item.species.common_name} 处理失败: {response}")
                item.notes.append("重要物种细化完成")
                continue
            
            # 从响应中提取 content
            content = response.get("content") if isinstance(response, dict) else None
            if isinstance(content, dict):
                summary = content.get("summary") or content.get("text") or "重要物种细化完成"
            elif isinstance(content, str):
                summary = content
            else:
                summary = "重要物种细化完成"
            item.notes.append(str(summary))
            
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

    
    def enhance(self, results: list[MortalityResult]) -> None:
        """同步方法已废弃，请使用 enhance_async"""
        raise NotImplementedError("Use enhance_async instead")
