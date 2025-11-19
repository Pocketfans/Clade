from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Column, Field, JSON, Relationship, SQLModel


class Species(SQLModel, table=True):
    __tablename__ = "species"

    id: int | None = Field(default=None, primary_key=True)
    lineage_code: str = Field(index=True)
    latin_name: str
    common_name: str
    description: str
    morphology_stats: dict[str, float] = Field(sa_column=Column(JSON))
    abstract_traits: dict[str, float] = Field(sa_column=Column(JSON)) 
    hidden_traits: dict[str, float] = Field(sa_column=Column(JSON))
    ecological_vector: list[float] = Field(sa_column=Column(JSON))
    parent_code: str | None = Field(default=None, index=True)
    status: str = Field(default="alive", index=True)
    created_turn: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_background: bool = Field(default=False, index=True)
    trophic_level: float = Field(default=1.0, index=True)
    
    # 结构化器官系统
    organs: dict[str, dict] = Field(default={}, sa_column=Column(JSON))
    # 格式: {"organ_category": {"type": "...", "parameters": {...}, "acquired_turn": int, "is_active": bool}}
    # 示例: {"locomotion": {"type": "flagella", "count": 4, "efficiency": 1.6, "acquired_turn": 5, "is_active": True}}
    
    capabilities: list[str] = Field(default=[], sa_column=Column(JSON))
    # 示例: ["photosynthesis", "flagellar_motion", "light_detection"]
    
    genus_code: str = ""
    taxonomic_rank: str = "species"
    hybrid_parent_codes: list[str] = Field(default=[], sa_column=Column(JSON))
    hybrid_fertility: float = 1.0
    
    dormant_genes: dict = Field(default={}, sa_column=Column(JSON))
    stress_exposure: dict = Field(default={}, sa_column=Column(JSON))

class PopulationSnapshot(SQLModel, table=True):
    __tablename__ = "population_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    species_id: int = Field(foreign_key="species.id")
    turn_index: int = Field(index=True)
    region_id: int = Field(default=0, index=True)
    count: int
    death_count: int
    survivor_count: int
    population_share: float
    ecological_pressure: dict[str, Any] = Field(sa_column=Column(JSON))

class LineageEvent(SQLModel, table=True):
    __tablename__ = "lineage_events"

    id: int | None = Field(default=None, primary_key=True)
    lineage_code: str = Field(index=True)
    event_type: str
    payload: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
