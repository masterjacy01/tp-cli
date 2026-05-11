# Changelog

## 0.1.2 - 2026-05-11

- Added `tp workout-sniff <workout_id>` to probe and validate richer workout-detail endpoints.
- Enriched `tp workout --full` with data from the workout details endpoint (zone distributions and mean-max summaries when available).
- Added installer hardening to remove stale `tp` launchers that point to old virtual environments.
- Installer now forces deterministic refresh (`uninstall` + `--upgrade --no-cache-dir`) and user-level script placement for more reliable upgrades.

## 0.1.0 - 2026-05-11

- Initial public project shape for the unofficial TrainingPeaks CLI.
- Supports auth setup, profile, workout list/detail, planned workout create/update/delete, `.zwo` import, fitness metrics, PR lookup, exercise catalog search, and structured strength workout creation.
