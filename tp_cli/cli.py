"""TrainingPeaks CLI — unofficial personal-use tool."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .auth import (
    AuthError,
    check_status,
    delete_session,
    extract_from_browser,
    import_tokens_file,
    save_session,
)
from .client import (
    SPORT_IDS,
    TPClient,
    _total_duration_from_structure,
    build_strength_blocks,
    build_structure,
    search_exercises,
)

app = typer.Typer(
    name="tp",
    help="Unofficial TrainingPeaks CLI",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"tp-cli {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed tp-cli version and exit.",
    ),
) -> None:
    """Unofficial TrainingPeaks CLI."""


# ---------------------------------------------------------------------------
# Auth subcommands
# ---------------------------------------------------------------------------

auth_app = typer.Typer(help="Manage authentication", no_args_is_help=True)
app.add_typer(auth_app, name="auth")


@auth_app.command("setup")
def auth_setup(
    browser: Optional[str] = typer.Option(
        None, "--browser", "-b",
        help="Auto-extract from browser: chrome / safari / firefox / edge / brave",
    ),
    cookie: Optional[str] = typer.Option(
        None, "--cookie", "-c",
        help="Paste Production_tpAuth cookie value directly",
    ),
    tokens_file: Optional[str] = typer.Option(
        None, "--import", "-i",
        help="Import existing tokens JSON file (from tpapi.py / trainingpeaks-mcp)",
    ),
):
    """Set up authentication. Three options: auto browser extraction, paste cookie, or import tokens file."""
    if tokens_file:
        _run_import(tokens_file)
        return

    if browser:
        with console.status(f"Extracting cookie from {browser}..."):
            try:
                value = extract_from_browser(browser)
            except (AuthError, Exception) as e:
                console.print(f"[red]Error:[/] {e}")
                raise typer.Exit(1)
    elif cookie:
        value = cookie.strip()
    else:
        console.print(
            "[bold]How to get your cookie manually:[/]\n"
            "1. Log into [link=https://app.trainingpeaks.com]app.trainingpeaks.com[/link]\n"
            "2. Open DevTools [dim](Cmd+Option+I)[/] → Application → Cookies → trainingpeaks.com\n"
            "3. Find [bold yellow]Production_tpAuth[/] and copy its value\n"
            "\n[dim]Or use --browser chrome to auto-extract it.[/]"
        )
        value = typer.prompt("Paste Production_tpAuth cookie value").strip()

    if not value:
        console.print("[red]Cookie value cannot be empty.[/]")
        raise typer.Exit(1)

    with console.status("Validating and saving credentials..."):
        try:
            tokens = save_session(value)
        except (AuthError, Exception) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(
        f"[green]Authenticated![/] "
        f"(athlete ID: {tokens.get('athlete_id') or 'unknown'})\n"
        f"[dim]Credentials saved to ~/.config/trainingpeaks-cli/tokens.json[/]"
    )


def _run_import(tokens_file: str) -> None:
    with console.status(f"Importing tokens from {tokens_file}..."):
        try:
            data = import_tokens_file(tokens_file)
        except (FileNotFoundError, ValueError, Exception) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)
    console.print(
        f"[green]Tokens imported![/] (athlete ID: {data.get('athlete_id') or 'unknown'})\n"
        f"[dim]Saved to ~/.config/trainingpeaks-cli/tokens.json[/]"
    )


@auth_app.command("import")
def auth_import(
    path: str = typer.Argument(..., help="Path to tokens JSON file (e.g. trainingpeaks/.tp_tokens.json)"),
):
    """Import an existing tokens file from tpapi.py or trainingpeaks-mcp."""
    _run_import(path)


@auth_app.command("status")
def auth_status():
    """Check authentication status."""
    with console.status("Checking..."):
        status = check_status()

    if status["authenticated"]:
        console.print(
            f"[green]Authenticated[/]  "
            f"athlete ID: [bold]{status['athlete_id']}[/]  "
            + (f"user: {status['username']}  " if status.get("username") else "")
            + f"[dim](token valid for ~{status['token_expires_in_s']}s)[/]"
        )
    else:
        console.print(f"[red]Not authenticated[/] — {status.get('reason')}")
        console.print("Run [bold]tp auth setup[/] to log in.")
        raise typer.Exit(1)


@auth_app.command("logout")
def auth_logout():
    """Remove stored credentials."""
    delete_session()
    console.print("[green]Logged out.[/] Credentials removed.")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@app.command()
def profile():
    """Show your TrainingPeaks profile."""
    client = TPClient()
    with console.status("Fetching profile..."):
        try:
            user_data = client.get_user()
        except AuthError as e:
            _auth_error(e)

    user = user_data.get("user", user_data) if isinstance(user_data, dict) else {}
    athletes = user.get("athletes", [])
    athlete = athletes[0] if athletes else user

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()

    def row(k, v):
        if v is not None and str(v).strip():
            table.add_row(k, str(v))

    row("Name", f"{user.get('firstName', '')} {user.get('lastName', '')}".strip())
    row("Email", user.get("email"))
    row("Athlete ID", athlete.get("athleteId") or user.get("personId"))
    row("Username", user.get("userName"))
    row("Timezone", user.get("timeZone"))
    row("Premium", "Yes" if (athlete.get("isPremium") or user.get("isPremium")) else "No")

    console.print(Panel(table, title="[bold]TrainingPeaks Profile[/]", expand=False))


@app.command("doctor")
def doctor():
    """Run local auth and API connectivity checks."""
    status = check_status()
    checks: list[tuple[str, str, str]] = []

    if status.get("authenticated"):
        checks.append(("auth", "pass", "credentials available"))
    else:
        checks.append(("auth", "fail", status.get("reason", "not authenticated")))

    if status.get("authenticated"):
        client = TPClient()
        try:
            user_data = client.get_user()
            user = user_data.get("user", user_data) if isinstance(user_data, dict) else {}
            ident = user.get("userName") or user.get("email") or "ok"
            checks.append(("api", "pass", f"reachable as {ident}"))
        except Exception as e:
            checks.append(("api", "fail", str(e)))
    else:
        checks.append(("api", "skip", "skipped due to failed auth"))

    table = Table(title="tp doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Result")
    table.add_column("Detail", style="dim")
    for name, result, detail in checks:
        result_color = {"pass": "green", "fail": "red", "skip": "yellow"}.get(result, "white")
        table.add_row(name, f"[{result_color}]{result}[/{result_color}]", detail)
    console.print(table)

    if any(result == "fail" for _, result, _ in checks):
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Workouts — list
# ---------------------------------------------------------------------------

@app.command()
def workouts(
    start: Optional[str] = typer.Option(
        None, "--start", "-s", help="Start date YYYY-MM-DD (default: 7 days ago)"
    ),
    end: Optional[str] = typer.Option(
        None, "--end", "-e", help="End date YYYY-MM-DD (default: today)"
    ),
    status: Optional[str] = typer.Option(
        None, "--status",
        help="Filter: all | planned | completed (default: all)",
    ),
    sport: Optional[str] = typer.Option(
        None, "--sport", help="Filter by sport name (e.g. bike, run, swim)"
    ),
):
    """List workouts in a date range."""
    end_date = _parse_date(end) if end else date.today()
    start_date = _parse_date(start) if start else end_date - timedelta(days=7)

    client = TPClient()
    with console.status(f"Fetching workouts {start_date} → {end_date}..."):
        try:
            items = client.list_workouts(start_date, end_date)
        except AuthError as e:
            _auth_error(e)

    # Filter by status
    if status and status != "all":
        items = [w for w in items if _workout_status(w) == status]

    # Filter by sport
    if sport:
        sport_id = SPORT_IDS.get(sport.lower())
        if sport_id:
            items = [w for w in items if w.get("workoutTypeValueId") == sport_id]
        else:
            items = [
                w for w in items
                if sport.lower() in (w.get("workoutTypeFamilyId") or "").lower()
            ]

    if not items:
        console.print("[dim]No workouts found.[/]")
        return

    table = Table(title=f"Workouts  {start_date} → {end_date}", show_lines=False)
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Title")
    table.add_column("Sport", style="dim")
    table.add_column("Duration", justify="right")
    table.add_column("Distance", justify="right")
    table.add_column("TSS", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("ID", style="dim")

    for w in sorted(items, key=lambda x: x.get("workoutDay", "")):
        ws = _workout_status(w)
        status_icon = "[green]done[/]" if ws == "completed" else "[yellow]plan[/]"
        table.add_row(
            (w.get("workoutDay") or "")[:10],
            w.get("title") or "-",
            _sport_name(w.get("workoutTypeValueId")),
            _fmt_duration(_hours_to_seconds(w.get("totalTime") or w.get("totalTimePlanned"))),
            _fmt_distance((w.get("totalDistance") or w.get("totalDistancePlanned") or 0)),
            _fmt_num(w.get("tssActual") or w.get("tssPlanned")),
            status_icon,
            str(w.get("workoutId", "")),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Workout — detail
# ---------------------------------------------------------------------------

@app.command()
def workout(
    workout_id: str = typer.Argument(..., help="Workout ID"),
    prs: bool = typer.Option(False, "--prs", "-p", help="Also show PRs set in this workout"),
):
    """Show detailed info for a single workout."""
    client = TPClient()
    with console.status(f"Fetching workout {workout_id}..."):
        try:
            w = client.get_workout(workout_id)
            pr_list = client.get_workout_prs(workout_id) if prs else []
        except AuthError as e:
            _auth_error(e)
        except ValueError as e:
            console.print(f"[red]{e}[/]")
            raise typer.Exit(1)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()

    def row(k, v):
        if v is not None and str(v).strip() not in ("", "-", "None"):
            table.add_row(k, str(v))

    row("Date", (w.get("workoutDay") or "")[:10])
    row("Sport", _sport_name(w.get("workoutTypeValueId")))
    row("Status", _workout_status(w).capitalize())
    row("Duration (planned)", _fmt_duration(_hours_to_seconds(w.get("totalTimePlanned"))))
    row("Duration (actual)", _fmt_duration(_hours_to_seconds(w.get("totalTime"))))
    row("Distance (planned)", _fmt_distance(w.get("totalDistancePlanned") or 0))
    row("Distance (actual)", _fmt_distance(w.get("totalDistance") or 0))
    row("TSS (planned)", _fmt_num(w.get("tssPlanned")))
    row("TSS (actual)", _fmt_num(w.get("tssActual")))
    row("IF", _fmt_num(w.get("intensityFactor") or w.get("ifPlanned"), decimals=2))
    row("Avg Power", _fmt_num(w.get("averagePower"), suffix=" W"))
    row("Norm Power", _fmt_num(w.get("normalizedPower"), suffix=" W"))
    row("Avg HR", _fmt_num(w.get("averageHeartRate"), suffix=" bpm"))
    row("Max HR", _fmt_num(w.get("maxHeartRate"), suffix=" bpm"))
    row("Elevation", _fmt_num(w.get("totalElevationGain"), suffix=" m"))
    row("Calories", _fmt_num(w.get("calories"), suffix=" kcal"))

    for label, key in [("Description", "description"), ("Coach notes", "coachComments"), ("Your notes", "athleteComments")]:
        val = (w.get(key) or "").strip()
        if val:
            table.add_row(label, Text(val[:400], overflow="fold"))

    console.print(Panel(table, title=f"[bold]{w.get('title') or workout_id}[/]", expand=False))

    if pr_list:
        console.print(f"\n[bold]PRs set in this workout[/] ({len(pr_list)}):")
        for pr in pr_list:
            console.print(
                f"  [cyan]{pr.get('type')}[/] ({pr.get('class')})  "
                f"[bold]{pr.get('value')}[/]  [dim]rank #{pr.get('rank')}[/]"
            )


# ---------------------------------------------------------------------------
# Create workout
# ---------------------------------------------------------------------------

@app.command("create")
def create_workout(
    sport: str = typer.Option(..., "--sport", "-s", help=f"Sport: {', '.join(SPORT_IDS)}"),
    workout_date: str = typer.Option(..., "--date", "-d", help="Date YYYY-MM-DD"),
    title: str = typer.Option(..., "--title", "-t", help="Workout title"),
    duration: Optional[int] = typer.Option(None, "--duration", help="Planned duration in seconds"),
    tss: Optional[float] = typer.Option(None, "--tss", help="Planned TSS"),
    distance: Optional[float] = typer.Option(None, "--distance", help="Planned distance in km"),
    description: str = typer.Option("", "--description", help="Description / notes"),
    structure_file: Optional[str] = typer.Option(
        None, "--structure",
        help="JSON file with structured workout steps (see tp structure-help)",
    ),
):
    """Create a new planned workout. Use --structure for interval/structured sessions."""
    import json as _json

    structure = None
    if structure_file:
        import pathlib
        p = pathlib.Path(structure_file).expanduser()
        if not p.exists():
            console.print(f"[red]Structure file not found:[/] {structure_file}")
            raise typer.Exit(1)
        raw = _json.loads(p.read_text())

        # Accept either a full TP structure or our simplified steps format
        if "structure" in raw and "primaryIntensityMetric" in raw:
            structure = raw  # already full TP format
        elif "steps" in raw:
            structure = build_structure(raw["steps"], sport=raw.get("sport", sport))
        else:
            console.print("[red]Invalid structure JSON.[/] Must have 'steps' list. See tp structure-help.")
            raise typer.Exit(1)

        # Auto-compute duration from structure if not given
        if duration is None:
            duration = int(_total_duration_from_structure(structure))

    client = TPClient()
    with console.status("Creating workout..."):
        try:
            result = client.create_workout(
                sport=sport,
                workout_date=_parse_date(workout_date).isoformat(),
                title=title,
                duration_s=duration,
                tss=tss,
                distance_km=distance,
                description=description,
                structure=structure,
            )
        except (AuthError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    wid = result.get("workoutId")
    structured_msg = " [dim](structured)[/]" if structure else ""
    console.print(f"[green]Created[/] workout [bold]{title}[/]{structured_msg} (ID: {wid}) on {workout_date}")


# ---------------------------------------------------------------------------
# Update workout
# ---------------------------------------------------------------------------

@app.command("update")
def update_workout(
    workout_id: str = typer.Argument(..., help="Workout ID to update"),
    title: Optional[str] = typer.Option(None, "--title", "-t"),
    duration: Optional[int] = typer.Option(None, "--duration", help="Duration in seconds"),
    tss: Optional[float] = typer.Option(None, "--tss"),
    description: Optional[str] = typer.Option(None, "--description"),
):
    """Update a planned workout's fields."""
    client = TPClient()
    with console.status(f"Updating workout {workout_id}..."):
        try:
            client.update_workout(workout_id, title=title, duration_s=duration, tss=tss, description=description)
        except (AuthError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(f"[green]Updated[/] workout {workout_id}")


# ---------------------------------------------------------------------------
# Delete workout
# ---------------------------------------------------------------------------

@app.command("delete")
def delete_workout(
    workout_id: str = typer.Argument(..., help="Workout ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a planned workout."""
    if not yes:
        confirm = typer.confirm(f"Delete workout {workout_id}?")
        if not confirm:
            console.print("Cancelled.")
            raise typer.Exit(0)

    client = TPClient()
    with console.status(f"Deleting workout {workout_id}..."):
        try:
            client.delete_workout(workout_id)
        except (AuthError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(f"[green]Deleted[/] workout {workout_id}")


# ---------------------------------------------------------------------------
# Structure help
# ---------------------------------------------------------------------------

@app.command("structure-help", hidden=False)
def structure_help():
    """Show the JSON format for structured workouts (--structure flag)."""
    from rich.syntax import Syntax

    console.print(Panel(
        "[bold]Structured Workout JSON Format[/]\n\n"
        "Write a JSON file with a [cyan]steps[/] list, then pass it to:\n"
        "  [dim]tp create --sport bike --date ... --title ... --tss ... --structure /tmp/workout.json[/]\n\n"
        "[bold]Target values:[/]\n"
        "  Bike  → % of FTP  (e.g. 88 = 88% FTP)\n"
        "  Run   → % of LTHR (e.g. 85 = 85% of lactate threshold HR)\n"
        "  Swim  → % of LTHR\n\n"
        "Sport is auto-detected from --sport flag.",
        title="tp create --structure", expand=False,
    ))

    bike_example = """\
{
  "steps": [
    {"type": "warmup",    "duration": 600, "start": 50, "end": 75},
    {"type": "intervals", "repeat": 3, "on_duration": 900, "off_duration": 300,
                          "on_target": 88, "off_target": 55, "name": "Sweet Spot"},
    {"type": "cooldown",  "duration": 300, "start": 60, "end": 40}
  ]
}"""
    console.print("\n[bold green]Bike example[/] (power / % FTP):")
    console.print(Syntax(bike_example, "json", theme="monokai", padding=1))

    run_example = """\
{
  "steps": [
    {"type": "warmup",    "duration": 600, "start": 65, "end": 80},
    {"type": "intervals", "repeat": 4, "on_duration": 300, "off_duration": 180,
                          "on_target": 95, "off_target": 70, "name": "Threshold"},
    {"type": "steady",    "duration": 600, "target": 75, "name": "Easy"},
    {"type": "cooldown",  "duration": 300, "start": 70, "end": 60}
  ]
}"""
    console.print("\n[bold yellow]Run example[/] (heart rate / % LTHR):")
    console.print(Syntax(run_example, "json", theme="monokai", padding=1))

    console.print(
        "\n[bold]Step types:[/]\n"
        "  [cyan]warmup[/]     — ramp from start% to end%\n"
        "  [cyan]cooldown[/]   — ramp from start% to end%\n"
        "  [cyan]steady[/]     — hold at target%\n"
        "  [cyan]rest[/]       — easy at target%\n"
        "  [cyan]ramp[/]       — ramp from start% to end%\n"
        "  [cyan]intervals[/]  — repeat × (on_duration at on_target + off_duration at off_target)\n"
    )


# ---------------------------------------------------------------------------
# Import .zwo
# ---------------------------------------------------------------------------

@app.command("import-zwo")
def import_zwo(
    file: str = typer.Argument(..., help="Path to .zwo file"),
    sport: str = typer.Option(..., "--sport", "-s", help="Sport: bike / run / swim"),
    workout_date: str = typer.Option(..., "--date", "-d", help="Date YYYY-MM-DD"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Override title"),
    tss: Optional[float] = typer.Option(None, "--tss"),
    description: Optional[str] = typer.Option(None, "--description"),
):
    """Import a Zwift .zwo file as a structured planned workout."""
    client = TPClient()
    with console.status(f"Parsing and creating workout from {file}..."):
        try:
            result = client.import_zwo(
                zwo_path=file,
                sport=sport,
                workout_date=_parse_date(workout_date).isoformat(),
                title=title,
                tss=tss,
                description=description,
            )
        except (AuthError, FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(
        f"[green]Created[/] structured workout [bold]{result['title']}[/] "
        f"(ID: {result['workout_id']})  "
        f"[dim]{result['duration_min']}min, {result['steps']} blocks[/]"
    )


# ---------------------------------------------------------------------------
# Fitness (CTL / ATL / TSB)
# ---------------------------------------------------------------------------

@app.command()
def fitness(
    start: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (default: 6 weeks ago)"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="End date (default: today)"),
    days: Optional[int] = typer.Option(None, "--days", "-n", help="Show last N days (overrides --start)"),
):
    """Show CTL (fitness), ATL (fatigue), and TSB (form) metrics."""
    end_date = _parse_date(end) if end else date.today()
    if days:
        start_date = end_date - timedelta(days=days)
    elif start:
        start_date = _parse_date(start)
    else:
        start_date = end_date - timedelta(weeks=6)

    client = TPClient()
    with console.status("Fetching fitness metrics..."):
        try:
            data = client.get_fitness(start_date, end_date)
        except AuthError as e:
            _auth_error(e)

    if not data:
        console.print("[dim]No data found.[/]")
        return

    table = Table(title=f"Fitness  {start_date} → {end_date}")
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("TSS", justify="right")
    table.add_column("CTL", justify="right", style="green")
    table.add_column("ATL", justify="right", style="yellow")
    table.add_column("TSB", justify="right")
    table.add_column("Form", style="dim")

    for d in sorted(data, key=lambda x: x.get("workoutDay", "")):
        tsb = d.get("tsb")
        tsb_str = f"{tsb:.1f}" if tsb is not None else "-"
        form = _tsb_label(tsb)

        if tsb is not None:
            if tsb > 10:
                tsb_str = f"[green]{tsb_str}[/]"
            elif tsb < -20:
                tsb_str = f"[red]{tsb_str}[/]"

        table.add_row(
            (d.get("workoutDay") or "")[:10],
            _fmt_num(d.get("tssActual")),
            _fmt_num(d.get("ctl"), decimals=1),
            _fmt_num(d.get("atl"), decimals=1),
            tsb_str,
            form,
        )

    console.print(table)

    latest = sorted(data, key=lambda x: x.get("workoutDay", ""))[-1]
    tsb_val = latest.get("tsb")
    tsb_label = _tsb_label(tsb_val)
    console.print(
        f"\n[bold]Today:[/]  "
        f"CTL=[green]{_fmt_num(latest.get('ctl'), decimals=1)}[/]  "
        f"ATL=[yellow]{_fmt_num(latest.get('atl'), decimals=1)}[/]  "
        f"TSB={_fmt_num(tsb_val, decimals=1)}  [dim]{tsb_label}[/]"
    )


# ---------------------------------------------------------------------------
# Personal records
# ---------------------------------------------------------------------------

@app.command("prs")
def personal_records(
    sport: str = typer.Argument(..., help="Sport: Bike or Run"),
    pr_type: str = typer.Argument(..., help="PR type (e.g. power20min, speed5K)"),
    start: Optional[str] = typer.Option(None, "--start", "-s"),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="Default: today"),
    limit: int = typer.Option(10, "--limit", "-n"),
):
    """Show personal records for a sport/type.

    Examples:
      tp prs Bike power20min
      tp prs Run speed5K
      tp prs Bike power5min --start 2024-01-01
    """
    sport_normalized = sport.capitalize()
    if sport_normalized not in ("Bike", "Run"):
        console.print("[red]Sport must be Bike or Run[/]")
        raise typer.Exit(1)

    end_date = _parse_date(end) if end else date.today()
    start_date = _parse_date(start) if start else None

    client = TPClient()
    with console.status(f"Fetching {sport_normalized} {pr_type} PRs..."):
        try:
            records = client.get_prs(sport_normalized, pr_type, start_date, end_date)
        except AuthError as e:
            _auth_error(e)

    if not records:
        console.print(f"[dim]No {pr_type} PRs found.[/]")
        return

    table = Table(title=f"{sport_normalized} — {pr_type}")
    table.add_column("Rank", justify="right", style="dim")
    table.add_column("Value", justify="right", style="bold")
    table.add_column("Date", style="cyan")
    table.add_column("Workout")

    for r in records[:limit]:
        table.add_row(
            f"#{r.get('rank', '-')}",
            str(r.get("value", "-")),
            (r.get("workoutDate") or "")[:10],
            r.get("workoutTitle") or "-",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Exercise catalog search
# ---------------------------------------------------------------------------

@app.command("exercises")
def exercises_search(
    query: str = typer.Argument(..., help="Search term (e.g. 'plank', 'squat', 'bridge')"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
):
    """Search the exercise catalog for strength workouts."""
    results = search_exercises(query, limit=limit)
    if not results:
        console.print(f"[dim]No exercises found matching '{query}'.[/]")
        return

    table = Table(title=f"Exercises matching '{query}'")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Parameters", style="dim")
    table.add_column("Video", style="dim", max_width=30)

    for ex in results:
        params = ", ".join(p.get("parameter", "") for p in ex.get("parameters", []))
        video = ex.get("videoUrl", "") or ""
        if len(video) > 30:
            video = video[:27] + "..."
        table.add_row(str(ex["id"]), ex["title"], params, video)

    console.print(table)


# ---------------------------------------------------------------------------
# Strength workouts
# ---------------------------------------------------------------------------

@app.command("strength-create")
def strength_create(
    workout_date: str = typer.Option(..., "--date", "-d", help="Date YYYY-MM-DD"),
    title: str = typer.Option(..., "--title", "-t", help="Workout title"),
    structure_file: str = typer.Option(..., "--structure", "-f", help="JSON file with strength workout definition"),
    instructions: str = typer.Option("", "--instructions", help="Workout instructions/notes"),
    duration: Optional[int] = typer.Option(None, "--duration", help="Duration in seconds"),
):
    """Create a structured strength workout with exercises, sets, and reps.

    The JSON file should contain an "exercises" list. Each exercise has:
      - exercise_id: ID from the catalog (use 'tp exercises' to search)
      - sets: number of sets
      - parameter: "Reps", "Duration", "RepsPerSide", etc.
      - value: prescribed value per set (e.g. "10" for reps, "30" for seconds)
      - coach_notes: optional notes

    Example JSON:
      {
        "exercises": [
          {"exercise_id": "5258", "sets": 2, "parameter": "Duration", "value": "60"},
          {"exercise_id": "5434", "sets": 1, "parameter": "Duration", "value": "120"}
        ]
      }
    """
    import json as _json
    import pathlib

    p = pathlib.Path(structure_file).expanduser()
    if not p.exists():
        console.print(f"[red]File not found:[/] {structure_file}")
        raise typer.Exit(1)

    raw = _json.loads(p.read_text())
    exercises_def = raw.get("exercises", [])
    if not exercises_def:
        console.print("[red]No exercises found in JSON.[/] Expected an 'exercises' list.")
        raise typer.Exit(1)

    client = TPClient()
    with console.status("Building exercise blocks..."):
        try:
            blocks = build_strength_blocks(exercises_def, client)
        except (AuthError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    with console.status("Creating strength workout..."):
        try:
            result = client.create_strength_workout(
                workout_date=_parse_date(workout_date).isoformat(),
                title=title,
                blocks=blocks,
                instructions=instructions,
                duration_s=duration,
            )
        except (AuthError, RuntimeError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    wid = result.get("id")
    snap = result.get("snapshot", {})
    console.print(
        f"[green]Created[/] strength workout [bold]{title}[/] (ID: {wid}) on {workout_date}\n"
        f"  [dim]{snap.get('totalBlocks', 0)} blocks, {snap.get('totalSets', 0)} sets, "
        f"{snap.get('totalPrescriptions', 0)} exercises[/]"
    )


@app.command("strength-delete")
def strength_delete(
    workout_id: str = typer.Argument(..., help="Strength workout numeric ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a structured strength workout."""
    if not yes:
        confirm = typer.confirm(f"Delete strength workout {workout_id}?")
        if not confirm:
            console.print("Cancelled.")
            raise typer.Exit(0)

    client = TPClient()
    with console.status(f"Deleting strength workout {workout_id}..."):
        try:
            client.delete_strength_workout(workout_id)
        except (AuthError, ValueError) as e:
            console.print(f"[red]Error:[/] {e}")
            raise typer.Exit(1)

    console.print(f"[green]Deleted[/] strength workout {workout_id}")


@app.command("strength-help", hidden=False)
def strength_help():
    """Show JSON format for structured strength workouts."""
    from rich.syntax import Syntax

    console.print(Panel(
        "[bold]Structured Strength Workout JSON Format[/]\n\n"
        "Write a JSON file with an [cyan]exercises[/] list, then pass it to:\n"
        "  [dim]tp strength-create --date ... --title ... --structure /tmp/strength.json[/]\n\n"
        "Search for exercises: [bold]tp exercises plank[/]\n"
        "Get exercise details by ID from the catalog.",
        title="tp strength-create --structure", expand=False,
    ))

    example = '''\
{
  "exercises": [
    {
      "exercise_id": "5258",
      "sets": 2,
      "parameter": "Duration",
      "value": "60",
      "coach_notes": "Per side"
    },
    {
      "exercise_id": "5434",
      "sets": 1,
      "parameter": "Duration",
      "value": "120"
    },
    {
      "exercise_id": "5178",
      "sets": 1,
      "parameter": "Duration",
      "value": "120"
    }
  ]
}'''
    console.print("\n[bold]Example[/] --- Mobility session:")
    console.print(Syntax(example, "json", theme="monokai", padding=1))

    console.print(
        "\n[bold]Exercise fields:[/]\n"
        "  [cyan]exercise_id[/]  --- ID from catalog (use [bold]tp exercises[/] to search)\n"
        "  [cyan]sets[/]         --- number of sets (default: 1)\n"
        "  [cyan]parameter[/]    --- 'Reps', 'Duration', 'RepsPerSide', 'WeightKg', 'WeightLb'\n"
        "  [cyan]value[/]        --- prescribed value per set (e.g. '10' reps or '30' seconds)\n"
        "  [cyan]values[/]       --- list of values if different per set (overrides value)\n"
        "  [cyan]coach_notes[/]  --- optional notes for this exercise\n"
        "\n[bold]Block types:[/]\n"
        "  [cyan]SingleExercise[/] --- one exercise per block (default, recommended)\n"
        "  [cyan]Circuit[/]        --- multiple exercises in one block (may have rendering issues)\n"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_error(e: Exception) -> None:
    console.print(f"[red]Auth error:[/] {e}")
    console.print("Run [bold]tp auth setup[/] to re-authenticate.")
    raise typer.Exit(1)


def _parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    console.print(f"[red]Invalid date '{s}'. Use YYYY-MM-DD.[/]")
    raise typer.Exit(1)


def _hours_to_seconds(h) -> Optional[int]:
    return round(float(h) * 3600) if h is not None else None


def _workout_status(w: dict) -> str:
    return "completed" if (w.get("completedDate") or w.get("totalTime")) else "planned"


def _sport_name(sport_id) -> str:
    if sport_id is None:
        return "-"
    names = {1: "Swim", 2: "Bike", 3: "Run", 4: "MTB", 5: "Ski", 6: "Walk", 7: "Strength", 9: "Other"}
    return names.get(int(sport_id), str(sport_id))


def _fmt_duration(seconds) -> str:
    if not seconds:
        return "-"
    try:
        s = int(float(seconds))
    except (TypeError, ValueError):
        return "-"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m {sec:02d}s"


def _fmt_distance(meters) -> str:
    if not meters:
        return "-"
    try:
        km = float(meters) / 1000
    except (TypeError, ValueError):
        return "-"
    return f"{km:.1f} km"


def _fmt_num(val, decimals: int = 0, suffix: str = "") -> str:
    if val is None:
        return "-"
    try:
        f = float(val)
        return f"{f:.{decimals}f}{suffix}" if decimals else f"{int(round(f))}{suffix}"
    except (TypeError, ValueError):
        return "-"


def _tsb_label(tsb) -> str:
    if tsb is None:
        return ""
    if tsb > 25:  return "Very Fresh"
    if tsb > 10:  return "Fresh"
    if tsb > 0:   return "Optimal"
    if tsb > -10: return "Tired"
    if tsb > -25: return "Very Tired"
    return "Exhausted"


if __name__ == "__main__":
    app()
