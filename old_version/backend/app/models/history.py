from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Column, Field, JSON, SQLModel


class TurnLog(SQLModel, table=True):
    __tablename__ = "turn_logs"

    id: int | None = Field(default=None, primary_key=True)
    turn_index: int = Field(index=True)
    pressures_summary: str
    narrative: str
    record_data: dict[str, Any] = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
