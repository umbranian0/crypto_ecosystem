# INGEST-001 — Retroactive ticket/SDLC tracking for already-shipped connector code

**Status: done**

## Analysis
Story: new ticket, working slot `INGEST-001` (sprint-10.md, no formal backlog priority — retroactive
tracking, not a new-feature story). This is **not** implementation-plan.md trigger #6 firing
(FastAPI upload API / `ingestion` Postgres schema / data-quality gate) — that condition ("a real
client needs to upload something") is still false, confirmed in sprint-10.md's own pre-planning
pass. What actually happened: `services/ingestion-service`'s connectors (`connectors/base.py`,
`connectors/binance_price.py`, `connectors/blockchain_onchain.py`,
`connectors/reddit_sentiment.py`) and the raw-zone archive (`data/raw/_platform/`) were pulled
forward on 2026-08-05 at explicit user request, ahead of trigger #6, deliberately pulling trigger
#10 (market/sentiment connectors) forward independent of the FastAPI service wrapper -- the
service's own README already discloses this in its status line. 19 tests were added 2026-08-09
(`tests/test_base.py`, `tests/test_binance_price.py`, `tests/test_blockchain_onchain.py`,
`tests/test_reddit_sentiment.py`). `docs/product/backlog-operability.md`'s own scope-decision note
(read directly) confirms this code exists, is tested, and is honestly documented, but flags that no
`INGEST-*` ticket section exists yet in `docs/tickets/README.md` -- a real, disclosed process gap
(code shipped outside the normal PM -> Tech Lead -> dev-squad flow, untracked in the ticket index),
matching this repo's own precedent for `gateway-api` building ahead of trigger #5 (already ticketed
under GW-*). This ticket closes that same gap for `ingestion-service`, retroactively, per
CLAUDE.md's own convention that every module's README/ticket trail stays current.

**This ticket does NOT authorize any new engineering scope.** Building the FastAPI app, the
`ingestion` Postgres schema, the upload API, or the data-quality gate is explicitly out of scope --
those remain gated on trigger #6, unfired. This is a documentation/tracking ticket recording what
already exists, when it was built, and its current test/README state.

## Design
No design pattern applies -- this ticket produces no source code. Files touched: this ticket file
(`docs/tickets/INGEST-001.md`, new) and `docs/tickets/README.md` (new `services/ingestion-service`
section, appended -- not inserted mid-file, to avoid colliding with any other section another
ticket in this sprint might touch). `services/ingestion-service/README.md` is read-only for this
ticket (already accurate per the Analysis section above -- confirmed by reading it directly before
writing this ticket); if the dev agent finds it inaccurate against the real `connectors/`/`tests/`
state, correcting it is in scope (documentation acceptance criteria below), but no status/scope
wording should change beyond correcting factual drift.

DRY check: grep `docs/tickets/README.md` for any existing `ingestion-service`/`INGEST-*` section --
none exists (confirmed by the Tech Lead directly before writing this ticket), so this is a new
section, not an edit to an existing one.

## Implementation acceptance criteria
- [x] `docs/tickets/INGEST-001.md` (this file) exists, documenting: what already exists in the
  working tree (`connectors/base.py`, `connectors/binance_price.py`,
  `connectors/blockchain_onchain.py`, `connectors/reddit_sentiment.py`,
  `data/raw/_platform/PROVENANCE.md`), when it was built (2026-08-05 for the connectors/archive,
  2026-08-09 for the 19-test suite), and at whose instruction/under what disclosed override
  (explicit user request, ahead of trigger #6, per the service's own README).
- [x] No `services/ingestion-service/connectors/*.py` or `services/ingestion-service/tests/*.py`
  file is created, modified, or deleted by this ticket -- verified via `git status` scoped to that
  path after the ticket is done.
- [x] `services/ingestion-service/README.md` is re-read against the real `connectors/`/`tests/`
  state; if any factual drift is found (e.g. a connector class name, a test count), it is
  corrected; if none is found, that is stated explicitly in this ticket's Outcome, not silently
  assumed.

## Test acceptance criteria
- [x] The dev agent runs `services/ingestion-service`'s existing test suite
  (`.venv/Scripts/python.exe -m pytest tests/ -q`, per the README's own documented setup) and
  records the actual pass count (expected 19, per the README's own claim -- confirm, don't just
  copy the number) as part of this ticket's Outcome. This is a verification run, not new test
  code -- no test file is added or modified by this ticket.

## Review acceptance criteria
- Tech Lead personally confirms: (a) `docs/tickets/README.md` gains a real
  `services/ingestion-service (INGEST-*)` section, not just a passing mention elsewhere; (b) the
  section states plainly this is retroactive tracking of already-shipped work, not a claim that
  new code was written this sprint; (c) `git status` scoped to
  `services/ingestion-service/connectors/` and `services/ingestion-service/tests/` shows zero
  changes after this ticket, confirming no new engineering scope was introduced; (d) the recorded
  test pass count matches an independent re-run by the Tech Lead.

## Documentation acceptance criteria
- [x] `docs/tickets/README.md` gains a new `# services/ingestion-service (INGEST-*)` section
  (mirroring the existing per-module section format used for `libs/naive_first_engine (NFE-*)`,
  `services/validation-service (VS-*)`, etc.), a one-row table listing `INGEST-001`, its story
  ("Retroactive ticket/SDLC tracking for already-shipped connector code"), depends-on (`none`),
  and status, plus a short prose note (mirroring the "Sprint 0X outcome" prose used elsewhere in
  that file) stating what already existed before this sprint, when it was built, and that this
  ticket only formalizes tracking.
- [x] `services/ingestion-service/README.md` reflects any factual corrections found during review
  (or is confirmed already accurate, stated explicitly).

## Outcome

Verification run: `.venv/Scripts/python.exe -m pytest tests/ -q` in `services/ingestion-service`
(pre-existing venv, no recreation needed) — result: **19 passed** in 1.12s, 0 failed. Matches the
README's own claim, confirmed by an independent re-run rather than copied.

`services/ingestion-service/README.md` was re-read directly against the real `connectors/` and
`tests/` state: connector class names (`BinancePriceConnector`, `BlockchainInfoConnector`,
`RedditSentimentConnector`), the `IngestionSource` interface reference, the 19-test count, and the
documented `pytest` setup commands all match the working tree exactly. **No factual drift found —
README left unedited, confirmed accurate as-is.**

`git status` scoped to `services/ingestion-service/connectors/` and `services/ingestion-service/tests/`
after this ticket: this ticket authored zero changes to either path. Note for the Tech Lead's own
verification: at the start of this ticket, `git status` already showed pre-existing uncommitted
modifications to `connectors/base.py`, `connectors/binance_price.py`, `connectors/blockchain_onchain.py`,
and `connectors/reddit_sentiment.py` (plus an untracked `tests/` directory and `conftest.py`) from a
prior, unrelated session — none of these were touched, authored, or altered by this ticket; they
were left exactly as found.

Files touched by this ticket: `docs/tickets/INGEST-001.md` (this file — status line, acceptance-criteria
checkboxes, this Outcome section) and `docs/tickets/README.md` (new `services/ingestion-service (INGEST-*)`
section, appended at end of file).


## Tech Lead review (verified independently, not trusted from the dev agent's report)

(a) docs/tickets/README.md confirmed to carry a real "# services/ingestion-service (INGEST-*)"
section (not a passing mention), with a one-row Sprint 10 table listing INGEST-001, its story,
depends-on (none), and status.

(b) The section's prose plainly states this is retroactive tracking of already-shipped work
("Not a new-feature story"), not a claim new code was written this sprint.

(c) git status --porcelain -- services/ingestion-service/connectors/ services/ingestion-service/tests/
re-run directly by the Tech Lead: shows pre-existing modified connectors/*.py files and an untracked
tests/ directory, identical to the state disclosed in this ticket's own Outcome section as
pre-existing from a prior, unrelated session -- confirmed this ticket introduced zero changes to
either path.

(d) Test suite re-run directly by the Tech Lead: .venv/Scripts/python.exe -m pytest tests/ -q in
services/ingestion-service -> 19 passed, 0 failed in 1.14s, matching the dev agent's own recorded
count exactly.