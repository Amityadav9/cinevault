"""Data access for the Streamlit pages: services → plain, display-ready objects.

Pages never touch SQLAlchemy objects directly; they get frozen dataclasses. That keeps
pages simple and lets st.cache_data cache results (it needs picklable values).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import streamlit as st
from sqlalchemy import select

from app.db.models import TmdbCache, WatchlistItem
from app.db.session import SessionLocal
from app.services import catalog, tmdb, watchlist
from app.services.matcher import Candidate, find_candidates
from app.services.parse_input import parse_input
from app.services.tmdb import poster_url, youtube_search_url, youtube_url


@dataclass(frozen=True)
class Card:
    tconst: str
    title: str
    year: int | None
    runtime_min: int | None
    is_adult: bool
    imdb_rating: Decimal | None
    num_votes: int | None
    genres: tuple[str, ...]
    status: str
    priority: int
    notes: str | None
    my_rating: Decimal | None
    added_at: datetime
    poster: str | None
    director: str | None
    overview: str | None
    tagline: str | None
    cast: tuple[tuple[str, str], ...]  # (actor, character), billing order
    trailer_url: str | None

    @property
    def imdb_url(self) -> str:
        return f"https://www.imdb.com/title/{self.tconst}/"

    @property
    def trailer_search_url(self) -> str:
        return youtube_search_url(self.title, self.year)


def load_cards(status: str | None) -> list[Card]:
    """Not cached: the watchlist changes (CLI, buttons) and the query takes milliseconds."""
    with SessionLocal() as session:
        items = watchlist.list_items(session, status)
        # one query for all TMDB rows instead of one per movie
        tmdb = {
            row.tconst: row
            for row in session.scalars(
                select(TmdbCache).where(TmdbCache.tconst.in_([i.tconst for i in items]))
            )
        }
        cards = []
        for it in items:
            m, d = it.movie, tmdb.get(it.tconst)
            cards.append(
                Card(
                    tconst=m.tconst,
                    title=m.title,
                    year=m.year,
                    runtime_min=m.runtime_min,
                    is_adult=m.is_adult,
                    imdb_rating=m.rating.avg_rating if m.rating else None,
                    num_votes=m.rating.num_votes if m.rating else None,
                    genres=tuple(sorted(g.name for g in m.genres)),
                    status=it.status,
                    priority=it.priority,
                    notes=it.notes,
                    my_rating=it.my_rating,
                    added_at=it.added_at,
                    poster=poster_url(d.poster_path) if d else None,
                    director=d.director if d else None,
                    overview=d.overview if d else None,
                    tagline=d.tagline if d else None,
                    cast=tuple((c["name"], c["character"]) for c in (d.cast or [])) if d else (),
                    trailer_url=youtube_url(d.trailer_key) if d else None,
                )
            )
        return cards


@st.cache_data(ttl=600)  # moods/genres barely change: cache for 10 minutes
def load_moods() -> list[catalog.MoodInfo]:
    with SessionLocal() as session:
        return catalog.list_moods(session)


@st.cache_data(ttl=600)
def load_genres() -> list[str]:
    with SessionLocal() as session:
        return catalog.list_genres(session)


# --- Add page -----------------------------------------------------------------------------


@st.cache_data(ttl=600, show_spinner=False)
def search(user_input: str) -> list[Candidate]:
    """Parse + match one pasted line. Cached: sliders/re-runs don't repeat the query.

    Raises UnparseableInput for junk; st.cache_data doesn't cache exceptions.
    """
    parsed = parse_input(user_input)
    with SessionLocal() as session:
        return find_candidates(session, parsed)


@dataclass(frozen=True)
class Preview:
    poster: str | None
    tagline: str | None
    overview: str | None
    director: str | None
    cast: tuple[str, ...]
    trailer_url: str | None
    error: str | None = None  # TMDB problem: shown as a hint, adding still works


@st.cache_data(ttl=3600, show_spinner=False)
def preview(tconst: str) -> Preview:
    """TMDB details for any movie (cached in tmdb_cache too: max 2 API calls per movie, ever)."""
    with SessionLocal() as session:
        try:
            client = tmdb.TmdbClient()
            try:
                d = tmdb.enrich(session, tconst, client)
            finally:
                client.close()
            session.commit()
        except tmdb.TmdbError as e:
            return Preview(None, None, None, None, (), None, error=str(e))
        return Preview(
            poster=poster_url(d.poster_path),
            tagline=d.tagline,
            overview=d.overview,
            director=d.director,
            cast=tuple(c["name"] for c in (d.cast or [])[:4]),
            trailer_url=youtube_url(d.trailer_key),
        )


def watchlist_status(tconst: str) -> str | None:
    """'to_watch' / 'watched' / 'dropped' if already on the list, else None. Not cached."""
    with SessionLocal() as session:
        item = session.scalars(select(WatchlistItem).where(WatchlistItem.tconst == tconst)).first()
        return item.status if item else None


def add_movie(tconst: str, priority: int, notes: str | None) -> None:
    """Raises watchlist.WatchlistError (e.g. AlreadyOnWatchlist) with a user-facing message."""
    with SessionLocal() as session:
        watchlist.add(session, tconst, priority=priority, notes=notes, source="streamlit")
        session.commit()


# --- Watchlist actions (card buttons) -------------------------------------------------------
# Each action = one short transaction. The item is looked up by IMDb id, and
# watchlist.find accepts "tt…" ids directly.


def mark_watched(tconst: str, my_rating: float | None) -> None:
    with SessionLocal() as session:
        watchlist.mark_watched(session, watchlist.find(session, tconst), my_rating)
        session.commit()


def set_status(tconst: str, status: str) -> None:
    with SessionLocal() as session:
        watchlist.set_status(session, watchlist.find(session, tconst), status)
        session.commit()


def set_priority(tconst: str, priority: int) -> None:
    with SessionLocal() as session:
        watchlist.set_priority(session, watchlist.find(session, tconst), priority)
        session.commit()


def remove_movie(tconst: str) -> None:
    with SessionLocal() as session:
        watchlist.remove(session, watchlist.find(session, tconst))
        session.commit()
