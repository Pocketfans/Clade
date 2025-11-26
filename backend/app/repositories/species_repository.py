from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import select
from sqlalchemy import text


from ..core.database import session_scope
from ..models.species import LineageEvent, PopulationSnapshot, Species


class SpeciesRepository:
    """Data access helpers for species and populations."""

    def list_species(self) -> list[Species]:
        with session_scope() as session:
            return list(session.exec(select(Species)))

    def get_by_lineage(self, lineage_code: str) -> Species | None:
        with session_scope() as session:
            return session.exec(
                select(Species).where(Species.lineage_code == lineage_code)
            ).first()

    def upsert(self, species: Species) -> Species:
        with session_scope() as session:
            merged = session.merge(species)
            session.flush()
            session.refresh(merged)
            return merged

    def add_population_snapshots(
        self, snapshots: Iterable[PopulationSnapshot]
    ) -> None:
        with session_scope() as session:
            for snap in snapshots:
                session.add(snap)

    def log_event(self, event: LineageEvent) -> None:
        with session_scope() as session:
            session.add(event)

    def clear_state(self) -> None:
        """清除所有物种相关数据（用于读档/重置）"""
        with session_scope() as session:
            session.exec(text("DELETE FROM population_snapshots"))
            session.exec(text("DELETE FROM lineage_events"))
            session.exec(text("DELETE FROM species"))



species_repository = SpeciesRepository()
