from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

from ...models.species import Species
from ...schemas.responses import BackgroundSummary, ReemergenceEvent
from ...simulation.species import MortalityResult

if TYPE_CHECKING:
    from .reemergence import ReemergenceService


@dataclass(slots=True)
class BackgroundConfig:
    population_threshold: int
    mass_extinction_threshold: float
    promotion_quota: int


class BackgroundSpeciesManager:
    """管理规则引擎托管的小型背景物种。"""

    def __init__(
        self,
        config: BackgroundConfig,
        reemergence_service: "ReemergenceService",
    ) -> None:
        self.config = config
        self._reemergence_service = reemergence_service

    def summarize(self, results: Sequence[MortalityResult]) -> list[BackgroundSummary]:
        buckets: dict[str, dict] = {}
        for result in results:
            role = self._infer_role(result.species)
            data = buckets.setdefault(
                role,
                {
                    "species": [],
                    "population": 0,
                    "survivors": 0,
                },
            )
            data["species"].append(result.species.lineage_code)
            data["population"] += result.initial_population
            data["survivors"] += result.survivors
        summaries: list[BackgroundSummary] = []
        for role, data in buckets.items():
            summaries.append(
                BackgroundSummary(
                    role=role,
                    species_codes=data["species"],
                    total_population=data["population"],
                    survivor_population=data["survivors"],
                )
            )
        return summaries

    def detect_mass_extinction(self, results: Sequence[MortalityResult]) -> bool:
        initial = sum(r.initial_population for r in results)
        deaths = sum(r.deaths for r in results)
        if initial == 0:
            return False
        return (deaths / initial) >= self.config.mass_extinction_threshold

    def promote_candidates(self, results: Sequence[MortalityResult]) -> list[Species]:
        if not results or self.config.promotion_quota <= 0:
            return []
        ranked = sorted(
            results,
            key=lambda r: (
                r.species.hidden_traits.get("evolution_potential", 0.0),
                r.survivors,
            ),
            reverse=True,
        )
        selected = ranked[: self.config.promotion_quota]
        promoted: list[Species] = []
        for result in selected:
            species = result.species
            promoted.append(species)
        return promoted

    def evaluate_reemergence(
        self,
        candidates: list[Species],
        modifiers: dict[str, float] | None = None,
    ) -> list[Any]:
        return self._reemergence_service.evaluate_reemergence(candidates, modifiers)

    def _infer_role(self, species: Species) -> str:
        description = species.description
        if any(keyword in description for keyword in ("藻", "菌", "光合", "植物")):
            return "初级生产者"
        if any(keyword in description for keyword in ("滤食", "草食", "浮游")):
            return "初级消费者"
        if any(keyword in description for keyword in ("捕食", "掠食", "肉食")):
            return "捕食者"
        return "生态配角"
