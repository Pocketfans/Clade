from __future__ import annotations

from sqlmodel import select

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


history_repository = HistoryRepository()
