from __future__ import annotations

from sqlmodel import select
from sqlalchemy import text


from ..core.database import session_scope
from ..models.history import TurnLog


class HistoryRepository:
    def log_turn(self, turn: TurnLog) -> TurnLog:
        with session_scope() as session:
            session.add(turn)
            session.flush()
            session.refresh(turn)
            return turn

    def list_turns(self, limit: int = 50) -> list[TurnLog]:
        with session_scope() as session:
            result = session.exec(
                select(TurnLog).order_by(TurnLog.turn_index.desc()).limit(limit)
            )
            return list(result)

    def clear_state(self) -> None:
        """清除所有历史记录（用于读档前）"""
        with session_scope() as session:
            session.exec(text("DELETE FROM turn_logs"))



# DEPRECATED: Module-level singleton
# Use container.history_repository instead for proper isolation.
# This global instance will be removed in a future version.
history_repository = HistoryRepository()
