"""accent-insensitive title search

Typing "amelie" should find "Amélie". We add a generated column
    title_search = lower(f_unaccent(title))
with its own trigram index, replacing the index on the raw title.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09 10:12:58.408183

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # unaccent() is only STABLE (its dictionary could change), and indexes / generated
    # columns require IMMUTABLE functions. Naming the dictionary explicitly makes the
    # result fixed, so this wrapper may be declared IMMUTABLE. The SQL-standard body
    # (RETURN …, PG 14+) lets the planner inline it.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        RETURN public.unaccent('public.unaccent'::regdictionary, $1)
        """
    )

    # STORED generated column: Postgres computes it on every insert/update by itself.
    # (Rewrites the table once: a few seconds for ~750k rows.)
    op.execute(
        "ALTER TABLE movies ADD COLUMN title_search text "
        "GENERATED ALWAYS AS (lower(f_unaccent(title))) STORED"
    )
    op.execute(
        "CREATE INDEX ix_movies_title_search_trgm ON movies USING gin (title_search gin_trgm_ops)"
    )
    # The old index on the raw title is now unused by the matcher; drop it so the
    # loader doesn't pay for maintaining two trigram indexes.
    op.drop_index("ix_movies_title_trgm", table_name="movies")


def downgrade() -> None:
    op.execute("CREATE INDEX ix_movies_title_trgm ON movies USING gin (title gin_trgm_ops)")
    op.drop_index("ix_movies_title_search_trgm", table_name="movies")
    op.drop_column("movies", "title_search")
    op.execute("DROP FUNCTION IF EXISTS f_unaccent(text)")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
