"""Load the downloaded IMDb TSVs into Postgres (Extract → Staging → Transform/Upsert).

Usage:
    uv run python -m app.etl.download       # first, if data/raw/ is empty
    uv run python -m app.etl.imdb_loader

Safe to re-run: rows are upserted, so new IMDb dumps simply refresh titles and ratings
without touching the watchlist that references them.
"""

import gzip
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg

from app.core.config import get_settings

ADULT_MIN_RATING = 6.5  # adult titles are kept only if rated at least this ...
ADULT_MIN_VOTES = 50  # ... by at least this many voters (a 7.0 from 4 votes means little)
BATCH_LINES = 50_000

# IMDb TSVs are tab-separated with \N for NULL and *no* quoting. We use COPY's csv mode with
# a quote char that never appears (\x01), so quotes and backslashes inside titles are kept
# literally (the plain "text" format would treat backslashes as escapes).
COPY_OPTS = "(FORMAT csv, DELIMITER E'\\t', NULL '\\N', QUOTE E'\\x01')"


@contextmanager
def step(name: str) -> Iterator[None]:
    start = time.perf_counter()
    print(f"→ {name} ...", end=" ", flush=True)
    yield
    print(f"{time.perf_counter() - start:.1f}s")


def connect() -> psycopg.Connection:
    s = get_settings()
    return psycopg.connect(
        host=s.postgres_host,
        port=s.postgres_port,
        dbname=s.postgres_db,
        user=s.postgres_user,
        password=s.postgres_password,
    )


# --- Extract: stream gz files into TEMP staging tables via COPY ----------------------------


def copy_basics(cur: psycopg.Cursor, path: Path) -> int:
    """Copy only titleType == 'movie' rows (~760k of ~12.8M lines)."""
    cur.execute(
        """
        CREATE TEMP TABLE stg_basics (
            tconst text, title_type text, primary_title text, original_title text,
            is_adult text, start_year text, end_year text, runtime text, genres text
        ) ON COMMIT DROP
        """
    )
    kept = 0
    with (
        cur.copy(f"COPY stg_basics FROM STDIN {COPY_OPTS}") as copy,
        gzip.open(path, "rt", encoding="utf-8") as f,
    ):
        next(f)  # header
        batch: list[str] = []
        for line in f:
            if line.split("\t", 2)[1] == "movie":
                batch.append(line)
                if len(batch) >= BATCH_LINES:
                    copy.write("".join(batch))
                    kept += len(batch)
                    batch.clear()
        copy.write("".join(batch))
        kept += len(batch)
    return kept


def copy_ratings(cur: psycopg.Cursor, path: Path) -> None:
    """Copy the whole ratings file (small); filtering to movies happens via a join."""
    cur.execute(
        "CREATE TEMP TABLE stg_ratings (tconst text, avg_rating text, num_votes text) "
        "ON COMMIT DROP"
    )
    with (
        cur.copy(f"COPY stg_ratings FROM STDIN {COPY_OPTS}") as copy,
        gzip.open(path, "rb") as f,
    ):
        f.readline()  # header
        while chunk := f.read(1024 * 1024):
            copy.write(chunk)


# --- Transform + Load: clean and upsert in SQL ---------------------------------------------

# Staging columns are text, so bad values can't break the load: we only cast what matches.
UPSERT_MOVIES = """
INSERT INTO movies (tconst, title, original_title, year, runtime_min, is_adult)
SELECT b.tconst,
       b.primary_title,
       b.original_title,
       CASE WHEN b.start_year ~ '^\\d{4}$' THEN b.start_year::smallint END,
       CASE WHEN b.runtime ~ '^\\d{1,6}$' THEN b.runtime::int END,
       b.is_adult = '1'
FROM stg_basics b
LEFT JOIN stg_ratings r USING (tconst)
WHERE b.primary_title IS NOT NULL
  AND (b.is_adult = '0'
       OR (r.avg_rating::numeric >= %(adult_min)s AND r.num_votes::int >= %(adult_votes)s))
ON CONFLICT (tconst) DO UPDATE SET
    title          = EXCLUDED.title,
    original_title = EXCLUDED.original_title,
    year           = EXCLUDED.year,
    runtime_min    = EXCLUDED.runtime_min,
    is_adult       = EXCLUDED.is_adult
"""

UPSERT_RATINGS = """
INSERT INTO ratings (tconst, avg_rating, num_votes)
SELECT r.tconst, r.avg_rating::numeric(3, 1), r.num_votes::int
FROM stg_ratings r
JOIN movies m USING (tconst)
ON CONFLICT (tconst) DO UPDATE SET
    avg_rating = EXCLUDED.avg_rating,
    num_votes  = EXCLUDED.num_votes
"""

# New genre names (if IMDb ever adds one) get an id; existing ones are left alone.
INSERT_NEW_GENRES = """
INSERT INTO genres (name)
SELECT DISTINCT x.name
FROM stg_basics b, unnest(string_to_array(b.genres, ',')) AS x(name)
ON CONFLICT (name) DO NOTHING
"""

# Replace genre links for the movies in this load (IMDb sometimes re-tags a film).
DELETE_MOVIE_GENRES = """
DELETE FROM movie_genres mg USING stg_basics b WHERE mg.tconst = b.tconst
"""

# "Drama,Romance" → two rows. LATERAL unnest = "for each staging row, split its genres".
INSERT_MOVIE_GENRES = """
INSERT INTO movie_genres (tconst, genre_id)
SELECT m.tconst, g.id
FROM stg_basics b
JOIN movies m USING (tconst)
CROSS JOIN LATERAL unnest(string_to_array(b.genres, ',')) AS x(name)
JOIN genres g ON g.name = x.name
ON CONFLICT DO NOTHING
"""

ADULT_STATS = """
SELECT count(*) FILTER (WHERE b.is_adult = '1'),
       count(*) FILTER (WHERE b.is_adult = '1' AND r.avg_rating::numeric >= %(adult_min)s
                        AND r.num_votes::int >= %(adult_votes)s)
FROM stg_basics b LEFT JOIN stg_ratings r USING (tconst)
"""

SUMMARY = """
SELECT (SELECT count(*) FROM movies),
       (SELECT count(*) FROM ratings),
       (SELECT count(*) FROM genres),
       (SELECT count(*) FROM movie_genres)
"""


def main() -> None:
    raw = get_settings().data_dir / "raw"
    basics, ratings = raw / "title.basics.tsv.gz", raw / "title.ratings.tsv.gz"
    for p in (basics, ratings):
        if not p.exists():
            sys.exit(f"✗ missing {p}. Run: uv run python -m app.etl.download")

    params = {"adult_min": ADULT_MIN_RATING, "adult_votes": ADULT_MIN_VOTES}
    total = time.perf_counter()

    # One transaction: either everything loads, or nothing changes. Commits on clean exit.
    with connect() as conn, conn.cursor() as cur:
        with step("extract basics → stg_basics (movies only)"):
            n_basics = copy_basics(cur, basics)
        with step("extract ratings → stg_ratings"):
            copy_ratings(cur, ratings)
        with step("upsert movies"):
            cur.execute(UPSERT_MOVIES, params)
            n_movies = cur.rowcount
        with step("upsert ratings"):
            cur.execute(UPSERT_RATINGS)
            n_ratings = cur.rowcount
        with step("genres + movie_genres"):
            cur.execute(INSERT_NEW_GENRES)
            cur.execute(DELETE_MOVIE_GENRES)
            cur.execute(INSERT_MOVIE_GENRES)
            n_links = cur.rowcount
        cur.execute(ADULT_STATS, params)
        adult_total, adult_kept = cur.fetchone()
        with step("ANALYZE (refresh planner statistics)"):
            cur.execute("ANALYZE movies, ratings, movie_genres")
        cur.execute(SUMMARY)
        t_movies, t_ratings, t_genres, t_links = cur.fetchone()

    print(f"\n✓ done in {time.perf_counter() - total:.1f}s")
    print(f"  staged movie rows : {n_basics:>9,}")
    print(f"  movies upserted   : {n_movies:>9,}")
    print(f"  ratings upserted  : {n_ratings:>9,}")
    print(f"  genre links       : {n_links:>9,}")
    rule = f"rating ≥ {ADULT_MIN_RATING}, votes ≥ {ADULT_MIN_VOTES}"
    print(f"  adult kept        : {adult_kept:>9,} of {adult_total:,} ({rule})")
    print(f"  tables now        : movies={t_movies:,} ratings={t_ratings:,} "
          f"genres={t_genres} movie_genres={t_links:,}")  # fmt: skip


if __name__ == "__main__":
    main()
