"""Reference data: moods and genres. Read-only, shared by UI, API and chatbot."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Genre, Mood


@dataclass(frozen=True)
class MoodInfo:
    name: str
    description: str | None
    genres: tuple[str, ...]


def list_moods(session: Session) -> list[MoodInfo]:
    moods = session.scalars(select(Mood).options(selectinload(Mood.genres)).order_by(Mood.name))
    return [MoodInfo(m.name, m.description, tuple(sorted(g.name for g in m.genres))) for m in moods]


def list_genres(session: Session) -> list[str]:
    return list(session.scalars(select(Genre.name).order_by(Genre.name)))
