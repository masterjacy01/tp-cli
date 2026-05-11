# tp-cli

Unofficial TrainingPeaks CLI for athletes, coaches, and agents that want a fast terminal interface to TrainingPeaks data.

`tp-cli` can read your profile, list workouts, inspect workout details, create planned workouts, import Zwift `.zwo` structured sessions, review CTL/ATL/TSB fitness metrics, search strength exercises, and create structured strength workouts.

This project is not affiliated with, endorsed by, or supported by TrainingPeaks. It uses private web APIs observed from the TrainingPeaks app, so endpoints can change without notice.

## Install

From this repository:

```bash
python -m pip install .
```

For isolated command-line installs:

```bash
pipx install .
```

Verify:

```bash
tp --version
tp --help
```

## Authentication

The CLI stores credentials in `~/.config/trainingpeaks-cli/tokens.json` with file mode `0600`.

Browser cookie extraction is the simplest path when supported by your browser:

```bash
tp auth setup --browser chrome
tp auth status
```

Manual setup also works:

```bash
tp auth setup
```

Then paste the `Production_tpAuth` cookie from a logged-in TrainingPeaks browser session. The CLI exchanges that cookie for bearer tokens and refreshes them from the stored session cookie when needed.

You can also import an existing compatible token file:

```bash
tp auth import ./tokens.json
```

Logout removes the local token file:

```bash
tp auth logout
```

## Quick Start

```bash
# Last week of workouts
tp workouts

# Date range with sport filter
tp workouts --start 2026-05-01 --end 2026-05-11 --sport bike

# Workout detail, including PRs from that workout
tp workout 123456789 --prs

# Fitness trend
tp fitness --days 42

# Create a simple planned workout
tp create --sport run --date 2026-05-12 --title "Easy run" --duration 2700 --tss 35

# Import a Zwift workout as TrainingPeaks structure
tp import-zwo ./threshold.zwo --sport bike --date 2026-05-13 --tss 72
```

## Structured Workouts

For bike, run, and swim planned workouts, write a compact JSON file and pass it to `tp create --structure`.

```json
{
  "steps": [
    {"type": "warmup", "duration": 600, "start": 50, "end": 75},
    {
      "type": "intervals",
      "repeat": 4,
      "on_duration": 480,
      "off_duration": 240,
      "on_target": 95,
      "off_target": 55,
      "name": "Threshold"
    },
    {"type": "cooldown", "duration": 300, "start": 60, "end": 40}
  ]
}
```

Then:

```bash
tp create --sport bike --date 2026-05-14 --title "4x8 threshold" --structure workout.json
```

Run `tp structure-help` for examples and supported step types.

## Strength Workouts

Search the bundled exercise catalog:

```bash
tp exercises plank
```

Create a strength workout from JSON:

```json
{
  "exercises": [
    {"exercise_id": "5258", "sets": 2, "parameter": "Duration", "value": "60"},
    {"exercise_id": "5434", "sets": 3, "parameter": "Reps", "value": "10"}
  ]
}
```

```bash
tp strength-create --date 2026-05-15 --title "Mobility and core" --structure strength.json
```

Run `tp strength-help` for the full format.

## Command Reference

Auth:

- `tp auth setup` - extract or paste a TrainingPeaks session cookie and save tokens
- `tp auth import <path>` - import a compatible token JSON file
- `tp auth status` - validate current credentials
- `tp auth logout` - remove local credentials

Workouts and profile:

- `tp profile` - show user and athlete profile details
- `tp workouts` - list workouts in a date range
- `tp workout <id>` - show one workout
- `tp create` - create a planned workout
- `tp update <id>` - update planned workout fields
- `tp delete <id>` - delete a planned workout
- `tp import-zwo <file>` - import a Zwift `.zwo` workout

Training insight:

- `tp fitness` - show CTL, ATL, TSB, and daily TSS metrics
- `tp prs <sport> <type>` - list personal records for bike or run

Strength:

- `tp exercises <query>` - search the bundled exercise catalog
- `tp strength-create` - create structured strength workouts
- `tp strength-delete <id>` - delete a structured strength workout

## Agent Notes

The current CLI is optimized for clear terminal use and deterministic flags. It does not yet implement a full Printing Press style `--agent` envelope, local SQLite sync, or MCP server. The highest-value future upgrades are:

- `--json` and `--agent` output for every command
- local SQLite sync/search for workouts and fitness metrics
- a `doctor` command for auth and endpoint checks
- typed exit codes for auth, not found, rate limited, and API errors
- a companion skill or MCP server for agent workflows

## Development

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Build artifacts:

```bash
python -m pip install build
python -m build
```

## Safety

This tool can create, update, and delete workouts in your TrainingPeaks account. Inspect command arguments before running write operations, and use `--yes` only when you intentionally want to skip confirmation.

## License

MIT. See [LICENSE](LICENSE).
