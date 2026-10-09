"""TMDB service tests against a *fake* TMDB (httpx.MockTransport): no network, no API quota."""

import httpx
import pytest

from app.services import tmdb

INTERSTELLAR = "tt0816692"  # TMDB knows it
GODFATHER = "tt0068646"  # our fake TMDB pretends not to

DETAILS = {
    "id": 157336,
    "poster_path": "/poster.jpg",
    "overview": "A team travels through a wormhole.",
    "tagline": "Mankind was born on Earth. It was never meant to die here.",
    "credits": {
        "cast": [  # deliberately out of billing order
            {"name": "Anne Hathaway", "character": "Brand", "order": 1},
            {"name": "Matthew McConaughey", "character": "Cooper", "order": 0},
        ],
        "crew": [
            {"name": "Christopher Nolan", "job": "Director"},
            {"name": "Christopher Nolan", "job": "Director"},  # TMDB sometimes repeats
            {"name": "Hans Zimmer", "job": "Original Music Composer"},
        ],
    },
}


class FakeTmdb:
    """Plays the TMDB server; records every request path."""

    def __init__(self, status: int = 200):
        self.status = status
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer test-token"
        if self.status != 200:
            return httpx.Response(self.status, json={"status_message": "nope"})
        if request.url.path == f"/3/find/{INTERSTELLAR}":
            assert request.url.params["external_source"] == "imdb_id"
            return httpx.Response(200, json={"movie_results": [{"id": 157336}]})
        if request.url.path.startswith("/3/find/"):
            return httpx.Response(200, json={"movie_results": []})
        if request.url.path == "/3/movie/157336":
            assert request.url.params["append_to_response"] == "credits"
            return httpx.Response(200, json=DETAILS)
        return httpx.Response(404)


def client_for(fake: FakeTmdb) -> tmdb.TmdbClient:
    return tmdb.TmdbClient(token="test-token", transport=httpx.MockTransport(fake))


def test_enrich_fetches_and_maps_fields(db):
    fake = FakeTmdb()
    row = tmdb.enrich(db, INTERSTELLAR, client_for(fake))
    assert row.tmdb_id == 157336
    assert row.poster_path == "/poster.jpg"
    assert row.tagline.startswith("Mankind")
    assert row.director == "Christopher Nolan"  # deduplicated
    assert [c["name"] for c in row.cast] == ["Matthew McConaughey", "Anne Hathaway"]  # by order
    assert fake.calls == [f"/3/find/{INTERSTELLAR}", "/3/movie/157336"]


def test_enrich_uses_cache_second_time(db):
    fake = FakeTmdb()
    client = client_for(fake)
    tmdb.enrich(db, INTERSTELLAR, client)
    tmdb.enrich(db, INTERSTELLAR, client)
    assert len(fake.calls) == 2  # not 4: the second call never left the database

    tmdb.enrich(db, INTERSTELLAR, client, force=True)
    assert len(fake.calls) == 4


def test_unknown_movie_is_remembered(db):
    fake = FakeTmdb()
    row = tmdb.enrich(db, GODFATHER, client_for(fake))
    assert row.tmdb_id is None and row.overview is None
    tmdb.enrich(db, GODFATHER, client_for(fake))
    assert fake.calls == [f"/3/find/{GODFATHER}"]  # asked once only


def test_bad_token_gives_clear_error(db):
    with pytest.raises(tmdb.TmdbError, match="401"):
        tmdb.enrich(db, INTERSTELLAR, client_for(FakeTmdb(status=401)))


def test_rate_limit_is_retried(monkeypatch):
    monkeypatch.setattr(tmdb.time, "sleep", lambda s: None)  # don't actually wait
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "1"}),  # 1st try: rate limited
            httpx.Response(200, json={"movie_results": []}),  # 2nd try: OK
        ]
    )
    client = tmdb.TmdbClient(
        token="t", transport=httpx.MockTransport(lambda request: next(responses))
    )
    assert client.find_movie_id(INTERSTELLAR) is None


def test_missing_token(monkeypatch):
    with pytest.raises(tmdb.TmdbError, match="TMDB_TOKEN"):
        tmdb.TmdbClient(token="")


def test_poster_url():
    assert tmdb.poster_url("/abc.jpg") == "https://image.tmdb.org/t/p/w342/abc.jpg"
    assert tmdb.poster_url("/abc.jpg", "w92").endswith("/w92/abc.jpg")
    assert tmdb.poster_url(None) is None
