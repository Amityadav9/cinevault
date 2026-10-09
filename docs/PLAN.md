# CineVault: Personal Movie Watchlist

> The master plan and reference for this project. It's kept up to date as we build:
> tick the progress boxes, append to the decisions log, and link the phase notes.

## Why this exists
I keep many browser windows open full of movie searches so I don't forget what to watch.
CineVault turns those tabs into a structured, searchable watchlist with metadata
(poster, year, IMDb rating, genres, plot, cast). Then it's built up one layer at a time
as a learning project: **SQL → Streamlit → FastAPI → LLM chatbot with tool calling → Docker**.
Every phase ends with something runnable and a "what I learned / why" note in `docs/phase-N.md`.

## Progress
- [x] **Phase 0: Setup** (uv, git, config, Postgres in Docker, pgAdmin): done 2026-10-08, see [phase-0.md](phase-0.md)
- [x] **Phase 1: Data and SQL** (IMDb ETL into Postgres, schema, queries, indexes): done 2026-10-08, see [phase-1.md](phase-1.md)
- [x] **Phase 2: Add movies one by one** (paste URL or title → match → confirm → watchlist, TMDB enrichment): done 2026-10-09, see [phase-2.md](phase-2.md)
- [ ] **Phase 3: Streamlit MVP** (add page, poster grid, mood picker, stats): *next*
- [ ] **Phase 4: FastAPI** (REST API, Streamlit switched to call it)
- [ ] **Phase 5: LLM chatbot** (Ollama/Groq, tool calling over the services)
- [ ] **Phase 6: Docker and production** (full compose stack, tests, CI)

## Architecture (end state)
```
Paste 1 URL / title ─┐
  (you confirm)      │
                     ▼
              FastAPI backend  ──► Postgres (from day 1; browse in pgAdmin)
               │   ▲                    ▲
               │   └── TMDB API         └── IMDb TSV loader (ETL)
               ▼
        LLM service (Ollama | Groq) with tools → calls the same service layer
               ▲
        Streamlit UI (talks only to FastAPI)
        all of it wrapped in docker-compose
```

## Project layout
```
movies_collection/
  pyproject.toml (uv)   uv.lock   .env.example   docker-compose.yml
  app/
    core/config.py        # pydantic-settings: DB, TMDB, LLM config
    db/models.py, session.py, migrations/ (alembic)
    etl/imdb_loader.py    # download + bulk-load IMDb TSVs
    services/             # movies.py, watchlist.py, matcher.py, tmdb.py  ← business logic
    services/parse_input.py  # URL or title → IMDb id or search text (+year)
    api/                  # FastAPI routers: movies, watchlist, import, chat
    llm/                  # provider.py (Ollama/Groq), tools.py, agent.py
    cli.py                # terminal: search / add / list / watched / remove (Typer + Rich)
  ui/main.py               # Streamlit entry (navigation + DB/schema guard)
  ui/views/*.py           # one file per page
  ui/data.py              # services → display-ready dataclasses for pages
  tests/
  sql/                  # 01_explain_indexes.sql, 02_practice_queries.sql (pgAdmin exercises)
  docs/PLAN.md, docs/phase-*.md
```

## Phases

### Phase 0: Setup
`uv init`, `uv add` for dependencies, `uv run` for every command (no manual venv), and `uv.lock` committed.
Plus git, ruff, `.env` read through pydantic-settings, and Postgres 18 (pgvector image) in Docker (named volume) connected in **pgAdmin**.
Get a TMDB API token.
*Learn:* reproducible environments, keeping config out of code, containers holding state.

### Phase 1: Data and SQL (Postgres + pgAdmin)
Download IMDb `title.basics`, `title.ratings` (and optionally `title.crew`, `name.basics`).
Filter to movies (titleType=movie, ~700k rows) and bulk-load them with Postgres `COPY` (psycopg 3),
with the schema managed by SQLAlchemy 2.0 + Alembic. Add a `pg_trgm` index for fuzzy title search.
Schema: `movies` (tconst PK, title, year, runtime), `genres` + `movie_genres` (many-to-many),
`moods` + `mood_genres` (e.g. "Feel-good" → Comedy, Family…; editable), `ratings`,
`watchlist` (movie_id, status: to_watch/watched/dropped, priority, source, added_at, notes, my_rating),
`tmdb_cache` (poster_path, overview, cast JSON).
Practice SQL in pgAdmin: joins, window functions (top-rated per genre), EXPLAIN plans.
*Learn:* ETL, normalization, indexes, migrations.

### Phase 2: Add movies one by one (the core feature)
I paste **one URL** (IMDb link, Google search, any movie page) **or type a title**, check the match, and confirm.
- `services/parse_input.py`: an IMDb URL gives the exact `tt…` id. A Google/other search URL gives the `q=` text.
  Plain text gives the title, plus a year if one is present.
- `services/matcher.py`: an exact tconst match first. Otherwise trigram similarity + popularity boost + year
  match, returning the top candidates.
- **Confirm step:** show the best match (title, year, rating, genres, poster). I pick it, or one of the alternatives,
  and set priority and notes. Only then is it added to the watchlist (`source='manual'`; duplicates rejected).
- TMDB enrichment: `/find/{imdb_id}?external_source=imdb_id` → poster and overview, cached in the DB.
- First as a small CLI (`uv run python -m app.cli add "<url or title>"`), then the same service powers Streamlit and the API.
*Learn:* URL parsing, entity resolution, fuzzy matching, caching, rate limits, keeping logic in a service layer.

### Phase 3: Streamlit MVP
At first it calls the services directly. Pages: **Add movie** (paste URL or title → check match → confirm),
**Watchlist** (poster grid, filters for genre/year/rating/status), **Stats** (genres, decades, ratings).
*Learn:* fast prototyping, how UI state works.

### Phase 4: FastAPI
`GET /movies/search`, `GET/POST/PATCH/DELETE /watchlist`, `POST /watchlist/resolve` (URL or title → candidates),
`GET /stats`. Pydantic schemas, dependency-injected DB sessions, async httpx for TMDB, OpenAPI docs.
Then switch Streamlit over to calling the API.
*Learn:* layered architecture, what belongs in the service layer vs. HTTP code, validation.

### Phase 5: LLM chatbot with tool calling
`llm/provider.py` puts one interface in front of **Ollama** (local `qwen3.5`) and **Groq**. Switch with `LLM_PROVIDER=ollama|groq`.
Tools wrap the existing services: `search_watchlist(filters)`, `add_movie(title)`,
`mark_watched(id, rating)`, `recommend_from_watchlist(mood, max_runtime)`, `get_stats()`.
`POST /chat` (streaming) plus a Streamlit chat page.
Optional: embeddings (`nomic-embed-text`) over plot overviews in pgvector for "movies like X".
*Learn:* function calling, the agent loop, provider abstraction, guarding tool inputs.

### Phase 6: Docker and production
Dockerfiles for the API and the UI (uv image pattern, `uv sync --frozen`), and a compose file with db, api, ui, and ollama.
Healthchecks, structured logging, pytest (services + API via TestClient), and GitHub Actions CI.
*Learn:* containers, networking between services, multi-stage builds, CI.

**Optional later:** auth, a browser-extension button that sends the current tab to the watchlist, "where to stream" via TMDB.

## Working style
- One phase at a time. The design choice gets explained before the code, then I run it myself.
- Each phase ends with a git commit and `docs/phase-N.md` (concepts, decisions, what to try next).

## Verification checklist
- Phase 0: `uv run python -m app.db.session` prints the Postgres version; pgAdmin connects to `localhost:5435`.
- Phase 1: the loader runs → `SELECT count(*) FROM movies` ≈ 700k in pgAdmin; EXPLAIN shows the trigram index being used.
- Phase 2: add a handful of real URLs and titles (IMDb link, Google search, typo'd title) → the right movie is proposed, the duplicate is rejected.
- Phase 3: `uv run streamlit run ui/main.py` shows the poster grid and filters work.
- Phase 4: `uv run pytest` passes; `/docs` Swagger can do full CRUD.
- Phase 5: chat asks resolve to correct tool calls on both Ollama and Groq.
- Phase 6: a fresh `docker compose up` runs the whole stack.

## Environment notes
- WSL2 (Linux) on Windows, uv 0.10, Python 3.13, git.
- Ollama runs locally on `:11434` with `qwen3.5:latest` (supports tool calling) and `nomic-embed-text-v2-moe`.
- Docker Desktop is on Windows. "Use WSL 2 based engine" (General) is on, but per-distro integration is a
  **separate switch**: Settings → Resources → WSL Integration → toggle **Ubuntu** → Apply & Restart.
  Until then, `docker` inside WSL can't find `/var/run/docker.sock`. ✅ Enabled 2026-10-08.
- Clicking Apply & Restart in Docker Desktop stops all containers, so the db service has
  `restart: unless-stopped` and comes back up by itself.
- pgAdmin "Host" means the *machine* (`localhost`), not the database name. Putting `cinevault` there
  gives `getaddrinfo failed`. A *timeout* means the container isn't running → `docker compose up -d db`.
- Postgres ports already taken by other projects: 5432, 5433, 5434. **CineVault uses 5435.**
- Image `pgvector/pgvector:pg18` (Postgres 18.3 + pgvector). PG 18 images store data in
  `/var/lib/postgresql/18/docker`, so the volume is mounted at `/var/lib/postgresql` (not `.../data` as in ≤17).
- conda `base` is auto-activated in the shell, so uv warns `VIRTUAL_ENV ... will be ignored`. That's harmless:
  uv uses `.venv` anyway. To silence it: `conda config --set auto_activate_base false`.
- TMDB API: free Developer plan, token = **API Read Access Token** (`eyJ…`, sent as `Authorization: Bearer`)
  in `.env` as `TMDB_TOKEN`. The sign-up form fails with a vague "There was a problem" if Application URL is
  `http://localhost…`, so use the GitHub profile URL. ✅ Verified 2026-10-09.
- pgAdmin is installed on Windows. Connect to host `localhost`, port **5435**, user/password/db `cinevault`.

## Decisions log
| Date | Decision | Why |
|---|---|---|
| 2026-10-08 | ~~Import from bulk tab export and manual add~~ → **manual only, one URL/title at a time** | Changed same day: I want to consciously pick every movie that goes on my watchlist |
| 2026-10-08 | IMDb TSV dumps + TMDB API | IMDb: free and complete, good for SQL practice. TMDB: posters, plots, cast |
| 2026-10-08 | Ollama locally, Groq as a switch | Private/free locally; Groq for speed. Learn the provider abstraction |
| 2026-10-08 | Postgres from day 1 (not SQLite) | pgAdmin already installed; one engine everywhere, pg_trgm + pgvector |
| 2026-10-08 | Postgres runs in Docker | Same service gets reused in Phase 6; nothing installed on the host |
| 2026-10-08 | `pgvector/pgvector:pg18` on port 5435 | Already pulled; PG 18 + vectors for phase 5; 5432-5434 used by other projects |
| 2026-10-08 | Genres normalized (`genres` + `movie_genres`) and `moods` → `mood_genres` seeded in phase 1 | Pick a movie by mood; good many-to-many SQL practice; moods are editable rows |
| 2026-10-08 | Adult movies: keep only if rating ≥ 6.5 **and** ≥ 50 votes (flagged `is_adult`) → 365 of 9,102 kept | 680 of the ≥6.5 titles had <50 votes (noise). App can hide or label them |
| 2026-10-08 | Schema via Alembic (`0001_initial_schema`); extensions + genre/mood seed inside the migration | Repeatable, reversible DB versions; the migration is a frozen snapshot |
| 2026-10-08 | Watchlist `status` uses a CHECK constraint, not a PG ENUM | Same safety; adding a status later is a trivial migration |
| 2026-10-08 | Loader = COPY into TEMP staging tables → SQL upsert, one transaction | Fast bulk load (~30 s); bad values can't break real tables; safe to re-run; never deletes (watchlist references movies) |
| 2026-10-08 | Keep unrated / obscure movies (54% have no rating) | Better matching of tab titles in phase 2; browse views filter by `num_votes` instead |
| 2026-10-08 | Matcher ranking = trigram similarity + 0.05·log10(votes+1) | Plain similarity ranked "Interstella" (no votes) above "Interstellar" (2.6M); the log boost fixes it without swamping text match |
| 2026-10-08 | Index `ratings.num_votes` (migration 0002) | Popularity filter in nearly every browse view; measured 8.4 → 3.1 ms |
| 2026-10-09 | Matcher score = similarity + 0.05·log10(votes+1) + year bonus (0.30 exact, 0.15 ±1); tries both query variants | Year picks between remakes (Dune 1984 vs 2021); "Bee Movie" needs the un-stripped variant |
| 2026-10-09 | Accent/case-insensitive search: `title_search = lower(f_unaccent(title))` STORED generated column + trigram index (migration 0003); old title index dropped | "amelie" now finds "Amélie"; `f_unaccent` is an IMMUTABLE wrapper because indexes need immutable functions |
| 2026-10-09 | Services change data but never commit; callers own the transaction (unit of work) | CLI commits after the user confirms; tests roll back; same services reused by Streamlit/API/chatbot |
| 2026-10-09 | Tests use a rolled-back transaction (`tests/conftest.py`, `join_transaction_mode="create_savepoint"`) | Real watchlist is never touched by tests, even when code calls `commit()` |
| 2026-10-09 | TMDB enrichment: /find (IMDb→TMDB id) + /movie?append_to_response=credits, cached in `tmdb_cache` (+tagline, director: migration 0004); misses cached too | 2 calls per movie, ever; adding never fails because TMDB is down |
| 2026-10-09 | CLI `add` without argument = paste loop | Pasted text never goes through bash, so no quoting problems with `&` in URLs |
| 2026-10-09 | TMDB tests use a fake server (`httpx.MockTransport`) | No network, no quota; can simulate 401 / 429 |
| 2026-10-09 | Project is an installable package (hatchling; `app` + `ui`), installed editable by uv | `import app` works from Streamlit (runs from ui/), scripts, anywhere |
| 2026-10-09 | Streamlit: `st.navigation` + `ui/views/`, pages get frozen dataclasses from `ui/data.py`; watchlist not cached, moods/genres cached 10 min | Pages stay simple; fresh data after CLI changes; AppTest smoke tests |
| 2026-10-09 | Streamlit entry is `ui/main.py`, never `ui/app.py` | Streamlit puts `ui/` first on sys.path, so `ui/app.py` shadowed the `app` package ("'app' is not a package"). Guarded by a test |
| 2026-10-08 | pre-commit runs ruff before every commit | Keeps messy code out of git history automatically |
| 2026-10-08 | Work step by step, with a check-in after each step | Learning project: understand every step |
| 2026-10-08 | uv for everything | Fast, lockfile, no manual venvs |
