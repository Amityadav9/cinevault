"""CineVault command line. The thin presentation layer; logic lives in app/services.

uv run python -m app.cli add                  # asks "Paste a URL or title" again and again
uv run python -m app.cli add "https://www.imdb.com/title/tt0816692/"   # quotes! (& in URLs)
uv run python -m app.cli add "intersteller 2014" -p 1 -n "Nolan, rewatch in IMAX"
uv run python -m app.cli search "the godfater"
uv run python -m app.cli list                 # to-watch (default)
uv run python -m app.cli list --status all
uv run python -m app.cli show "interstellar"  # plot, director, cast, poster link
uv run python -m app.cli enrich               # fetch TMDB details for older entries
uv run python -m app.cli watched "interstellar" --rating 9
uv run python -m app.cli remove "interstellar"
"""

from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal, schema_versions
from app.services import tmdb, watchlist
from app.services.matcher import Candidate, find_candidates
from app.services.parse_input import UnparseableInput, parse_input

app = typer.Typer(help="CineVault: your personal movie watchlist.", no_args_is_help=True)
console = Console()


@app.callback()
def _check_database() -> None:
    """Runs before every command: fail early and clearly if the DB is down or behind."""
    try:
        current, head = schema_versions()
    except OperationalError as e:
        console.print("[red]✗ Can't reach the database.[/red] Start it: docker compose up -d db")
        raise typer.Exit(1) from e
    if current != head:
        console.print(
            f"[red]✗ Database schema is at {current}, the code expects {head}.[/red]\n"
            "  Run: uv run alembic upgrade head"
        )
        raise typer.Exit(1)


STATUS_STYLE = {"to_watch": "cyan", "watched": "green", "dropped": "dim"}


def _fmt_votes(n: int | None) -> str:
    if not n:
        return "-"
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


def _fmt_movie(title: str, year: int | None, is_adult: bool = False) -> str:
    return f"[bold]{title}[/bold] ({year or '?'})" + (" [red]18+[/red]" if is_adult else "")


def _candidates_table(candidates: list[Candidate]) -> Table:
    t = Table(show_lines=False, header_style="bold magenta")
    for col in ("#", "Movie", "★", "Votes", "Min", "Genres", "Score"):
        t.add_column(col, justify="right" if col in {"#", "★", "Votes", "Min", "Score"} else "left")
    for i, c in enumerate(candidates, 1):
        t.add_row(
            str(i),
            _fmt_movie(c.title, c.year, c.is_adult),
            str(c.avg_rating or "-"),
            _fmt_votes(c.num_votes),
            str(c.runtime_min or "-"),
            ", ".join(c.genres),
            f"{c.score:.2f}",
        )
    return t


def _find_or_exit(session, user_input: str) -> list[Candidate]:
    try:
        parsed = parse_input(user_input)
    except UnparseableInput as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1) from e
    candidates = find_candidates(session, parsed)
    if not candidates:
        hint = " (is it a TV series? only movies are loaded)" if parsed.imdb_id else ""
        console.print(f"[yellow]No movie found for '{user_input}'{hint}[/yellow]")
        raise typer.Exit(1)
    return candidates


@app.command()
def search(user_input: Annotated[str, typer.Argument(help="IMDb URL, any URL, or a title")]):
    """Show matching movies without adding anything."""
    with SessionLocal() as session:
        console.print(_candidates_table(_find_or_exit(session, user_input)))


@app.command()
def add(
    user_input: Annotated[
        str | None,
        typer.Argument(help="IMDb URL, any URL, or a title. Leave out to paste several in a row."),
    ] = None,
    priority: Annotated[int | None, typer.Option("--priority", "-p", min=1, max=5)] = None,
    notes: Annotated[str | None, typer.Option("--notes", "-n")] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="take the best match, no questions")
    ] = False,
):
    """Find a movie and add it to your watchlist (you confirm first).

    Without an argument it keeps asking "Paste a URL or title". Pasting into the prompt
    means no quotes are needed (bash never sees the & in long URLs). Empty Enter = done.
    """
    if user_input is not None:
        _add_one(user_input, priority, notes, yes)
        return

    console.print("[dim]Paste a URL or type a title. Empty Enter (or Ctrl+C) = done.[/dim]")
    added = 0
    while True:
        try:
            text = Prompt.ask(
                "\n[bold cyan]Paste a URL or title[/bold cyan]", default="", show_default=False
            )
        except (KeyboardInterrupt, EOFError):
            break
        if not text.strip():
            break
        try:
            added += _add_one(text, priority, notes, yes)
        except typer.Exit:  # "not found", cancel, duplicate → just ask for the next one
            continue
        except KeyboardInterrupt:  # Ctrl+C in the middle of one movie → skip it
            console.print("[dim]skipped[/dim]")
    console.print(f"\n[green]Done: {added} added.[/green] See them with: list")


def _add_one(user_input: str, priority: int | None, notes: str | None, yes: bool) -> bool:
    """Add one movie interactively. Returns True if added; raises typer.Exit otherwise."""
    with SessionLocal() as session:  # one session (= transaction) per movie
        candidates = _find_or_exit(session, user_input)

        if yes:
            chosen = candidates[0]
        elif len(candidates) == 1:  # exact IMDb id
            c = candidates[0]
            console.print(_candidates_table(candidates))
            if not Confirm.ask(f"Add {_fmt_movie(c.title, c.year)}?", default=True):
                raise typer.Exit()
            chosen = c
        else:
            console.print(_candidates_table(candidates))
            pick = IntPrompt.ask(
                "Which one? [dim](0 = cancel)[/dim]",
                choices=[str(i) for i in range(len(candidates) + 1)],
                default=1,
                show_choices=False,
            )
            if pick == 0:
                raise typer.Exit()
            chosen = candidates[pick - 1]

        if priority is None:
            priority = 3 if yes else IntPrompt.ask(
                "Priority [dim](1 = watch first … 5 = someday)[/dim]",
                choices=["1", "2", "3", "4", "5"], default=3, show_choices=False,
            )  # fmt: skip
        if notes is None and not yes:
            notes = Prompt.ask("Notes [dim](optional)[/dim]", default="", show_default=False)

        try:
            item = watchlist.add(session, chosen.tconst, priority=priority, notes=notes)
        except watchlist.WatchlistError as e:
            console.print(f"[yellow]• {e}[/yellow]")
            raise typer.Exit(1) from e
        session.commit()  # the user confirmed → make it permanent
        console.print(
            f"[green]✓ Added[/green] {_fmt_movie(item.movie.title, item.movie.year)} "
            f"· priority {item.priority} · {chosen.imdb_url}"
        )
        # Details are a nice-to-have: if TMDB fails, the movie is still on the list.
        if details := _enrich_quietly(session, chosen.tconst):
            if details.director:
                console.print(f"  [dim]Director:[/dim] {details.director}")
            if details.overview:
                console.print(f"  [dim]{_shorten(details.overview, 160)}[/dim]")
        return True


def _shorten(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1].rsplit(" ", 1)[0] + "…"


def _enrich_quietly(session, tconst: str, force: bool = False) -> tmdb.TmdbCache | None:
    try:
        client = tmdb.TmdbClient()
        try:
            row = tmdb.enrich(session, tconst, client, force=force)
        finally:
            client.close()
    except tmdb.TmdbError as e:
        session.rollback()
        console.print(f"  [yellow]• no TMDB details: {e}[/yellow]")
        return None
    session.commit()
    return row


@app.command()
def show(
    user_input: Annotated[str, typer.Argument(help="title or IMDb URL of a watchlist entry")],
):
    """Full details of a watchlist movie: plot, director, cast, poster link."""
    with SessionLocal() as session:
        try:
            item = watchlist.find(session, user_input)
        except (watchlist.WatchlistError, UnparseableInput) as e:
            console.print(f"[yellow]• {e}[/yellow]")
            raise typer.Exit(1) from e
        m, d = item.movie, _enrich_quietly(session, item.tconst)  # cached → no API call
        console.print(f"\n{_fmt_movie(m.title, m.year, m.is_adult)}")
        if d and d.tagline:
            console.print(f"[italic]{d.tagline}[/italic]")
        rating = f"{m.rating.avg_rating} ★ ({_fmt_votes(m.rating.num_votes)})" if m.rating else "-"
        console.print(
            f"{rating} · {m.runtime_min or '?'} min · {', '.join(g.name for g in m.genres)}"
        )
        if d and d.director:
            console.print(f"[dim]Director:[/dim] {d.director}")
        if d and d.cast:
            cast = ", ".join(c["name"] for c in d.cast[:5])
            console.print(f"[dim]Cast:[/dim] {cast}")
        if d and d.overview:
            console.print(f"\n{d.overview}\n")
        style = STATUS_STYLE[item.status]
        console.print(
            f"[dim]Status:[/dim] [{style}]{item.status}[/] · priority {item.priority}"
            + (f" · my rating {item.my_rating}" if item.my_rating is not None else "")
            + (f" · notes: {item.notes}" if item.notes else "")
        )
        console.print(f"[dim]IMDb:[/dim] https://www.imdb.com/title/{m.tconst}/")
        if d and (url := tmdb.poster_url(d.poster_path, "w500")):
            console.print(f"[dim]Poster:[/dim] {url}")


@app.command()
def enrich(
    force: Annotated[bool, typer.Option("--force", help="re-fetch even if cached")] = False,
):
    """Fetch TMDB details for watchlist movies that don't have them yet."""
    with SessionLocal() as session:
        items = watchlist.list_items(session, status=None)
        todo = [it for it in items if force or session.get(tmdb.TmdbCache, it.tconst) is None]
        if not todo:
            console.print("[dim]All watchlist movies already have TMDB details.[/dim]")
            return
        for it in todo:
            ok = _enrich_quietly(session, it.tconst, force=force)
            mark = "[green]✓[/green]" if ok and ok.tmdb_id else "[yellow]–[/yellow]"
            console.print(f"{mark} {_fmt_movie(it.movie.title, it.movie.year)}")


@app.command("list")
def list_cmd(
    status: Annotated[
        str, typer.Option("--status", "-s", help="to_watch | watched | dropped | all")
    ] = "to_watch",
):
    """Show your watchlist."""
    with SessionLocal() as session:
        items = watchlist.list_items(session, None if status == "all" else status)
        if not items:
            console.print(f"[dim]Nothing here yet (status: {status}).[/dim]")
            return
        t = Table(title=f"CineVault · {status} · {len(items)} movies", header_style="bold magenta")
        for col in ("P", "Movie", "★", "Votes", "Min", "Genres", "Status", "Added", "Notes"):
            t.add_column(col, justify="right" if col in {"P", "★", "Votes", "Min"} else "left")
        for it in items:
            m = it.movie
            status_txt = it.status + (f" {it.my_rating}" if it.my_rating is not None else "")
            t.add_row(
                str(it.priority),
                _fmt_movie(m.title, m.year, m.is_adult),
                str(m.rating.avg_rating) if m.rating else "-",
                _fmt_votes(m.rating.num_votes if m.rating else None),
                str(m.runtime_min or "-"),
                ", ".join(g.name for g in m.genres),
                f"[{STATUS_STYLE[it.status]}]{status_txt}[/]",
                it.added_at.strftime("%Y-%m-%d"),
                it.notes or "",
            )
        console.print(t)


@app.command()
def watched(
    user_input: Annotated[str, typer.Argument(help="title or IMDb URL of a watchlist entry")],
    rating: Annotated[float | None, typer.Option("--rating", "-r", min=0, max=10)] = None,
):
    """Mark a watchlist movie as watched (optionally with your own rating)."""
    with SessionLocal() as session:
        try:
            item = watchlist.find(session, user_input)
            watchlist.mark_watched(session, item, rating)
        except (watchlist.WatchlistError, UnparseableInput) as e:
            console.print(f"[yellow]• {e}[/yellow]")
            raise typer.Exit(1) from e
        session.commit()
        console.print(f"[green]✓ Watched[/green] {_fmt_movie(item.movie.title, item.movie.year)}")


@app.command()
def remove(
    user_input: Annotated[str, typer.Argument(help="title or IMDb URL of a watchlist entry")],
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
):
    """Remove a movie from your watchlist."""
    with SessionLocal() as session:
        try:
            item = watchlist.find(session, user_input)
        except (watchlist.WatchlistError, UnparseableInput) as e:
            console.print(f"[yellow]• {e}[/yellow]")
            raise typer.Exit(1) from e
        label = _fmt_movie(item.movie.title, item.movie.year)
        if not yes and not Confirm.ask(f"Remove {label}?", default=False):
            raise typer.Exit()
        watchlist.remove(session, item)
        session.commit()
        console.print(f"[green]✓ Removed[/green] {label}")


if __name__ == "__main__":
    app()
