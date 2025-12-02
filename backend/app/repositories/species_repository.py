from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

from sqlmodel import select, func
from sqlalchemy import text


from ..core.database import session_scope
from ..models.species import LineageEvent, PopulationSnapshot, Species


class SpeciesRepository:
    """Data access helpers for species and populations."""

    def list_species(self, 
                     status: Optional[str] = None,
                     prefix: Optional[str] = None,
                     limit: Optional[int] = None,
                     offset: int = 0) -> list[Species]:
        """
        获取物种列表，支持可选过滤和分页
        
        Args:
            status: 可选，筛选状态 ("alive", "extinct", "split")
            prefix: 可选，按lineage_code前缀筛选
            limit: 可选，返回数量限制
            offset: 分页偏移量
        """
        with session_scope() as session:
            query = select(Species)
            
            if status:
                query = query.where(Species.status == status)
            if prefix:
                query = query.where(Species.lineage_code.startswith(prefix))
            
            query = query.offset(offset)
            if limit:
                query = query.limit(limit)
                
            return list(session.exec(query))
    
    def count_species(self, status: Optional[str] = None, prefix: Optional[str] = None) -> int:
        """获取物种总数（用于分页）"""
        with session_scope() as session:
            query = select(func.count(Species.id))
            if status:
                query = query.where(Species.status == status)
            if prefix:
                query = query.where(Species.lineage_code.startswith(prefix))
            return session.exec(query).first() or 0
    
    def get_population_stats_batch(self, species_ids: list[int]) -> dict[int, dict]:
        """
        批量获取物种的人口统计信息（峰值人口、最后回合）
        
        Returns:
            dict: {species_id: {"peak_population": int, "last_turn": int}}
        """
        if not species_ids:
            return {}
        
        with session_scope() as session:
            # 单次查询获取所有物种的峰值人口和最后回合
            query = (
                select(
                    PopulationSnapshot.species_id,
                    func.max(PopulationSnapshot.count).label("peak_pop"),
                    func.max(PopulationSnapshot.turn_index).label("last_turn")
                )
                .where(PopulationSnapshot.species_id.in_(species_ids))
                .group_by(PopulationSnapshot.species_id)
            )
            
            results = session.exec(query).all()
            
            return {
                row.species_id: {
                    "peak_population": row.peak_pop or 0,
                    "last_turn": row.last_turn
                }
                for row in results
            }
    
    def get_all(self) -> list[Species]:
        """list_species的别名，保持API兼容"""
        return self.list_species()

    def get_by_lineage(self, lineage_code: str) -> Species | None:
        with session_scope() as session:
            return session.exec(
                select(Species).where(Species.lineage_code == lineage_code)
            ).first()

    def get_by_code(self, code: str) -> Species | None:
        """根据物种代码获取物种（lineage_code的别名）"""
        return self.get_by_lineage(code)

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



# DEPRECATED: Module-level singleton
# Use container.species_repository instead for proper isolation.
# This global instance will be removed in a future version.
species_repository = SpeciesRepository()
