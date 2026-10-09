"""Data access for the Streamlit pages: services → plain, display-ready objects.

Pages never touch SQLAlchemy objects directly; they get frozen dataclasses. That keeps
pages simple and lets st.cache_data cache results (it needs picklable values).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import streamlit as st
from sqlalchemy import select

from app.db.models import TmdbCache
from app.db.session import SessionLocal
from app.services import catalog, watchlist
from app.services.tmdb import poster_url, youtube_url


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
