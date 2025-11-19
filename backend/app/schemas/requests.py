from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, Field


PressureType = Literal[
    "temperature",
    "humidity",
    "drought",
    "flood",
    "wind",
    "volcano",
    "terrain",
    "predator",
    "competitor",
    "resource_bonus",
]


class PressureConfig(BaseModel):
    kind: PressureType
    intensity: int = Field(ge=1, le=10)
    target_region: tuple[int, int] | None = None  # (x, y) grid coordinate for local events
    radius: int | None = Field(default=None, ge=1)
    narrative_note: str | None = None


class TurnCommand(BaseModel):
    rounds: int = Field(gt=0, le=100)
    pressures: Sequence[PressureConfig] = Field(default_factory=list)
    auto_reports: bool = True


class SpeciesEditRequest(BaseModel):
    lineage_code: str
    description: str | None = None
    trait_overrides: dict[str, float] | None = None
    abstract_overrides: dict[str, float] | None = None  # 修复：与Species模型一致，使用float
    open_new_lineage: bool = False


class WatchlistRequest(BaseModel):
    lineage_codes: list[str]


class QueueRequest(BaseModel):
    pressures: list[PressureConfig] = Field(default_factory=list)
    rounds: int = Field(ge=1, le=20, default=1)


class CreateSaveRequest(BaseModel):
    save_name: str = Field(min_length=1, max_length=50)
    scenario: str = Field(default="原初大陆")
    species_prompts: list[str] | None = None  # 用于空白剧本的物种描述
    map_seed: int | None = None  # 可选的地图种子


class SaveGameRequest(BaseModel):
    save_name: str


class LoadGameRequest(BaseModel):
    save_name: str


class GenerateSpeciesRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    lineage_code: str = Field(default="A1")


class NicheCompareRequest(BaseModel):
    species_a: str = Field(description="第一个物种的lineage_code")
    species_b: str = Field(description="第二个物种的lineage_code")
