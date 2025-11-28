"""属数据仓储"""
from __future__ import annotations

from typing import Sequence

from sqlmodel import Session, select

from ..core.database import session_scope
from ..models.genus import Genus


class GenusRepository:
    """属数据访问层"""
    
    def get_by_code(self, code: str) -> Genus | None:
        """根据编码获取属"""
        with session_scope() as session:
            statement = select(Genus).where(Genus.code == code)
            return session.exec(statement).first()
    
    def list_all(self) -> Sequence[Genus]:
        """列出所有属"""
        with session_scope() as session:
            statement = select(Genus)
            return session.exec(statement).all()
    
    def upsert(self, genus: Genus) -> Genus:
        """插入或更新属"""
        with session_scope() as session:
            existing = session.exec(
                select(Genus).where(Genus.code == genus.code)
            ).first()
            
            if existing:
                existing.name_latin = genus.name_latin
                existing.name_common = genus.name_common
                existing.genetic_distances = genus.genetic_distances
                existing.updated_turn = genus.updated_turn
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return existing
            else:
                session.add(genus)
                session.commit()
                session.refresh(genus)
                return genus
    
    def update_distances(self, code: str, distances: dict[str, float], turn: int):
        """更新属的遗传距离矩阵"""
        with session_scope() as session:
            genus = session.exec(select(Genus).where(Genus.code == code)).first()
            if genus:
                genus.genetic_distances.update(distances)
                genus.updated_turn = turn
                session.add(genus)
                session.commit()

    def clear_state(self) -> None:
        """清除所有属数据（用于存档切换时隔离数据）"""
        from sqlalchemy import text
        with session_scope() as session:
            session.exec(text("DELETE FROM genus"))


genus_repository = GenusRepository()

