"""Second database — Cheradip VS Code extension (``extcheradip``).

Kept separate from the AILT app database (``ailanguagetutor``). All extension
models use ``ExtBase`` so ``ExtBase.metadata.create_all(bind=ext_engine)`` only
creates extension tables in this database.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

ext_engine = create_engine(
    settings.ext_database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)
ExtSessionLocal = sessionmaker(bind=ext_engine, autoflush=False, autocommit=False)


class ExtBase(DeclarativeBase):
    pass


def get_ext_db() -> Generator[Session, None, None]:
    db = ExtSessionLocal()
    try:
        yield db
    finally:
        db.close()
