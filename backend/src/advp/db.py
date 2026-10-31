"""SQLite setup and health checks."""

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def configure_database(database_path: Path, *, create_parent: bool = True) -> None:
    """Create or replace the process-wide SQLite engine."""
    global _engine, _session_factory

    if create_parent:
        database_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{database_path.as_posix()}"
    _engine = create_engine(url, connect_args={"check_same_thread": False})
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine() -> Engine:
    """Return the configured engine, raising if the app is not started."""
    if _engine is None:
        raise RuntimeError("database is not configured")
    return _engine


def init_db() -> None:
    """Create missing tables and apply lightweight additive migrations."""
    from advp.models import Base

    engine = get_engine()
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "datasets" in tables:
        columns = {column["name"] for column in inspector.get_columns("datasets")}
        if "kind" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE datasets ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'table'"
                    )
                )
    if "llm_usage" in tables:
        columns = {column["name"] for column in inspector.get_columns("llm_usage")}
        if "project_id" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE llm_usage ADD COLUMN project_id VARCHAR(32)"))
    if "chart_selections" in tables:
        columns = {column["name"] for column in inspector.get_columns("chart_selections")}
        if "parent_selection_id" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE chart_selections ADD COLUMN parent_selection_id VARCHAR(32)")
                )
        if "source" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE chart_selections "
                        "ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'ai'"
                    )
                )
    if "pipeline_runs" in tables:
        columns = {column["name"] for column in inspector.get_columns("pipeline_runs")}
        if "parent_run_id" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE pipeline_runs ADD COLUMN parent_run_id VARCHAR(32)")
                )
    if "llm_usage" in tables:
        columns = {column["name"] for column in inspector.get_columns("llm_usage")}
        if "run_id" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE llm_usage ADD COLUMN run_id VARCHAR(32)"))
        if "tag" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE llm_usage "
                        "ADD COLUMN tag VARCHAR(30) NOT NULL DEFAULT 'initial'"
                    )
                )


def get_session() -> Session:
    """Create a database session for future request dependencies."""
    if _session_factory is None:
        raise RuntimeError("database is not configured")
    return _session_factory()


def check_database() -> bool:
    """Return True when a trivial query succeeds."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
