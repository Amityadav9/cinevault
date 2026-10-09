"""TMDB enrichment: posters, plot, tagline and top cast, fetched once per movie and cached.

    tt0816692 ──GET /find/{imdb_id}──► TMDB id 157336
              ──GET /movie/157336?append_to_response=credits──► details + cast (1 call)
              ──► tmdb_cache row (never fetched again unless force=True)

Docs: https://developer.themoviedb.org/reference/find-by-id
"""

import time
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import TmdbCache

BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"
TOP_CAST = 8


class TmdbError(Exception):
    """TMDB unreachable / misconfigured. Enrichment is optional, so callers just warn."""


def poster_url(poster_path: str | None, size: str = "w342") -> str | None:
    """Sizes: w92 w154 w185 w342 w500 w780 original."""
    return f"{IMAGE_BASE}/{size}{poster_path}" if poster_path else None


class TmdbClient:
    def __init__(self, token: str | None = None, transport: httpx.BaseTransport | None = None):
        token = token if token is not None else get_settings().tmdb_token.strip()
        if not token:
            raise TmdbError("TMDB_TOKEN is not set in .env")
        # transport= lets tests plug in a fake TMDB (httpx.MockTransport): no network needed.
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
            transport=transport,
        )

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        for attempt in range(3):
            try:
                resp = self._http.get(path, params=params)
            except httpx.HTTPError as e:
                raise TmdbError(f"TMDB request failed: {e}") from e
            if resp.status_code == 429 and attempt < 2:  # rate limited: wait as told, retry
                time.sleep(float(resp.headers.get("Retry-After", 1)))
                continue
            if resp.status_code == 401:
                raise TmdbError("TMDB rejected the token (401): check TMDB_TOKEN in .env")
            if resp.is_error:
                raise TmdbError(f"TMDB error {resp.status_code} for {path}")
            return resp.json()
        raise TmdbError("TMDB rate limit: still 429 after retries")

    def find_movie_id(self, imdb_id: str) -> int | None:
        data = self._get(f"/find/{imdb_id}", external_source="imdb_id")
        results = data.get("movie_results") or []
        return results[0]["id"] if results else None

    def movie_details(self, tmdb_id: int) -> dict[str, Any]:
        return self._get(f"/movie/{tmdb_id}", append_to_response="credits")

    def close(self) -> None:
        self._http.close()


def enrich(session: Session, tconst: str, client: TmdbClient, *, force: bool = False) -> TmdbCache:
    """Return cached TMDB details for a movie, fetching them first if needed.

    A movie TMDB doesn't know still gets a row (tmdb_id NULL), so we don't ask again.
    Like the watchlist service: flushes, never commits.
    """
    cached = session.get(TmdbCache, tconst)
    if cached is not None and not force:
        return cached

    row = cached or TmdbCache(tconst=tconst)
    tmdb_id = client.find_movie_id(tconst)
    row.tmdb_id = tmdb_id
    row.poster_path = row.overview = row.tagline = row.director = row.cast = None
    if tmdb_id is not None:
        d = client.movie_details(tmdb_id)
        credits = d.get("credits", {})
        row.poster_path = d.get("poster_path")
        row.overview = d.get("overview") or None
        row.tagline = d.get("tagline") or None
        directors = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
        row.director = ", ".join(dict.fromkeys(directors)) or None  # dedupe, keep order
        row.cast = [
            {"name": c["name"], "character": c.get("character") or ""}
            for c in sorted(credits.get("cast", []), key=lambda c: c.get("order", 99))
        ][:TOP_CAST]
    row.fetched_at = datetime.now(UTC)
    session.add(row)
    session.flush()
    return row
