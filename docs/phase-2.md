# Phase 2: Add movies one by one

**Result:** paste one URL or title → see the best matches → confirm → it's on the watchlist,
with director, plot, cast and poster from TMDB. Everything is driven from the terminal.

## Daily use
```bash
uv run python -m app.cli add                       # paste loop: URL/title, Enter, … empty Enter = done
uv run python -m app.cli add "<url or title>"      # one movie. QUOTES are required (& in URLs!)
uv run python -m app.cli list                      # to watch;  list -s all | watched | dropped
uv run python -m app.cli show "highwaymen"         # plot, director, cast, poster link
uv run python -m app.cli watched "luck" -r 7       # mark watched with my rating
uv run python -m app.cli remove "luck"
uv run python -m app.cli search "the godfater"     # look only, don't add
uv run python -m app.cli enrich                    # TMDB details for entries that lack them
```

## Steps
| Step | What | Files |
|---|---|---|
| 1 | Input parser: IMDb id / search-engine URL / site URL / typed title → id or query + year | `app/services/parse_input.py` |
| 2 | Matcher: id lookup, or trigram similarity + popularity + year bonus | `app/services/matcher.py` |
| 2b | Accent/case-insensitive search (`unaccent`, generated `title_search`) | migration `0003` |
| 3 | Watchlist service + Typer/Rich CLI, rollback test fixture | `app/services/watchlist.py`, `app/cli.py`, `tests/conftest.py` |
| 4 | TMDB enrichment, cached (+ tagline, director) | `app/services/tmdb.py`, migration `0004` |
| 5 | CLI guards: paste loop (no quoting), DB/schema check before every command | `app/cli.py`, `app/db/session.py` |

## How a paste becomes a watchlist entry
```
"https://www.google.com/search?q=charlie+wilson%27s+war&sca_esv=…"
   │ parse_input   → query "charlie wilson's war", year None   (IMDb URL → exact id instead)
   │ matcher       → score = similarity(title_search, query) + 0.05·log10(votes+1) + year bonus
   │ CLI           → table of top 5 → you pick → priority, notes
   │ watchlist.add → INSERT (unique tconst: no duplicates) → COMMIT
   └ tmdb.enrich   → /find/{imdb_id} → /movie/{id}?append_to_response=credits → tmdb_cache → COMMIT
```

## Concepts
- **Pure functions first.** The parser has no DB or network, so its 35 tests run in about 0.07 s. Push I/O to the edges.
- **Parsing heuristics have edge cases; tests pin them down:** "1917" is a title, not a year. "Blade Runner 2049"
  keeps 2049. "Full Metal Jacket" keeps "Full" (noise words only count at the start or end, with separate lists for
  each). "Bee Movie" keeps a second variant (`query_full`) because "movie" can be part of a title.
- **Entity resolution = recall then rank.** The trigram index finds candidates (recall) and the score orders them
  (precision). Text alone ranks "Interstella" above "Interstellar", popularity fixes that, and the year picks between
  remakes (Dune 1984 vs 2021).
- **Generated columns + IMMUTABLE functions.** `title_search = lower(f_unaccent(title))` is computed by
  Postgres, so it can never drift from `title`. Indexes need immutable functions, hence the wrapper.
- **xfail tests** document a known bug. When the fix lands, the xfail becomes a real test.
- **Service layer + unit of work.** Services flush but never commit, so the caller owns the transaction: the CLI
  commits after you confirm, and tests roll back. The same services will serve Streamlit, FastAPI and the chatbot.
- **N+1 queries.** `selectinload` loads movies, ratings and genres for all rows in 3 queries, not 1 + 3·N.
- **Test isolation.** `tests/conftest.py` wraps each test in a transaction that is rolled back, and
  `join_transaction_mode="create_savepoint"` makes even `session.commit()` inside code safe.
- **HTTP integration done right.** One client with a Bearer token header. 401 gives a clear message, 429 waits for
  `Retry-After` and retries. Everything is cached, including "TMDB doesn't know this", and is optional (adding never fails
  because of TMDB). Tests use a fake server (`httpx.MockTransport`): no network, no quota.
- **Shell gotcha.** An unquoted `&` in a URL sends the command to the background, where it gets `Stopped` when it
  tries to read input. Fix: quote URLs, or paste into the prompt (the program reads it, bash never sees it).
- **Fail fast with a clear message.** The CLI checks DB reachability and `alembic current == head` before every
  command, instead of crashing mid-way with a traceback.

## Troubleshooting we hit
| Symptom | Cause | Fix |
|---|---|---|
| `[1]+ Stopped`, then `1: command not found` | unquoted `&` in URL → background job | quote the URL, or use the `add` paste loop |
| Stopped jobs keep DB connections "idle in transaction" | paused processes | `jobs`, `kill %1 %2` |
| TMDB sign-up: "There was a problem" | Application URL `http://localhost…` rejected | use GitHub profile URL |
| `UndefinedColumn tmdb_cache.tagline` traceback | code at 0004, DB at 0003 | `uv run alembic upgrade head` (CLI now says so itself) |
| `amelie` found "Amelia" first | accents | migration 0003 (`unaccent`) |
| pgAdmin `%` query showed odd rows | no `ORDER BY` → arbitrary order | `ORDER BY similarity(...) DESC` |

## Try next
- Add movies from your remaining tabs with the paste loop.
- `uv run pytest -v` and read the test names: they describe the behaviour.
- In pgAdmin: `SELECT * FROM tmdb_cache;` (look at the JSONB `cast` column) and
  `SELECT cast_member->>'name' FROM tmdb_cache, jsonb_array_elements("cast") AS cast_member;`
