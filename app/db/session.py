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


def check_connection() -> str:
    with engine.connect() as conn:
        return conn.execute(text("select version()")).scalar_one()


if __name__ == "__main__":
    print(check_connection())
