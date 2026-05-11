# Security

Do not open public issues with cookies, bearer tokens, refresh tokens, account IDs tied to real identities, or private workout data.

Report sensitive issues privately to the repository owner.

## Credential Storage

`tp-cli` stores tokens at:

```text
~/.config/trainingpeaks-cli/tokens.json
```

The file is written with `0600` permissions. Delete it with:

```bash
tp auth logout
```

## Scope

This project is unofficial and uses private TrainingPeaks web APIs. Treat credentials with the same care as a logged-in browser session.
