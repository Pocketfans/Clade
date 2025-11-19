from __future__ import annotations

from ..ai.model_router import ModelRouter
from ..simulation.species import MortalityResult


class CriticalAnalyzer:
    """针对玩家关注的物种（Critical 层）逐个调用 AI 模型补充细化叙事。
    
    这是最高级别的 AI 处理，为每个 critical 物种提供详细的个性化分析。
    通常 critical 层最多包含3个玩家主动标记的物种。
    """

    def __init__(self, router: ModelRouter) -> None:
        self.router = router

    def enhance(self, results: list[MortalityResult]) -> None:
        """为 critical 层物种的死亡率结果添加 AI 生成的详细叙事。"""
        for item in results:
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
            response = self.router.invoke("critical_detail", payload)
            # 从响应中提取 content
            content = response.get("content") if isinstance(response, dict) else None
            if isinstance(content, dict):
                summary = content.get("summary") or content.get("text") or "重要物种细化完成"
            elif isinstance(content, str):
                summary = content
            else:
                summary = "重要物种细化完成"
            item.notes.append(str(summary))
