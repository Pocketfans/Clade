from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from scipy.ndimage import label

from .state import TensorState


@dataclass
class SpeciationTrigger:
    """分化触发信号的数据结构。"""

    lineage_code: str
    type: str
    regions: List[np.ndarray] | None = None
    divergence_score: float | None = None
    num_regions: int | None = None


class SpeciationMonitor:
    """张量监控器 - 纯张量分化信号检测。"""

    def __init__(self, species_map: Dict[str, int]):
        self.species_map = species_map

    def detect_isolation(
        self,
        pop_tensor: np.ndarray,  # (S, H, W)
    ) -> Dict[str, List[np.ndarray]]:
        """检测地理隔离（异域分化）。"""
        isolation_regions: Dict[str, List[np.ndarray]] = {}
        for s_idx, lineage in enumerate(self.species_map.keys()):
            presence = pop_tensor[s_idx] > 0
            labeled, num_regions = label(presence)
            if num_regions >= 2:
                isolation_regions[lineage] = [labeled == r for r in range(1, num_regions + 1)]
        return isolation_regions

    def detect_divergence(
        self,
        pop_tensor: np.ndarray,
        env_tensor: np.ndarray,
    ) -> Dict[str, float]:
        """检测种群内部环境差异（生态分化）。"""
        divergence_scores: Dict[str, float] = {}
        for s_idx, lineage in enumerate(self.species_map.keys()):
            presence = pop_tensor[s_idx] > 0
            if not presence.any():
                continue
            env_in_range = env_tensor[:, presence]
            variance = np.var(env_in_range, axis=1).mean()
            divergence_scores[lineage] = min(1.0, float(variance) / 10.0)
        return divergence_scores

    def get_speciation_triggers(
        self,
        tensor_state: TensorState,
        threshold: float = 0.5,
    ) -> List[SpeciationTrigger]:
        """汇总所有分化触发信号。"""
        triggers: List[SpeciationTrigger] = []

        isolation = self.detect_isolation(tensor_state.pop)
        for lineage, regions in isolation.items():
            triggers.append(
                SpeciationTrigger(
                    lineage_code=lineage,
                    type="geographic_isolation",
                    regions=regions,
                    num_regions=len(regions),
                )
            )

        divergence = self.detect_divergence(tensor_state.pop, tensor_state.env)
        for lineage, score in divergence.items():
            if score >= threshold:
                triggers.append(
                    SpeciationTrigger(
                        lineage_code=lineage,
                        type="ecological_divergence",
                        divergence_score=score,
                    )
                )

        return triggers








