"""Turn whatever the user pastes (a URL or a typed title) into something we can match.

    https://www.imdb.com/title/tt0816692/            → imdb_id="tt0816692"            (exact)
    https://www.google.com/search?q=interstellar+movie → query="interstellar"
    https://letterboxd.com/film/dune-part-two/        → query="dune part two"
    Interstellar (2014)                               → query="Interstellar", year=2014

Pure functions, no database: easy to test, and reused by the CLI, Streamlit and the API.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse

IMDB_ID_RE = re.compile(r"\btt\d{7,9}\b")
# A plausible release year: 1888 (first film) … 2039. "2049" (Blade Runner) is not a year here.
YEAR_RE = re.compile(r"^\(?(18(?:8[89]|9\d)|19\d\d|20[0-3]\d)\)?$")
LOOKS_LIKE_URL_RE = re.compile(r"^(https?://|www\.)|^[\w-]+(\.[\w-]+)+/", re.IGNORECASE)

# Search-engine query parameters: google/bing/ddg "q", youtube "search_query", yahoo "p", …
QUERY_PARAMS = ("q", "query", "search_query", "p", "text", "term", "s", "k")
# Path segments that are never the title itself.
GENERIC_SEGMENTS = {"film", "films", "movie", "movies", "m", "title", "wiki", "search", "watch"}
# Words people add around a title when searching, stripped only from the *ends*.
# Separate lists: "Full Metal Jacket" starts with "full", but "… full movie" ends with it.
LEADING_NOISE = {
    "watch", "imdb", "official", "wikipedia", "letterboxd", "netflix", "stream", "streaming",
    "free", "download",
}  # fmt: skip
TRAILING_NOISE = LEADING_NOISE | {
    "movie", "movies", "film", "films", "trailer", "online", "full", "hd", "review",
    "reviews", "cast", "rating", "ratings", "wiki", "english",
}  # fmt: skip
# Noise words that can also be part of a real title ("Bee Movie", "The Film Critic").
# query_full keeps them; query drops them.
AMBIGUOUS_NOISE = {"movie", "movies", "film", "films", "full"}
PUNCT_ONLY_RE = re.compile(r"^[\W_]+$")


@dataclass(frozen=True)
class ParsedInput:
    raw: str
    imdb_id: str | None = None  # exact IMDb id → no fuzzy matching needed
    query: str | None = None  # cleaned title text for fuzzy matching
    year: int | None = None  # helps pick the right one of several same-named films
    # The text *before* noise stripping, when different ("Bee Movie" vs query "Bee"):
    # the matcher tries both, because a noise word can be part of the real title.
    query_full: str | None = None


class UnparseableInput(ValueError):
    """Raised when no IMDb id or title text can be found."""


def parse_input(text: str) -> ParsedInput:
    raw = text.strip()
    if not raw:
        raise UnparseableInput("empty input")

    # 1. An IMDb id anywhere (imdb.com, m.imdb.com, Google redirect links, a bare "tt…").
    if m := IMDB_ID_RE.search(raw):
        return ParsedInput(raw=raw, imdb_id=m.group())

    # 2. A URL: use the search query, else the most title-like path segment.
    title_text = _text_from_url(raw) if LOOKS_LIKE_URL_RE.match(raw) else raw
    if not title_text:
        raise UnparseableInput(f"no title found in URL: {raw}")

    # 3. Clean: drop noise words at the ends, pull a trailing year.
    query, year, query_full = _clean(title_text)
    if not query:
        raise UnparseableInput(f"nothing left after cleaning: {raw}")
    return ParsedInput(
        raw=raw,
        query=query,
        year=year,
        query_full=query_full if query_full.lower() != query.lower() else None,
    )


def _text_from_url(url: str) -> str | None:
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    parts = urlparse(url)

    params = parse_qs(parts.query)
    for name in QUERY_PARAMS:
        if values := params.get(name):
            return values[0]

    # e.g. /film/dune-part-two/  /wiki/Interstellar_(film)  /movie/157336-interstellar
    segments = [unquote(s) for s in parts.path.split("/") if s]
    for seg in reversed(segments):
        seg = re.sub(r"^\d+-", "", seg)  # TMDB style "157336-interstellar"
        seg = re.sub(r"\.\w{2,5}$", "", seg)  # "interstellar.html"
        if seg.lower() not in GENERIC_SEGMENTS and not seg.isdigit():
            return re.sub(r"[-_+]", " ", seg)
    return None


def _clean(text: str) -> tuple[str, int | None, str]:
    """Return (query, year, query_full)."""
    # Separators → spaces, so "Interstellar (2014) - IMDb" and "the_dark_knight" tokenise well.
    text = re.sub(r"[|_+]|\s[-–—:]\s", " ", text)
    tokens = [t for t in text.split() if not PUNCT_ONLY_RE.match(t)]
    full_tokens = list(tokens)
    year_full = _strip(full_tokens, TRAILING_NOISE - AMBIGUOUS_NOISE)
    year = _strip(tokens, TRAILING_NOISE)
    return _join(tokens), year or year_full, _join(full_tokens)


def _strip(tokens: list[str], trailing_noise: set[str]) -> int | None:
    """Strip noise words and a trailing year from the ends (in place); return the year."""
    year = _pop_year(tokens)
    for _ in range(3):  # a few passes: "watch interstellar 2014 movie online"
        _strip_noise(tokens, trailing_noise)
        year = year or _pop_year(tokens)
    return year


def _pop_year(tokens: list[str]) -> int | None:
    # Trailing year, but never the *whole* title ("1917" is a film, not a year).
    if len(tokens) > 1 and (m := YEAR_RE.match(tokens[-1])):
        tokens.pop()
        return int(m.group(1))
    return None


def _strip_noise(tokens: list[str], trailing_noise: set[str]) -> None:
    def word(tok: str) -> str:
        return tok.strip("()[]").lower()

    while len(tokens) > 1 and word(tokens[-1]) in trailing_noise:
        tokens.pop()
    while len(tokens) > 1 and word(tokens[0]) in LEADING_NOISE:
        tokens.pop(0)


def _join(tokens: list[str]) -> str:
    return re.sub(r"[()\[\]]", "", " ".join(tokens)).strip(" -–—:,.")
