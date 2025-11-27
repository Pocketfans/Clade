from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from ...ai.model_router import ModelRouter
from ...simulation.species import MortalityResult

logger = logging.getLogger(__name__)


def chunk_iter(items: Sequence[MortalityResult], size: int) -> Iterable[Sequence[MortalityResult]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


class FocusBatchProcessor:
    """批量调用模型，为重点物种补充叙事与差异。
    
    【优化】使用顺序执行队列，避免并发请求过多导致API卡死。
    """

    def __init__(self, router: ModelRouter, batch_size: int) -> None:
        self.router = router
        self.batch_size = max(1, batch_size)

    async def enhance_async(self, results: list[MortalityResult]) -> None:
        """异步批量增强（顺序执行队列）"""
        if not results:
            return
        
        chunks = list(chunk_iter(results, self.batch_size))
        logger.info(f"[Focus增润] 开始处理 {len(results)} 个物种，分为 {len(chunks)} 个批次（顺序队列）")
        
        # 【修改】顺序执行，逐批处理，避免并发
        for batch_idx, chunk in enumerate(chunks):
            logger.info(f"[Focus增润] 处理批次 {batch_idx + 1}/{len(chunks)}（{len(chunk)} 个物种）")
            
            payload = [
                {
                    "lineage_code": item.species.lineage_code,
                    "population": item.survivors,
                    "deaths": item.deaths,
                    "pressure_notes": item.notes,
                }
                for item in chunk
            ]
            
            try:
                response = await self.router.ainvoke("focus_batch", {"batch": payload})
                
                content = response.get("content") if isinstance(response, dict) else None
                details = content.get("details") if isinstance(content, dict) else None
                
                if not isinstance(details, list):
                    details = []
                    
                for item, detail in zip(chunk, details, strict=False):
                    summary = None
                    if isinstance(detail, dict):
                        summary = detail.get("summary") or detail.get("text")
                    elif isinstance(detail, str):
                        summary = detail
                    
                    if summary:
                        item.notes.append(str(summary))
                    else:
                        item.notes.append("重点批次分析完成")
                        
                # 为没有对应 detail 的物种添加默认说明
                if len(details) < len(chunk):
                    for item in chunk[len(details):]:
                        item.notes.append("重点批次分析完成")
                        
            except Exception as e:
                logger.warning(f"[Focus增润] 批次 {batch_idx + 1} 处理失败: {e}")
                # 为失败批次的所有物种添加默认说明
                for item in chunk:
                    item.notes.append("重点批次分析完成")
        
        logger.info(f"[Focus增润] 全部批次处理完成")

    def enhance(self, results: list[MortalityResult]) -> None:
        # Deprecated sync wrapper
        raise NotImplementedError("Use enhance_async instead")
