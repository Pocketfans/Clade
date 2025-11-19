from __future__ import annotations

from pydantic import BaseModel


class TerrainChange(BaseModel):
    """单个地形变化"""
    tile_ids: list[int]
    change_type: str  # elevation, biome, climate
    elevation_delta: float | None = None
    new_biome: str | None = None
    temperature_delta: float | None = None
    humidity_delta: float | None = None
    rationale: str


class ProcessContinuation(BaseModel):
    """持续过程的继续决策"""
    region: str
    process_id: int
    continue_process: bool
    reason: str


class NewTerrainChange(BaseModel):
    """新的地形演化"""
    region_name: str
    evolution_type: str  # uplift, subsidence, erosion, glaciation, volcanic, desertification
    intensity: str  # conservative, moderate, dramatic
    start_new_process: bool
    expected_duration: int
    rationale: str


class TerrainEvolutionResult(BaseModel):
    """AI返回的地形演化结果"""
    analysis: str
    continue_processes: list[ProcessContinuation] = []
    new_changes: list[NewTerrainChange] = []


class CandidateRegion(BaseModel):
    """候选变化区域"""
    name: str
    tile_count: int
    avg_elevation: float
    dominant_biome: str
    pressure_types: list[str]
    reason: str
    tile_ids: list[int]
    ongoing_process_id: int | None = None

