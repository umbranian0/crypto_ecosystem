# INGEST-010 (Sprint 45 revision) — `seed_tenant.py` backfill CLI, base mode + `--all-existing-tenants`

**Sprint**: 45. **Module**: `services/ingestion-service`. **Status**: done (2026-09-15). **Priority**: Must.
**Depends on**: `INGEST-002`, `INGEST-003` (both done). No other ticket dependency — first in this
sprint's sequential chain (`INGEST-010` → `INGEST-030` → `GW-030`).

## Analysis

Story: `docs/product/backlog-ingestion-pipeline-integration.md`'s `INGEST-010` (revised 2026-09-15,
founder decision: copy the platform-wide historical CSV archive to **every existing tenant**, no
demo-tenant special case). Despite the prior sprint-18 ticket file at this same path describing
`seed_tenant.py` as already built, **it does not exist on disk** — `services/ingestion-service/scripts/`
has no `seed_tenant.py` and no `scripts/` directory at all (verified 2026-09-15,
`ls services/ingestion-service/scripts` → not found). This ticket therefore builds the CLI from
scratch, including both the base single-tenant mode the prior ticket file described and the new
`--all-existing-tenants` mode the backlog's 2026-09-15 revision adds — not a diff against existing code.

Constrained by: CLAUDE.md ("no service reads another service's DB schema directly" — tenant enumeration
must go through `gateway-api`'s own `GET /tenants` HTTP contract, never a direct read of the `identity`
schema); `implementation-plan.md` section 9 (DRY — reuse `INGEST-003`'s `ConnectorRecordRepository`
write path, `connectors/base.py`'s existing helpers, no second CSV-parsing/DB-writing implementation);
this sprint's idempotency requirement (re-running must not duplicate rows for any tenant).

## Design

**Files** (all within `services/ingestion-service`, one module):
- New `services/ingestion-service/src/app/seed_platform_history.py` — the actual backfill logic,
  importable, **not** placed under `scripts/`. `scripts/` is not part of this service's packaged
  wheel (`pyproject.toml`'s `[tool.hatch.build.targets.wheel]` only packages `src/app`, the same fact
  `gateway-api/src/app/provisioning.py`'s own docstring already documents for its own move out of
  `scripts/provision_tenant.py`) — `INGEST-030` (next ticket in this chain) needs to call this same
  logic for one tenant from inside the running FastAPI process, so it must live in `src/app` from the
  start, not be extracted later. This is this ticket's own DRY move, following the exact precedent
  `gateway-api`'s `provisioning.py` already set for the identical problem.
- New `services/ingestion-service/scripts/seed_tenant.py` — thin CLI wrapper (argument parsing +
  stdout only) importing and calling `seed_platform_history.py`'s functions, mirroring
  `gateway-api/scripts/provision_tenant.py`'s "CLI wrapper imports the real function from `src/app`"
  shape exactly.

**DRY check (grepped before writing)**: `connectors/base.py::run_incremental` already contains the
CSV-parsing → `add_{price,onchain,sentiment}_records` write path and `record_crawl_run` bookkeeping —
this ticket's write path must call the **same** `ConnectorRecordRepository.add_*_records` methods
(`app/repositories/interfaces.py`), not a new parsing/writing implementation. `_TABLE_SPECS`
(`postgres_repository.py`) is the single source of truth for which table/event-time-column a given
`record_kind` maps to — reused, not re-derived. `PROVENANCE.md`'s documented `data/raw/_platform/
<source>/{seed,incremental}/...` layout is the CSV read path — reused verbatim, not reinterpreted.

**Idempotency mechanism (explicit design decision, since `add_*_records` do a plain `session.add_all`
with no upsert/`ON CONFLICT` — confirmed by reading `postgres_repository.py` directly, lines ~209-234)**:
rather than adding a new upsert primitive to the repository (out of this ticket's minimal-diff scope,
and not needed), `seed_platform_history.py` achieves idempotency by **reading before writing**: for each
`(tenant_id, source)`, call the existing `ConnectorRecordRepository.latest_event_time(tenant_id, source)`
query first, then filter the CSV-derived records to only those with event-time strictly greater than
that watermark (or all rows, if `latest_event_time` returns `None`) before calling the matching
`add_*_records` method. Running the same CSV range twice is then a no-op on the second run — no new
rows qualify, because everything already written is `<=` the resolved watermark. Document this
mechanism explicitly in the README (see Documentation AC) as "skip-then-append", not a literal SQL
`UPSERT`, since it is not one — this is a disclosed, deliberate design choice, not a shortcut.

**Source → table/record-kind mapping** (read `PROVENANCE.md` and each connector's `self.name`/
`timestamp_column` directly, do not guess): `price/binance_btcusdt_1h` → `record_kind="price"`,
`connector.name = "binance_price_btcusdt_1h"`, event-time column `open_time`; `onchain/
blockchain_info_hash-rate` and `onchain/blockchain_info_n-unique-addresses` → `record_kind="onchain"`,
`connector.name = "blockchain_info_hash-rate"` / `"blockchain_info_n-unique-addresses"`, event-time
column `date`/`timestamp` (confirm exact CSV column name against the seed CSV header, `_TABLE_SPECS`
resolves the model-side name); `sentiment/kaggle_bitcoin_sentiments_21_24` → `record_kind="sentiment"`.
**Open naming question, your call, document whichever you pick**: whether the Kaggle seed's DB `source`
value should be written as `"reddit_vader_sentiment"` (continuity with the live connector's own
`self.name`, so a tenant's dataset listing shows one continuous `sentiment_score` series) or as a
distinct `"kaggle_bitcoin_sentiments_21_24"` source (preserves `PROVENANCE.md`'s own discontinuity
warning literally, avoids implying one continuous signal). `PROVENANCE.md` itself explicitly warns:
*"If the two sentiment series are ever combined for feature engineering, document that discontinuity
explicitly — don't let a report imply one continuous sentiment signal across the boundary."* Given that
warning, prefer the **distinct source name** (`"kaggle_bitcoin_sentiments_21_24"`) — do not silently
merge it into `"reddit_vader_sentiment"`'s identity. State the choice and the reasoning in the README's
backfill section either way.

`--from platform-csv` reads `data/raw/_platform/<source>/{seed,incremental}/*.csv` (the CLI iterates
every `source` under `data/raw/_platform/{price,onchain,sentiment}/*` rather than requiring one
`--source` per invocation when combined with `--all-existing-tenants` — each tenant gets all four
CSV-backed sources in one pass). `--from <arbitrary-path>` (single-tenant mode only) reads one arbitrary
CSV for one `--source`, per the original ticket's own CLI shape.

## Implementation acceptance criteria

- [x] `seed_tenant.py --tenant-id <id> --source <source> --from <path-or-"platform-csv"> [--dry-run]` —
  base single-tenant mode, `--tenant-id`/`--source` required (no hardcoded default anywhere).
- [x] `seed_tenant.py --all-existing-tenants [--dry-run]` — enumerates every tenant via `gateway-api`'s
  `GET /tenants` (operator-authenticated, `SETUP-011`; reuses the `GATEWAY_API_URL` env var/default
  `http://localhost:8000` `dashboard-web`'s `downstream.py` already establishes, plus a new
  `OPERATOR_TOKEN` env var read the same way `gateway-api`'s own `operator_auth.py` reads it — the same
  shared-secret value already provisioned in `infra/docker-compose.yml`/`infra/.env.example`, not a new
  secret). For each tenant returned, writes a full, independent copy of every row from all four
  CSV-backed sources under `data/raw/_platform/<source>/{seed,incremental}/...` into that tenant's rows,
  via the DRY-checked write path above. No tenant is special-cased as "the" demo tenant. `gateway-api`
  unreachable is a clear, fatal CLI error (non-zero exit, no partial silent success) — this is an
  operator-run script, not the degraded-not-blocking provisioning hook (`INGEST-030`/`GW-030` below cover
  that separate, live-request-path concern).
- [x] Idempotent per tenant, per source: running `--all-existing-tenants` (or a repeated single-tenant
  invocation) twice does not duplicate rows for any tenant — via the skip-then-append mechanism above.
- [x] `--dry-run` prints row counts per source **per tenant** (when combined with `--all-existing-tenants`)
  or per source (single-tenant mode) without writing — assert zero repository write calls in tests.
- [x] `PROVENANCE.md`'s existing per-source caveats (raw/processed boundary for price — the seed file
  carries ~200 `ta`-library indicator columns the connector's own incremental output does not — the
  Kaggle-sentiment discontinuity note, the licensing-review-not-done flag) are copied into
  `ingestion-service/README.md`'s new backfill section, not lost in the move to DB-based storage.

## Test acceptance criteria

- [x] Idempotency test: running the write path twice against the same CSV range writes zero new rows the
  second time (assert against a fake/test-double `ConnectorRecordRepository`'s call count and
  `latest_event_time` return value, not a real Postgres instance).
- [x] `--dry-run` test: zero `add_*_records` calls on the fake repository.
- [x] `--all-existing-tenants` test: a fake `gateway-api` HTTP transport returning N tenants results in
  N independent write passes, one tenant's rows never landing under a different tenant's `tenant_id`.
- [x] `gateway-api` unreachable (fake transport raising `httpx.ConnectError`) surfaces a clear CLI error,
  not a silent empty-tenant no-op.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms `seed_platform_history.py` lives under `src/app` (not `scripts/`), matching `INGEST-030`'s
  stated need to import it directly.
- Confirms the write path calls `INGEST-003`'s exact `ConnectorRecordRepository.add_*_records` methods —
  no second CSV-parsing/DB-writing implementation (grep-checked).
- Confirms `--tenant-id` has no hardcoded default anywhere in the script.
- Confirms tenant enumeration goes through `gateway-api`'s HTTP `GET /tenants`, never a direct read of
  the `identity` schema (grep for any `sqlalchemy`/`psycopg` import touching `identity.*` in this
  service — must return nothing).
- Confirms idempotency is real: reads the actual `latest_event_time`-based filtering logic, not just the
  test's assertion.

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md`'s new backfill section records: the mechanism (CLI +
  underlying `seed_platform_history.py` module), the skip-then-append idempotency design and why (no
  upsert primitive on the repository today), the `PROVENANCE.md` caveats carried forward, the sentiment
  source-naming decision made above, the founder's resolved tenant-attachment decision verbatim (copy to
  every tenant, no demo-tenant special case), and a link to `INGEST-030`/`GW-030` for the
  provisioning-time-forward half of the same decision.
