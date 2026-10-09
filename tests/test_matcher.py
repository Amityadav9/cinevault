"""Integration tests: run the matcher against the real loaded database.

Skipped automatically if Postgres isn't reachable or the IMDb data isn't loaded.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.services.matcher import find_candidates
from app.services.parse_input import parse_input


@pytest.fixture(scope="module")
def session():
    try:
        with SessionLocal() as s:
            if s.execute(text("SELECT count(*) FROM movies")).scalar_one() < 100_000:
                pytest.skip("IMDb data not loaded (run app.etl.imdb_loader)")
            yield s
    except OperationalError:
        pytest.skip("database not reachable (docker compose up -d db)")


def top(session, user_input: str) -> str:
    candidates = find_candidates(session, parse_input(user_input))
    assert candidates, f"no match for {user_input!r}"
    return candidates[0].tconst


@pytest.mark.parametrize(
    ("user_input", "tconst"),
    [
        # exact ids
        ("https://www.imdb.com/title/tt0816692/", "tt0816692"),  # Interstellar
        # typos: fuzzy + popularity
        ("intersteller 2014", "tt0816692"),
        ("intersteller", "tt0816692"),
        ("the godfater", "tt0068646"),  # The Godfather
        ("spirited away", "tt0245429"),
        # a noise word that is part of the title ("Bee" alone ties with obscure films)
        ("Bee Movie", "tt0389790"),
        ("the lego movie", "tt1490017"),
        # the year picks between remakes
        ("dune 2021", "tt1160419"),
        ("dune 1984", "tt0087182"),
        ("parasite 2019", "tt6751668"),
        # titles that look like years / noise
        ("1917", "tt8579674"),
        ("Full Metal Jacket", "tt0093058"),
        # URLs
        ("https://www.google.com/search?q=past+lives+2023+movie", "tt13238346"),
        ("https://letterboxd.com/film/dune-part-two/", "tt15239678"),
    ],
)
def test_best_match(session, user_input, tconst):
    assert top(session, user_input) == tconst


def test_tv_series_id_is_not_a_movie(session):
    # Breaking Bad: valid IMDb id, but we only load movies
    assert find_candidates(session, parse_input("https://www.imdb.com/title/tt0903747/")) == []


def test_candidates_are_ranked_and_complete(session):
    candidates = find_candidates(session, parse_input("intersteller 2014"), limit=5)
    assert len(candidates) == 5
    assert [c.score for c in candidates] == sorted((c.score for c in candidates), reverse=True)
    best = candidates[0]
    assert best.title == "Interstellar" and best.year == 2014
    assert "Sci-Fi" in best.genres and best.num_votes > 1_000_000


@pytest.mark.parametrize(
    ("user_input", "tconst"),
    [
        ("amelie", "tt0211915"),  # Amélie (2001)
        ("leon the professional", "tt0110413"),  # Léon: The Professional
        ("AMÉLIE", "tt0211915"),  # accents/case on the input side too
    ],
)
def test_accents_and_case_are_ignored(session, user_input, tconst):
    assert top(session, user_input) == tconst
