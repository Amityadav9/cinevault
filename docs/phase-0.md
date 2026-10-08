# Phase 0: Setup

**Result:** a uv-managed Python project, typed config, and Postgres 18 + pgvector running in Docker,
reachable from Python (WSL) and pgAdmin (Windows).

## What was built
| File | Purpose |
|---|---|
| `pyproject.toml`, `uv.lock` | Dependencies (declared) and exact resolved versions (locked) |
| `.env.example` → `.env` | Config template (committed) → real values (git-ignored) |
| `app/core/config.py` | `Settings` (pydantic-settings) builds `database_url` |
| `app/db/session.py` | SQLAlchemy engine + `SessionLocal` + connection check |
| `docker-compose.yml` | `db` service: `pgvector/pgvector:pg18`, port 5435, named volume, healthcheck, auto-restart |
| `tests/test_config.py` | First test: URL built with the psycopg 3 driver |

## Concepts
- **uv:** `uv add pkg` updates `pyproject.toml` and `uv.lock`, and `uv run cmd` syncs `.venv` and runs inside it.
  The lockfile makes installs reproducible on any machine, including Docker in phase 6.
- **12-factor config:** code reads settings from the environment, so secrets live in `.env`, never in git.
  `Settings` validates types at startup: `POSTGRES_PORT=abc` fails immediately, not halfway through a run.
  `@lru_cache` on `get_settings()` means `.env` is parsed once.
- **SQLAlchemy URL** `postgresql+psycopg://…`: the `+psycopg` part picks the psycopg **3** driver
  (psycopg2 is the old one). We'll use psycopg 3's fast `COPY` support in phase 1.
- **Engine vs. Session:** the engine is a connection *pool* (one per app). A session is one unit of work (one per
  request or task). `pool_pre_ping=True` checks that a connection still works before using it, which helps after the DB restarts.
- **Docker volume:** the container is disposable but the `pgdata` volume isn't. `docker compose down` keeps
  data, while `docker compose down -v` deletes it. PG 18 images store data in `/var/lib/postgresql/18/docker`,
  so we mount `/var/lib/postgresql`.
- **Port mapping** `5435:5432` means host port : container port. Inside the container it's always 5432.
- **Healthcheck + `restart: unless-stopped`:** `pg_isready` reports when the DB really accepts connections, and
  the restart policy brings it back after Docker Desktop or Windows restarts.

## Troubleshooting we hit
| Symptom | Cause | Fix |
|---|---|---|
| `docker: ... /var/run/docker.sock: no such file` in WSL | Docker Desktop's WSL *integration* was off for Ubuntu (the "WSL 2 engine" setting is a separate switch) | Settings → Resources → WSL Integration → Ubuntu |
| pgAdmin: `failed to resolve host 'cinevault'` | DB name put in the **Host** field | Host = `localhost` |
| pgAdmin: `connection timeout expired` | Container had stopped (Docker Desktop restart) | `docker compose up -d db`; now auto-restarts |
| uv warns `VIRTUAL_ENV=…miniconda3 … ignored` | conda base auto-activates | Harmless; `conda config --set auto_activate_base false` |

## Useful commands
```bash
docker compose up -d db          # start DB
docker compose ps                # status + health
docker compose logs -f db        # follow logs
uv run python -m app.db.session  # prints Postgres version if connection works
uv run pytest -q                 # tests
uv run ruff check . && uv run ruff format .
```

## Try next
- In pgAdmin: Query Tool → `SELECT version();` and `SELECT * FROM pg_available_extensions WHERE name IN ('vector','pg_trgm');`
- Change `POSTGRES_PORT` in `.env` to a bad value like `abc` and run the session module to see validation fail.
