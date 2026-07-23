from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from sqlalchemy.engine import Connection, RootTransaction
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

settings = get_settings()

# 确保数据库目录存在
db_path = settings.database_url.replace("sqlite:///", "")
if db_path and not db_path.startswith(":memory:"):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})

_transaction_connection: ContextVar[Connection | None] = ContextVar(
    "transaction_connection",
    default=None,
)


def init_db() -> None:
    """Create database tables if they do not exist."""
    # 确保所有模型已注册到 SQLModel 元数据
    from ..models import environment, species, genus, history  # noqa: F401
    SQLModel.metadata.create_all(engine)
    _migrate_species_table()


@contextmanager
def session_scope() -> Session:
    """Provide a transactional scope around a series of operations."""

    transaction_connection = _transaction_connection.get()
    if transaction_connection is None:
        session = Session(engine, expire_on_commit=False)
    else:
        session = Session(
            bind=transaction_connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def transaction_scope() -> Iterator[RootTransaction]:
    """Group repository sessions into one commit or rollback boundary."""

    connection = engine.connect()
    try:
        if connection.dialect.name == "sqlite":
            # SQLite otherwise starts lazily at the first SAVEPOINT, whose release
            # could persist data before this outer transaction decides to commit.
            connection.exec_driver_sql("BEGIN")
            transaction = connection.get_transaction()
            if transaction is None:
                raise RuntimeError("Unable to start SQLite transaction")
        else:
            transaction = connection.begin()
    except BaseException:
        connection.close()
        raise

    token = _transaction_connection.set(connection)
    try:
        yield transaction
        if transaction.is_active:
            transaction.commit()
    except BaseException:
        if transaction.is_active:
            transaction.rollback()
        raise
    finally:
        _transaction_connection.reset(token)
        connection.close()


def _migrate_species_table() -> None:
    """
    轻量级迁移：为 species 表添加新字段（兼容旧存档）
    
    - gene_diversity_radius: REAL
    - explored_directions: JSON/TEXT
    - gene_stability: REAL
    """
    try:
        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA table_info(species)")
            existing = {row[1] for row in result.fetchall()}

            alter_statements: list[tuple[str, str]] = []
            if "gene_diversity_radius" not in existing:
                alter_statements.append(
                    ("gene_diversity_radius", "ALTER TABLE species ADD COLUMN gene_diversity_radius REAL DEFAULT 0.35")
                )
            if "explored_directions" not in existing:
                alter_statements.append(
                    ("explored_directions", "ALTER TABLE species ADD COLUMN explored_directions JSON DEFAULT '[]'")
                )
            if "gene_stability" not in existing:
                alter_statements.append(
                    ("gene_stability", "ALTER TABLE species ADD COLUMN gene_stability REAL DEFAULT 0.5")
                )

            for _, stmt in alter_statements:
                try:
                    conn.exec_driver_sql(stmt)
                except Exception:
                    # 如果列已存在或SQLite版本不支持JSON类型，忽略错误
                    pass

            # 为缺失值填充默认值，确保运行期不会出现 None
            try:
                conn.exec_driver_sql(
                    "UPDATE species SET gene_diversity_radius = COALESCE(gene_diversity_radius, 0.35)"
                )
                conn.exec_driver_sql(
                    "UPDATE species SET explored_directions = COALESCE(explored_directions, '[]')"
                )
                conn.exec_driver_sql(
                    "UPDATE species SET gene_stability = COALESCE(gene_stability, 0.5)"
                )
            except Exception:
                pass
    except Exception:
        # 迁移失败不影响启动，但会记录警告
        import logging

        logging.getLogger(__name__).warning("[DB] species 表迁移失败，可能缺少新字段")
