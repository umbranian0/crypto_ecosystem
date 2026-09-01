# INGEST-013 — Tenant-specified first-crawl backfill depth + verified further-back defaults

**Module**: `services/ingestion-service`
**Story source**: direct requester ask (2026-09-01, immediately after Sprint 18 close), not from
`docs/product/backlog-ingestion-pipeline-integration.md`. Builds on Sprint 18's per-tenant TimescaleDB
ingestion pipeline (`INGEST-002/003/004/005/008`) — see `docs/sprints/sprint-18.md`.
**Depends on**: `INGEST-008` (done, Sprint 18) — this ticket extends its router and the three
connectors it dispatches to. No other ticket depends on this one directly; `GW-023` (gateway-api
proxy pass-through) depends on this ticket's response/request shape being final.
**Status**: done

## Analysis

Today, `POST /connectors/{source}/run` (`INGEST-008`, `src/app/routers/connectors.py`) resolves a
brand-new tenant's first-ever crawl `since` watermark from each connector's own
`default_seed_watermark()` — `binance_price.py`: `2025-01-09`, `blockchain_onchain.py`:
`2025-07-05`/`2025-07-19`, `reddit_sentiment.py`: `2024-09-12`. Those constants exist to mark "last
timestamp already covered by the platform's historical CSV seed file" — a concept unrelated to a
tenant's own, independent per-tenant DB history (Sprint 18's per-tenant crawler model: each tenant's
DB rows are its own, nothing is pre-seeded from the CSV files). Reusing them as the DB-path fallback
was an accidental conflation, not a deliberate design choice, and it caps a new tenant's own backfill
depth at little more than a year.

Two requirements from the requester:
1. A tenant must be able to specify how far back their **first-ever** crawl of a given source goes,
   via an optional `since` param on the existing crawl-trigger endpoint. Once a tenant has any rows
   for `(tenant_id, source)`, the existing incremental "continue from latest watermark" behavior is
   unchanged and the param has no effect — this ticket is backfill depth on first crawl only, not
   arbitrary re-backfill of an already-started series (each connector's `fetch(since)` only fetches
   forward from a point; re-backfilling an earlier range for a series that already has later rows is
   out of scope, flagged below as a possible future ticket).
2. The **default** (no override) must go back much further than today's CSV-seed-derived values.
   Verified against each source's own real API before hardcoding (Design section below):
   - Binance BTCUSDT 1h klines: real listing/data start confirmed via Binance's own public API.
   - blockchain.info on-chain charts (`hash-rate`, `n-unique-addresses`): real earliest-available date
     confirmed via blockchain.info's own public API — turned out to be the Bitcoin genesis block date,
     clearly better than an arbitrary 5-years-back default, so used instead of 5-years-back per the
     ticket's own "unless you find a source-specific date that's easy to determine and clearly better"
     allowance.
   - Reddit: no genuine "earliest available" concept applies (`praw`'s `.new()` only ever returns the
     most recent ~1000 submissions per subreddit regardless of how far back `since` is set) — defaults
     to 5 years back from now, per the ticket's own fallback instruction, not a verified data boundary.

Not a leakage/causal-lag concern (`CLAUDE.md`, `docs/da-tese-ao-produto.md` 1.6) — this only changes
how far back raw historical *collection* starts, never touches `libs/naive_first_engine`'s purge-gap/
walk-forward logic, and every record still carries its own `fetched_at` unchanged.

## Design

**Verified data-availability findings (recorded here, not assumed):**
- `curl https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&startTime=0&limit=5` returns
  its first row at `open_time=1502942400000` ms regardless of how early `startTime` is set — i.e.
  Binance's own earliest available 1h BTCUSDT kline opens at **2017-08-17 04:00:00 UTC**. Confirms the
  requester's own recollection (BTCUSDT listed 2017-08-17) against the real API, not assumed. New
  default backfill start uses **2017-08-17 00:00:00 UTC** (midnight of the same day — safely before
  the first real candle without needing to hardcode the exact hour, `fetch()`'s `since`-is-exclusive
  semantics mean Binance simply returns from its own true earliest candle forward).
- `curl "https://api.blockchain.info/charts/hash-rate?start=2009-01-01&format=json&sampled=false&timespan=6000days"`
  and the same for `n-unique-addresses` both return their first `values` entry at `x=1230940800`
  (**2009-01-03 00:00:00 UTC**, the Bitcoin genesis block date) — confirmed for both charts this
  connector uses, not just one. Used as the new default backfill start for both, in place of the
  ticket's 5-years-back fallback, since it's a real, verified, clearly-more-meaningful boundary than an
  arbitrary 5-year window (early values are mostly `0.0`/near-zero for hash-rate, which is itself
  real/correct data, not a defect).
- Reddit: no equivalent floor exists to verify (`.new()`'s recency cap is a platform limit, not a
  calendar date) — 5-years-back-from-now is used as specified, explicitly documented as *not* a
  verified availability boundary, unlike the two sources above.

**New concept, kept structurally separate from the existing one**: each connector module gets a new
`default_backfill_start()` function (binance/onchain: fixed `datetime` constant; reddit:
`utcnow() - timedelta(days=5*365)`), distinct from the existing `default_seed_watermark()` (which stays
unchanged, still used only by that module's own standalone CSV `__main__` block — out of this ticket's
scope). Naming makes the distinction explicit: "seed watermark" = CSV historical-seed-file cutoff;
"backfill start" = default depth for a brand-new tenant's first DB crawl.

**DRY check (grepped first)**: `_resolve_connector`/`_binance_source`/`_onchain_source`/
`_reddit_source` in `src/app/routers/connectors.py` already centralize "which watermark value backs
this source's DB-path fallback" as one 4-tuple return value — extend that tuple (adding a 5th element,
the optional validation floor) rather than adding a second dispatch mechanism. `_run_and_record`
already computes `since = latest_watermark_from_db(...); if since is None: since = seed_watermark` —
this is the exact "is this a first crawl" signal (`since is None`) needed for requirement 1; extend
this function's existing branch, don't duplicate the "first crawl" check elsewhere. `connectors/
base.py`'s `run_incremental`/CSV path is a separate, deliberately untouched code path (no HTTP
surface, no tenant override applies there) — do not add `since`-override plumbing to `base.py`.

**Files touched** (all within `services/ingestion-service`, one module — no other service touched by
this ticket):
- `connectors/binance_price.py`: add `default_backfill_start() -> datetime` (returns
  `datetime(2017, 8, 17, tzinfo=timezone.utc)`), docstring explains it's distinct from
  `default_seed_watermark()` and cites the verified API check above.
- `connectors/blockchain_onchain.py`: add a `BITCOIN_GENESIS_DATE = datetime(2009, 1, 3,
  tzinfo=timezone.utc)` constant (cites the verified API check above) and
  `default_backfill_start() -> datetime` returning it (chart-name-independent — verified true for both
  charts this connector serves).
- `connectors/reddit_sentiment.py`: add `default_backfill_start() -> datetime` returning
  `utcnow() - timedelta(days=5 * 365)`; import `timedelta`.
- `src/app/routers/connectors.py`:
  - `_binance_source`/`_onchain_source`/`_reddit_source`/`_resolve_connector` return a 5-tuple
    `(connector, default_start, record_kind, requires_credentials, since_floor)` — `since_floor` is the
    same value as `default_start` for binance/onchain (a real, verified availability boundary an
    override must not predate) and `None` for reddit (no such boundary exists to enforce).
  - `default_seed_watermark`/`SEED_WATERMARKS`-based fallbacks in this router are replaced by each
    connector module's new `default_backfill_start()` — this is the actual behavior change requirement
    2 asks for (the CSV-seed values stop being used as the tenant-DB-path fallback at all).
  - New `since: str | None = Query(default=None, ...)` parameter on `run_connector`, parsed via a new
    `_parse_since_override(raw, floor) -> datetime` helper: `datetime.fromisoformat`, naive → assume
    UTC, `> utcnow()` → `422`, `< floor` (when `floor` is not `None`) → `422`, malformed → `422`. Full
    validation always runs when `since` is supplied (even on a non-first crawl, where the parsed value
    is simply not used afterward) — fails fast on bad input rather than silently accepting garbage that
    happens to be ignored.
  - `_run_and_record` gains an optional `since_override: datetime | None = None` parameter: when
    `latest_watermark_from_db(...)` returns `None` (first crawl), use `since_override` if given,
    otherwise the connector's `default_backfill_start()`; when it returns non-`None` (tenant already
    has data), `since_override` is not consulted at all — existing incremental behavior is byte-for-
    byte unchanged for a returning tenant, matching requirement 1's explicit constraint.

**Explicitly out of scope, flagged rather than silently built**: arbitrary re-backfill of an earlier
range for a source a tenant has already started crawling (`fetch(since)`'s forward-only contract would
need a second, different fetch mode to support this) — noted here as a candidate future ticket, not
attempted.

## Implementation acceptance criteria

- `default_backfill_start()` added to all three connector modules, returning the verified values above;
  `default_seed_watermark()`/`SEED_WATERMARKS` left completely unchanged (still used by each module's
  own `__main__` CSV block only).
- `POST /connectors/{source}/run` accepts an optional `since` query parameter (ISO 8601 date or
  datetime).
- On a tenant's first-ever crawl of `(tenant_id, source)` (`latest_watermark_from_db` returns `None`):
  `since` override honored if supplied and valid; otherwise falls back to the connector's
  `default_backfill_start()` (never the old `default_seed_watermark()`/`SEED_WATERMARKS`).
- On a tenant's non-first crawl: `since` query param has zero effect on the resolved watermark — the
  existing `latest_watermark_from_db`-continues behavior is unchanged, proven by a test.
- Malformed `since`, a future `since`, or (binance/onchain only) a `since` before the connector's
  verified earliest-available date all return `422` with a clear `detail` message, never `500` and
  never a silent clamp.
- Reddit's `since` override has no lower-floor rejection (no genuine floor exists) — only malformed/
  future-date validation applies to it.
- `ConnectorRunResponse.since` in the response body reflects whatever `since` was actually used
  (override or default) — no response-shape change needed, this already flows through the existing
  field.

## Test acceptance criteria

Extend `tests/test_connectors_router.py` (existing fakes, no live network/DB — matches this file's own
established pattern):
- First-crawl + valid override honored: connector's `fetch` is called with the overridden `since`, not
  the default.
- First-crawl + no override: connector's `fetch` is called with the new `default_backfill_start()`
  value for binance (`2017-08-17`) and onchain (`2009-01-03`), not the old seed-watermark constants.
- Non-first-crawl + override supplied: override is ignored, `fetch` is called with the existing
  DB-derived watermark (prove by first running one crawl, then a second with a different `since` value,
  asserting the second `fetch` call's `since` equals the first crawl's `fetched_at`, not the override).
- Malformed `since` → `422`.
- Future `since` → `422`.
- `since` before `2017-08-17` for binance → `422`; before `2009-01-03` for onchain → `422`.
- Reddit: a `since` older than 5 years back (e.g. 2015-01-01) with valid stored credentials → `202`,
  `fetch` called with that value (proves no floor is enforced for reddit).
- No regression to any existing test in this file (run the full file, not just new tests).
This is not a `naive_first_engine`/model/feature-engineering ticket (pure ingestion date-range
plumbing) — the `/ml-engineer` train-only-splitting/no-leakage skill checklist does not apply, and no
regression check against `docs/da-tese-ao-produto.md` section 1.3 numbers applies here.

## Review acceptance criteria (Tech Lead verifies personally)

- Read the actual diff (not the dev agent's summary) confirming: `default_seed_watermark()`/
  `SEED_WATERMARKS` are unmodified and still only referenced from each module's own `__main__` block;
  the new `default_backfill_start()` values match this ticket's verified dates exactly; `_run_and_record`
  only consults `since_override` inside the `since is None` (first-crawl) branch, never otherwise.
- Confirm no change to `connectors/base.py`'s `run_incremental`/CSV path (`git status` scoped to that
  file shows no diff, or a diff strictly limited to import additions if genuinely needed).
- Confirm no change anywhere in `libs/naive_first_engine` (`git status` scoped to that path shows zero
  diff) — this ticket must not touch the purge-gap/walk-forward/validation logic.
- Run `services/ingestion-service`'s full test suite directly (not trust the dev agent's report) and
  confirm zero regressions plus all new tests passing.
- Independently re-verify the two real-API findings myself (re-run the two `curl` checks against
  Binance's and blockchain.info's live public APIs) before accepting the hardcoded dates as correct.

## Documentation acceptance criteria

- `services/ingestion-service/README.md`'s `POST /connectors/{source}/run` section gains a paragraph
  documenting: the new `since` query parameter, that it's honored only on a tenant's first-ever crawl
  of a source, the new verified default-backfill-start dates per source (and that Reddit's is an
  unverified 5-year convention, not a real data boundary), and the `422` validation rules.
  `default_seed_watermark()`'s own existing doc mention is left as-is (unchanged concept).
- This ticket file's status updated to `done` (or `blocked`/left `in-review` with a reason) once
  verified; `docs/tickets/README.md`'s Sprint 19 section updated to match.
