"""Watchlist service tests. The `db` fixture rolls everything back afterwards."""

import pytest

from app.services import watchlist

INTERSTELLAR = "tt0816692"
GODFATHER = "tt0068646"
LEGO = "tt1490017"


def test_add_and_list(db):
    item = watchlist.add(db, INTERSTELLAR, priority=1, notes="IMAX")
    assert item.id is not None
    assert (item.status, item.priority, item.notes, item.source) == (
        "to_watch",
        1,
        "IMAX",
        "manual",
    )
    assert item.movie.title == "Interstellar"
    assert item.added_at is not None  # server_default now()

    items = watchlist.list_items(db)
    assert [i.tconst for i in items if i.tconst == INTERSTELLAR] == [INTERSTELLAR]


def test_list_sorted_by_priority(db):
    watchlist.add(db, GODFATHER, priority=4)
    watchlist.add(db, INTERSTELLAR, priority=1)
    ours = [i.tconst for i in watchlist.list_items(db) if i.tconst in {GODFATHER, INTERSTELLAR}]
    assert ours == [INTERSTELLAR, GODFATHER]


def test_duplicate_is_rejected(db):
    watchlist.add(db, INTERSTELLAR)
    with pytest.raises(watchlist.AlreadyOnWatchlist, match="already on your watchlist"):
        watchlist.add(db, INTERSTELLAR)


@pytest.mark.parametrize(
    ("tconst", "priority", "error"),
    [
        ("tt0903747", 3, watchlist.MovieNotFound),  # Breaking Bad: TV, not in movies
        (INTERSTELLAR, 0, watchlist.WatchlistError),
        (INTERSTELLAR, 6, watchlist.WatchlistError),
    ],
)
def test_add_validation(db, tconst, priority, error):
    with pytest.raises(error):
        watchlist.add(db, tconst, priority=priority)


@pytest.mark.parametrize(
    "user_input",
    ["interstellar", "INTERSTELER", "https://www.imdb.com/title/tt0816692/", "stellar"],
)
def test_find_on_watchlist(db, user_input):
    watchlist.add(db, INTERSTELLAR)
    watchlist.add(db, GODFATHER)
    assert watchlist.find(db, user_input).tconst == INTERSTELLAR


def test_find_contains_match(db):
    watchlist.add(db, LEGO)
    assert watchlist.find(db, "lego").tconst == LEGO  # "contains", not just fuzzy


def test_find_only_searches_watchlist(db):
    watchlist.add(db, GODFATHER)
    with pytest.raises(watchlist.NotOnWatchlist):
        watchlist.find(db, "interstellar")  # a real movie, but not on the list


def test_mark_watched_and_filter(db):
    item = watchlist.add(db, INTERSTELLAR)
    watchlist.mark_watched(db, item, 9.5)
    assert (item.status, float(item.my_rating)) == ("watched", 9.5)
    assert item.watched_at is not None
    assert INTERSTELLAR not in {i.tconst for i in watchlist.list_items(db, "to_watch")}
    assert INTERSTELLAR in {i.tconst for i in watchlist.list_items(db, "watched")}


def test_bad_rating_and_status(db):
    item = watchlist.add(db, INTERSTELLAR)
    with pytest.raises(watchlist.WatchlistError):
        watchlist.mark_watched(db, item, 11)
    with pytest.raises(watchlist.WatchlistError):
        watchlist.set_status(db, item, "maybe")


def test_remove(db):
    item = watchlist.add(db, INTERSTELLAR)
    watchlist.remove(db, item)
    with pytest.raises(watchlist.NotOnWatchlist):
        watchlist.find(db, "interstellar")


def test_commit_inside_code_is_still_rolled_back(db):
    # The CLI calls session.commit(); the fixture turns that into a SAVEPOINT release,
    # so even "committed" test data disappears after the test.
    watchlist.add(db, INTERSTELLAR)
    db.commit()
    assert watchlist.find(db, "interstellar").tconst == INTERSTELLAR
