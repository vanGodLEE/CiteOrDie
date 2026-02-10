"""
Database connection and initialisation.

Uses SQLite for persistent storage with SQLAlchemy ORM.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from pathlib import Path
from loguru import logger

# ---------------------------------------------------------------------------
# Declarative base for ORM models
# ---------------------------------------------------------------------------

Base = declarative_base()

# ---------------------------------------------------------------------------
# Database file path
# ---------------------------------------------------------------------------

DB_DIR = Path("data")
DB_PATH = DB_DIR / "document_analysis.db"

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# - check_same_thread=False : allow multi-threaded access to the same connection
# - timeout=30              : wait up to 30 s for a database lock
# - poolclass=NullPool      : create a fresh connection every time (avoids
#                             sharing connections across threads)
# - echo=False              : set True to log all SQL statements

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
    poolclass=NullPool,
    echo=False,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create the data directory (if needed) and all ORM tables."""
    DB_DIR.mkdir(exist_ok=True)
    logger.info(f"Initializing database: {DB_PATH}")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")


def get_db():
    """Yield a database session (for FastAPI dependency injection)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_session():
    """Return a database session for direct (non-DI) use."""
    return SessionLocal()

