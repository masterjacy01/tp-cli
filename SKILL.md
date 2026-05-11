---
name: tp-cli
description: "Use the unofficial TrainingPeaks CLI for profile, workouts, fitness metrics, structured workout creation, Zwift .zwo import, and strength workout workflows."
author: "Jakob Gmoser"
license: "MIT"
argument-hint: "<command> [args] | install"
allowed-tools: "Read Bash"
---

# tp-cli

This skill drives the local `tp` command from the unofficial `tp-cli` Python package.

## Prerequisites

Verify the CLI is installed before use:

```bash
tp --version
```

If missing from a source checkout:

```bash
python -m pip install .
```

## Auth

```bash
tp auth setup --browser chrome
tp auth status
```

Manual cookie setup:

```bash
tp auth setup
```

Credentials are stored at `~/.config/trainingpeaks-cli/tokens.json`.

## Common Commands

- `tp profile` - show TrainingPeaks profile details
- `tp workouts --start YYYY-MM-DD --end YYYY-MM-DD` - list workouts
- `tp workout <id> --prs` - inspect one workout
- `tp fitness --days 42` - show CTL, ATL, TSB, and TSS
- `tp create --sport bike --date YYYY-MM-DD --title "Title" --duration 3600 --tss 60` - create a planned workout
- `tp import-zwo workout.zwo --sport bike --date YYYY-MM-DD` - import a Zwift workout
- `tp exercises plank` - search strength exercises
- `tp strength-create --date YYYY-MM-DD --title "Strength" --structure strength.json` - create a structured strength workout

## Safety

This CLI can write to a real TrainingPeaks account. Use `tp delete` and `tp strength-delete` only after confirming the target ID. Do not expose cookies or token file contents.
