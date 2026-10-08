# Phase 1: Data and SQL

**Result:** 750,127 IMDb movies with ratings, genres and moods in Postgres, loaded in about 30 s by a
re-runnable ETL, with indexes for fuzzy and popularity search, plus SQL exercises in `sql/`.

## Steps
| Step | What | Run |
|---|---|---|
| 1 | Download IMDb TSVs (streamed, skip-if-exists, `.part` → rename) | `uv run python -m app.etl.download` |
| 2 | Alembic + models + migration `0001` (tables, extensions, genre/mood seed) | `uv run alembic upgrade head` |
| 3 | Loader: COPY → staging → SQL upsert, one transaction | `uv run python -m app.etl.imdb_loader` |
| 4 | EXPLAIN + indexes (`0002`: `ix_ratings_num_votes`), SQL practice | `sql/01_*.sql`, `sql/02_*.sql` in pgAdmin |

## Schema
```
movies (tconst PK, title, original_title, year, runtime_min, is_adult)
  ├─ ratings (tconst PK/FK, avg_rating, num_votes)              1 : 0..1
  ├─ movie_genres (tconst, genre_id) ── genres (id, name)       many : many
  │                                       └─ mood_genres ── moods (id, name, description)
  ├─ watchlist (id, tconst UNIQUE FK, status, priority, source, notes, my_rating, …)
  └─ tmdb_cache (tconst PK/FK, tmdb_id, poster_path, overview, cast JSONB)
```

## Data profile (from the raw files)
- 12.8 M titles in total → **758,864 movies** → 750,127 loaded (adult rule dropped 8,737).
- **Adult rule:** keep only if rating ≥ 6.5 **and** ≥ 50 votes → 365 of 9,102 kept.
- 27 genres. Drama 277k, Documentary 151k, Comedy 126k. About 1.03 M movie↔genre links.
- **54% of movies have no rating.** Only about 49k have 1,000+ votes. They're kept for matching;
  browse views filter on `num_votes`.
- Outliers: "Logistics" (2012) runs 51,420 min (35 days). Years go from 1894 to 2032 (announced films).
- New releases get inflated early ratings (9+ from fans), so "hidden gems" queries should exclude recent years.

## Concepts
- **Migrations (Alembic).** The schema is versioned code. `alembic upgrade head` / `downgrade -1`, and the
  current version is stored in the `alembic_version` table. Autogenerate diffs the models against the DB, but
  extensions, seed data and data fixes are added by hand. Seed data lives *in* the migration, as a frozen snapshot.
- **Naming convention.** Predictable names (`pk_movies`, `fk_ratings_tconst_movies`, `ix_…`) make
  migrations reversible and pgAdmin readable.
- **Many-to-many** through a link table (`movie_genres`). Its composite PK serves the lookup
  "genres of a movie", and the extra index on `genre_id` serves "movies of a genre".
- **CHECK constraint vs ENUM.** Same validation, but much easier to change later.
- **COPY** streams rows in bulk (about 100× faster than INSERT per row). IMDb's TSV is almost COPY's native format.
  We use `FORMAT csv` with an unused quote char so quotes and backslashes in titles stay literal.
- **Staging tables** (TEMP, all `text`): raw data lands first and is cast safely in SQL
  (`CASE WHEN x ~ '^\d{4}$' THEN x::smallint END`), so bad rows can't break real tables.
- **Upsert** (`INSERT … ON CONFLICT DO UPDATE`) makes the loader idempotent (safe to re-run). It never
  deletes, so the watchlist's foreign keys stay valid. Tightening a filter later therefore needs a separate cleanup.
- **One transaction** for the whole load: all or nothing. `ANALYZE` afterwards refreshes planner statistics.
- **Where load time goes:** COPY takes about 4 s, but maintaining the trigram index and foreign keys takes about 20 s.
- **pg_trgm.** similarity = shared trigrams / all distinct trigrams (Jaccard). `'Interstellar'` vs
  `'Intersteller'` = 10/16 = 0.625. `%` means similarity ≥ `pg_trgm.similarity_threshold` (0.3).
- **Popularity boost.** Text similarity alone ranks "Interstella" (2023, no votes) above "Interstellar".
  `similarity + 0.05 * log10(votes + 1)` fixes it (0.946 vs 0.667). This is the core of the phase-2 matcher.
- **EXPLAIN ANALYZE.** Read plans bottom-up. Seq Scan vs Index/Bitmap scans. "Rows Removed by Filter"
  is wasted work. The planner skips an index when a query matches most rows (selectivity).
- **Index results on this data:** fuzzy `%` went from 331 → 25 ms, `ILIKE '%godfather%'` from 59 → 5.8 ms (the trigram
  index helps leading wildcards, which a B-tree can't), and popular-movies from 8.4 → 3.1 ms (small table, small gain).
- **Postgres DDL is transactional.** `BEGIN; CREATE INDEX …; EXPLAIN …; ROLLBACK;` lets you experiment safely.

## Useful commands
```bash
uv run alembic current            # which migration the DB is at
uv run alembic history            # all migrations
uv run alembic downgrade -1       # undo the last one
uv run alembic revision --autogenerate --rev-id 0003 -m "..."   # after changing models.py
uv run python -m app.etl.imdb_loader                              # refresh with new IMDb dumps
```

## Try next
- Work through `sql/02_practice_queries.sql`, section 7 (challenges).
- Edit a mood in `mood_genres` and re-run the mood query.
- Re-download in a month (`download --force` + loader) and compare `num_votes` for a few films.
