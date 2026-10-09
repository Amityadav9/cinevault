"""🎬 Watchlist: poster grid + filters (sidebar).

Streamlit re-runs this whole script on every interaction; widget values are the "state".
"""

import streamlit as st

from app.services.watchlist import WatchlistError
from ui.data import (
    Card,
    load_cards,
    load_genres,
    load_moods,
    mark_watched,
    remove_movie,
    set_priority,
    set_status,
)

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
        if c.tagline:
            st.caption(f"_“{c.tagline}”_")
        st.caption(_meta_line(c))
        st.caption(", ".join(c.genres))
        if c.cast:
            st.caption("🎭 " + ", ".join(name for name, _ in c.cast[:3]))
        if c.status != "to_watch":
            mine = f" · mine {c.my_rating}" if c.my_rating is not None else ""
            st.caption(f"✔ {c.status}{mine}")
        if c.notes:
            st.caption(f"📝 _{c.notes}_")
        label = "▶ Trailer & details" if c.trailer_url else "ℹ️ Details"
        if st.button(label, key=f"details-{c.tconst}", width="stretch"):
            show_details(c)
        render_actions(c)


# --- Card actions ---------------------------------------------------------------------------
# on_click / on_change callbacks run BEFORE the next re-run, so the re-run already shows the
# new state (no st.rerun() needed). Callbacks read widget values from st.session_state.

NO_RATING = "–"
RATINGS = [NO_RATING, *[x / 2 for x in range(0, 21)]]  # –, 0.0, 0.5 … 10.0


def _do(action, *args, done: str) -> None:
    try:
        action(*args)
    except WatchlistError as e:
        st.toast(f"⚠️ {e}")
    else:
        st.toast(done)


def _on_watched(c: Card) -> None:
    rating = st.session_state[f"rate-{c.tconst}"]
    stars = f" · you: {rating}" if rating != NO_RATING else ""
    _do(mark_watched, c.tconst, None if rating == NO_RATING else float(rating),
        done=f"✓ Watched {c.title}{stars}")  # fmt: skip


def _on_priority(c: Card) -> None:
    new = st.session_state[f"prio-{c.tconst}"]
    if new and new != c.priority:  # segmented control can be de-selected → None
        _do(set_priority, c.tconst, new, done=f"{c.title}: priority {new}")


def render_actions(c: Card) -> None:
    with st.popover("⚙️ Manage", width="stretch"):
        if c.status == "to_watch":
            st.segmented_control(
                "Priority (1 = watch first)", [1, 2, 3, 4, 5], default=c.priority,
                key=f"prio-{c.tconst}", on_change=_on_priority, args=(c,),
            )  # fmt: skip
            st.select_slider("Your rating", RATINGS, value=NO_RATING, key=f"rate-{c.tconst}")
            st.button("✓ Mark watched", key=f"watched-{c.tconst}", type="primary",
                      width="stretch", on_click=_on_watched, args=(c,))  # fmt: skip
            st.button("🚫 Drop (not interested)", key=f"drop-{c.tconst}", width="stretch",
                      on_click=_do, args=(set_status, c.tconst, "dropped"),
                      kwargs={"done": f"🚫 Dropped {c.title}"})  # fmt: skip
        else:
            st.button("↩ Back to 'to watch'", key=f"undo-{c.tconst}", width="stretch",
                      on_click=_do, args=(set_status, c.tconst, "to_watch"),
                      kwargs={"done": f"↩ {c.title} is back on your to-watch list"})  # fmt: skip
        st.divider()
        sure = st.checkbox("Yes, remove it for good", key=f"sure-{c.tconst}")
        st.button("🗑 Remove", key=f"remove-{c.tconst}", width="stretch", disabled=not sure,
                  on_click=_do, args=(remove_movie, c.tconst),
                  kwargs={"done": f"🗑 Removed {c.title}"})  # fmt: skip


def _meta_line(c: Card) -> str:
    bits = [
        f"★ {c.imdb_rating}" if c.imdb_rating else None,
        f"{c.runtime_min} min" if c.runtime_min else None,
        f"P{c.priority}",
        "🔞" if c.is_adult else None,
    ]
    return " · ".join(b for b in bits if b)


# A modal window over the grid. Streamlit shows it when the decorated function is called
# (here: when a card's button was clicked in this re-run); closing it re-runs the page.
@st.dialog("Movie details", width="large")
def show_details(c: Card) -> None:
    st.subheader(f"{c.title} ({c.year or '?'})")
    if c.tagline:
        st.markdown(f"_“{c.tagline}”_")
    left, right = st.columns([3, 2])
    with left:
        if c.trailer_url:
            st.video(c.trailer_url)  # YouTube embed, plays right here
        elif c.poster:
            st.image(c.poster, width=260)
        else:
            st.caption("No poster on TMDB.")
        if not c.trailer_url:
            st.caption("TMDB has no trailer for this movie.")
            st.link_button("🔎 Search trailer on YouTube", c.trailer_search_url)
    with right:
        votes = f" ({c.num_votes:,} votes)" if c.num_votes else ""
        st.markdown(f"**★ {c.imdb_rating or '–'}**{votes}")
        st.caption(_meta_line(c) + " · " + ", ".join(c.genres))
        if c.director:
            st.markdown(f"**Director:** {c.director}")
        if c.cast:
            st.markdown("**Cast**")
            st.markdown("\n".join(f"- {name} _as {role}_" if role else f"- {name}"
                                  for name, role in c.cast))  # fmt: skip
    if c.overview:
        st.markdown("**Plot**")
        st.write(c.overview)
    if c.notes:
        st.caption(f"📝 {c.notes}")
    links = f"[IMDb ↗]({c.imdb_url})"
    if c.trailer_url:
        links += f" · [Trailer on YouTube ↗]({c.trailer_url})"
    else:
        links += f" · [🔎 Search trailer ↗]({c.trailer_search_url})"
    st.caption(links)


for start in range(0, len(cards), columns):
    row = st.columns(columns)
    for col, card in zip(row, cards[start : start + columns], strict=False):
        with col:
            render_card(card)
