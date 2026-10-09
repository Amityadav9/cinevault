# 🎬 CineVault

A personal movie watchlist, built as a step-by-step learning project. It turned dozens of open
browser tabs into a searchable list with posters, trailers, cast and moods.

Paste an IMDb link, a Google search URL or just a (misspelled) title → CineVault finds the movie in
~750k IMDb titles, shows poster, plot, cast and trailer, and you confirm before it's saved.

## Features
- **Smart matching**: IMDb/Google/Letterboxd/Wikipedia URLs or typed titles. Fuzzy search
  (`pg_trgm`) + popularity + year, accent-insensitive ("amelie" → *Amélie*)
- **Streamlit app**: poster grid with filters (mood, genre, runtime, rating), trailer & details
  dialog, card actions (priority, watched + your rating, drop, remove), Add page, Stats page
- **CLI**: `add`, `search`, `list`, `show`, `watched`, `remove`, `enrich`
- **Moods**: "Feel-good", "Mind-bending", "Edge of my seat"… mapped to genres, editable in the DB

## Stack
Python 3.13 · uv · PostgreSQL 18 + pgvector (Docker) · SQLAlchemy 2 · Alembic · Streamlit · Typer + Rich ·
httpx · pytest. Planned: FastAPI, an Agno agent (Groq / Ollama) with RAG + memory, full Docker setup.

## Quick start
```bash
cp .env.example .env              # add your TMDB "API Read Access Token"
docker compose up -d db           # Postgres on 127.0.0.1:5435
uv sync                           # install dependencies
uv run alembic upgrade head       # create the schema
uv run python -m app.etl.download     # IMDb datasets (~240 MB) → data/raw/
uv run python -m app.etl.imdb_loader  # load ~750k movies (~30 s)
uv run streamlit run ui/main.py   # → http://localhost:8501
```
CLI: `uv run python -m app.cli --help` · Tests: `uv run pytest`

## Project docs
The full plan, decisions log and a learning write-up per phase live in [`docs/`](docs/PLAN.md).

## Data sources
- **IMDb**: [non-commercial datasets](https://developer.imdb.com/non-commercial-datasets/),
  for personal and non-commercial use only. This repository contains the download script, not the data.
- **TMDB**: posters, plots, cast and trailers via the [TMDB API](https://www.themoviedb.org/).


  *This product uses the TMDB API but is not endorsed or certified by TMDB.*
