# Backlog — Operability

Source: `CONTEXT.md` (Operability definition — the deliberately-not-split umbrella term covering
both maintainability/code-ops-health — dependency upgrades, doc-sync checks, test-coverage gaps —
and runtime observability — logs, metrics, health checks, alerting); `docs/implementation-plan.md`
section 6 (trigger-based build order) and section 8 ("for libs, the public function signatures in
the README stay in sync with the code — CI should fail if they drift, add a doc-check step once the
first lib ships"); `docs/solution-design.md`; `CLAUDE.md`; `docs/product/backlog-infra.md` and
`docs/product/backlog-technical-upgrades.md` (read in full to avoid duplicating anything already
tracked there); `docs/tickets/README.md`; the full module-by-module Standards+Spec review that ran
earlier in this session, whose findings were mostly already fixed directly (Dockerfiles now run
non-root, Postgres/Redis/validation-service ports bound to `127.0.0.1`, stale docs corrected,
`ingestion-service` went from 0 to 19 tests, `PROVENANCE.md` gained licensing notes).

**Scope.** Every real, shipped module: `libs/naive_first_engine`, `libs/common`,
`services/validation-service`, `services/gateway-api`, `services/ingestion-service`, `infra/`.
This is not a feature backlog — like `backlog-technical-upgrades.md`, it is a gap analysis: what
operability tooling/practice does the platform actually have vs. what CONTEXT.md's Operability
definition and implementation-plan.md's own stated conventions say it should have by this point.
Every story cites the exact file/lines or the exact command run to confirm the gap. Where something
was checked and found already fine, or already tracked elsewhere, that is stated explicitly rather
than padded with a manufactured story.

**Explicit scope decision on LC-009 / ARCH-005 (per the requester's own instruction to use
judgement, not duplicate).** `libs/common/src/naive_first_common/tenant_context.py:43-58`'s
unverified `X-Tenant-Id` header trust, and its scheduled fix (`LC-009`), are already tracked in
full — evidence, acceptance criteria, priority rationale — as `ARCH-005` in
`docs/product/backlog-technical-upgrades.md`. This is judged a **security/authentication** gap
(who is allowed to claim to be which tenant), not a maintainability or runtime-observability one —
it does not fit either half of CONTEXT.md's Operability definition (dependency upgrades/doc-sync/
test-coverage-gaps, or logs/metrics/health-checks/alerting). It stays solely in
`backlog-technical-upgrades.md`; nothing about it is re-proposed here.

**Explicit scope decision on `ingestion-service` shipping ahead of its Sprint/ticket process.**
`services/ingestion-service/README.md:3` already discloses, in its own words, that the service was
"pulled forward on 2026-08-05 at explicit user request, independent of the FastAPI service
wrapper," and no `INGEST-*`/ticket section exists yet in `docs/tickets/README.md` for that code.
This is real, but it is a **sprint-process/scope-tracking** gap (should a PM backlog exist and be
retroactively ticketed for already-shipped work), not a code-health or runtime-observability gap —
CONTEXT.md's Operability definition doesn't reach process/ticket bookkeeping, and the README already
does the one thing doc-sync would ask for (state plainly and accurately what was built ahead of
schedule and why). Flagged here for the PM to decide whether it warrants a retroactive ticket, not
written up as an Operability story.

## Areas checked with no real gap found

- **Non-root containers**: `services/validation-service/Dockerfile:29-33` and
  `services/gateway-api/Dockerfile:37-41` both `useradd`/`chown`/`USER appuser` before `CMD`,
  dated "operability finding, 2026-08-09 review." No story here.
- **Port binding**: `infra/docker-compose.yml`'s `postgres` (line 10), `redis` (line 37), and
  `validation-service` (line 60) entries are all `127.0.0.1:<port>:<container-port>`, not bound to
  the host's public interface. `gateway-api` (line 84) is deliberately still open — it is the one
  internet-facing service per implementation-plan.md section 2. No story here.
- **`ingestion-service` test coverage existing at all**: `services/ingestion-service/README.md:18-23`
  documents 19 tests added 2026-08-09 covering `connectors/base.py` and all three connectors, using
  fakes rather than live APIs. The *existence* of tests is fine; the platform-wide absence of any
  coverage *measurement* tool is a separate, real gap — see OPS-002.
- **`PROVENANCE.md` licensing notes**: confirmed present in
  `services/ingestion-service/data/raw/_platform/PROVENANCE.md`. No story here.
- **Doc-sync tooling itself**: `libs/naive_first_engine/scripts/check_doc_sync.py` (NFE-018) already
  exists, is runnable standalone or via `tests/test_doc_sync.py`, and checks the README's "Public
  API" section against the actual AST of all six source modules. The gap is not "no doc-sync check
  exists" — it does — the gap is that nothing runs it (or any other module's test suite)
  automatically. See OPS-001.
- **Compose-level healthchecks/startup ordering for `validation-service`/`gateway-api` themselves**
  (not just `postgres`/`redis`): already tracked as `INF-009` ("Compose healthchecks and startup
  ordering," Should, deferred) in `docs/product/backlog-infra.md:116-125`. Not duplicated here —
  see OPS-005 below for the one related gap that is *not* already covered by INF-009 (health-check
  *depth*, not compose wiring).
- **Postgres non-superuser runtime role / repeatable migration & bootstrap scripts**: `INF-014`
  (role creation) is done — `infra/postgres-init/02-create-app-role.sh` exists and
  `infra/docker-compose.yml`'s `DATABASE_URL` entries already reference `naive_first_app`. `INF-015`
  (`infra/bootstrap.*`) and `INF-016` (`infra/migrate.*`) do not exist yet, confirmed by directory
  listing, but this is disclosed, in-flight Sprint 07 work already sequenced and tracked in
  `docs/sprints/sprint-07.md` and `docs/product/backlog-infra.md` — not a silent gap, and not
  duplicated into this backlog.

## Stories

### OPS-001 — Wire an automated CI pipeline that runs every module's test suite, including naive_first_engine's own doc-sync and regression gates [Must]

**As** the Naive-First platform (specifically, whoever merges the next change to any of the five
shipped modules) **I want** every module's test suite to run automatically on every push, not only
when a Tech Lead happens to run it by hand during review **so that** a regression is caught before
it reaches `main`, not discovered later by a human re-deriving "did anyone actually run this."

Evidence: `docs/implementation-plan.md` section 8 states outright, as a binding convention, not a
suggestion: *"for libs, the public function signatures in the README stay in sync with the code —
CI should fail if they drift (add a doc-check step once the first lib ships)."* The first lib
(`libs/naive_first_engine`) shipped in Sprint 01/02 (`docs/tickets/README.md`'s NFE-001–018 table);
its own doc-sync check (`NFE-018`, `libs/naive_first_engine/scripts/check_doc_sync.py`, also runnable
via `tests/test_doc_sync.py`) has existed since Sprint 02. That trigger fired many sprints ago and
has never been acted on: a repo-wide search confirms no `.github/workflows/` directory (or any other
CI config) exists anywhere in this repository. Every regression check recorded in
`docs/tickets/README.md`'s sprint outcomes ("`.venv\Scripts\python.exe -m pytest -q` passes N/N") was
run by a human, by hand, once, at the end of a sprint — there is no automated gate today that
prevents a future change from silently breaking `naive_first_engine`'s NFE-015/016 regression suite
(the hard gate reproducing the thesis's own published 1h/6h/24h numbers, docs section 1.3), any
service's fail-closed tenant-isolation tests, or the doc-sync check itself.

Acceptance criteria:
- [ ] A CI workflow (e.g. `.github/workflows/ci.yml`, or the repo's chosen equivalent) runs on every push/PR and, at minimum, executes each of the five modules' own test commands as already documented in their READMEs: `libs/naive_first_engine` (`pytest`, includes NFE-015/016's regression gate and NFE-018's doc-sync check), `libs/common`, `services/validation-service`, `services/gateway-api` (each `uv run pytest` / `.venv\Scripts\python.exe -m pytest -q` per their own README setup sections), and `services/ingestion-service` (`pytest tests/`)
- [ ] A failing test in any one module fails the CI run for that module specifically (not a single opaque pass/fail for the whole monorepo), so a contributor can tell which module broke without re-running everything locally
- [ ] The workflow is documented in each module's README (or a single root `CONTEXT.md`/`README.md` pointer) so "how do I know this passed" has one authoritative answer instead of five ad hoc `.venv` invocations
- [ ] `naive_first_engine`'s NFE-015 regression suite (the hard gate against the thesis's published numbers) specifically is confirmed to run in CI, not skipped for speed — this is the one test suite implementation-plan.md's own section 6 names as the reason the library exists at all

Rationale for priority: Must — this closes a gap implementation-plan.md itself already named as a required convention whose trigger fired in Sprint 01/02 and has sat unactioned since; five independently-built modules with zero automated regression protection, verified only by a human's one-time manual run at the end of each sprint, is exactly the kind of "easy to change safely" gap CONTEXT.md's Operability definition exists to name — and the platform is past `services/gateway-api`'s own trigger #5 (first pilot client), meaning changes now ship toward something external clients depend on.
Depends on: none

### OPS-002 — Measure and report test coverage in CI instead of relying on test *existence* as a proxy for test *adequacy* [Should]

**As** the Tech Lead reviewing a future ticket's diff **I want** a coverage report generated per module **so that** "does this change have adequate test coverage" is answered by a number, not by re-reading the diff and guessing.

Evidence: no module's `pyproject.toml` (`libs/naive_first_engine`, `libs/common`,
`services/validation-service`, `services/gateway-api`) or `services/ingestion-service/requirements.txt`
declares `pytest-cov` or any other coverage tool — confirmed by grep across all `pyproject.toml`
files in the repo, zero matches for `coverage`. Every "N/N tests passed" outcome recorded in
`docs/tickets/README.md` states a pass count, never a coverage percentage or an uncovered-lines
report; "test-coverage gaps" is one of the three maintainability items CONTEXT.md's Operability
definition names by name, and today there is no tooling that could even surface one — the platform
has no way to *see* a coverage gap, only to notice one by inspection after the fact (as this session's
own review did for `ingestion-service`, manually, before it had any tests at all).

Acceptance criteria:
- [ ] `pytest-cov` (or equivalent) is added as a dev dependency to each of the five modules
- [ ] OPS-001's CI workflow runs each module's tests with coverage enabled and surfaces the report (minimum: printed in CI logs; nice-to-have, not required: uploaded as a CI artifact or badge)
- [ ] No minimum coverage threshold is enforced as a hard CI gate by this story — that is a separate policy decision for the PM/Tech Lead to make once real numbers exist, not one this story should invent unilaterally
- [ ] Each module's README gains one line stating how to run its own tests with coverage locally, matching the existing "how to run tests" convention already present in every module's README

Rationale for priority: Should, not Must — the absence of coverage tooling has not caused a known regression to slip through (Tech Lead diff review has substituted for it so far, per every sprint outcome in `docs/tickets/README.md`), but it is a named gap in CONTEXT.md's own Operability definition and is cheap to add once OPS-001's CI pipeline exists to run it in.
Depends on: OPS-001

### OPS-003 — Establish a dependency-upgrade cadence or policy across the platform's five independently-lockfiled modules [Should]

**As** the Naive-First platform **I want** a documented, repeatable way that dependency versions get
reviewed and bumped **so that** five separately-managed dependency sets (three `uv.lock` files plus
one unpinned `requirements.txt`) don't silently drift out of date with no one ever deciding to look.

Evidence: `libs/common/uv.lock`, `services/validation-service/uv.lock`, and
`services/gateway-api/uv.lock` all exist (confirmed via glob) — each locks that module's dependency
graph at whatever version was current when it was last regenerated, with no automation re-checking
it. `services/ingestion-service/requirements.txt` is not lockfile-pinned at all — every line is a
floor (`requests>=2.31`, `pandas>=2.0`, `praw>=7.7`, `vaderSentiment>=3.3.2`), meaning a fresh
`pip install` today can silently resolve to a materially newer major version than whatever was
tested against. `libs/naive_first_engine/pyproject.toml` likewise only declares floors
(`pandas>=2.0`, `numpy>=1.24`, `scipy>=1.10`) with no lockfile at all for the library itself (only
its consumers lock it as a path dependency). No `.github/dependabot.yml`, no Renovate config, and no
documented manual review cadence exists anywhere in the repo (confirmed via glob, zero matches for
both).

Acceptance criteria:
- [ ] A documented policy exists (either automated — e.g. a `dependabot.yml`/Renovate config once OPS-001's CI exists to gate its PRs — or explicitly manual, e.g. "reviewed once per sprint, tracked as a recurring line in `docs/tickets/README.md`'s sprint template") for how each of the five modules' dependencies get reviewed for updates
- [ ] The policy explicitly states whether `services/ingestion-service/requirements.txt`'s unpinned floors are acceptable as-is or should move to a lockfile (`uv`/`pip-tools`), matching the other four modules' pinning discipline — this is a real, named inconsistency this story surfaces, not one it silently resolves either way without a decision
- [ ] Wherever the policy lives (README, `CONTEXT.md`, or a new short doc), it is referenced from each of the five modules' own READMEs, not left in one place a future contributor has to already know to look for

Rationale for priority: Should, not Must — nothing today is known to be running a version with an active vulnerability or a breaking change (no incident has occurred), so this is preventive rather than fixing a live problem; but leaving five independently-drifting dependency sets with zero review cadence is exactly the kind of maintainability gap CONTEXT.md names, and it gets more expensive the longer it's deferred (more modules, more time since last bump, larger jumps when finally addressed).
Depends on: none (OPS-001 makes the automated-Dependabot-PR option viable, but the manual-cadence option does not require it)

### OPS-004 — Verify `docker compose build`/`up` still succeeds end-to-end after this session's own Dockerfile and port-binding edits [Must]

**As** the Naive-First platform **I want** the non-root (`USER appuser`) and port-binding changes
this session made to `services/validation-service/Dockerfile`, `services/gateway-api/Dockerfile`,
and `infra/docker-compose.yml` actually proven to build and run, not merely reviewed as
source-correct **so that** "fixed" means proven, the same standard `INF-004`'s own Definition of
Done already held itself to (a real, executed full-stack smoke test, not a simulated one).

Evidence: `services/validation-service/Dockerfile:29-33` and
`services/gateway-api/Dockerfile:37-41` both add `RUN useradd ... && chown -R appuser:appuser /repo`
and `USER appuser` before the final `CMD`, dated "operability finding, 2026-08-09 review" —
correct-looking, standard-shaped Dockerfile changes, but they were made and reviewed as source only;
this session's own task framing states explicitly that actually running `docker compose build` was
"explicitly skipped for time." A `chown -R` immediately before switching to a non-root user is a
common, cheap-looking change that has a real, concrete failure mode worth ruling out here
specifically: if `uv sync`'s `.venv` (created while still root, at `/repo/services/*/.venv`) or any
file written by the `uv sync` step ends up with permissions or ownership the subsequent `chown -R`
doesn't actually reach the way the Dockerfile assumes (e.g. because of build-cache layering, or a
`.dockerignore` interaction), the container can build successfully but fail at `CMD` time with a
permissions error — a class of bug that source review alone cannot catch, only an actual build +
run can.

Acceptance criteria:
- [ ] `docker compose -f infra/docker-compose.yml build validation-service gateway-api` is actually run and confirmed to succeed
- [ ] `docker compose -f infra/docker-compose.yml up -d` (full stack) is actually run and both services' `/health` endpoints respond `200 {"status":"ok"}` from the host, per the exact curl commands `infra/README.md`'s INF-003/INF-004 sections already document
- [ ] The full-stack smoke test `infra/README.md`'s "Full-stack smoke test (Definition of Done, INF-004)" section already documents (provision a tenant, `POST /runs` through `gateway-api`, confirm a `201`) is re-run once, specifically to confirm the non-root user change didn't break the `provision_tenant.py` script's ability to write to whatever file/DB it needs inside the now-non-root container
- [ ] `infra/README.md` gains a one-line dated note confirming this verification was performed and when, following the same "state plainly, don't leave silent" convention the rest of that README already uses for its own disclosed gaps

Rationale for priority: Must — this is not new scope, it is finishing verification of changes already claimed as "fixed" in this same session; shipping an unverified Dockerfile change that could silently break container startup is a worse operability posture than not having made the non-root change at all, since the source now *looks* fixed while nobody has confirmed it *is*.
Depends on: none

### OPS-005 — Deepen `/health` endpoints to report real dependency connectivity, not a hardcoded constant [Should]

**As** an operator (or, later, an external uptime/monitoring check) polling `validation-service`'s
or `gateway-api`'s `/health` endpoint **I want** the response to reflect whether the service can
actually reach its database (and, for `validation-service`, Redis once `VS-014`'s publisher is the
active path) **so that** "healthy" means the service can do its job, not merely that the FastAPI
process is running.

Evidence: `services/validation-service/src/app/main.py:26-28` and
`services/gateway-api/src/app/main.py:25-27` are byte-identical:
```python
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```
This returns `{"status": "ok"}` unconditionally — it cannot fail, because it never touches the
database, Redis, or any other dependency; a container whose Postgres connection is completely dead
still reports healthy. This is distinct from `INF-009` (`docs/product/backlog-infra.md:116-125`,
Should, deferred), which is about **Compose-level startup ordering** (waiting for `postgres`'s own
`pg_isready` healthcheck before starting the app containers) — INF-009 never touches what the app's
own `/health` endpoint *checks*, only when the app container is allowed to start relative to
Postgres's container-level healthcheck. Both gaps are real and don't overlap: INF-009 is about
sequencing at boot; this story is about the endpoint's own honesty at any point after boot.

Acceptance criteria:
- [ ] `validation-service`'s `/health` performs a lightweight real check against its active repository backend (e.g. `SELECT 1` via the already-memoized engine from `_get_engine`) and returns a non-`200` status (or a body distinguishing `"ok"` from `"degraded"`/`"unhealthy"`) if that check fails
- [ ] `gateway-api`'s `/health` does the same against its own repository backend
- [ ] The check is cheap enough to poll frequently (no full query, just a connectivity probe) and does not itself become a source of load or false negatives under normal latency
- [ ] Existing callers of `/health` (`infra/README.md`'s documented `curl` verification steps) are confirmed to still receive a `200`/`{"status":"ok"}` shape in the healthy case, so this is additive, not a breaking contract change
- [ ] A test exists for each service asserting `/health` returns a non-`200` (or a distinguishable failure body) when the underlying dependency is unreachable, using the same dependency-override/fake pattern the rest of each service's test suite already uses

Rationale for priority: Should — nothing today consumes `/health` for automated alerting (no external monitoring exists yet, see OPS-006/OPS-007), so the current shallow check has not caused a real incident; but it is cheap, it is exactly what CONTEXT.md's "health checks" phrase names directly, and doing it now avoids a container reporting falsely healthy the day something *does* start polling it.
Depends on: none

### OPS-006 — Adopt structured logging with a request/tenant-correlation id as the platform-wide convention [Could]

**As** a future operator debugging a cross-service request (a `POST /runs` that entered through
`gateway-api` and was proxied to `validation-service`) **I want** every log line either service
emits for that request to carry a shared correlation id **so that** the two services' logs can be
joined for one request without guessing by timestamp proximity.

Evidence: a repo-wide search for `logging`/`logger`/`structlog` across all `.py` files returns
exactly three hits: `services/validation-service/migrations/env.py` and
`services/gateway-api/migrations/env.py` (both Alembic's own generated boilerplate, not
application code), and `services/validation-service/src/app/events.py:24-27,49`, whose single
`logger.info("event published: %s", ...)` call inside `InProcessLogEventPublisher.publish` is the
*only* application log statement anywhere in either FastAPI service. There is no logging
configuration (no log level, no formatter, no JSON structuring) set anywhere, and nothing attaches a
request id, tenant id, or trace id to any log line — a future operator correlating a `gateway-api`
request with the `validation-service` request it was proxied into would have nothing but wall-clock
proximity to go on.

Acceptance criteria:
- [ ] A structured logging convention (e.g. `structlog`, or stdlib `logging` configured with a JSON formatter) is adopted as the documented standard for both FastAPI services
- [ ] A correlation/request id is generated (or read from an inbound header, if `gateway-api` already forwards one) at the start of each request and attached to every log line emitted during that request's handling, via middleware or a context var — not passed explicitly through every function call
- [ ] `gateway-api`'s proxying to `validation-service` forwards the same correlation id as a header, so a single id threads through both services' logs for one logical request
- [ ] The existing single log call in `events.py` is migrated to the new convention as the first real usage, not left as the one pre-existing exception
- [ ] This story does not require standing up a log-aggregation backend (ELK/Loki/CloudWatch) — that is a separate, larger infrastructure decision; this story's scope ends at "logs are structured and correlatable," not "logs are centrally searchable"

**Explicit trigger override (2026-08-24)**: pulled forward now, at explicit user request, per `docs/adr/0003-disclosed-trigger-override-pattern.md` and the assessment in `docs/product/backlog-hardening-wave-review.md`. Pure observability/maintainability tooling — adopts a logging convention and a correlation id, does not stand up a log-aggregation backend (still correctly deferred, see OPS-007). Care condition: this is a precondition for GW-014 (auth event audit logging, also pulled forward this wave, `docs/product/backlog-gateway-api.md`) — sequence this story first or alongside GW-014 so that story builds on this convention rather than inventing a second one.

Rationale for priority: Could, not Should/Must — there is no live pilot client and no incident on record that better logging would have shortened; this is a real gap named directly in CONTEXT.md's Operability definition ("logs") — pulled forward per the override note above despite that.
Depends on: none

### OPS-007 — Stand up a metrics/alerting stack (Prometheus/Grafana, Sentry, or equivalent) [Won't, for now]

**As** an operator running this platform in a shared or always-on deployment **I want** request-rate,
error-rate, and latency metrics with alerting on anomalies **so that** a degraded service is caught
before a client reports it.

This story is written to record a deliberate decline, matching the style
`docs/product/backlog-infra.md` already uses for INF-011/012/017, not to leave the request
unaddressed. **What was checked**: a repo-wide search for `prometheus`, `opentelemetry`, and
`sentry` across all `.py` files returns zero real hits (the only `metrics` matches found are the
domain concept `naive_first_engine.metrics`/`MetricSet` — MAE/RMSE/etc. — not runtime observability
metrics; confirmed by reading every match). No metrics-exposition endpoint, no tracing, no error
aggregator exists anywhere in the platform.

**Decision: Won't, this backlog, for now.** Every service today runs either on a developer's laptop
or, at most, in the local Docker Compose stack (`infra/docker-compose.yml`) — there is no deployed,
always-on, externally-reachable instance of this platform yet (`gateway-api`'s own README already
states it is the only internet-facing service, and even it is not deployed anywhere outside local
Compose). Standing up Prometheus/Grafana/Sentry today would mean operating and maintaining a
monitoring stack with nothing running continuously enough to alert on and no on-call process to
receive the alert — pure speculative infrastructure, the same category `backlog-infra.md`'s INF-010/
INF-017 already declined for the same YAGNI reason, and precisely what CLAUDE.md's own "local-first
deployment... design for scale now so that later step isn't a rewrite" principle is compatible with
*declining until the actual step arrives*, not building preemptively.

**Concrete revisit trigger** (matching the pattern this backlog's other Won't/deferred stories use):
the first time this platform is deployed anywhere it runs continuously and unattended — i.e.
`docs/implementation-plan.md` section 6's later, not-yet-triggered move off "local-first" (the
cloud-portability step CLAUDE.md names but does not schedule), or the first external pilot client
whose SLA requires it, whichever comes first. At that point OPS-006 (structured logging) should
already be in place, since a metrics/alerting stack is materially easier to wire up against
already-structured logs than against today's single ad hoc log line.

Rationale for priority: Won't — no concrete, current trigger; revisit only when the stated trigger above becomes true, not preemptively.
Depends on: none (OPS-006 is a soft prerequisite in practice, not a formal blocker)

## Summary

| Priority | Count | IDs |
|---|---|---|
| Must | 2 | OPS-001, OPS-004 |
| Should | 3 | OPS-002, OPS-003, OPS-005 |
| Could | 1 | OPS-006 |
| Won't | 1 | OPS-007 |

Single most important finding: **OPS-001** — `docs/implementation-plan.md` section 8 already
commits this platform, in writing, to "CI should fail if they drift... once the first lib ships,"
and that trigger fired back in Sprint 01/02. Every sprint since has relied entirely on a human
running each module's tests by hand once, at the end of the sprint, with the outcome recorded as
prose in `docs/tickets/README.md` rather than enforced by any automated gate — this is the one gap
in this backlog that the platform's own prior planning documents already said should not exist by
now.
