"""Database tables as SQLAlchemy 2.0 ORM classes.

`Mapped[X]` = NOT NULL column, `Mapped[X | None]` = nullable column.
Alembic autogenerate reads these classes to write migrations.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Predictable constraint/index names (instead of DB-generated ones) make migrations reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# --- IMDb reference data (filled by the ETL loader) -------------------------------------


class Movie(Base):
    __tablename__ = "movies"

    tconst: Mapped[str] = mapped_column(String(12), primary_key=True)  # IMDb id, e.g. tt0111161
    title: Mapped[str] = mapped_column(Text)
    original_title: Mapped[str | None] = mapped_column(Text)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    runtime_min: Mapped[int | None] = mapped_column(Integer)
    is_adult: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Lowercase, accent-free copy of title ("Amélie" → "amelie"), computed by Postgres itself.
    # f_unaccent is an IMMUTABLE wrapper around unaccent() (see migration 0003).
    title_search: Mapped[str | None] = mapped_column(
        Text, Computed("lower(f_unaccent(title))", persisted=True)
    )

    rating: Mapped["Rating | None"] = relationship(back_populates="movie")
    genres: Mapped[list["Genre"]] = relationship(secondary="movie_genres", back_populates="movies")

    __table_args__ = (
        # Trigram GIN index: fast fuzzy search, e.g. WHERE title_search % 'intersteller'.
        # Needs the pg_trgm extension (created in migration 0001).
        Index(
            "ix_movies_title_search_trgm",
            "title_search",
            postgresql_using="gin",
            postgresql_ops={"title_search": "gin_trgm_ops"},
        ),
        Index("ix_movies_year", "year"),
    )


class Rating(Base):
    __tablename__ = "ratings"

    tconst: Mapped[str] = mapped_column(
        ForeignKey("movies.tconst", ondelete="CASCADE"), primary_key=True
    )
    avg_rating: Mapped[Decimal] = mapped_column(Numeric(3, 1))  # 0.0 – 10.0
    num_votes: Mapped[int] = mapped_column(Integer)

    movie: Mapped[Movie] = relationship(back_populates="rating")

    # "Popular movies only" (num_votes >= N) is a filter in nearly every browse view.
    __table_args__ = (Index("ix_ratings_num_votes", "num_votes"),)


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)

    movies: Mapped[list[Movie]] = relationship(secondary="movie_genres", back_populates="genres")


class MovieGenre(Base):
    """Many-to-many link: one movie has 0-3 genres, one genre has many movies."""

    __tablename__ = "movie_genres"

    tconst: Mapped[str] = mapped_column(
        ForeignKey("movies.tconst", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )

    # The composite PK (tconst, genre_id) already serves "genres of movie X";
    # this index serves the reverse: "movies of genre Y".
    __table_args__ = (Index("ix_movie_genres_genre_id", "genre_id"),)


# --- Moods: user-editable mapping mood -> genres -----------------------------------------


class Mood(Base):
    __tablename__ = "moods"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str | None] = mapped_column(Text)

    genres: Mapped[list[Genre]] = relationship(secondary="mood_genres")


class MoodGenre(Base):
    __tablename__ = "mood_genres"

    mood_id: Mapped[int] = mapped_column(
        ForeignKey("moods.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )


# --- The user's own data -----------------------------------------------------------------

WATCH_STATUSES = ("to_watch", "watched", "dropped")


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tconst: Mapped[str] = mapped_column(ForeignKey("movies.tconst"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="to_watch", server_default="to_watch")
    priority: Mapped[int] = mapped_column(SmallInteger, default=3, server_default="3")  # 1 = top
    source: Mapped[str | None] = mapped_column(String(20))  # 'tabs' | 'manual' | 'chat'
    notes: Mapped[str | None] = mapped_column(Text)
    my_rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    watched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    movie: Mapped[Movie] = relationship()

    # CHECK constraints instead of a Postgres ENUM type: same safety, but adding a new
    # status later is a one-line migration (ENUMs are awkward to alter).
    __table_args__ = (
        CheckConstraint(f"status IN {WATCH_STATUSES}", name="status_valid"),
        CheckConstraint("priority BETWEEN 1 AND 5", name="priority_range"),
        CheckConstraint("my_rating BETWEEN 0 AND 10", name="my_rating_range"),
    )


class TmdbCache(Base):
    """TMDB details fetched once per movie (posters, plot, cast), so we don't re-call the API."""

    __tablename__ = "tmdb_cache"

    tconst: Mapped[str] = mapped_column(
        ForeignKey("movies.tconst", ondelete="CASCADE"), primary_key=True
    )
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    poster_path: Mapped[str | None] = mapped_column(Text)
    overview: Mapped[str | None] = mapped_column(Text)
    tagline: Mapped[str | None] = mapped_column(Text)
    director: Mapped[str | None] = mapped_column(Text)  # "A, B" if several
    cast: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
