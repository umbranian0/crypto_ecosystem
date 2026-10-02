# CHORE-66-04 -- ingestion-service: log seed failures at the point of failure + README statements

**Status: todo.** Sprint 66 item 2. Module: services/ingestion-service (+ the one `infra/README.md` sentence).

## Analysis
`src/app/routers/internal.py` (platform-history seed endpoint) catches every exception and returns a fixed 503 with no log line. `_load_platform_csvs` raises `FileNotFoundError("no CSV files found under <dir>/(seed|incremental)")`. CSVs under `data/raw/**` are gitignored, so a fresh checkout seeds nothing, silently.

## Design
- In the handler: catch `FileNotFoundError` separately, log at ERROR the missing directory path and a pointer to `data/raw/_platform/PROVENANCE.md`; the HTTP body stays the fixed generic 503 (no path in the body; the existing no-leak test must still pass).
- Other exceptions: log at ERROR with the exception class name only, NOT the message (may carry connection strings).
- Use the module's existing logging convention (grep how other routers log). No startup warning, no new abstractions, no CSVs committed, no invented download source.

## Implementation AC
As above.

## Test AC
FileNotFoundError path logs the directory (caplog) and returns the same generic 503 with no path in the body; a generic exception logs class name only (no message). Existing no-leak test still green. Full ingestion suite green (`.venv/Scripts/python.exe -m pytest tests -q -rs -p no:cacheprovider` from the service dir; prior baseline 165 passed / 2 skipped).

## Review AC (TL)
Read diff; rerun suite; confirm no path/secret in the response body.

## Documentation AC
- services/ingestion-service/README.md: archive is untracked by design; what is missing (`data/raw/_platform/{price,onchain,sentiment}/.../{seed,incremental}/*.csv`, ~103 MB); PROVENANCE.md documents sources and how it was produced; without it new tenants get no sample data and dashboard `/demo-run` shows the empty-data message; the seed-failure log line.
- infra/README.md: replace "A checkout without the host archive still seeds empty." with the same statement (brief).
- Check `data/raw/_platform/PROVENANCE.md`; if it does not say how the archive is obtained, add one paragraph stating it is not distributed in the repo; do not invent a source.

## Rules
Never run tests, alembic or SQL against the live database `naive_first`; Postgres-backed tests target `naive_first_test`. Do not git commit. Stay in the module (plus the named infra/README.md sentence).
