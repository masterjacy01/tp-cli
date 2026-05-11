# Contributing

Thanks for considering a contribution.

This project talks to unofficial TrainingPeaks web APIs. Please keep changes conservative, easy to test without a real account where possible, and explicit about any endpoint assumptions.

## Local Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check .
```

## Pull Requests

- Keep behavior changes focused.
- Add tests for pure parsing, formatting, and request-building logic.
- Do not commit credentials, cookies, tokens, FIT files, or private workout data.
- Document new commands in `README.md`.

## Endpoint Changes

When TrainingPeaks changes an endpoint, include:

- the failing command
- the HTTP status and endpoint path, without secrets
- the observed response shape, redacted if needed
- the proposed compatibility behavior
