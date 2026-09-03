# INGEST-027 — Blockchain.info connector: document the before/after-only progress ceiling

Sprint: docs/sprints/sprint-23.md. Backlog: docs/product/backlog-crawl-lifecycle-control.md.
Status: **done** (scoped + live verification complete; full-suite re-confirmation performed once
alongside INGEST-025/026, see this sprint's index note)
Depends on: INGEST-024 (the schema/contract it documents against). Runs in **parallel** with
INGEST-025/026 — disjoint files, no shared data (`blockchain_onchain.py` + `README.md`, not touched by
either sibling ticket).

## Analysis

Covers the backlog's INGEST-027 story. This is a documentation/contract-shape guard for the platform's
non-negotiable honesty posture (CLAUDE.md: "never let a subsystem's README, code comments, or docs imply
[a capability the code doesn't have]") — not new capability, and explicitly not to be allowed to slip
past this sprint despite being the lowest-engineering-cost story in the backlog. `BlockchainInfoConnector.
fetch` already, after INGEST-022, checks `should_cancel()` exactly once before its one blocking `GET` and
never calls `on_progress` at all (confirmed by reading that connector's own merged code, not assumed).
This ticket's own scope is: (1) confirm the docstring INGEST-022 wrote is accurate and complete, (2)
make sure the status endpoint's response shape genuinely reflects "no live progress" rather than a
zero/stale value for this connector specifically, (3) update `README.md`.

**Binding non-goal, restated from the backlog** (do not implement, even as a stretch addition): no
self-chunking of blockchain.info's date range into multiple smaller requests to manufacture progress —
that is a real behavior/API-load change against a free public endpoint, explicitly out of scope, to be
flagged to the founder as a possible future story rather than silently bundled into this ticket.

## Design

**Files touched**: `services/ingestion-service/connectors/blockchain_onchain.py` (docstring only, unless
review finds INGEST-022's docstring incomplete) and `services/ingestion-service/README.md`. No production
code change is anticipated for this ticket — if the live status-endpoint check below reveals a real gap
(e.g. `rows_fetched_so_far` defaulting to `0` instead of `None` for this connector specifically), the
minimal fix belongs to INGEST-024's own scope (the schema/response-shape ticket), flagged back to that
ticket rather than silently patched here — this ticket's own file scope is docs plus, at most, a
docstring edit.

**DRY check**: does not re-derive the granularity finding — cites it from the backlog's own "Design
finding that shapes Epic 2" section and from INGEST-022's own docstring, rather than restating the
reasoning a third time in inconsistent words.

## Implementation acceptance criteria

- [x] `BlockchainInfoConnector.fetch`'s docstring states plainly: makes one blocking HTTP call, has no
      natural mid-fetch checkpoint; `should_cancel`/`on_progress` are accepted for interface uniformity
      but `on_progress` is never called and `should_cancel` is checked at most once, before the request
      starts. (INGEST-022's docstring already covered the checked-once/never-called facts; added one
      sentence explicitly naming "interface uniformity" as the reason both parameters exist, since that
      wasn't stated verbatim before.)
- [x] Confirm (read the actual code path, INGEST-024's `datasets.py::connector_status` +
      `postgres_repository.py::latest_crawl_run`) that `GET /connectors/{source}/status` for a
      `blockchain_info_*` source, while `"running"`, returns `rows_fetched_so_far` as `null`/absent — not
      `0` — since this connector's `"running"` row is never touched by `record_crawl_progress` (nothing
      ever calls `on_progress` for it), so the column's own nullable-with-no-default nature already
      produces the correct honest answer without any special-casing. Confirmed true by reading
      `postgres_repository.py`'s `record_crawl_run`/`latest_crawl_run` and `fake_repository.py`'s
      equivalent: `rows_fetched_so_far` starts `None` on every insert and is only ever set by
      `record_crawl_progress`, which `blockchain_onchain.py` never triggers. No INGEST-024 gap found; no
      production code changed.

## Test acceptance criteria

- [x] A test (extend `tests/test_datasets_router.py` or `tests/test_connectors_router.py`, whichever
      already covers `GET /connectors/{source}/status`) proves: for a `blockchain_info_*` source with a
      `"running"` `crawl_runs` row that has never had `record_crawl_progress` called against it, the
      status response's `rows_fetched_so_far` field is `None`/absent — not `0` — a non-tautological check
      that would fail if a default of `0` were ever accidentally introduced.
      (`test_connector_status_blockchain_info_running_never_reported_progress_is_none`, added to
      `tests/test_datasets_router.py`, closing the Binance-only gap the INGEST-024 test left.)
- [x] A test proves `BlockchainInfoConnector.fetch` never calls a supplied `on_progress` callback across
      both the cancelled-before-request and completed-normally cases (a spy/mock asserting zero calls,
      not just that the test happens to pass).
      (`test_fetch_never_calls_on_progress_when_cancelled_before_request` and
      `test_fetch_never_calls_on_progress_on_normal_completion`, added to `tests/test_blockchain_onchain.py`.)

## Review acceptance criteria (Tech Lead verifies personally)

- [x] **Live-verified**: triggered a real `POST /connectors/blockchain_info_hash-rate/run` against the
      rebuilt live `ingestion-service` container, immediately read `GET .../status` — real JSON response
      `{"status": "running", ..., "rows_fetched_so_far": null, ...}`, genuinely `null`, not `0`.
- [x] Confirmed the diff to `blockchain_onchain.py` is docstring/signature-only (adds `should_cancel`/
      `on_progress` params for interface uniformity, one early-return branch for the pre-request cancel
      check — all already landed by INGEST-022, this ticket added one clarifying sentence) — no
      self-chunking or other behavior change.
- [x] Scoped re-run: `tests/test_blockchain_onchain.py tests/test_datasets_router.py` → `26 passed`.
      Full-suite re-run performed once alongside INGEST-025/026 (see this sprint's cross-cutting note on
      concurrent-migration-test DB lock contention).

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md` gains a short, explicit note under this connector's existing
      description: "no live progress; status reports only queued/running/completed/failed/cancelled, no
      incremental row count" — placed alongside the connector's existing description, not buried
      elsewhere. (New "Design notes" bullet directly after the existing `IngestionSource`/connector-list
      bullet.)
- [x] `services/ingestion-service/README.md`'s `GET /connectors/{source}/status` section explicitly
      states the progress field is `null`/absent (never a fabricated `0`) for any source connector that
      never reports progress, naming blockchain.info as the current example. (Already true — landed as
      part of INGEST-024's own uncommitted work in this session's working tree; verified accurate, no
      change needed.)
