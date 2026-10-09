from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Yield a session and always close it (used as a FastAPI dependency later)."""
    with SessionLocal() as session:
        yield session


def schema_versions() -> tuple[str | None, str | None]:
    """(revision the DB is at, newest revision in the code). Equal = up to date."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from app.core.config import ROOT_DIR

    head = ScriptDirectory.from_config(Config(ROOT_DIR / "alembic.ini")).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, head


def check_connection() -> str:
    with engine.connect() as conn:
        return conn.execute(text("select version()")).scalar_one()


if __name__ == "__main__":
    print(check_connection())
