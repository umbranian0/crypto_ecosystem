# Sprint 62 — Epic D onboarding (ONB-001, ONB-002) in `services/dashboard-web` (+ one possible minimal gateway-api endpoint)

Sprint goal: by the end of this sprint, a fresh operator who finishes the setup wizard is pointed to a concrete
next step and can launch a clearly-labeled "demo run" (sample data, fixed illustrative configuration, honest
naive-first result) from the browser without any CLI or container access.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md`, Epic D (`ONB-001`, `ONB-002`, both Should, both
already approved/prioritized). Capacity: not stated by the requester; two small stories, no capacity claim made.

## Independent verification (code read, not taken from the backlog)

- **Neither story is done.** `services/dashboard-web/src/app/routers/setup.py` renders `setup_key_reveal.html`
  (a 6-line wrapper including `_setup_key_reveal.html`, itself a thin wrapper over the shared
  `_one_time_reveal.html`) with only `tenant_name`/`api_key` and a single "Continue to log in" link. No "what's
  next" section exists. Grep of `dashboard-web/src` for `demo`/`seed_tenant` finds only the unrelated
  `/help/leakage-demo` (TRUST-002) page; no `/demo-run` route exists.
- **Finding that changes ONB-002's shape: seeding is no longer CLI-only.** The backlog (written earlier)
  describes `INGEST-010` as CLI/operator-only. Since then, `INGEST-030` (`ingestion-service`
  `POST /internal/seed-platform-history`, `X-Internal-Token`, body `{tenant_id}`, idempotent, calls
  `seed_tenant_platform_history` directly) and `GW-030` (`gateway-api/src/app/provisioning.py::provision()`
  calls that endpoint after creating a tenant, degraded-not-blocking) shipped. `POST /setup/initialize` and
  `POST /tenants` both use `provision()`. So **a tenant created through the wizard is already auto-seeded**, and
  ONB-001's AC text ("sample data can be seeded via `seed_tenant.py`") is now stale/misleading for that
  path. The seed only fails to happen when the GW-030 call degraded (logged `tenant_seed_degraded`), or for
  tenants created before GW-030.
- **How dashboard-web can reach seeding today, HTTP-only:** it cannot trigger it. `/internal/seed-platform-history`
  needs `INGESTION_INTERNAL_TOKEN`, which only gateway-api holds; gateway-api's tenant-facing ingestion routes
  (`routers/ingestion.py`: connector run/status/cancel, `GET /ingestion/datasets`, series) have no seed route.
  What dashboard-web can already do is read `GET /ingestion/datasets` (used by `run_new_form`/`/datasets`) to
  detect "tenant has no ingested data".
- **Session gating:** the key-reveal page is pre-login (no session), and `/login` has no `next` redirect
  support. Any demo action needing the tenant's API key (`POST /runs` via `DownstreamHeadersDep`) can only be
  invoked post-login. So the key-reveal page can only *link toward* the demo; the button itself must live on a
  post-login page.
- `RunRequest` (libs/common `contracts.py`) requires `dataset_id`, `dataset_reference`, `horizon`,
  `purge_gap_hours`, `train_window`, `test_window`, `step`; `run_new_submit` already posts `/runs` through the
  shared downstream-call helper. `dataset_reference` already supports the "Stored dataset" source mode (DASH-108).

## Decision needing the user (blocks the exact shape of ONB-002 part (a))

The ONB-002 AC says the demo action seeds "if the tenant has no ingested data yet". Given the finding above:

- **Option A (recommended, YAGNI): no new endpoint.** `POST /demo-run` checks `GET /ingestion/datasets`; if the
  price dataset is present, it submits the demo run. If empty (seed degraded / pre-GW-030 tenant), it renders an
  explicit "sample data is not loaded for this tenant; ask your operator to seed it" message instead of
  failing opaquely. Zero new cross-service surface. Cost: AC (a)'s "trigger seeding" is satisfied only by
  the already-shipped GW-030 auto-seed, not by the demo action itself; the backlog AC must be amended to say
  so (PO call, recorded in the backlog status note).
- **Option B: one new minimal gateway-api endpoint**, e.g. tenant-authenticated `POST /ingestion/seed-demo`,
  which takes `tenant_id` from the authenticated tenant (never from the body), reuses the existing
  `_seed_platform_history` helper/ingestion client in `provisioning.py`, and returns the row-count summary.
  dashboard-web calls it when datasets are empty. No new ingestion-service endpoint is needed (INGEST-030
  already exists). Honors the literal AC; adds one gateway route plus tests, and the tenant-scoping rule
  (cannot seed another tenant) becomes a required test.

If the user does not choose, the plan proceeds with **Option A**. Under neither option is a new
ingestion-service endpoint required.

## Stories in scope, in execution order

1. **ONB-001** — "What's next" section on `setup_key_reveal.html` only (not on the shared `_one_time_reveal.html`,
   which SETUP-012's Settings reveal also uses). Links to `/login` first, then `/runs/new` and the demo entry;
   copy describes submitting a validation run and sample data only. Copy about seeding must reflect reality
   (new tenants are auto-seeded; the demo action covers the rest), not `seed_tenant.py`. No change to
   SETUP-002/003 creation logic. Order: first, per the backlog's stated dependency (it is the surface that
   ONB-002's entry point hangs off).
2. **ONB-002** — `POST /demo-run` (post-login, session-gated like other `dashboard-web` actions) plus a
   clearly-labeled entry point reachable from ONB-001's next-step links after login. Submits one run with a
   fixed, disclosed config held in dashboard-web code, never as form defaults. Order: second, depends on
   ONB-001 and on INGEST-010/030/GW-030 (all shipped).

## Binding constraints carried into tickets

- Do not touch `run_new.html` defaults (DASH-006 no-pre-filled-defaults rule). Demo config lives only in the
  demo action's own code/page, and the demo page and the resulting run's detail view carry the literal
  statement "demo configuration -- not a recommended default for your own data".
- Result presented with the same honest naive-first framing (TRUST-005) as any run; no curated "impressive"
  example, no "first prediction"/signal/forecast language anywhere; no green/red pairing.
- Idempotent: repeat clicks do not duplicate seeded rows (INGEST-010 guarantee) and just submit another run.
- Boundary rules: dashboard-web uses only gateway-api HTTP; no imports from other services; gateway-api
  (Option B only) must not reimplement seeding.
- Demo config values (horizon/windows/gap) must be chosen so a run actually produces splits on the seeded
  dataset; Tech Lead to validate against the real seeded data, since the engine silently yields zero splits on
  bad config.
- How to mark a run as "demo" for the run-detail disclosure (new field vs. reuse of existing metadata vs.
  query flag on redirect) is a Tech Lead decision; prefer no new validation-service schema change if a simpler
  mechanism suffices.

## Stories explicitly deferred

- ADMIN-005, other Epic A-C stories: untouched, carried forward (see sprint-61 "Next").
- `ONB-003`: Won't (duplicate of RPT-003), not pulled in.
- The `DBOPT-*` follow-ups listed in sprint-61 "Next": not in this sprint.

## Definition of done

- ONB-001 and ONB-002 acceptance criteria (amended per the user's Option A/B decision) checked in their tickets.
- Tests: next-step section renders on the key reveal and not on the SETUP-012 reveal; no key leaks into URLs
  or logs; `/demo-run` happy path, empty-dataset path, repeat-click idempotency, unauthenticated rejection;
  `run_new.html` unchanged (assert no defaults); demo disclosure present on the run detail; Option B only:
  tenant-scoping/cross-tenant test and token never exposed to dashboard-web.
- Positioning grep (prediction/forecast/signal/recommend, green/red) over every touched template and route.
- READMEs updated as shipped: `services/dashboard-web/README.md` (new routes), and `services/gateway-api/README.md`
  if Option B. `docs/tickets/README.md` gets a Sprint 62 section; `docs/product/backlog-trust-and-admin-ops.md`
  ONB-001/ONB-002 statuses updated in place (including correcting the stale "CLI/operator-only" wording).
- QA gate (mandatory): Tech Lead raises the `qa` agent (`/qa-validation`) after tickets are done. QA runs
  against the real rebuilt `naive-first-*` Docker containers (check the images are not stale first; host-run
  scripts hit a stale SQLite copy): fresh-tenant wizard to key reveal to login to demo run to a run detail
  with the demo disclosure and the real naive-first outcome; a tenant with empty datasets exercises the empty
  path; repeat click shows no duplicated dataset rows; `/runs/new` still shows no pre-filled values. Any
  fixture tenants/keys QA creates must be cleaned up afterwards.

## Next (not this sprint)

Standing candidate: ADMIN-005 (self-serve key rotation, lockout-guard risk, `/grilling` first), and the
`split_points` index / `get_splits` `test_start`-predicate DBA follow-ups from sprint-61.

## Tech Lead execution notes

- Orchestrator decision: Option A (no new endpoint). Backlog ONB-001/002 ACs amended in place and disclosed.
- Deviation found at validation time: stored price `close` is rejected by the MR-001 guardrail, so the demo
  run targets `volume` of `binance_price_btcusdt_1h` (2024-01-01..2024-03-01, horizon 1, gap 24, train 500,
  test 100, step 100 -> 9 splits on the real stack), disclosed on the page.
- Disclosure mechanism: `RunRequest.label` (no schema change); run detail already renders the label.
