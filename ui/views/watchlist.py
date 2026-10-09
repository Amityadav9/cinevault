"""🎬 Watchlist: poster grid + filters (sidebar).

Streamlit re-runs this whole script on every interaction; widget values are the "state".
"""

import streamlit as st

from ui.data import Card, load_cards, load_genres, load_moods

STATUS_OPTIONS = {"To watch": "to_watch", "Watched": "watched", "Dropped": "dropped", "All": None}
SORTS = {
    "Priority": lambda c: (c.priority, -c.added_at.timestamp()),
    "IMDb rating": lambda c: -(c.imdb_rating or 0),
    "Shortest first": lambda c: c.runtime_min or 10_000,
    "Recently added": lambda c: -c.added_at.timestamp(),
    "Year (newest)": lambda c: -(c.year or 0),
}

# --- Sidebar filters ----------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    status_label = st.radio("Status", list(STATUS_OPTIONS), horizontal=True)
    moods = {m.name: m for m in load_moods()}
    mood_name = st.selectbox(
        "Mood",
        ["Any", *moods],
        help="A movie fits a mood if it has at least one of the mood's genres.",
    )
    if mood_name != "Any":
        st.caption(f"{moods[mood_name].description} · {', '.join(moods[mood_name].genres)}")
    genres = st.multiselect("Genres (any of)", load_genres())
    max_runtime = st.slider("Max runtime (min)", 60, 240, 240, step=10)
    keep_unknown_runtime = st.checkbox("Include unknown runtime", value=True)
    min_rating = st.slider("Min IMDb rating", 0.0, 10.0, 0.0, step=0.5)
    sort_by = st.selectbox("Sort by", list(SORTS))
    columns = st.slider("Posters per row", 2, 8, 5)


# --- Load + filter (plain Python: the list is small) --------------------------------------
def matches(c: Card) -> bool:
    if mood_name != "Any" and not set(c.genres) & set(moods[mood_name].genres):
        return False
    if genres and not set(c.genres) & set(genres):
        return False
    if c.runtime_min is None:
        if not keep_unknown_runtime:
            return False
    elif max_runtime < 240 and c.runtime_min > max_runtime:  # 240 = "no limit"
        return False
    return not (min_rating and (c.imdb_rating or 0) < min_rating)


all_cards = load_cards(STATUS_OPTIONS[status_label])
cards = sorted(filter(matches, all_cards), key=SORTS[sort_by])

# --- Header metrics -----------------------------------------------------------------------
st.title("🎬 CineVault")
hours = sum(c.runtime_min or 0 for c in cards) / 60
m1, m2, m3 = st.columns(3)
m1.metric("Movies shown", len(cards), help=f"{len(all_cards)} before filters")
m2.metric("Watch time", f"{hours:.1f} h")
rated = [float(c.imdb_rating) for c in cards if c.imdb_rating]
m3.metric("Avg IMDb ★", f"{sum(rated) / len(rated):.1f}" if rated else "–")

if not cards:
    st.info("Nothing matches. Loosen the filters, or add movies (CLI: `app.cli add`).")
    st.stop()


# --- Poster grid --------------------------------------------------------------------------
def render_card(c: Card) -> None:
    with st.container(border=True):
        if c.poster:
            st.image(c.poster, width="stretch")
        else:
            st.markdown(
                f"<div style='aspect-ratio:2/3;display:flex;align-items:center;"
                f"justify-content:center;background:#8882;border-radius:6px;"
                f"text-align:center;padding:8px'>🎞️<br>{c.title}</div>",
                unsafe_allow_html=True,
            )
        st.markdown(f"**[{c.title}]({c.imdb_url})** ({c.year or '?'})")
        bits = [
            f"★ {c.imdb_rating}" if c.imdb_rating else None,
            f"{c.runtime_min} min" if c.runtime_min else None,
            f"P{c.priority}",
            "🔞" if c.is_adult else None,
        ]
        st.caption(" · ".join(b for b in bits if b))
        st.caption(", ".join(c.genres))
        if c.status != "to_watch":
            mine = f" · mine {c.my_rating}" if c.my_rating is not None else ""
            st.caption(f"✔ {c.status}{mine}")
        if c.notes:
            st.caption(f"📝 _{c.notes}_")
        if c.overview:
            with st.expander("Plot"):
                if c.director:
                    st.caption(f"Director: {c.director}")
                st.write(c.overview)


for start in range(0, len(cards), columns):
    row = st.columns(columns)
    for col, card in zip(row, cards[start : start + columns], strict=False):
        with col:
            render_card(card)
