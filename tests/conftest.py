"""Shared pytest fixtures.

`db` gives each test a Session inside a transaction that is ROLLED BACK afterwards,
so tests can add/remove watchlist entries without touching your real data.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import engine


@pytest.fixture(scope="session")
def db_ready() -> None:
    try:
        with engine.connect() as conn:
            if conn.execute(text("SELECT count(*) FROM movies")).scalar_one() < 100_000:
                pytest.skip("IMDb data not loaded (run app.etl.imdb_loader)")
    except OperationalError:
        pytest.skip("database not reachable (docker compose up -d db)")


@pytest.fixture
def db(db_ready):
    with engine.connect() as conn:
        outer = conn.begin()
        # "create_savepoint": a session.commit() inside the code under test only releases a
        # SAVEPOINT; the outer transaction still rolls everything back at the end.
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
