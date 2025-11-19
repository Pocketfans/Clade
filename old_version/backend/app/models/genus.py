"""属模型：管理同属物种的遗传关系"""
from __future__ import annotations

from sqlmodel import Column, Field, JSON, SQLModel


class Genus(SQLModel, table=True):
    """属：记录同属物种间的遗传距离矩阵和共享基因库"""
    __tablename__ = "genus"
    
    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(unique=True, index=True)
    name_latin: str
    name_common: str
    
    genetic_distances: dict[str, float] = Field(default={}, sa_column=Column(JSON))
    
    gene_library: dict = Field(default={}, sa_column=Column(JSON))
    
    created_turn: int = 0
    updated_turn: int = 0

