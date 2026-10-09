"""📊 Stats: what's on the list, what fits tonight, and how your taste compares to IMDb.

Chart rules (dataviz skill): single-series charts in one validated accent hue (light/dark
steps), no legend (the title names the series), thin rounded bars, recessive grid,
hover tooltips everywhere, a table view under each chart.
"""

import altair as alt
import pandas as pd
import streamlit as st

from ui.data import Card, load_cards, load_moods

# Validated with the dataviz palette script: PASS on Streamlit's light (#ffffff) and
# dark (#0e1117) surfaces.
_dark = getattr(getattr(st.context, "theme", None), "type", None) == "dark"
ACCENT = "#3987e5" if _dark else "#2a78d6"
SURFACE = "#0e1117" if _dark else "#ffffff"
REFERENCE = "#8a8a85"  # neutral gray for the "you = IMDb" diagonal
GRID = "#88888833"

RUNTIME_BUCKETS = ["< 90 min", "90–120 min", "120–150 min", "150+ min", "unknown"]

st.title("📊 Stats")
cards = load_cards(None)
if not cards:
    st.info("Your watchlist is empty. Add some movies first.")
    st.stop()

to_watch = [c for c in cards if c.status == "to_watch"]
watched = [c for c in cards if c.status == "watched"]
active = [c for c in cards if c.status != "dropped"]


# --- KPI row ------------------------------------------------------------------------------
def _hours(cs: list[Card]) -> float:
    return sum(c.runtime_min or 0 for c in cs) / 60


rated = [c for c in watched if c.my_rating is not None and c.imdb_rating is not None]
k1, k2, k3, k4 = st.columns(4)
k1.metric("To watch", len(to_watch))
unknown = sum(1 for c in to_watch if c.runtime_min is None)
k2.metric(
    "Hours left",
    f"{_hours(to_watch):.1f} h",
    help=f"{unknown} movie(s) without a known runtime aren't counted" if unknown else None,
)
k3.metric("Watched", len(watched))
if rated:
    mine = sum(float(c.my_rating) for c in rated) / len(rated)
    imdb = sum(float(c.imdb_rating) for c in rated) / len(rated)
    k4.metric("Your avg rating", f"{mine:.1f}", f"{mine - imdb:+.1f} vs IMDb",
              help="Only movies you've rated; IMDb average over the same movies.")  # fmt: skip
else:
    k4.metric("Your avg rating", "–", help="Mark movies as watched with a rating to see this.")


# --- Chart helpers ------------------------------------------------------------------------
def _axis(title: str | None = None, **kw) -> alt.Axis:
    return alt.Axis(title=title, grid=True, gridColor=GRID, domain=False, **kw)


def _count_axis(df: pd.DataFrame) -> alt.Axis:
    """Whole-number ticks only: there is no half a movie (tickMinStep alone wasn't honoured)."""
    top = int(df["movies"].max()) if len(df) else 1
    step = max(1, top // 6)
    return _axis("movies", values=list(range(0, top + step, step)), format="d")


def hbar(df: pd.DataFrame, cat: str, title: str, tooltip_label: str) -> alt.Chart:
    """Ranked horizontal bars: longest on top."""
    return (
        alt.Chart(df, title=title)
        .mark_bar(color=ACCENT, cornerRadiusEnd=4, height={"band": 0.6})
        .encode(
            y=alt.Y(f"{cat}:N", sort="-x", title=None, axis=alt.Axis(domain=False, ticks=False)),
            x=alt.X("movies:Q", axis=_count_axis(df)),
            tooltip=[alt.Tooltip(f"{cat}:N", title=tooltip_label), "movies:Q", "hours:Q"],
        )
        .properties(height=max(140, 28 * len(df)))
    )


def vbar(df: pd.DataFrame, cat: str, order: list[str], title: str) -> alt.Chart:
    return (
        alt.Chart(df, title=title)
        .mark_bar(color=ACCENT, cornerRadiusEnd=4, width={"band": 0.4})
        .encode(
            x=alt.X(f"{cat}:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, ticks=False)),
            y=alt.Y("movies:Q", axis=_count_axis(df)),
            tooltip=[alt.Tooltip(f"{cat}:N"), "movies:Q", "hours:Q"],
        )
        .properties(height=260)
    )


def chart_with_table(chart: alt.Chart, df: pd.DataFrame, key: str) -> None:
    st.altair_chart(chart.configure_view(stroke=None), width="stretch")  # no frame
    with st.expander("Show as table"):
        st.dataframe(df, hide_index=True, width="stretch", key=f"table-{key}")


def _count(rows: list[tuple[str, Card]], col: str) -> pd.DataFrame:
    df = pd.DataFrame(
        [{col: k, "movies": 1, "hours": (c.runtime_min or 0) / 60} for k, c in rows],
        columns=[col, "movies", "hours"],
    )
    return df.groupby(col, as_index=False).sum().round({"hours": 1})


base = to_watch or active  # stats about what's still ahead; fall back to everything
scope = "to-watch" if to_watch else "all"

# --- Genres + moods -----------------------------------------------------------------------
left, right = st.columns(2)
with left:
    genres = _count([(g, c) for c in base for g in c.genres], "genre")
    chart_with_table(hbar(genres, "genre", f"Genres in your {scope} list", "Genre"),
                     genres.sort_values("movies", ascending=False), "genres")  # fmt: skip
with right:
    moods = load_moods()
    mood_rows = [(m.name, c) for m in moods for c in base if set(c.genres) & set(m.genres)]
    mood_df = _count(mood_rows, "mood")
    chart_with_table(hbar(mood_df, "mood", f"Moods your {scope} list can serve", "Mood"),
                     mood_df.sort_values("movies", ascending=False), "moods")  # fmt: skip
    st.caption("A movie counts for a mood if it has at least one of the mood's genres.")


# --- Decades + runtime --------------------------------------------------------------------
def _runtime_bucket(c: Card) -> str:
    m = c.runtime_min
    if m is None:
        return "unknown"
    return (
        "< 90 min"
        if m < 90
        else "90–120 min"
        if m <= 120
        else "120–150 min"
        if m <= 150
        else "150+ min"
    )


left, right = st.columns(2)
with left:
    dec = _count([(f"{c.year // 10 * 10}s", c) for c in base if c.year], "decade")
    order = sorted(dec["decade"])
    chart_with_table(vbar(dec, "decade", order, "By decade"), dec, "decades")
with right:
    rt = _count([(_runtime_bucket(c), c) for c in base], "runtime")
    present = [b for b in RUNTIME_BUCKETS if b in set(rt["runtime"])]
    chart_with_table(vbar(rt, "runtime", present, "What fits tonight? (runtime)"), rt, "runtime")

# --- Your rating vs IMDb ------------------------------------------------------------------
st.subheader("Your rating vs IMDb")
if not rated:
    st.caption(
        "Nothing to compare yet. On the Watchlist page: ⚙️ Manage → pick your rating → "
        "✓ Mark watched."
    )
else:
    df = pd.DataFrame(
        [{"title": f"{c.title} ({c.year or '?'})", "imdb": float(c.imdb_rating),
          "mine": float(c.my_rating)} for c in rated]
    )  # fmt: skip
    df["difference"] = (df["mine"] - df["imdb"]).round(1)
    scale = alt.Scale(domain=[0, 10])
    diagonal = (
        alt.Chart(pd.DataFrame({"v": [0, 10]}))
        .mark_line(color=REFERENCE, strokeDash=[4, 4], strokeWidth=1)
        .encode(x=alt.X("v:Q", scale=scale), y=alt.Y("v:Q", scale=scale))
    )
    dots = (
        alt.Chart(df)
        .mark_circle(size=110, color=ACCENT, opacity=1, stroke=SURFACE, strokeWidth=2)
        .encode(
            x=alt.X("imdb:Q", scale=scale, axis=_axis("IMDb rating")),
            y=alt.Y("mine:Q", scale=scale, axis=_axis("your rating")),
            tooltip=["title:N", "imdb:Q", "mine:Q", "difference:Q"],
        )
    )
    chart_with_table((diagonal + dots).properties(height=360), df, "ratings")
    st.caption("Above the dashed line = you liked it more than IMDb; below = less.")
