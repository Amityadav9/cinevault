"""Find the movie(s) a parsed input refers to.

IMDb id   → direct primary-key lookup (exact, score 1.0)
text      → trigram fuzzy search, ranked by
                similarity(title, query)              0 … 1    how alike the text is
              + POPULARITY_WEIGHT · log10(votes + 1)  0 … ~0.35 famous films win ties
              + year bonus                            0.3 exact / 0.15 off-by-one
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.parse_input import ParsedInput

POPULARITY_WEIGHT = 0.05
YEAR_EXACT_BONUS = 0.30
YEAR_CLOSE_BONUS = 0.15  # release years differ between countries / festival vs. cinema


@dataclass(frozen=True)
class Candidate:
    tconst: str
    title: str
    year: int | None
    runtime_min: int | None
    avg_rating: Decimal | None
    num_votes: int | None
    genres: list[str]
    is_adult: bool
    similarity: float  # pure text similarity (1.0 for an IMDb-id hit)
    score: float  # final ranking score

    @property
    def imdb_url(self) -> str:
        return f"https://www.imdb.com/title/{self.tconst}/"


# Shared column list; genres are aggregated per movie with a correlated ARRAY subquery
# (cheap here: it only runs for the handful of rows that survive LIMIT).
_COLUMNS = """
    m.tconst, m.title, m.year, m.runtime_min, m.is_adult, r.avg_rating, r.num_votes,
    ARRAY(SELECT g.name FROM movie_genres mg JOIN genres g ON g.id = mg.genre_id
          WHERE mg.tconst = m.tconst ORDER BY g.name) AS genres
"""

_BY_ID_SQL = text(f"""
SELECT {_COLUMNS}, 1.0 AS similarity, 1.0 AS score
FROM movies m
LEFT JOIN ratings r USING (tconst)
WHERE m.tconst = :tconst
""")

# LATERAL runs the indexed `title % q` search once per query variant ("Bee" and "Bee Movie");
# a movie found by both keeps its best similarity.
_FUZZY_SQL = text(f"""
WITH hits AS (
    SELECT h.tconst, max(h.sim) AS sim
    FROM unnest(CAST(:queries AS text[])) AS q(q)
    CROSS JOIN LATERAL (
        -- both sides lowercase + accent-free: "amelie" matches "Amélie"
        SELECT tconst, similarity(title_search, lower(f_unaccent(q.q))) AS sim
        FROM movies
        WHERE title_search % lower(f_unaccent(q.q))
    ) h
    GROUP BY h.tconst
)
SELECT {_COLUMNS},
       h.sim AS similarity,
       h.sim
         + :pop_weight * log(coalesce(r.num_votes, 0) + 1)
         + CASE
             WHEN CAST(:year AS int) IS NULL OR m.year IS NULL THEN 0
             WHEN m.year = :year                               THEN :year_exact
             WHEN abs(m.year - :year) = 1                      THEN :year_close
             ELSE 0
           END AS score
FROM hits h
JOIN movies m USING (tconst)
LEFT JOIN ratings r USING (tconst)
ORDER BY score DESC, r.num_votes DESC NULLS LAST
LIMIT :limit
""")


def find_candidates(session: Session, parsed: ParsedInput, limit: int = 5) -> list[Candidate]:
    """Best matches first. Empty list = nothing found (e.g. an IMDb id of a TV series)."""
    if parsed.imdb_id:
        rows = session.execute(_BY_ID_SQL, {"tconst": parsed.imdb_id}).mappings()
    else:
        queries = [q for q in (parsed.query, parsed.query_full) if q]
        rows = session.execute(
            _FUZZY_SQL,
            {
                "queries": queries,
                "year": parsed.year,
                "pop_weight": POPULARITY_WEIGHT,
                "year_exact": YEAR_EXACT_BONUS,
                "year_close": YEAR_CLOSE_BONUS,
                "limit": limit,
            },
        ).mappings()
    return [
        Candidate(**{**row, "similarity": float(row["similarity"]), "score": float(row["score"])})
        for row in rows
    ]
