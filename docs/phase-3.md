# Phase 3: Streamlit app

**Result:** the watchlist in the browser. A poster grid with filters, moods, trailers and card actions;
an Add page for pasting one or many URLs/titles; a Stats page. It reuses the Phase 2 services unchanged.

```bash
uv run streamlit run ui/main.py      # → http://localhost:8501   (Ctrl+C to stop)
```

## Pages
| Page | File | What |
|---|---|---|
| 🎬 Watchlist | `ui/views/watchlist.py` | poster grid; sidebar filters (status, mood, genres, runtime, ★, sort); tagline + top-3 cast; **▶ Trailer & details** dialog (YouTube, full cast as characters, plot); **⚙️ Manage** popover (priority, rating + watched, drop, undo, remove with confirm) |
| ➕ Add movies | `ui/views/add.py` | paste lines → one box per line: pick match, preview (poster, tagline, cast, plot, trailer link), priority, notes, **Add** |
| 📊 Stats | `ui/views/stats.py` | KPIs (to watch, hours left, watched, your avg vs IMDb); genres; moods your list can serve; decades; runtime ("what fits tonight"); your rating vs IMDb scatter |

Supporting files: `ui/main.py` (entry: navigation + DB/schema guard), `ui/data.py` (services → frozen
dataclasses, caching, actions), `.streamlit/config.toml`.

## Steps
| Step | What |
|---|---|
| 1 | Package install (hatchling, editable), app skeleton, poster grid + filters, AppTest tests |
| fix | `ui/app.py` shadowed the `app` package, so the entry became `ui/main.py` (+ regression test) |
| 2 | Trailers (TMDB `videos`, migration 0005), tagline + cast on cards, details dialog |
| 3 | Add page (multi-line paste, per-line confirm) |
| 4 | Card actions via callbacks; `set_priority`; undo clears `watched_at` |
| fix | Trailers in more languages (`include_video_language`); YouTube search fallback |
| 5 | Stats page (dataviz method: validated colour, integer axes, tooltips, table views) |

## Concepts
- **Streamlit's model.** The whole script re-runs top to bottom on every interaction, and widget values *are* the
  state. No callbacks are needed for display; the script just describes the page for the current state.
- **`st.session_state`** survives re-runs (e.g. the "✓ Added" message across `st.rerun()`). Widget `key`s are
  how you read a widget's value from anywhere: `st.session_state["prio-tt1860242"]`.
- **Callbacks (`on_click`/`on_change`)** run *before* the next re-run, so the re-run already shows the new
  state. They are also the only legal place to change a widget's value (the "Clear" button).
- **Caching.** `st.cache_data` for pure, picklable results (search results, moods, previews); the watchlist
  itself is *not* cached, so changes from the CLI show up immediately. Don't cache what must be fresh.
- **`st.dialog`** (modal), **`st.popover`** (small panel), `st.segmented_control`, `st.link_button`.
- **Packaging.** `[build-system]` + `uv sync` installs `app` and `ui` in editable mode, so imports work from
  Streamlit, scripts and tests alike.
- **Name shadowing.** Streamlit puts the script's folder first on `sys.path`, so `ui/app.py` hid the `app`
  package. Never name a script after a package you import.
- **Closures in loops (ruff B023).** A lambda sees the loop variable as it is *when called*, so bind it:
  `lambda i, c=candidates: …`.
- **AppTest** runs pages headless: set widget values, click buttons, assert on output. It's fast and needs no browser,
  but it's not identical to `streamlit run` (it missed the shadowing bug).
- **Dataviz method.** Pick the form first (KPI tiles for headline numbers, ranked bars for categories, a scatter
  for "mine vs IMDb" with a y = x reference). One validated accent hue for single-series charts (light and dark
  steps), no legend for one series, thin rounded bars, recessive grid, tooltips, a table view per chart.
  Then *render and look*: that's how we caught "0.5 movies" on an axis.
- **External data has gaps.** TMDB simply has no video for some films (Vaaranam Aayiram). Show a graceful
  fallback (YouTube search link) instead of nothing.

## Troubleshooting we hit
| Symptom | Cause | Fix |
|---|---|---|
| `No module named 'app.db'; 'app' is not a package` | `ui/app.py` shadowed package `app` | renamed to `ui/main.py` |
| `ModuleNotFoundError: app` from a script outside the project | `app` not installed | package install (`[build-system]`) |
| Cast/tagline visible in CLI but not on cards | not mapped into `Card` | added fields to `ui/data.py` |
| No trailer for a non-English film | TMDB returns only English videos by default | `include_video_language`; search fallback when TMDB has none |
| AppTest `FileNotFoundError` | `AppTest.from_file` resolves paths relative to the test file | absolute paths |
| Axis showing 0.5 movies | `tickMinStep` not honoured | explicit integer tick values |

## Try next
- Mark a few movies watched with your rating, then open 📊 Stats → "Your rating vs IMDb".
- Edit a mood (pgAdmin: `mood_genres`) and watch the Mood filter and the Stats mood chart change.
