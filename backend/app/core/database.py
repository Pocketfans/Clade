from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()

# 确保数据库目录存在
db_path = settings.database_url.replace("sqlite:///", "")
if db_path and not db_path.startswith(":memory:"):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    """Create database tables if they do not exist."""
    # 确保所有模型已注册到 SQLModel 元数据
    from ..models import environment, species, genus, history  # noqa: F401
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Session:
    """Provide a transactional scope around a series of operations."""

    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
