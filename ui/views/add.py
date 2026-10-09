"""➕ Add: paste one or more URLs/titles (one per line), check each match, add it yourself.

Nothing is saved until you click a line's "Add" button.
"""

import hashlib

import streamlit as st

from app.services.parse_input import UnparseableInput
from app.services.watchlist import WatchlistError
from ui.data import add_movie, preview, search, watchlist_status

st.title("➕ Add movies")
st.caption(
    "Paste IMDb links, Google/Letterboxd/Wikipedia/any movie URL, or just type a title, "
    "**one per line**. Each line gets its own box; nothing is saved until you click **Add**."
)


def _clear() -> None:
    # on_click callbacks run *before* the next re-run, so changing a widget's value is allowed
    st.session_state.add_input = ""


text = st.text_area(
    "URLs or titles",
    key="add_input",
    height=140,
    placeholder="https://www.imdb.com/title/tt0816692/\nhttps://www.google.com/search?q=past+lives\n"
    "the godfater",
)
st.button("Clear", on_click=_clear)

# Message from the previous run ("✓ Added …") survives the st.rerun() via session_state.
if flash := st.session_state.pop("flash", None):
    st.success(flash)

lines = list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
if not lines:
    st.stop()


def _fmt_votes(n: int | None) -> str:
    if not n:
        return "no votes"
    return (
        f"{n / 1e6:.1f}M votes"
        if n >= 1e6
        else f"{n / 1e3:.0f}k votes"
        if n >= 1e3
        else f"{n} votes"
    )


for line in lines:
    key = hashlib.md5(line.encode()).hexdigest()[:10]  # stable widget keys per line
    with st.container(border=True):
        st.caption(f"`{line[:110]}{'…' if len(line) > 110 else ''}`")
        try:
            with st.spinner("Searching…"):
                candidates = search(line)
        except UnparseableInput as e:
            st.warning(f"Can't read this line: {e}")
            continue
        if not candidates:
            st.warning("No movie found (if it's an IMDb link, it may be a TV series).")
            continue

        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            idx = st.radio(
                "Which movie?",
                range(len(candidates)),
                key=f"pick-{key}",
                # c=candidates binds *this* line's list (a bare lambda would see the variable
                # as it is when called, i.e. possibly another line's candidates: ruff B023)
                format_func=lambda i, c=candidates: (
                    f"{c[i].title} ({c[i].year or '?'}) · "
                    f"★ {c[i].avg_rating or '–'} · {_fmt_votes(c[i].num_votes)}"
                ),
            )
            chosen = candidates[idx]

        with st.spinner("Loading details…"):
            p = preview(chosen.tconst)

        left, right = st.columns([1, 3])
        with left:
            if p.poster:
                st.image(p.poster, width="stretch")
            else:
                st.caption("🎞️ no poster")
        with right:
            st.markdown(f"### {chosen.title} ({chosen.year or '?'})")
            if p.tagline:
                st.caption(f"_“{p.tagline}”_")
            meta = [
                f"★ {chosen.avg_rating}" if chosen.avg_rating else None,
                f"{chosen.runtime_min} min" if chosen.runtime_min else None,
                ", ".join(chosen.genres) or None,
                "🔞" if chosen.is_adult else None,
            ]
            st.caption(" · ".join(m for m in meta if m))
            if p.director:
                st.caption(f"Director: {p.director}")
            if p.cast:
                st.caption("🎭 " + ", ".join(p.cast))
            if p.overview:
                st.write(p.overview)
            links = f"[IMDb ↗]({chosen.imdb_url})"
            if p.trailer_url:
                links += f" · [▶ Trailer ↗]({p.trailer_url})"
            st.caption(links)
            if p.error:
                st.caption(f"⚠️ No TMDB details: {p.error}")

            if status := watchlist_status(chosen.tconst):
                st.success(f"✓ On your watchlist ({status.replace('_', ' ')})")
                continue

            c1, c2, c3 = st.columns([2, 4, 1], vertical_alignment="bottom")
            priority = c1.select_slider(
                "Priority", options=[1, 2, 3, 4, 5], value=3, key=f"prio-{key}",
                help="1 = watch first … 5 = someday",
            )  # fmt: skip
            notes = c2.text_input("Notes", key=f"notes-{key}", placeholder="optional")
            if c3.button("Add", key=f"add-{key}", type="primary", width="stretch"):
                try:
                    add_movie(chosen.tconst, priority, notes or None)
                except WatchlistError as e:
                    st.warning(str(e))
                else:
                    st.session_state.flash = f"✓ Added {chosen.title} ({chosen.year or '?'})"
                    st.rerun()  # redraw: this box now shows "On your watchlist"
