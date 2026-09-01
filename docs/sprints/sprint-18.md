# Sprint 18 — Per-tenant TimescaleDB ingestion pipeline, ingestion-service API, dataset picker, ops dashboard

Source: `docs/product/backlog-ingestion-pipeline-integration.md` (backlog), `docs/solution-design.md`
section 8 (binding technical design, supersedes the backlog's `INGEST-009`/`VS-023`/`DASH-108`
sketches where noted), `docs/adr/0004-tenant-credential-encryption-at-rest.md`,
`docs/adr/0005-dataset-is-a-continuous-tenant-source-table.md`, `CONTEXT.md`'s "Dataset"/"Seed data"
glossary entries, `docs/product/backlog-first-run-setup-and-ops.md` (sibling backlog — `SETUP-010`
operator auth and `SETUP-020` Monitoring page are **not** part of this sprint; three Epic E tickets
below are sequenced but flagged `blocked` on that backlog's own delivery, not silently built around).

This sprint's ticket IDs follow the backlog's own numbering where the backlog already assigned one
(`INGEST-002`…`010`, `LC-010`, `VS-023`/`024`, `GW-019`/`020`, `DASH-108`…`112`). One new ticket not
in the original backlog, `INGEST-011` (credential encryption primitive), is added because
`docs/solution-design.md` section 8.5/ADR-0004 revised `INGEST-004`'s original plaintext-at-rest
posture to Fernet encryption after the backlog was written — the primitive is small and dependency-free
enough to be its own ticket rather than inflating `INGEST-004`'s scope.

## Binding technical refinements this sprint carries (do not re-litigate)

1. **Dataset = `{tenant_id, source}` continuous table, not a snapshot** (ADR-0005). Every dataset-read
   endpoint/reference shape takes `start`/`end`, not a static id.
2. **`GET /datasets/{id}` → `GET /datasets/{source}/series?start=&end=&field=`** (supersedes the
   backlog's `INGEST-009` sketch). `GET /datasets` remains a discovery-only list.
3. **`VS-023`'s `dataset_reference` shape → `{"source", "start", "end", "field"}`**, a fourth,
   distinct key from `"inline"`/`"path"`/`"object_key"` (supersedes the backlog's `{"dataset_id",
   "field"}` sketch).
4. **`DASH-108`'s "stored dataset" mode needs date-range inputs**, not just a dropdown (supersedes the
   backlog's sketch, which predates the continuous-table decision).
5. **`INGEST-004`'s credentials are encrypted at rest via Fernet** (ADR-0004), not plaintext as the
   backlog originally, explicitly, disclosed as an open question.
6. **`INGEST-010` → a repeatable `scripts/seed_tenant.py --tenant-id --source --from [--dry-run]`
   CLI**, not a one-time script — the historical CSV archive is one `--from` option among others.

## Three decisions adopted by default, not user-confirmed (flag to requester, per solution-design.md 8.9)

- **(a)** Credential-write UI (`DASH-112`'s "set/rotate" form) is deferred to a later phase. CLI-only
  (`scripts/set_connector_credentials.py`) for now. `DASH-112` in this sprint ships **read-only**
  status only.
- **(b)** Dashboard operator auth is `SETUP-010`'s single shared `OPERATOR_TOKEN`, not multi-admin.
- **(c)** `SETUP-002`'s bootstrap endpoint is protected by a one-time setup secret, not loopback-binding.

None of these three were re-litigated by this Tech Lead — they are carried into ticket ACs as given.

## Open questions NOT resolved by this sprint (flagged to requester, tickets build the general
capability so any answer is a config choice, not a design fork)

1. Backfill tenant attachment (`INGEST-010`) — every existing tenant vs. one designated seed tenant.
2. `field` defaults per source (`close`/`value`/`reddit_sid_com`) — implemented as documented defaults,
   need product confirmation.
3. `INGESTION_CREDENTIAL_ENCRYPTION_KEY` has no rotation/recovery path — accepted MVP gap, decide if
   in-scope later.

## Dependency chain (per solution-design.md 8.8) and ticket sequencing

| Batch | Tickets | Depends on | Parallel? |
|---|---|---|---|
| 1 | `INGEST-002` (schema+hypertables+RLS), `LC-010` (tenant_scope extraction), `INGEST-011` (Fernet encryption primitive) | none | Yes — 3 disjoint modules/files, launched together |
| 2 | `INGEST-003` (connectors → DB), `INGEST-007` (FastAPI scaffolding) | `INGEST-002`, `LC-010` (003 only); `INGEST-002` (007 only) | Yes — disjoint files (`connectors/`+new repository vs `src/app/main.py`+`Dockerfile`) |
| 3 | `INGEST-004` (credentials, encrypted), `INGEST-005` (crawl-run tracking) | `INGEST-003`, `INGEST-011` (004); `INGEST-003` (005) | No — both extend the same `ConnectorRecordRepository` file; run 004 then 005 sequentially |
| 4 | `INGEST-006` (regression test) | `INGEST-003/004/005` | — |
| 5 | `INGEST-008` (`POST /connectors/{source}/run`), `INGEST-009` (`GET /datasets`, `GET /datasets/{source}/series`) | `INGEST-003/004/005/007` | Yes — separate router files |
| 6 | `GW-019` (proxy crawl-trigger), `GW-020` (proxy datasets) | `INGEST-008`; `INGEST-009` | Yes — separate router files |
| 7 | `VS-023` (`IngestionServiceDatasetSource`), `VS-024` (tenant-forwarding) | `INGEST-009` reachable by hostname (023); `VS-023` (024) | No — same file(s), sequential |
| 8 | `DASH-108` (dataset picker, date-range), `DASH-111` (dataset browsing page) | `GW-020`, `VS-024` (108); `DASH-108`, `GW-020` (111) | 111 after 108 (reuses its component) |
| 9 | `DASH-109`, `DASH-110`, `DASH-112` (read-only) | `INGEST-007`'s `/health`, **and** `SETUP-020`/`SETUP-010` from the sibling backlog | **Blocked** — sibling backlog not scheduled this sprint |
| any time after Batch 2 | `INGEST-010` (`seed_tenant.py`) | `INGEST-003` | Blocked only on founder's tenant-attachment decision, not on other tickets |

Batches 1–2 are started now (this sprint's opening squad). Batches 3+ are queued, each raised once its
predecessor batch is verified done — per the standing sequential/parallel rule for this repo (same-file
tickets never run concurrently).

## Standing safety rule (repeated in every dev handoff, non-negotiable)

Never run `git reset`, `git checkout -- <file>`, `git clean`, or any command that could discard
uncommitted changes. If a file write fails (OneDrive-sync ENOENT), write to the scratchpad and copy
into place via PowerShell `[System.IO.File]::WriteAllText(path, content,
[System.Text.UTF8Encoding]::new($false))` — never troubleshoot by resetting git state. Never run
`git add -A` or a broad `git add`.


## Addendum (post-launch): requester resolved all open blocking questions, sprint proceeds autonomously

The requester reviewed this sprint's open questions and resolved them as follows — no further
check-ins on these points:

1. **`DASH-109`/`110`/`112` unblocked**: rather than waiting on the sibling
   `backlog-first-run-setup-and-ops.md`'s own scheduling, this sprint pulls in the **minimal slice**
   needed: `GW-021` (a bare operator-token dependency, single shared `OPERATOR_TOKEN` env var — not
   `SETUP-011`'s full `/tenants` CRUD) and `GW-022` (a bare aggregate `GET /system/health` — not
   `SETUP-020`'s/`021`'s/`022`'s full Monitoring epic with recent-errors/throughput), plus `DASH-113`
   (a bare `/monitoring` page + operator-session gate for `/settings/*` — not `SETUP-003`'s setup
   wizard or `SETUP-012`'s full tenant-management UI). `DASH-109`/`110`/`112` are re-sequenced to depend
   on this minimal slice instead of the sibling backlog's own tickets, and their status changed from
   `blocked` back to `todo`.
2. **Field defaults** (`close`/`value`/`reddit_sid_com`) — confirmed correct as implemented in
   `INGEST-009`, not relitigated.
3. **Encryption-key rotation** — confirmed accepted MVP gap, explicitly out of scope this sprint, no
   ticket opened. Documented as a known limitation in `services/ingestion-service/README.md` and
   `docs/adr/0004-tenant-credential-encryption-at-rest.md` (already stated there from this sprint's
   start).
4. The three originally-"adopted by default" decisions (CLI-only credential-write, single
   `OPERATOR_TOKEN`, setup-secret-not-loopback-binding) are now **final**, not provisional.

Updated batch plan:

| Batch | Tickets | Status after this addendum |
|---|---|---|
| 1 | `INGEST-002`, `LC-010`, `INGEST-011` | done (Tech-Lead-verified) |
| 2 | `INGEST-003`, `INGEST-007`, `GW-021` (new, independent of Batch 2's ingestion work) | in-progress |
| 2b | `GW-022` (depends on `INGEST-007`) | queued, starts once `INGEST-007` lands |
| 2c | `DASH-113` (depends on `GW-021` + `GW-022`) | queued |
| 3 | `INGEST-004` → `INGEST-005` (sequential) | queued |
| 4 | `INGEST-006` | queued |
| 5 | `INGEST-008`, `INGEST-009` (parallel) | queued |
| 6 | `GW-019` → `GW-020` (sequential) | queued |
| 7 | `VS-023` → `VS-024` (sequential) | queued |
| 8 | `DASH-108`, `DASH-111` | queued |
| 9 | `DASH-109`, `DASH-110`, `DASH-112` (depend on `DASH-113` + their original deps) | queued, now unblocked |
| any time after Batch 2 | `INGEST-010` | queued |

The Tech Lead drives every remaining batch through implementation, personal review against each
ticket's acceptance criteria, and real test execution (actually running suites, not trusting
self-reports) autonomously, per the requester's explicit instruction — interrupting only for a genuine
blocker (a real bug, an unresolvable conflict with existing code, or a decision truly outside this
sprint's now-settled scope).

## Disclosed incident (found during Batch 1 review, not caused by this sprint's own tickets)

`services/ingestion-service/`'s top level has been used as a de facto, uncleaned scratch dump by dev
agents across many past sprints (files dated back to 2026-08-05, spanning Sprint 05 through Sprint 17
material — DASH-*, GW-*, ECON-*, VS-*, INF-* drafts, HTML/PNG artifacts, logs — none of it committed,
all untracked). This is a pre-existing, cross-session incident, not something this sprint's tickets
caused, though `INGEST-002`'s and `INGEST-011`'s own dev agents briefly added a few more stray
top-level duplicates before their final, correctly-placed files were also written (confirmed
byte-identical duplicates, harmless but part of the same pattern). Every dev agent raised from this
point in the sprint has been given the real scratchpad path explicitly and instructed not to add to
this pile. The pile itself is untouched (not deleted) pending a dedicated cleanup ticket — deleting ~190
untracked files without full certainty of ownership/concurrent-session safety was judged out of scope
for this sprint's mandate and is flagged to the requester as a separate, real repo-hygiene finding.


## UAT addendum: three live integration bugs found and fixed (not caught by any ticket-level suite)

During live UAT setup, the coordinator found and fixed three real bugs — none caught by this sprint's
ticket-level test suites because those run exclusively against fakes/mocks, never the real Docker
Compose network:

1. **`services/ingestion-service/pyproject.toml` was missing `pandas`** (`interfaces.py` imports it
   directly) — fixed: added `pandas>=2.0`, `uv.lock` regenerated via a scratch-mirror workaround (the
   real path hits the same OneDrive `uv.lock`-write issue this sprint hit repeatedly elsewhere).
2. **`services/ingestion-service/Dockerfile` never copied `connectors/` into the image** —
   `src/app/routers/connectors.py` imports `from connectors.base import ...`, which only worked in
   tests because `tests/conftest.py` manually inserts that directory onto `sys.path`; the real
   container crashed on startup with `ModuleNotFoundError`. Fixed: `COPY connectors ./connectors` +
   `ENV PYTHONPATH=/repo/services/ingestion-service`; `connectors/`'s own runtime deps (`requests`,
   `praw`, `vaderSentiment`, previously only in the old `requirements.txt`) added to `pyproject.toml`.
3. **`infra/docker-compose.yml`'s `gateway-api` entry never set `REPORTING_SERVICE_URL`,
   `INGESTION_SERVICE_URL`, or `OPERATOR_TOKEN`** — only `VALIDATION_SERVICE_URL`/`DATABASE_URL` were
   wired. `http_client.py`'s own defaults (`localhost:8002`/`8003`) resolved to `gateway-api`'s own
   container inside the Compose network, not the sibling services — every `reporting-service`/
   `ingestion-service` proxy route 502'd and every operator-gated route 401'd regardless of token,
   despite all the underlying application code being correct. Fixed: all three env vars added with
   Compose-network hostnames, matching `VALIDATION_SERVICE_URL`'s existing pattern.

All three fixed, rebuilt, and live-verified against the real running stack: a real crawl trigger
against Binance's actual API returned 14,246 rows end-to-end (`POST
/ingestion/connectors/binance_price_btcusdt_1h/run` through `gateway-api` → `ingestion-service` → real
DB write); `GET /ingestion/datasets`/`GET /ingestion/datasets/{source}/series` both confirmed working
through the gateway; `reporting-service`'s proxy confirmed still healthy (a legitimate `404` on a fake
`run_id`, not a connectivity failure). Independently confirmed present in the codebase by the Tech Lead
(direct file reads of `pyproject.toml`, `Dockerfile`, `docker-compose.yml`) as part of this sprint's own
verification record — these are real, live-tested fixes, counted alongside every other ticket's
Review acceptance criteria, not hypothetical.

**Lesson for future sprints, recorded rather than silently absorbed**: every ticket-level test suite
this sprint mocked its downstream/dependency boundary (fakes, `httpx.MockTransport`) — correct
per-ticket practice, but it means Dockerfile completeness, cross-service env-var wiring, and
transitive-dependency declarations were never exercised until a real Compose `up`. No new process
change is being made here (a full live-stack smoke test after a multi-service sprint is already this
platform's convention, e.g. `INF-018`/Sprint 06/Sprint 14's own live verifications) — this is a
reminder that convention is what actually caught these three, not a gap in it.

## Design decision: GW-021/DASH-112 credentials-status endpoint mismatch (resolved)

**The gap**: `GW-021`'s `GET /ingestion/connectors/credentials-status` proxies to a path that was never
actually built. `INGEST-009` shipped `GET /connectors/{source}/status` (per-source **crawl-run**
status, tenant-scoped) — a different resource entirely from "is a credential stored for this tenant/
source," which is `INGEST-004`'s `CredentialRepository` concern and has no HTTP endpoint at all yet.
This was live-confirmed as a permanent `404`, not a "not built yet" `502`/`504`.

**The real design question**: `DASH-112` is an *operator*-gated Settings page (not a tenant
self-service page), but every credential-scoped query in `ingestion-service` today (per `INGEST-002`'s
RLS policy) is tenant-scoped by construction — there is no cross-tenant "list every tenant's credential
status" query path anywhere in this platform, and building one would mean either (a) a new
operator-level RLS-bypass code path (a real, new trust-boundary decision, not a small addition), or
(b) reintroducing `SETUP-011`'s full tenant-directory/list scope (explicitly out of scope this sprint)
so an operator has something to enumerate in the first place.

**Resolution (Tech Lead decision, consistent with this sprint's own "smallest correct slice" pattern
already applied to `GW-021`/`GW-022`/`DASH-113`)**: `DASH-112` becomes a **per-tenant** credential-status
lookup, not a cross-tenant aggregate. An operator supplies a `tenant_id` explicitly (there is no tenant
directory to pick from this sprint — the same CLI-only-tenant-management reality `provision_tenant.py`
already lives in), and the query stays tenant-scoped via the existing RLS mechanism, no new trust
boundary introduced. Concretely:
- New ticket `INGEST-012`: `GET /connectors/credentials-status` in `ingestion-service`, tenant-scoped
  (same `X-Tenant-Id` convention every other endpoint uses), returning `{"source": bool_is_set,
  "last_set_at": timestamp | null}` per known credentialed source (Reddit only, today) — reuses
  `CredentialRepository.get_credentials` (INGEST-004), returning only presence + timestamp, never the
  value (same one-time-reveal-adjacent discipline this platform already applies elsewhere).
- Small patch to `GW-021`'s existing proxy: accept an explicit `tenant_id` query/path parameter from
  the operator caller, forward it as `X-Tenant-Id` on the downstream call (NOT derived from the
  operator's own auth, since an operator has no tenant context) — a corrective patch to an
  already-`done` ticket, not a new ticket, tracked here.
- `DASH-112` (not yet started) is revised to include a `tenant_id` input field alongside its
  credential-status table — an honest reflection of "no tenant directory exists yet," not a silently
  degraded feature.

This keeps every change inside the existing per-tenant RLS trust boundary already proven throughout
this sprint, defers the genuinely larger "operator sees all tenants" capability to `SETUP-011`'s own
future scope (unchanged, not duplicated here), and unblocks `DASH-112` without guessing past what this
sprint's own adopted-by-default operator-auth posture (single shared token, no tenant directory)
already implies.


## UAT addendum 2: fourth live integration bug found and fixed

While live-testing `VS-024`'s dataset-picker flow end-to-end, a fourth real bug (same class as the
three in the first UAT addendum — a runtime dependency never exercised by any ticket-level mocked
test) was found and fixed: **`services/validation-service/pyproject.toml` declared `httpx` only under
`[dependency-groups] dev`** (used there for `TestClient`), but `IngestionServiceDatasetSource`
(`src/app/dataset_source.py`, `VS-023`/`VS-024`) imports `httpx` at runtime in production code. Since
`validation-service`'s `Dockerfile` runs `uv sync --frozen --no-dev`, `httpx` was never installed in the
real container, crash-looping `validation-service` on startup with `ModuleNotFoundError` the moment a
real Compose deployment tried to start it post-`VS-023`. Fixed: `httpx>=0.27` moved into the main
`dependencies` list (confirmed present in both `[project] dependencies` and `[dependency-groups] dev`
after the fix — the latter is fine/redundant for local dev tooling, the former is what the production
image actually needs); `uv.lock` regenerated via the scratch-mirror trick already used for the earlier
`ingestion-service` fixes. Independently confirmed present in the codebase by the Tech Lead.


## UAT addendum 3: methodological finding, not a code bug — raw levels vs. returns

While live-testing the dataset-picker flow end-to-end (a real `POST /runs` against real ingested
Binance data via `dataset_reference={"source": "binance_price_btcusdt_1h", "field": "close", ...}`),
the coordinator found that using `field="close"` pulls raw price levels (~$62k), not returns. On raw
levels, Naive0 (predicts exactly 0) is nonsensically wrong by construction, while NaiveLast (predicts
the last observed price) is naturally very close — producing a "better" DM verdict that is an artifact
of the field choice, not a real finding. **This directly touches CLAUDE.md's core, non-negotiable
positioning**: the whole naive-first methodology this platform exists to validate is built around
forecasting *returns*, not raw price levels.

**Quick fix applied now** (doc-only, in scope): added an explicit warning to `dashboard-web`'s submit-run
form's "Field" tooltip (`run_new.html`, `DASH-108`), `ingestion-service/README.md`'s field-default
table, and `validation-service/README.md`'s dataset-access section — each now states plainly that every
ingested field is a raw level, not a returns series, and that validating against a raw level does not
produce a meaningful naive-first audit.

**Open architecture question, NOT resolved by this sprint, flagged to the requester rather than
guessed at**: `ingestion-service` stores only raw OHLCV/on-chain/sentiment values today — nothing in
this pipeline computes a returns series. Does the platform need a returns-computation step between
ingestion and validation (a new `ingestion-service` endpoint/field, a `validation-service`-side
transform, or something in `naive_first_engine` itself), or does that responsibility stay with the
caller indefinitely? This is a real product/architecture decision with implications for
`implementation-plan.md`'s module boundaries (which service would own a "returns" derived series?) —
not something a Tech Lead should decide unilaterally mid-sprint. No ticket is opened for this; it is
recorded here for the requester's own scoping call.
