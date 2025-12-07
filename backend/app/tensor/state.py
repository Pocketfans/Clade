from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import numpy as np


@dataclass
class TensorState:
    """统一的张量状态容器。

    env: 环境张量 (C, H, W)
    pop: 种群张量 (S, H, W)
    species_params: 物种参数矩阵 (S, F)
    masks: 辅助掩码 (H, W) 集合
    species_map: 谱系编码到张量索引的映射
    """

    env: np.ndarray
    pop: np.ndarray
    species_params: np.ndarray
    masks: Dict[str, np.ndarray] = field(default_factory=dict)
    species_map: Dict[str, int] = field(default_factory=dict)

    def population_slice(self, lineage_code: str) -> np.ndarray | None:
        """根据谱系编码获取对应的种群切片。"""
        idx = self.species_map.get(lineage_code)
        if idx is None:
            return None
        return self.pop[idx]

    def ensure_shapes(self) -> None:
        """简单的形状检查，便于调试早期影子运行。"""
        if self.env.ndim != 3:
            raise ValueError("env tensor must be 3D (C, H, W)")
        if self.pop.ndim != 3:
            raise ValueError("pop tensor must be 3D (S, H, W)")
        if self.species_params.ndim != 2:
            raise ValueError("species_params must be 2D (S, F)")








