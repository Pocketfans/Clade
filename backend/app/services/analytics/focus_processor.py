from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from ...ai.model_router import ModelRouter, staggered_gather
from ...simulation.species import MortalityResult

logger = logging.getLogger(__name__)


def chunk_iter(items: Sequence[MortalityResult], size: int) -> Iterable[Sequence[MortalityResult]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


class FocusBatchProcessor:
    """批量调用模型，为重点物种补充叙事与差异。
    
    【优化】使用间隔并行执行，兼顾效率和稳定性。
    """

    def __init__(self, router: ModelRouter, batch_size: int) -> None:
        self.router = router
        self.batch_size = max(1, batch_size)

    async def _process_chunk(self, chunk: Sequence[MortalityResult]) -> list:
        """处理单个批次"""
        payload = [
            {
                "lineage_code": item.species.lineage_code,
                "population": item.survivors,
                "deaths": item.deaths,
                "pressure_notes": item.notes,
            }
            for item in chunk
        ]
        
        response = await self.router.ainvoke("focus_batch", {"batch": payload})
        
        content = response.get("content") if isinstance(response, dict) else None
        details = content.get("details") if isinstance(content, dict) else None
        
        return details if isinstance(details, list) else []

    async def enhance_async(self, results: list[MortalityResult]) -> None:
        """异步批量增强（间隔并行执行）"""
        if not results:
            return
        
        chunks = list(chunk_iter(results, self.batch_size))
        logger.info(f"[Focus增润] 开始处理 {len(results)} 个物种，分为 {len(chunks)} 个批次（间隔并行）")
        
        # 【优化】间隔并行执行，每2秒启动一个批次，最多同时3个
        coroutines = [self._process_chunk(chunk) for chunk in chunks]
        batch_results = await staggered_gather(
            coroutines, 
            interval=2.0,  # 每2秒启动一个
            max_concurrent=3,  # 最多同时3个
            task_name="Focus批次"
        )
        
        # 处理结果
        for batch_idx, (chunk, details) in enumerate(zip(chunks, batch_results)):
            if isinstance(details, Exception):
                logger.warning(f"[Focus增润] 批次 {batch_idx + 1} 处理失败: {details}")
                for item in chunk:
                    item.notes.append("重点批次分析完成")
                continue
            
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
        
        logger.info(f"[Focus增润] 全部批次处理完成")

    def enhance(self, results: list[MortalityResult]) -> None:
        # Deprecated sync wrapper
        raise NotImplementedError("Use enhance_async instead")
