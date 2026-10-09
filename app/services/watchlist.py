"""Watchlist business logic, shared by the CLI now and Streamlit / FastAPI / the chatbot later.

Functions take a Session and change data, but never commit: the *caller* owns the
transaction ("unit of work"). The CLI commits after the user confirms; tests roll back.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import WATCH_STATUSES, Movie, WatchlistItem
from app.services.parse_input import parse_input


class WatchlistError(Exception):
    """Base class: a user-facing problem, safe to show as a message."""


class MovieNotFound(WatchlistError):
    pass


class AlreadyOnWatchlist(WatchlistError):
    def __init__(self, item: WatchlistItem):
        super().__init__(f"'{item.movie.title}' is already on your watchlist ({item.status})")
        self.item = item


class NotOnWatchlist(WatchlistError):
    pass


# Eager-load what every view shows. selectinload = one extra query per relationship for
# *all* rows, instead of one query per row (the "N+1 problem").
_WITH_DETAILS = (
    selectinload(WatchlistItem.movie).selectinload(Movie.rating),
    selectinload(WatchlistItem.movie).selectinload(Movie.genres),
)


def add(
    session: Session,
    tconst: str,
    *,
    priority: int = 3,
    notes: str | None = None,
    source: str = "manual",
) -> WatchlistItem:
    if not 1 <= priority <= 5:
        raise WatchlistError("priority must be between 1 (top) and 5")
    if session.get(Movie, tconst) is None:
        raise MovieNotFound(f"{tconst} is not in the movie database")
    if existing := _by_tconst(session, tconst):
        raise AlreadyOnWatchlist(existing)

    item = WatchlistItem(tconst=tconst, priority=priority, notes=notes or None, source=source)
    session.add(item)
    session.flush()  # send the INSERT now: assigns item.id, surfaces DB errors early
    return _by_tconst(session, tconst)  # reload with movie details


def list_items(session: Session, status: str | None = "to_watch") -> list[WatchlistItem]:
    """status=None → everything. Sorted: top priority first, then newest."""
    stmt = select(WatchlistItem).options(*_WITH_DETAILS)
    if status:
        stmt = stmt.where(WatchlistItem.status == status)
    stmt = stmt.order_by(WatchlistItem.priority, WatchlistItem.added_at.desc())
    return list(session.scalars(stmt))


def find(session: Session, user_input: str) -> WatchlistItem:
    """Find an entry on *your watchlist* by IMDb URL/id or (fuzzy) title."""
    parsed = parse_input(user_input)
    if parsed.imdb_id:
        item = _by_tconst(session, parsed.imdb_id)
    else:
        q = func.lower(func.f_unaccent(parsed.query))
        stmt = (
            select(WatchlistItem)
            .join(WatchlistItem.movie)
            .options(*_WITH_DETAILS)
            # fuzzy (%) or plain "contains": "lego" should find "The Lego Movie"
            .where(or_(Movie.title_search.op("%")(q), Movie.title_search.contains(q)))
            .order_by(func.similarity(Movie.title_search, q).desc())
            .limit(1)
        )
        item = session.scalars(stmt).first()
    if item is None:
        raise NotOnWatchlist(f"nothing on your watchlist matches '{user_input}'")
    return item


def mark_watched(
    session: Session, item: WatchlistItem, my_rating: float | None = None
) -> WatchlistItem:
    if my_rating is not None and not 0 <= my_rating <= 10:
        raise WatchlistError("rating must be between 0 and 10")
    item.status = "watched"
    item.watched_at = datetime.now(UTC)
    if my_rating is not None:
        item.my_rating = Decimal(str(my_rating))
    session.flush()
    return item


def set_status(session: Session, item: WatchlistItem, status: str) -> WatchlistItem:
    if status not in WATCH_STATUSES:
        raise WatchlistError(f"status must be one of {', '.join(WATCH_STATUSES)}")
    item.status = status
    if status != "watched":
        item.watched_at = None  # "back to to-watch" must not keep a watched date
    session.flush()
    return item


def set_priority(session: Session, item: WatchlistItem, priority: int) -> WatchlistItem:
    if not 1 <= priority <= 5:
        raise WatchlistError("priority must be between 1 (top) and 5")
    item.priority = priority
    session.flush()
    return item


def remove(session: Session, item: WatchlistItem) -> None:
    session.delete(item)
    session.flush()


def _by_tconst(session: Session, tconst: str) -> WatchlistItem | None:
    stmt = select(WatchlistItem).options(*_WITH_DETAILS).where(WatchlistItem.tconst == tconst)
    return session.scalars(stmt).first()
