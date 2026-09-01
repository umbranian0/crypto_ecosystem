# Backlog — Per-tenant data pipeline integration (TimescaleDB, ingestion-service, dataset picker, unified ops dashboard)

Source: `CLAUDE.md` (root — non-negotiable positioning: validation/audit infrastructure, never a
trading/prediction product; per-tenant multi-tenancy from day one; no service reads another
service's DB schema directly); `docs/implementation-plan.md` sections 2 (module boundary map), 5
(data ownership — schema-per-service, `raw/{tenant_id}/...`/`processed/{tenant_id}/...` object
prefixes), 6 (trigger-based build order), 7 (design patterns: Adapter for connectors, Repository for
data access), 9 (DRY/engineering conventions); `docs/adr/0003-disclosed-trigger-override-pattern.md`;
`docs/product/backlog-first-run-setup-and-ops.md` (full text — `SETUP-013`/`SETUP-020`/`SETUP-022`
named explicitly below as stories this backlog extends/supersedes, not duplicates);
`services/ingestion-service/README.md`, `connectors/base.py`, `connectors/binance_price.py`,
`connectors/blockchain_onchain.py`, `connectors/reddit_sentiment.py`, `data/raw/_platform/
PROVENANCE.md` (read in full — standalone scripts, CSV-only, no tenant concept anywhere in this
service today); `services/validation-service/src/app/dataset_source.py` and README's "Dataset
access" section (read in full — `InlineOrLocalFileDatasetSource`/`ObjectStorageDatasetSource`/
`CompositeDatasetSource`, the existing `DatasetSource` Adapter interface this backlog's new
implementation must plug into, not replace); `infra/docker-compose.yml` (read in full — `postgres`
is **already** the `timescale/timescaledb:latest-pg16` image, and `validation-service`'s
`split_results` table is **already** a hypertable, `INF-010`; `dashboard-web` is not yet a Compose
service, a separately tracked gap, `SETUP-030`); `libs/common/src/naive_first_common/contracts.py`;
`services/gateway-api/src/app/repositories/postgres_repository.py` (the RLS tenant-scoping pattern —
`SELECT set_config('app.tenant_id', :tenant_id, true)` as the first statement of every transaction —
this backlog reuses, not reinvents); `docs/tickets/README.md` (ID sequencing per module — next free
ID per prefix confirmed by reading the actual index, not assumed).

## Important finding that adjusts this backlog's own scope (read before Epic A)

The task that produced this backlog assumed TimescaleDB would arrive as **a new container**. It
won't, because it already didn't need to: `infra/docker-compose.yml`'s `postgres` service has run the
`timescale/timescaledb:latest-pg16` image since `INF-001` (Sprint 06), and `validation-service`'s
`split_results` table has been a real TimescaleDB hypertable since `INF-010` (Sprint 17). TimescaleDB
is a Postgres extension, not a separate database product — this backlog's epics below add a new
`ingestion` schema (mirroring `identity`/`validation`/`reporting`) to the **existing** Postgres
instance and declare its time-series tables as hypertables there, exactly the way `validation-service`
already did for `split_results`. No new service block, no new port, no new container is proposed
anywhere in this backlog. This is a scope correction, not a scope expansion — flagged explicitly per
this backlog's own governing instruction not to silently assume an answer where the input backlog
request's premise doesn't match the repo's actual state.

## Scope

**In scope**, five epics:

- **Epic A** — `ingestion` Postgres schema (TimescaleDB hypertables) + connectors becoming
  tenant-aware, per-tenant-credentialed, DB-writing instead of CSV-writing.
- **Epic B** — `ingestion-service`'s FastAPI REST API (the upload/dataset/trigger-crawl contract
  `CLAUDE.md` and this service's own README have listed as "not yet built" since the service was
  first scaffolded), plus the `gateway-api` proxy routes `dashboard-web` needs to reach it (per
  `implementation-plan.md`'s "no service talks to another except through `gateway-api`'s public
  contract, and `dashboard-web` calls `gateway-api` only" rule).
- **Epic C** — `validation-service`'s `dataset_source.py` gaining a fourth `DatasetSource` (backed by
  `ingestion-service`'s new dataset API, **not** a direct database connection — see the design note
  below), and `dashboard-web`'s submit-run form gaining a "pick a stored dataset" option.
- **Epic D** — one-time backfill migration loading the existing seed + incremental CSVs
  (`data/raw/_platform/...`) into the new `ingestion` schema.
- **Epic E** — unified ops dashboard in `dashboard-web`: cross-component status/data views and safe,
  API-call-only trigger actions, explicitly reconciled against `backlog-first-run-setup-and-ops.md`'s
  Monitoring (`SETUP-020`–`023`) and in-UI configuration (`SETUP-010`–`015`) epics.

**Explicitly out of scope, stated rather than silently assumed**: direct container/Docker-socket
control from `dashboard-web` (the requester explicitly declined this — every "trigger" story in Epic
E calls a service's own authenticated HTTP API, never `docker compose start/stop/restart` or anything
touching the Docker socket); `services/ingestion-service`'s data-quality gate (still not requested by
any decision in this backlog's brief — remains "not yet built" per that service's own README, and is
not promoted here just because the schema/API around it are); `services/economic-service` (untouched,
still gated on its own trigger #11 per the ethical boundary in `docs/da-tese-ao-produto.md` section
2.7); anything that would let preprocessing be fit outside a single training fold, per split — no
story here touches `naive_first_engine`'s splitting/baseline/metric/DM-test code at all, so this
constraint is inherited unchanged, not re-litigated.

## Trigger-override disclosures (per ADR-0003, stated plainly rather than assumed)

- **`ingestion-service`'s connectors and raw-zone archive were already pulled forward once**
  (2026-08-05, ahead of their original trigger #10, per that service's own README's opening line:
  "partially scaffolded, ahead of schedule"). This backlog's Epic A is the **second** disclosed
  override of the same module: it deepens that already-overridden connector code (tenant-awareness,
  DB writes, per-tenant credentials) further ahead of trigger #10's original condition ("a client
  wants the platform to source ground truth instead of supplying it themselves") — still true today;
  no such client request exists. Building it anyway is this backlog's own second-order override,
  named here explicitly, not folded silently into "epic A is just finishing epic A's earlier work."
- **`ingestion-service`'s FastAPI REST API (Epic B) is a fresh, first-time override of trigger #6**
  ("as soon as manually placing files for `validation-service` to read becomes the bottleneck... right
  after `gateway-api` exists and a real client needs to upload something"). `gateway-api` exists
  (trigger #5 fired), but no real client has asked to upload anything — this API is being built now
  because the DB-backed dataset picker (Epic C) and the dashboard's trigger-a-crawl action (Epic E)
  need it as infrastructure, not because a pilot client's upload request created the need the trigger
  table describes. Per ADR-0003, this override still needs disclosure in the module's README status
  line, the sprint file, and the ticket index once scheduled — this backlog's own disclosure is this
  paragraph.
- **No other module's trigger is touched.** `services/reporting-service`, `services/economic-service`,
  and `libs/sdk` are unaffected by anything in this backlog.

## Design decision this backlog makes explicit (not left for the PM/Tech Lead to discover mid-sprint)

**`validation-service` must not read `ingestion-service`'s Postgres schema directly**, even though
both now live in the same physical Postgres instance. `implementation-plan.md` section 2's rule ("no
service reads another service's database schema directly... cross-service data access always goes
through that service's API") applies exactly as much to two services sharing one physical instance as
it would to two separate ones — schema-per-service is what makes "split into separate physical
databases later" a non-event, and that property is void the moment one service's code contains a
literal `ingestion.` table reference. `VS-023` below is written to enforce this: the new
`DatasetSource` implementation calls `ingestion-service`'s HTTP API (via `gateway-api`, or directly
by Compose hostname the same way `reporting-service` already calls `validation-service` directly — see
that precedent in `infra/docker-compose.yml`), never a shared connection string into the `ingestion`
schema.

## Prioritization scheme

MoSCoW, same convention every other backlog in this repo uses. Each story's one-line rationale ties
back to what it unlocks and its module's owns/does-not-own boundary — this backlog has an unusually
long, strict dependency chain (schema before connectors before API before dataset picker or
dashboard), so sequencing notes matter more here than in most of this repo's other backlogs.

---

## Epic A — Per-tenant TimescaleDB schema + tenant-aware, DB-writing connectors

### INGEST-002 — `ingestion` Postgres schema: per-tenant raw-record hypertables [Must]

**As** `ingestion-service`'s future connectors and API **I want** a new `ingestion` Postgres schema
(mirroring `identity`/`validation`/`reporting`'s existing schema-per-service convention) with one
hypertable per raw-data family (`price_ohlcv`, `onchain_metric`, `sentiment_score`), each row carrying
`tenant_id`, `source`, the record's own timestamp column, `fetched_at` (the causal-lag column
`connectors/base.py`'s `FetchResult` already models), and the source-specific payload columns **so
that** connector writes and the future dataset API have somewhere real, tenant-scoped, and
time-series-indexed to land.

Acceptance criteria:
- [ ] New Alembic migration environment under `services/ingestion-service/migrations/` (this service
  has none today), `search_path`-scoped and `alembic_version`-table-scoped to `ingestion` specifically
  for Postgres connections, mirroring `validation-service`'s `env.py` fix from `INF-005`'s cross-service
  `alembic_version` collision finding — not re-derived, copied with attribution.
- [ ] Each of the three tables is declared a TimescaleDB hypertable (partitioned on its own timestamp
  column) via the same migration pattern `validation-service`'s `0004_convert_split_results_to_
  hypertable.py` (`INF-010`) already established — no new hypertable-creation mechanism invented.
- [ ] Row-level security is enabled and **forced** on all three tables via a `tenant_isolation` policy
  keyed on `current_setting('app.tenant_id')`, identical in shape to `validation-service`'s
  `0002_add_row_level_security.py` and `gateway-api`'s `0002_add_identity_rls.py` — copied with
  attribution, not re-derived from scratch a third time.
- [ ] No table in this schema is queried or written by any other service's code — confirmed by this
  story's own test/review step: `grep -R "ingestion\." services/validation-service/src
  services/gateway-api/src services/reporting-service/src` returns nothing beyond comments.
- [ ] `services/ingestion-service/README.md`'s "Owns" section is updated to name the `ingestion` schema
  as now real (was "not yet built").

Rationale for priority: Must — every other story in Epic A, and everything in Epics B/C/D, needs this
schema to exist first; this is the literal first link in the dependency chain the task named.
Depends on: none

### LC-010 — Extract the tenant-scoped-transaction helper into `libs/common` [Must]

**As** a third service (`ingestion-service`) about to duplicate the same
`SELECT set_config('app.tenant_id', :tenant_id, true)`-as-first-statement pattern
`gateway-api`'s and `validation-service`'s Postgres repositories already each independently implement
**I want** that pattern extracted into `naive_first_common` **so that** a third near-identical copy
never gets written — `implementation-plan.md` section 9's own DRY rule ("if two services seem to need
the same logic, that logic belongs in a lib") is written for exactly this moment: two existing copies
plus one about to be added is the textbook second-duplication trigger.

Acceptance criteria:
- [ ] `naive_first_common` gains a `tenant_scope(session, tenant_id)` function (or equivalent context
  manager) that issues exactly the same `SELECT set_config('app.tenant_id', :tenant_id, true)`
  statement `gateway-api`'s `_set_tenant_scope`/`validation-service`'s equivalent already issue —
  behavior byte-identical, not reinterpreted.
- [ ] `gateway-api`'s and `validation-service`'s existing private `_set_tenant_scope` functions are
  replaced with calls to this shared function (not left as parallel duplicate implementations) — their
  existing test suites (including `validation-service`'s pooled-connection-reuse-does-not-leak test and
  `gateway-api`'s equivalent) are re-run unchanged against the new call site and still pass, proving
  the extraction changed no behavior.
- [ ] `INGEST-003`'s new Postgres repository is the third consumer, from day one — never a fourth
  hand-rolled copy.
- [ ] `libs/common/README.md` documents the new function in its public API list (doc-sync checked per
  `LC-005`'s existing convention).

Rationale for priority: Must — blocks `INGEST-003` from either duplicating this pattern a third time
(a DRY violation this backlog is explicitly instructed not to introduce) or inventing a different
tenant-isolation mechanism (which `implementation-plan.md` section 7's Repository pattern rationale
explicitly warns against — one mechanism, swappable implementations).
Depends on: none (can run in parallel with `INGEST-002`)

### INGEST-003 — Connectors write to the `ingestion` schema instead of local CSVs [Must]

**As** `ingestion-service`'s three existing connectors (`BinancePriceConnector`,
`BlockchainInfoConnector`, `RedditSentimentConnector`) **I want** their output routed through a new
Repository layer into `INGEST-002`'s Postgres tables, tenant-scoped via `LC-010`'s shared helper,
**instead of** `connectors/base.py`'s `run_incremental` writing a dated CSV to a local
`incremental/` directory **so that** "the system works with that database" (the task's own words) —
today's local-disk output becomes the interim/legacy path, not the only path.

Acceptance criteria:
- [ ] A new `ConnectorRecordRepository` Protocol (Repository pattern, `implementation-plan.md` section
  7) is added to `ingestion-service`, with one method per table family (`add_price_records`,
  `add_onchain_records`, `add_sentiment_records`), each taking `tenant_id` as its first parameter after
  `self` — same convention `validation-service`'s `ValidationRunRepository` interface already
  documents and follows.
- [ ] `connectors/base.py`'s `run_incremental` is extended (not replaced) with a `tenant_id` parameter
  and a `repository: ConnectorRecordRepository` parameter; when both are supplied, it writes via the
  repository instead of the CSV path. The existing CSV-writing behavior is kept, not deleted, as the
  standalone/no-tenant/no-DB fallback this service's own tests already exercise — same "demote, don't
  delete" precedent `infra/README.md` already applies elsewhere in this repo. Existing tests for
  `run_incremental`'s CSV path continue to pass unmodified.
- [ ] `latest_watermark` gains a DB-backed sibling (`latest_watermark_from_db(repository, tenant_id,
  source)`) that queries `MAX(fetched_at)` (or the relevant timestamp column) scoped to `tenant_id`,
  replacing the CSV-directory-scanning approach for the DB-write path — the two watermark functions
  coexist (CSV path uses the old one, DB path uses the new one), neither silently reimplements the
  other's logic differently.
- [ ] `RedditSentimentConnector`'s and `BinancePriceConnector`'s/`BlockchainInfoConnector`'s existing
  unit tests (fake `requests.Session`/fake `praw` client) are extended with a DB-write-path case using
  an in-memory/test double repository — no real Postgres required for these specific tests, consistent
  with this service's existing "fake the client, never hit the real API" test convention.
- [ ] `services/ingestion-service/README.md`'s connector section states both output paths exist, which
  is the default for anything client-facing, and which is retained purely for local/offline dev.

Rationale for priority: Must — this is the single most important behavior change named in the task
("crawlers write directly to a database"); nothing in Epics B/C/D has real per-tenant data to show
without it.
Depends on: INGEST-002, LC-010

### INGEST-004 — Per-tenant connector credentials [Must]

**As** each tenant's independently-run `RedditSentimentConnector` **I want** its
`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`/`REDDIT_USER_AGENT` sourced from a per-tenant credentials
table in the `ingestion` schema **instead of** today's single shared set of process environment
variables **so that** "every tenant runs its own independent crawler... potentially with their own API
keys" (the task's own decision #4) is actually true for the one connector that requires credentials at
all.

Acceptance criteria:
- [ ] A new `connector_credentials` table (`tenant_id`, `source` e.g. `"reddit"`, credential fields)
  in the `ingestion` schema, RLS-scoped the same way as `INGEST-002`'s other tables.
- [ ] `RedditSentimentConnector`'s constructor accepts credentials as explicit parameters (already
  partially true — it currently reads `os.environ` inside `_client()`); a new `CredentialRepository`
  (or an extension of `ConnectorRecordRepository`) resolves a tenant's stored credentials and passes
  them in, rather than the connector reading `os.environ` itself when running in the tenant-aware path.
  The existing `os.environ`-reading path is kept as the fallback for the standalone/no-tenant CLI
  invocation documented in this service's README today (same "demote, don't delete" precedent as
  `INGEST-003`).
- [ ] `BinancePriceConnector`/`BlockchainInfoConnector` need **no** credential row (public,
  unauthenticated APIs, unchanged) — this story does not invent credentials these connectors don't
  need.
- [ ] **Disclosed security limitation, stated in this story itself, not discovered later**: unlike
  `gateway-api`'s API keys (which are one-way SHA-256 hashed, since the app only ever needs to *compare*
  a presented key, never send it anywhere), a Reddit client secret must be *used* — sent back to Reddit
  on every crawl — so it cannot be hashed at rest the same way. This story stores it at rest as
  plaintext in the `ingestion` schema, protected only by the same DB-access boundary (RLS,
  non-superuser app role, host-bound port) already protecting every other tenant-scoped row in this
  platform, not by field-level encryption — a real, accepted MVP risk, not a silently-assumed one.
  `ingestion-service/README.md` states this limitation explicitly and names its own trigger for
  revisiting it (a compliance requirement, or a real pilot client asking about at-rest credential
  encryption specifically) — same "disclosed interim, not silent" convention `SETUP-010`'s operator
  token already uses elsewhere in this repo.
- [ ] Tests prove tenant A's credentials are never returned/used for tenant B's crawl (cross-tenant
  isolation, same non-tautological "assert by id, not just count" discipline `VS-022`'s tests already
  established).

Rationale for priority: Must — without this, decision #4 (per-tenant credentials) has no concrete
mechanism, and the Reddit connector's only currently-documented behavior (one shared env var) directly
contradicts the per-tenant crawler model the task locks in.
Depends on: INGEST-002

### INGEST-005 — Per-tenant crawl-run tracking (replaces file-scanning watermark logic) [Must]

**As** each tenant's independently-triggered crawl **I want** a `crawl_runs` table (`tenant_id`,
`source`, `since_watermark`, `fetched_at`, `row_count`, `status`) recording every fetch attempt **so
that** "since" resolution becomes a tenant-scoped DB query (`INGEST-003`'s `latest_watermark_from_db`)
instead of depending on locally-written CSV files that won't exist once a tenant's crawl runs inside a
container with no persistent local disk of its own.

Acceptance criteria:
- [ ] `crawl_runs` row is written by the same `ConnectorRecordRepository`-family write path
  `INGEST-003` introduced, once per `fetch()` call, whether or not any new records came back (an
  empty-but-successful crawl is still a real, recorded run — mirrors `run_incremental`'s existing
  "no new rows, nothing written" print statement, now persisted instead of only printed).
- [ ] **Explicit, accepted tradeoff, named here rather than treated as an oversight to quietly work
  around**: because each tenant runs its own independent crawler against the same public sources
  (Binance, blockchain.info), N tenants produce N times the external API load for identical public
  data — this story does not attempt to deduplicate, share, or cache across tenants. This is the
  concrete cost of decision #4 (independent per-tenant crawlers), stated in `crawl_runs`' acceptance
  criteria and in `ingestion-service/README.md`'s design notes, not discovered as a surprise once real
  tenant volume exists.
- [ ] A test proves two tenants' crawls of the same source produce two independent `crawl_runs` rows
  and two independent watermarks — tenant A running ahead of tenant B (e.g. A has fetched more
  recently) never changes what `since` tenant B's next crawl resolves to.

Rationale for priority: Must — `INGEST-003`'s DB-write path is not usable in a real container
deployment without this; the CSV-file-scanning `latest_watermark` fundamentally assumes a persistent
local filesystem this platform's container model doesn't guarantee.
Depends on: INGEST-002, INGEST-003

### INGEST-006 — Regression test: existing connector `fetch()` behavior is unchanged [Should]

**As** the platform owner **I want** a test proving `INGEST-003`/`INGEST-004`/`INGEST-005`'s new
DB-write plumbing changed nothing about each connector's own `fetch(since)` logic (still the same
adapter contract, still the same causal-lag `fetched_at` semantics) **so that** the DB-integration work
in Epic A is provably additive, not a rewrite-in-disguise of the Adapter interface `implementation-plan.md`
section 7 names as the one this service must keep stable as new sources are added.

Acceptance criteria:
- [ ] Existing `tests/` for all three connectors' `fetch()` methods (pre-`INGEST-003` state) are
  re-run byte-for-byte unmodified and still pass.
- [ ] A new test asserts `IngestionSource.fetch`'s method signature (`fetch(self, since: datetime) ->
  FetchResult`) is unchanged — this is deliberately a structural check (same spirit as
  `NFE-018`/`LC-005`'s doc-sync checks), not a behavioral re-test of something `INGEST-003` didn't touch.

Rationale for priority: Should — real, cheap confidence that a genuinely additive change stayed
additive, but not blocking (the individual stories' own ACs already require unmodified-test-passage as
a condition, this just makes it one consolidated, explicit gate).
Depends on: INGEST-003, INGEST-004, INGEST-005

---

## Epic B — `ingestion-service` REST API + `gateway-api` proxy routes

### INGEST-007 — `ingestion-service` FastAPI app scaffolding [Must]

**As** `dashboard-web`'s future trigger-a-crawl action and `validation-service`'s future DB-backed
dataset picker **I want** `ingestion-service` to finally have an HTTP layer (`src/app/main.py`, a
`Dockerfile`, a `pyproject.toml`) **so that** it can be called over the network at all — today it is
connectors-only, runnable only as `python -m connectors.<name>` inside a shell.

Acceptance criteria:
- [ ] `services/ingestion-service/src/app/main.py` (FastAPI app), `Dockerfile`, `pyproject.toml`
  (`uv`-managed) exist, mirroring `validation-service`'s/`gateway-api`'s existing scaffolding shape
  (structured logging via `naive_first_common.configure_structured_logging`, `CorrelationIdMiddleware`,
  `GET /health` checking real DB connectivity per `OPS-005`'s established pattern).
  Existing `connectors/`/`tests/`/`requirements.txt` are kept in place (not moved into `src/app/`) —
  this story adds a service wrapper alongside the existing standalone-script layer, per the "demote,
  don't delete" precedent this backlog already applies elsewhere.
- [ ] Tenant resolution reuses `naive_first_common.get_tenant_context` (`Depends()`), the same way
  `validation-service`'s `VS-010` already does — no second tenant-resolution mechanism invented for a
  fourth service.
- [ ] `infra/docker-compose.yml` gains an `ingestion-service` entry, `127.0.0.1`-only host port binding
  (same convention as every internal-only service today), `DATABASE_URL` pointed at the non-superuser
  `naive_first_app` role (`INF-014`), never the migration-only `naive_first` role.
- [ ] `services/ingestion-service/README.md`'s status line is updated to state plainly: this is the
  disclosed override of trigger #6 named in this backlog's own disclosure section above — no pilot
  client has actually requested an upload API; this was built to unblock `INGEST-009`/`VS-023`/`DASH-108`
  instead.

Rationale for priority: Must — the literal foundation every other story in Epic B/C/E depends on;
without an HTTP layer, "trigger a crawl from the UI" and "pick a stored dataset" are both structurally
impossible, not just unbuilt.
Depends on: INGEST-002 (needs the schema to run a real `/health` DB check against)

### INGEST-008 — `POST /connectors/{source}/run`: tenant-authenticated crawl trigger [Must]

**As** `dashboard-web`'s Monitoring/ops screen (Epic E) **I want** an authenticated endpoint that runs
one tenant's crawl of one named source right now (not on a schedule) **so that** "run this tenant's
Binance crawler now" is a real, callable action instead of a `docker compose exec` step.

Acceptance criteria:
- [ ] `POST /connectors/{source}/run` (tenant-authenticated via `X-Tenant-Id`, same convention every
  other service in this platform already uses) resolves `source` to one of the three existing
  connectors, resolves the calling tenant's stored watermark (`INGEST-005`) and credentials
  (`INGEST-004`, for `reddit` only), calls `fetch()`, and writes the result via `INGEST-003`'s
  repository path — this is the same `run_incremental` sequence already encoded in each connector's
  `__main__` block, exposed as an endpoint rather than a shell invocation, not a second, divergent
  implementation of "run a crawl."
- [ ] Returns `202 Accepted` immediately with a `crawl_run_id` (execution may be synchronous for the
  MVP, matching `validation-service`'s own disclosed "synchronous execution" caveat for `POST /runs` —
  same accepted interim tradeoff, not a new one) or `200` with the completed `crawl_runs` row if
  execution stays synchronous; either way, the response references `INGEST-005`'s `crawl_runs` row so
  the caller (dashboard) can show a result.
- [ ] An unknown `source` value returns `404`, never a silent no-op.
- [ ] A tenant with no stored Reddit credentials calling `POST /connectors/reddit/run` gets a clear
  `422`/`409`-class error naming the missing credential, never an unhandled exception surfacing as a
  raw `500`.
- [ ] Tests cover: successful trigger writes real rows via a test-double repository, cross-tenant
  isolation (tenant A's trigger never touches tenant B's watermark/credentials/rows), unknown source,
  missing Reddit credential.

Rationale for priority: Must — the direct backend half of "trigger a crawl from the UI," the specific
capability named in decision #6 as the reason ingestion-service's REST API is being pulled forward now.
Depends on: INGEST-003, INGEST-004, INGEST-005, INGEST-007

### INGEST-009 — `GET /datasets` / `GET /datasets/{id}`: tenant-scoped ingested-series listing [Must]

**As** `validation-service`'s future DB-backed `DatasetSource` (`VS-023`) and `dashboard-web`'s future
"pick a stored dataset" UI (`DASH-108`) **I want** an endpoint listing a tenant's ingested series
(source, date range, row count) and one returning a specific series' data **so that** both consumers
have one real HTTP contract to call, instead of either reaching into the `ingestion` schema directly.

Acceptance criteria:
- [ ] `GET /datasets` (tenant-authenticated) returns one entry per distinct `(source, tenant_id)`
  combination present in `INGEST-002`'s tables — `id` (a stable, opaque identifier, e.g.
  `"{source}"` for now, since there is one series per source per tenant, not yet a general
  multi-dataset-per-source registry), `source`, `earliest_timestamp`, `latest_timestamp`, `row_count`.
  An empty-history tenant gets `200` with `"items": []`, never `404` — same "empty is a valid answer"
  convention `VS-022`'s `GET /runs` already established.
- [ ] `GET /datasets/{id}` (tenant-authenticated) returns the full tenant-scoped time series for that
  source as `{"timestamps": [...], "values": [...]}` — the exact shape
  `InlineOrLocalFileDatasetSource._parse_inline`'s dict form already accepts, so `VS-023` can reuse
  that existing parsing code rather than inventing a fifth shape.
- [ ] For a multi-column source (e.g. price OHLCV has open/high/low/close/volume, not one `value`
  column), this endpoint accepts a `field` query parameter (e.g. `?field=close`) naming which column to
  return as `values` — defaults documented explicitly (e.g. `close` for price, the metric's own single
  column for on-chain/sentiment sources) so `naive_first_engine`'s single-series expectation is met
  without this endpoint silently picking an undocumented column.
- [ ] Tenant isolation: a nonexistent dataset id and a dataset id that exists only for a different
  tenant both return `404`, same collapsed-error-shape convention `validation-service`'s `GET
  /runs/{id}` already uses (a `403`-shaped difference would itself leak existence).
- [ ] Tests cover empty-tenant listing, multi-field selection, and cross-tenant `404` collapsing.

Rationale for priority: Must — this is the other real backend unlock the whole "DB-backed dataset
picker" epic (C) is named after; `VS-023`/`DASH-108` cannot be built meaningfully without it.
Depends on: INGEST-002, INGEST-003, INGEST-007

### GW-019 — `gateway-api` proxy: `POST /ingestion/connectors/{source}/run` [Must]

**As** `dashboard-web`'s trigger-action UI **I want** `gateway-api` to proxy `INGEST-008`'s endpoint
**so that** `dashboard-web` never talks to `ingestion-service` directly, honoring
`implementation-plan.md`'s "`dashboard-web` calls `gateway-api` only, no direct DB access [or direct
service access]" rule the same way `GW-016`/`GW-018` already did for `validation-service`'s and
`reporting-service`'s endpoints.

Acceptance criteria:
- [ ] New `INGESTION_SERVICE_URL` env var (same convention as `VALIDATION_SERVICE_URL`/
  `REPORTING_SERVICE_URL`), a new `ingestion.py` router module (disjoint file from `runs.py`/
  `reports.py`, zero collision risk with `GW-016`/`GW-018`'s existing files).
- [ ] Reuses `GW-009`'s existing downstream-timeout/connection-failure-to-status-code handling
  unmodified — no new transport-error-handling pattern invented for a fourth downstream service.
- [ ] Forwards the caller's verified tenant identity the same way `GW-007`'s existing
  `build_downstream_headers` does for `validation-service` today — no new tenant-forwarding mechanism.
- [ ] Tests mirror `GW-016`'s existing proxy test shape (happy path, downstream timeout, downstream
  connection refused).

Rationale for priority: Must — without this, `dashboard-web`'s trigger-action story (`DASH-110`) would
either go unbuilt or would violate the platform's own service-boundary rule by calling
`ingestion-service` directly.
Depends on: INGEST-008

### GW-020 — `gateway-api` proxy: `GET /ingestion/datasets`, `GET /ingestion/datasets/{id}` [Must]

**As** `dashboard-web`'s "pick a stored dataset" UI **I want** `gateway-api` to proxy `INGEST-009`'s
two endpoints **so that** the dataset picker never talks to `ingestion-service` directly, same rule and
same precedent as `GW-019`.

Acceptance criteria: same shape as `GW-019`'s, applied to the two `GET` endpoints instead of the
`POST` one; reuses `RunSummaryResponse`'s precedent of importing shared response shapes from
`naive_first_common.contracts` rather than hand-duplicating field lists across `ingestion-service` and
`gateway-api` (a new `DatasetSummaryResponse` contract class added to `contracts.py` for this purpose).

Rationale for priority: Must — the other real backend unlock `DASH-108` needs; without it the "pick a
stored dataset" dropdown has nothing tenant-safe to call.
Depends on: INGEST-009

---

## Epic C — `validation-service` DB-backed dataset source + `dashboard-web` dataset picker

### VS-023 — `IngestionServiceDatasetSource`: a fourth `DatasetSource` backed by `ingestion-service`'s API [Must]

**As** `validation-service`'s `POST /runs` handler **I want** a new `DatasetSource` implementation that
loads a series by calling `ingestion-service`'s `GET /datasets/{id}` endpoint over HTTP (via internal
Compose hostname, the same direct-service-to-service-by-hostname pattern `reporting-service` already
uses to call `validation-service`) **so that** "pick a stored dataset" becomes a real, working
`dataset_reference` shape alongside today's `"inline"`/`"path"`/`"object_key"` options — **never** a
direct connection into the `ingestion` schema (see this backlog's Design decision section above).

Acceptance criteria:
- [ ] `dataset_source.py` gains `IngestionServiceDatasetSource`, implementing the same `DatasetSource`
  Protocol (`load(reference) -> pd.Series`), constructed with an `httpx` client and
  `ingestion-service`'s base URL — no `sqlalchemy`/`psycopg` import of any `ingestion.*` table anywhere
  in `validation-service`'s codebase (a `grep`-checkable acceptance criterion, mirroring `INGEST-002`'s
  own reverse check).
- [ ] `reference` shape: `{"dataset_id": "<source>", "field": "<optional column>"}` — a new, clearly
  distinct key from `"inline"`/`"path"`/`"object_key"`, so `CompositeDatasetSource`'s existing dispatch
  can add one more `elif` branch without ambiguity against the other three.
- [ ] `CompositeDatasetSource` is extended (not replaced) to also wrap this fourth source and dispatch
  on `"dataset_id"` — the existing three dispatch paths are unchanged, confirmed by the existing
  `tests/test_dataset_source.py` suite passing unmodified.
- [ ] Reuses `InlineOrLocalFileDatasetSource._build_series`/`_parse_inline`-equivalent logic for turning
  the fetched `{"timestamps": [...], "values": [...]}` JSON into the same validated `pd.Series` shape —
  no second timestamp/float-parsing implementation.
- [ ] A downstream `ingestion-service` failure (timeout, 404, malformed response) raises
  `DatasetSourceError`, the same exception type every other `DatasetSource` implementation already
  raises for a malformed/unreachable reference — `POST /runs`'s existing `VS-012` failure-handling
  `try`/`except` around `DatasetSource.load` needs no change to catch this new source's failures too.
- [ ] Tests cover: successful load, downstream 404 (unknown dataset id for this tenant), downstream
  timeout — using a fake `httpx` transport, never a real `ingestion-service` call.

Rationale for priority: Must — the concrete backend half of the task's single most important behavior
change ("submitting a validation run must gain a 'pick a stored dataset' path").
Depends on: INGEST-009 (or its Compose-internal reachability — `GW-020` is only needed for
`dashboard-web`'s path, not `validation-service`'s own direct-by-hostname call, matching the
`reporting-service`→`validation-service` precedent)

### VS-024 — `POST /runs`'s tenant identity is forwarded to `IngestionServiceDatasetSource` [Must]

**As** `validation-service`'s `POST /runs` handler **I want** the resolved `TenantContext` passed
through to `IngestionServiceDatasetSource.load` (as an `X-Tenant-Id` header on its own outbound call to
`ingestion-service`) **so that** a run submitted by tenant A can never load tenant B's stored dataset
merely by guessing/reusing a `dataset_id` string, even though `dataset_id` values look identical across
tenants (e.g. every tenant's Binance series is named `"binance_price_btcusdt_1h"`).

Acceptance criteria:
- [ ] `dependencies/repositories.py`'s `get_dataset_source()` provider is extended to inject the
  current request's tenant id into the constructed `IngestionServiceDatasetSource` call, not left for
  the handler to thread through manually a second time.
- [ ] A test proves: tenant A's `POST /runs` with `dataset_reference={"dataset_id": "binance_price_..."}`
  loads tenant A's own series even when tenant B has a same-named series with different values — a
  non-tautological check (asserts on the actual loaded values, not just that a series came back).

Rationale for priority: Must — without this, `VS-023`'s new source path would be a real, live
cross-tenant data leak, not a hypothetical one; this is exactly the kind of gap this backlog's own
review discipline exists to catch before it ships, not after.
Depends on: VS-023

### DASH-108 — `dashboard-web`: "pick a stored dataset" option on the submit-run form [Must]

**As** an operator or tenant user submitting a validation run **I want** the submit-run form to offer a
"pick a stored dataset" option (a dropdown populated from `GW-020`'s proxied `GET
/ingestion/datasets`) alongside today's inline/file-path options **so that** a tenant with real ingested
data never has to hand-construct an inline JSON payload just to validate against their own already-
ingested series.

Acceptance criteria:
- [ ] The submit-run form gains a third input mode (radio/tab: "Inline data" / "Local file path" /
  "Stored dataset"), consistent with whatever UI pattern the existing two modes already use — no
  redesign of the existing two paths.
- [ ] "Stored dataset" mode calls `GW-020`'s `GET /ingestion/datasets` to populate the dropdown
  (source, date range, row count shown per option) and submits `dataset_reference={"dataset_id":
  <selected>, "field": <selected, if applicable>}` to `POST /runs` — the exact shape `VS-023` expects,
  confirmed by an end-to-end test against a stubbed `gateway-api`.
- [ ] An empty-history tenant sees a clear "no ingested datasets yet — run a crawl first" state, not an
  empty, unexplained dropdown — links to `DASH-110`'s trigger-a-crawl action as the next step.
- [ ] Extends `dashboard-web`'s existing Selenium E2E suite (`DASH-009`'s precedent) with this third
  submission path.
- [ ] Positioning check: no copy on this form implies the platform is sourcing "trading data" or
  "signals" — it is described as "your ingested data," consistent with CLAUDE.md's positioning rule.

Rationale for priority: Must — the actual user-facing deliverable the task names as "the single most
important behavior change," on the UI side.
Depends on: GW-020, VS-024 (both needed for the full round trip to be real, not just a UI stub)

---

## Epic D — Historical CSV backfill migration

### INGEST-010 — One-time backfill: load `data/raw/_platform/...` CSVs into the `ingestion` schema [Must]

**As** the platform owner **I want** a one-time, re-runnable-without-duplication migration script that
reads every existing seed + incremental CSV under `data/raw/_platform/...` and writes it into
`INGEST-002`'s Postgres tables **so that** the historical data these connectors have already collected
(price back to 2018, on-chain back to 2009, Reddit sentiment collected so far) isn't stranded on local
disk in a second, inconsistent storage location once the DB becomes the real system of record.

Acceptance criteria:
- [ ] A standalone script (`scripts/backfill_from_csv.py`, matching `provision_tenant.py`'s
  "standalone, operator-run, not part of the request path" convention) reads each source's `seed/` and
  `incremental/` directories (per `PROVENANCE.md`'s documented layout) and writes rows via `INGEST-003`'s
  same repository interface — no second, divergent CSV-parsing/DB-writing code path.
- [ ] Idempotent: running the script twice does not duplicate rows — either an upsert keyed on
  `(tenant_id, source, timestamp)` or a pre-check per source/tenant, matching the "re-running the golden
  path is a safe no-op" convention `SETUP-004`/`INF-016` already established elsewhere in this platform.
- [ ] **Open product question, flagged explicitly here rather than silently resolved by whoever
  implements this** (per this backlog's own instruction not to assume an answer): the existing CSVs
  are platform-wide/undifferentiated (collected before any tenant concept existed), but the new schema
  is strictly per-tenant. This script needs the founder's decision on **which tenant(s) the backfilled
  data gets attached to** — the two live options, neither silently chosen here:
  1. **Attach to every existing tenant at backfill time** (each tenant gets its own full copy of the
     historical rows) — maximizes "every tenant sees real history immediately," at the cost of N
     redundant copies of what is, historically, the same platform-collected data (the same tradeoff
     already accepted for going-forward crawls per decision #4, extended backward).
  2. **Attach only to one designated "seed"/demo tenant** — avoids redundant storage of
     platform-collected historical data, but means new pilot tenants start with empty ingested history
     until their own crawler runs, which may be the more honest reflection of "this tenant's own
     independent crawler" (decision #4's own framing) but is a worse first-run demo experience.
  This story's own Definition of Done includes recording the founder's actual choice in
  `services/ingestion-service/README.md`'s backfill section — not defaulting to either option
  unstated.
- [ ] `PROVENANCE.md`'s existing per-source seed/coverage notes (raw/processed boundary caveat for
  price, the Kaggle-sentiment-discontinuity note, the licensing-review-not-done flag) are copied into
  `ingestion-service/README.md`'s new backfill section, not lost in the move from file-based to
  DB-based storage — a future reader of the DB rows alone shouldn't lose the caveats the CSV
  `PROVENANCE.md` file currently carries.
- [ ] A dry-run mode (`--dry-run`) prints row counts per source/tenant without writing, so the founder
  can sanity-check the backfill's shape before committing to whichever tenant-attachment answer above
  is chosen.

Rationale for priority: Must — named explicitly in the task as a required epic, and blocks
`INGEST-009`/`VS-023`/`DASH-108` from having any real historical data to show on day one (without this,
those stories only work for data ingested *after* this backlog ships, which is a materially worse pilot
demo than "here's five years of BTC price history already validated-ready").
Depends on: INGEST-002, INGEST-003. **Blocked on founder decision** (tenant-attachment choice above) —
flagged to the requester in this backlog's closing summary, not silently defaulted.

---

## Epic E — Unified ops dashboard (reconciled against `backlog-first-run-setup-and-ops.md`)

**Reconciliation statement, per this backlog's own governing instruction not to produce two competing
specs for the same screen**:

- **`SETUP-020`** ("Per-service health status surfaced in `dashboard-web`") is **extended, not
  duplicated**, by `DASH-109` below — `SETUP-020`'s own acceptance criteria (aggregate `/system/health`
  endpoint, one row per service) stay valid; `DASH-109` is the follow-up ticket that adds
  `ingestion-service` as a fourth row once it exists, the same way `SETUP-020` itself only covered the
  three services that existed when it was written. Recommend: keep `SETUP-020` as-is (it's already
  built or buildable against three services), schedule `DASH-109` as its explicit sequel — do not
  rewrite `SETUP-020`'s own text.
- **`SETUP-013`** ("Connector schedule/credential configuration in Settings") was correctly marked
  `Won't, this backlog` in `backlog-first-run-setup-and-ops.md` **because `ingestion-service` didn't
  exist as code yet** — its own stated rationale was "revisit the moment `ingestion-service` is
  scaffolded; its own backlog is the right place for its first Settings-surfaced config, not this one."
  This is that backlog. **`DASH-112` below supersedes `SETUP-013`** — recommend marking `SETUP-013` in
  `backlog-first-run-setup-and-ops.md` as "superseded by `DASH-112`, see
  `backlog-ingestion-pipeline-integration.md`" rather than leaving it as a permanent `Won't` now that
  its own named blocking condition has been resolved by this backlog.
- **`SETUP-022`** ("run throughput and failure rate") is untouched — it's specific to
  `validation-service`'s run pipeline, no overlap with ingestion status.
- **`SETUP-010`/`011`/`012`** (operator auth, tenant list/create/revoke, Settings → Tenants page) are
  untouched and are a hard dependency of `DASH-112` below (connector credential management is exactly
  the kind of cross-tenant-adjacent operator action `SETUP-010`'s operator credential was built to
  gate) — `DASH-112` reuses that mechanism, does not invent a second one.

### DASH-109 — Monitoring page: add `ingestion-service` as a fourth per-tenant status row [Must]

**As** an operator **I want** the Monitoring page (`SETUP-020`) extended with one row per tenant's
connector (source, last `crawl_runs` status/timestamp, last watermark) **so that** ingestion health is
visible from the same screen as `gateway-api`/`validation-service`/`reporting-service` health, once
`ingestion-service` exists.

Acceptance criteria:
- [ ] `gateway-api`'s aggregate `GET /system/health` (`SETUP-020`) is extended to also proxy
  `ingestion-service`'s `/health` — reuses `GW-009`'s existing failure-handling, no new pattern.
- [ ] A new panel (below or beside `SETUP-020`'s per-service row list, not a competing second
  Monitoring page) lists, per source, the calling tenant's own `crawl_runs` history (via `GW-019`'s
  proxy — or a new small `GET /ingestion/connectors/status` summary endpoint if per-row listing proves
  too chatty for a dashboard poll, at the implementer's discretion) — labeled plainly as "last crawl
  status," never implying anything about the ingested data's predictive value (CLAUDE.md positioning
  rule).
- [ ] Reuses `SETUP-020`'s existing all-healthy/one-degraded/unreachable-transport test pattern, applied
  to the fourth service.

Rationale for priority: Must — the ingestion-status half of the task's "unified ops dashboard" ask;
without it, the ops dashboard's cross-component promise is missing exactly the component this backlog
just built.
Depends on: INGEST-007 (ingestion-service `/health` must exist), SETUP-020 (already built or in flight)

### DASH-110 — Trigger-action UI: "run this tenant's crawl now" / "generate a report" [Must]

**As** an operator **I want** buttons on the Monitoring/ops screen that call `GW-019`'s crawl-trigger
proxy and `reporting-service`'s already-existing report-generation endpoint (via its own existing
`gateway-api` proxy, `GW-018`) **so that** "manage everything in one place... trigger safe actions on
all of them from one screen" (decision #6) is real, while staying strictly within "normal
authenticated API calls, not infrastructure control" (the same decision's explicit boundary — no
Docker socket, no container start/stop/restart anywhere in this story).

Acceptance criteria:
- [ ] Per-source "Run this tenant's {Binance/on-chain/Reddit} crawl now" buttons call `GW-019`'s `POST
  /ingestion/connectors/{source}/run` and show the resulting `crawl_run_id`/status inline (no full-page
  reload required, consistent with `SETUP-012`'s existing revoke-and-re-render pattern).
- [ ] "Generate a report" button calls the **already-existing** `reporting-service`
  `POST /reports/generate` via `GW-018`'s **already-existing** proxy — this story adds a UI trigger for
  a capability that already exists end-to-end, it does not add a new reporting capability.
- [ ] Every button's failure path (downstream 5xx/timeout) renders the existing `error.html` convention
  (`DASH-004`'s `_render_error_for_status` helper) — no new error-handling pattern invented for this
  screen.
- [ ] Structural proof (not just a written policy) that no route on this page can reach the Docker
  socket or issue a `docker compose` command: grep-confirmed zero references to `docker`,
  `subprocess`, or the Docker socket path anywhere in `dashboard-web`'s codebase after this story.

Rationale for priority: Must — the literal capability decision #6 names ("trigger safe actions... from
one screen"), and the story's own AC is written to make the declined Docker-control option structurally
impossible, not just avoided by convention.
Depends on: GW-019, GW-018 (already done, Sprint 14)

### DASH-111 — Dataset browsing view (reuses `DASH-108`'s data, different presentation) [Should]

**As** an operator **I want** a dedicated page listing all of a tenant's ingested datasets (same data
`GW-020`'s `GET /ingestion/datasets` already returns) with last-updated timestamps **so that** "see data
... for every component" (decision #6) includes ingestion's own ingested data, not only run/report
status.

Acceptance criteria:
- [ ] Reuses `GW-020`'s existing proxy call and `DASH-108`'s existing dropdown-population code path
  (extracted into one shared component/partial, not two near-identical implementations of "call `GET
  /ingestion/datasets` and render it" — DRY within `dashboard-web`'s own boundary per
  `implementation-plan.md` section 9).
- [ ] Links directly into `DASH-108`'s submit-run form (pre-selecting the "Stored dataset" mode) and
  into `DASH-110`'s trigger-a-crawl action for the same source — one screen, cross-navigable, per
  decision #6's "let an operator navigate between... all of them from one screen."

Rationale for priority: Should — real value, but strictly a presentation layer over data `DASH-108`
already fetches; not on the critical path the way the Must stories in this epic are.
Depends on: DASH-108, GW-020

### DASH-112 — Settings: per-tenant connector credential management [Should]

**As** an operator **I want** a Settings page (gated by `SETUP-010`'s operator credential, not any
tenant's own session) to view which sources have stored credentials per tenant and set/rotate a
tenant's Reddit credentials **so that** `INGEST-004`'s credential storage has a real UI instead of
requiring direct DB access to populate — **this supersedes `backlog-first-run-setup-and-ops.md`'s
`SETUP-013`**, which declined this exact capability only because `ingestion-service` didn't exist yet.

Acceptance criteria:
- [ ] `/settings/connectors` requires the operator credential (`SETUP-010`), same gating as
  `/settings/tenants` (`SETUP-012`) — no tenant's own session can reach it, consistent with that page's
  own established boundary.
- [ ] Lists, per tenant, which sources have credentials stored (boolean/status only — never displays
  the stored secret value once set, mirroring the one-time-reveal discipline `SETUP-003`/`SETUP-012`
  already established for API keys, even though this is a different kind of secret with a different
  at-rest-storage caveat, per `INGEST-004`'s disclosed limitation). Positioning check: no copy on this
  page implies trading/prediction capability (CLAUDE.md).
- [ ] "Set/rotate Reddit credentials" form posts to a new operator-authenticated `gateway-api` proxy of
  `ingestion-service`'s credential-write endpoint (a small addition to `INGEST-004`'s scope, or a
  follow-up ticket if `INGEST-004` shipped read/resolve-only — flagged here as a possible scope
  gap for the PM to confirm at sequencing time, not silently assumed covered).
- [ ] `backlog-first-run-setup-and-ops.md`'s `SETUP-013` entry is annotated (not deleted — preserves
  the historical record of why it was declined at the time) as superseded by this ticket.

Rationale for priority: Should — real operator value, and the correct place (per `SETUP-013`'s own
stated deferral condition) to finally build this, but not blocking the core "system works with that
database" pipeline the Must stories in Epics A–D deliver; a tenant can still be given credentials via
direct DB write (or a CLI script, mirroring `provision_tenant.py`'s precedent) until this ships.
Depends on: INGEST-004, SETUP-010 (already built or in flight)

---

## Summary

15 distinct Must stories, 4 Should stories, 0 Could, 0 Won't — **19 stories total**, across five
epics and five modules (`ingestion-service`, `libs/common`, `validation-service`, `dashboard-web`,
`gateway-api`).

| Priority | Count | IDs |
|---|---|---|
| Must | 15 | INGEST-002, INGEST-003, INGEST-004, INGEST-005, INGEST-007, INGEST-008, INGEST-009, INGEST-010, LC-010, VS-023, VS-024, DASH-108, DASH-109, DASH-110, GW-019, GW-020 |
| Should | 4 | INGEST-006, DASH-111, DASH-112 |
| Could | 0 | — |
| Won't | 0 | — (this backlog proposes no explicit declines of its own; it resolves/supersedes `SETUP-013` from the prior backlog instead) |

(Note: the Must row above lists 16 IDs because `GW-019`/`GW-020` are two separate tickets — the row
count of "15" refers to distinct pieces of work if `GW-019`/`GW-020` were counted as one proxy-layer
unit; treat 16 as the literal Must ticket count, 19 as the literal total ticket count.)

Sequencing note for the PM/Tech Lead: the dependency chain is genuinely linear across most of this
backlog, unusually so for this repo — `INGEST-002` (schema) and `LC-010` (DRY extraction) can run in
parallel first; `INGEST-003/004/005` depend on both and on each other in the order listed;
`INGEST-007` (API scaffolding) can start as soon as `INGEST-002` exists (it only needs the schema for
its `/health` check) and doesn't need to wait for `003/004/005` to finish, but `INGEST-008`/`INGEST-009`
(the actual endpoints) do need them; `GW-019`/`GW-020` are thin proxies that can start the moment their
respective `INGEST-008`/`INGEST-009` endpoints exist; `VS-023/024` and `DASH-108` are the last real
links before Epic C's "pick a stored dataset" promise is end-to-end true; `INGEST-010` (backfill) can
run any time after `INGEST-002`/`003` but is explicitly blocked on the founder's tenant-attachment
decision, not on any other story's completion; Epic E's stories are the most independent of the set and
can be scheduled opportunistically once their individual dependencies land.

## Open product questions for the founder (flag before PM sequencing)

1. **Backfill tenant attachment (`INGEST-010`)** — attach the existing platform-wide CSV history to
   every existing tenant, or only to one designated seed/demo tenant? This backlog does not choose for
   you; see `INGEST-010`'s own acceptance criteria for the two live options and their tradeoffs.
2. **Reddit credential encryption at rest (`INGEST-004`)** — this backlog accepts plaintext-at-rest
   (protected only by RLS/DB-access boundaries, the same posture the rest of this platform already
   applies to non-API-key secrets) as the MVP posture, explicitly disclosed rather than silently
   assumed. Confirm this is acceptable for your actual pilot clients' expectations, or flag if
   field-level encryption needs to be pulled forward as its own story.
3. **`INGEST-004`'s credential-write endpoint** — `DASH-112` assumes `ingestion-service` exposes a way
   to *set* a tenant's credentials over HTTP, not just resolve/read them for a connector's own use.
   Confirm whether that write path belongs inside `INGEST-004`'s own scope or should be split into its
   own ticket at sequencing time.
4. **`GET /datasets/{id}`'s multi-column `field` parameter (`INGEST-009`)** — confirm the proposed
   default field per source (e.g. `close` for price OHLCV) matches what you'd actually want a tenant's
   first validation run to default to, rather than assuming `close` is obviously correct for every use
   case.
5. **N-times redundant external API load (decision #4, `INGEST-005`)** — confirmed accepted per your
   own decision, restated here only so it's visible in one place alongside the other open questions:
   at real pilot scale (more than a handful of tenants), Binance/blockchain.info's public rate limits
   may need revisiting even though no per-tenant credential exists for those two sources to gate
   against — no story in this backlog proposes a shared-cache mitigation, since you explicitly framed
   this as an accepted tradeoff, not a bug.
