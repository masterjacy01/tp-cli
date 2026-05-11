# Agent Notes

Use `tp --help` and command-level help before invoking write operations.

This project is an unofficial TrainingPeaks CLI. Never print or commit cookies, bearer tokens, token JSON, account identifiers tied to private data, FIT files, or user workout exports.

## Verification

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

Networked TrainingPeaks commands require real credentials and should not run in automated tests unless the test explicitly uses a disposable account.
