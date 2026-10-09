import pytest

from app.services.parse_input import ParsedInput, UnparseableInput, parse_input


@pytest.mark.parametrize(
    ("text", "imdb_id"),
    [
        ("https://www.imdb.com/title/tt0816692/", "tt0816692"),
        ("https://m.imdb.com/title/tt0816692/?ref_=nv_sr_srsg_0", "tt0816692"),
        ("www.imdb.com/title/tt15239678/reviews", "tt15239678"),  # 8-digit id, no scheme
        ("https://www.google.com/url?q=https://www.imdb.com/title/tt0068646/", "tt0068646"),
        ("tt0111161", "tt0111161"),
    ],
)
def test_imdb_ids_are_exact(text, imdb_id):
    assert parse_input(text) == ParsedInput(raw=text, imdb_id=imdb_id)


@pytest.mark.parametrize(
    ("text", "query", "year"),
    [
        # search engines
        ("https://www.google.com/search?q=interstellar+movie", "interstellar", None),
        (
            "https://www.google.com/search?q=the+dark+knight+2008+imdb&sca_esv=1",
            "the dark knight",
            2008,
        ),
        ("https://www.bing.com/search?q=watch+dune+part+two+online", "dune part two", None),
        ("https://duckduckgo.com/?q=past+lives+(2023)+review", "past lives", 2023),
        (
            "https://www.youtube.com/results?search_query=oppenheimer+official+trailer",
            "oppenheimer",
            None,
        ),
        # movie sites: title from the URL path
        ("https://letterboxd.com/film/dune-part-two/", "dune part two", None),
        ("https://www.themoviedb.org/movie/157336-interstellar", "interstellar", None),
        ("https://en.wikipedia.org/wiki/Interstellar_(film)", "Interstellar", None),
        ("https://en.wikipedia.org/wiki/Dune_(2021_film)", "Dune", 2021),
        ("https://www.rottentomatoes.com/m/interstellar_2014", "interstellar", 2014),
        # typed titles
        ("Interstellar", "Interstellar", None),
        ("intersteller 2014", "intersteller", 2014),
        ("Interstellar (2014) - IMDb", "Interstellar", 2014),
        ("  The Godfather   ", "The Godfather", None),
        # titles that look like noise or years must survive
        ("1917", "1917", None),
        ("1917 2019", "1917", 2019),
        ("2001: A Space Odyssey", "2001: A Space Odyssey", None),
        ("Blade Runner 2049", "Blade Runner 2049", None),
        ("Full Metal Jacket", "Full Metal Jacket", None),  # "full" is only trailing noise
        ("Dune: Part Two", "Dune: Part Two", None),
    ],
)
def test_queries_and_years(text, query, year):
    parsed = parse_input(text)
    assert parsed.imdb_id is None
    assert (parsed.query, parsed.year) == (query, year)


@pytest.mark.parametrize(
    ("text", "query", "query_full", "year"),
    [
        # A noise word may belong to the title: keep both variants for the matcher.
        ("Bee Movie", "Bee", "Bee Movie", None),
        ("The Lego Movie 2014", "The Lego", "The Lego Movie", 2014),
        ("interstellar full movie", "interstellar", "interstellar full movie", None),
        # Unambiguous junk is dropped from both → no second variant.
        ("Interstellar (2014) - IMDb", "Interstellar", None, 2014),
        ("oppenheimer official trailer", "oppenheimer", None, None),
    ],
)
def test_query_full_variant(text, query, query_full, year):
    parsed = parse_input(text)
    assert (parsed.query, parsed.query_full, parsed.year) == (query, query_full, year)


@pytest.mark.parametrize(
    "text", ["", "   ", "https://www.google.com/", "https://letterboxd.com/film/"]
)
def test_unparseable(text):
    with pytest.raises(UnparseableInput):
        parse_input(text)
