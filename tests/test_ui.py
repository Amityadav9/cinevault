"""Streamlit smoke tests with AppTest: runs pages headless (no browser) and checks for errors.

They read the real watchlist (read-only), so assertions don't depend on its contents.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# AppTest resolves relative paths from *this test file*, so build absolute ones.
UI = Path(__file__).resolve().parents[1] / "ui"


@pytest.fixture
def watchlist_page(db_ready) -> AppTest:
    return AppTest.from_file(str(UI / "views/watchlist.py"), default_timeout=30).run()


def test_app_entry_runs(db_ready):
    at = AppTest.from_file(str(UI / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert not at.error  # schema/DB guard didn't fire


def test_watchlist_page_renders(watchlist_page):
    assert not watchlist_page.exception
    assert watchlist_page.title[0].value == "🎬 CineVault"
    assert [m.label for m in watchlist_page.metric] == ["Movies shown", "Watch time", "Avg IMDb ★"]


@pytest.mark.parametrize("mood", ["Feel-good", "Mind-bending", "Spooky night"])
def test_mood_filter_never_shows_more(watchlist_page, mood):
    before = int(watchlist_page.metric[0].value)
    watchlist_page.sidebar.selectbox[0].set_value(mood).run()
    assert not watchlist_page.exception
    shown = int(watchlist_page.metric[0].value) if watchlist_page.metric else 0
    assert shown <= before
