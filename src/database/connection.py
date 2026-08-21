"""
Database Connection
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.database.models import Base
from src.config.loader import get_config

log = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def _get_engine():
    global _engine
    if _engine is None:
        cfg = get_config()
        url = cfg.get("database", {}).get(
            "url",
            f"sqlite:///{Path(__file__).parents[2]}/data/trading.db"
        )
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            from sqlalchemy import event as sa_event
            @sa_event.listens_for(_engine, "connect")
            def set_wal(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        log.info(f"Database engine created")
    return _engine


def init_db():
    engine = _get_engine()
    Base.metadata.create_all(engine)
    log.info("Database tables initialised.")


def get_session():
    return _session_context()


@contextmanager
def _session_context():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health_check():
    try:
        with _get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error(f"Database health check failed: {e}")
        return False
