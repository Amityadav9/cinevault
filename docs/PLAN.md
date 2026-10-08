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
- [ ] **Phase 1: Data and SQL** (IMDb ETL into Postgres, schema, queries, indexes): *next*
- [ ] **Phase 2: Import pipeline** (browser tabs + manual add → matched movies, TMDB enrichment)
- [ ] **Phase 3: Streamlit MVP** (import review, poster grid, stats)
- [ ] **Phase 4: FastAPI** (REST API, Streamlit switched to call it)
- [ ] **Phase 5: LLM chatbot** (Ollama/Groq, tool calling over the services)
- [ ] **Phase 6: Docker and production** (full compose stack, tests, CI)

## Architecture (end state)
```
Browser tabs export ─┐
Manual add ──────────┤
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
    importers/tabs.py     # parse exported tab URLs/titles → candidate titles
    api/                  # FastAPI routers: movies, watchlist, import, chat
    llm/                  # provider.py (Ollama/Groq), tools.py, agent.py
  ui/streamlit_app.py
  tests/
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

### Phase 2: Import pipeline (the core problem)
- Tab export: a "copy all tab URLs" browser extension, or a session file → txt/JSON.
- `importers/tabs.py`: pull out the IMDb ID straight from `imdb.com/title/tt…` URLs. For Google/other
  search URLs, take the `q=` param or the page title and strip noise ("movie", "imdb", "trailer", a year).
- `services/matcher.py`: an exact tconst match first. Otherwise fuzzy match (`pg_trgm` / `rapidfuzz`),
  boosted by year and by numVotes for popularity. Low-confidence matches go to a **review queue**.
- Manual add: the same matcher, applied to a single title.
- TMDB enrichment: `/find/{imdb_id}?external_source=imdb_id` → poster and overview, cached in the DB.
*Learn:* entity resolution, fuzzy matching, caching, rate limits.

### Phase 3: Streamlit MVP
At first it calls the services directly. Pages: **Import** (upload export → review matches → confirm),
**Watchlist** (poster grid, filters for genre/year/rating/status), **Stats** (genres, decades, ratings).
*Learn:* fast prototyping, how UI state works.

### Phase 4: FastAPI
`GET /movies/search`, `GET/POST/PATCH/DELETE /watchlist`, `POST /import/tabs`, `POST /import/manual`,
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
- Phase 2: import a real tab export → check the match rate and spot-check the review queue.
- Phase 3: `uv run streamlit run ui/streamlit_app.py` shows the poster grid and filters work.
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
- pgAdmin is installed on Windows. Connect to host `localhost`, port **5435**, user/password/db `cinevault`.

## Decisions log
| Date | Decision | Why |
|---|---|---|
| 2026-10-08 | Import from bulk tab export **and** manual add | Clear the backlog once, then keep adding |
| 2026-10-08 | IMDb TSV dumps + TMDB API | IMDb: free and complete, good for SQL practice. TMDB: posters, plots, cast |
| 2026-10-08 | Ollama locally, Groq as a switch | Private/free locally; Groq for speed. Learn the provider abstraction |
| 2026-10-08 | Postgres from day 1 (not SQLite) | pgAdmin already installed; one engine everywhere, pg_trgm + pgvector |
| 2026-10-08 | Postgres runs in Docker | Same service gets reused in Phase 6; nothing installed on the host |
| 2026-10-08 | `pgvector/pgvector:pg18` on port 5435 | Already pulled; PG 18 + vectors for phase 5; 5432-5434 used by other projects |
| 2026-10-08 | Genres normalized (`genres` + `movie_genres`) and `moods` → `mood_genres` seeded in phase 1 | Pick a movie by mood; good many-to-many SQL practice; moods are editable rows |
| 2026-10-08 | pre-commit runs ruff before every commit | Keeps messy code out of git history automatically |
| 2026-10-08 | Work step by step, with a check-in after each step | Learning project: understand every step |
| 2026-10-08 | uv for everything | Fast, lockfile, no manual venvs |
