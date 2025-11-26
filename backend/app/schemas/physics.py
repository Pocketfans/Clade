from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PhysicsConfig(BaseModel):
    """GPU 物理引擎的配置参数。"""

    mode: Literal["uplift", "erosion", "volcanic", "neutral"] = "neutral"
    region_mask: list[int] = Field(default_factory=list)
    region_coords: list[tuple[int, int]] = Field(default_factory=list)
    uplift_factor: float = 1.0
    erosion_rate: float = 1.0
    volcanic_intensity: float = 0.0
    global_temp_change: float = 0.0
    active_species: list[int] = Field(default_factory=list)
    steps: int = 10

