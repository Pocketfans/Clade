from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable, Sequence

from ...ai.model_router import ModelRouter
from ...simulation.species import MortalityResult


def chunk_iter(items: Sequence[MortalityResult], size: int) -> Iterable[Sequence[MortalityResult]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


class FocusBatchProcessor:
    """批量调用模型，为重点物种补充叙事与差异。"""

    def __init__(self, router: ModelRouter, batch_size: int) -> None:
        self.router = router
        self.batch_size = max(1, batch_size)

    async def enhance_async(self, results: list[MortalityResult]) -> None:
        """异步批量增强"""
        chunks = list(chunk_iter(results, self.batch_size))
        tasks = []
        
        for chunk in chunks:
            payload = [
                {
                    "lineage_code": item.species.lineage_code,
                    "population": item.survivors,
                    "deaths": item.deaths,
                    "pressure_notes": item.notes,
                }
                for item in chunk
            ]
            tasks.append(self.router.ainvoke("focus_batch", {"batch": payload}))
            
        if not tasks:
            return

        ai_responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for chunk, response in zip(chunks, ai_responses):
            if isinstance(response, Exception):
                # Handle exception or log error
                continue
            
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

    def enhance(self, results: list[MortalityResult]) -> None:
        # Deprecated sync wrapper
        raise NotImplementedError("Use enhance_async instead")
