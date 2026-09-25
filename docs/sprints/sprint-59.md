# Sprint 59 — Epic C (Admin/Ops Maturity), slice 2: health-transition notification (ADMIN-001)

Sprint goal: an operator who is not actively watching `/monitoring` gets a single, fire-and-forget outbound
notification the moment `gateway-api`'s aggregate health flips from all-healthy to degraded/unreachable (and
back), without standing up any paging/alerting stack — closing the last "pull-only" gap left in the
`SETUP-020`/`021`/`022` monitoring surface.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md` — `ADMIN-001` (Should). Sprint 58's own "Next"
roadmap note tentatively named `ADMIN-001` the more self-contained candidate for this sprint ("one new
optional env var, one best-effort outbound POST, no new UI, no lockout-risk design work"); this file
independently re-verifies that framing against current code rather than carrying it over on trust, per this
platform's standing convention that a follow-up sprint's citations get their own PM pass — and, per that
re-verification, **corrects** part of that framing (see below) rather than repeating it unchanged.

## Verification of the backlog's cited findings (done independently, not taken on trust)

- **`ADMIN-001`'s verbatim AC, confirmed at the cited lines**: `docs/product/backlog-trust-and-admin-ops.md`
  lines 408–447. The story requires a single optional `MONITORING_WEBHOOK_URL` env var (unset by default,
  same disclosed-optional convention `NARRATIVE_API_URL` already uses — confirmed real, not an invented
  analogy: `services/reporting-service/src/app/subscriber.py` reads `NARRATIVE_API_URL` exactly that way),
  firing a fixed-shape JSON payload (`{"event": "health_transition", "previous_status": ...,
  "current_status": ..., "at": ...}`) "exactly once per transition... never on every poll," no
  retry/backoff/queueing beyond one best-effort POST with a short timeout, log-and-drop on failure, and an
  explicit out-of-scope line (no escalation policy, no multi-channel, no ack/snooze, no paging-service
  integration) so it cannot silently reopen `OPS-007`'s already-declined full alerting stack.
- **Correction to sprint-58's "Next" framing, confirmed by reading the actual code, not assumed from the
  AC's env-var-and-POST framing.** `services/gateway-api/src/app/routers/system.py`'s `get_system_health`
  (`GET /system/health`, lines 120–132, read in full) is a pure, stateless aggregate: on every call it
  freshly computes `gateway-api`'s own DB check (`_own_health_status`, lines 90–96) plus one live HTTP probe
  each to `validation-service`/`reporting-service`/`ingestion-service` (`_downstream_health_status`, lines
  99–117) and returns the result. Nothing in this file stores a "previous status" anywhere, and nothing
  calls it on a recurring schedule — it only runs when something (a caller, `dashboard-web`'s polling) hits
  the endpoint. `docs/product/backlog-trust-and-admin-ops.md`'s own AC requires firing "exactly once per
  transition... never on every poll," which is a stateful, recurring-evaluation requirement this endpoint's
  current pure request/response shape cannot satisfy as-is.
- **Confirmed no startup/lifespan hook exists to extend.** `services/gateway-api/src/app/main.py` (read in
  full) constructs the `FastAPI` app, configures structured logging, adds `CorrelationIdMiddleware`, and
  mounts routers — no `@app.on_event("startup")`, no `lifespan=` context manager, nothing that launches any
  background task at process start. There is no existing hook this story's polling loop could attach to
  without adding one from scratch.
- **Confirmed no recurring in-process background-job precedent exists anywhere in this repo.** Repo-wide grep
  (not just `services/`) for `BackgroundTasks|asyncio\.create_task|APScheduler|lifespan|scheduler|periodic|
  @repeat_every|cron` across all `.py` files turns up exactly two real code precedents, neither of which is
  a recurring internal timer: (1) `services/ingestion-service/src/app/routers/connectors.py`'s
  `BackgroundTasks` usage (`INGEST-015`) — FastAPI's per-request `BackgroundTasks.add_task`, firing one
  background task per HTTP call (schedule-a-crawl-then-return-202), not a loop; and (2)
  `services/validation-service/scripts/prune_split_points.py` (`VS-032`), whose own docstring states it is a
  "standalone, operator/cron-run deletion script (operator/cron-run tool, no app process dependency)" — i.e.
  this platform's one existing "needs to run repeatedly" precedent is *external cron invoking a one-shot
  script*, not an in-process scheduler. This confirms the orchestrating PM's finding: nothing in this
  codebase does "evaluate on an interval and remember the last result inside the running process" today.
- **Net effect on scope, stated honestly rather than repeating sprint-58's framing**: `ADMIN-001` needs one
  genuinely new piece of infrastructure for this platform — a recurring health-evaluation mechanism inside
  `gateway-api` that polls the same aggregate logic `GET /system/health` already exposes on some interval,
  compares it to a remembered previous status, and fires the webhook only on a change. This is real added
  design/implementation surface sprint-58's "no design work" framing did not disclose. It does not, however,
  cross any locked-in architectural line: it stays inside `gateway-api` (already-live, trigger #5), adds no
  new UI, needs no new service, and is a bounded, ordinary engineering judgment call — not a question that
  contradicts `CLAUDE.md`'s locked-in assumptions or one ambiguous enough to need the requester's input, so
  it is decided here rather than escalated.
- **Two mechanically valid shapes exist for the recurring-evaluation half; this file records the scope
  decision so the Tech Lead doesn't have to reopen it**: (a) an in-process `FastAPI` `lifespan`-launched
  `asyncio` task that sleeps/wakes on a fixed interval and calls the same health-aggregation logic directly
  (in-process, no new external trigger), or (b) following this platform's own existing "external cron calls
  a one-shot endpoint/script" precedent (`VS-032`'s shape) instead, with a new internal endpoint the crawl
  container's cron invokes. Both are legitimate; **this file decides (a)** — in-process `lifespan` task — as
  the better fit for this specific story, because the webhook's own transition-comparison state
  (`previous_status`) needs to live somewhere in-process regardless, and a second external cron entry adds
  an `infra/`-level moving part (a new cron job definition, a new invocable endpoint, a way to fail silently
  if that external cron isn't wired) for no benefit over a self-contained task the service already owns
  end-to-end. The Tech Lead's ticket breakdown should treat this as decided, not open.
- **Single-instance, in-memory "last known status" is the correct scope call here, confirmed against both
  governing docs before asserting it, not assumed.** `CLAUDE.md`'s locked-in assumptions state "local-first
  deployment (Docker Compose, cloud-portable)" with no multi-replica requirement disclosed anywhere for the
  MVP. `docs/implementation-plan.md` line 105 states the platform runs "Single Postgres + TimescaleDB
  instance for the pilot phase," and line 16 frames the whole services split as "even while everything runs
  on one laptop via Docker Compose" — consistent with a single `gateway-api` process, not a load-balanced
  fleet, for this phase. In-memory, single-process `previous_status` state (reset on restart, which simply
  means the next transition — if any — re-evaluates from a fresh unknown baseline rather than misfiring) is
  therefore the right-sized scope: no external state store (Redis/DB row) is justified for one boolean-ish
  value in a single-instance deployment. This is stated here explicitly as a scope decision, not left
  implicit, so the Tech Lead doesn't have to guess or reopen it — and so a future multi-instance deployment
  (a real trigger, not assumed now) is the explicit revisit point, matching this repo's own "design for scale
  later without a premature rewrite now" posture without building that scale now.
- **`OPS-007`/`SETUP-023`'s decline, confirmed still the live framing to build against.** `services/
  gateway-api/README.md` line 54 and the AC's own text both reference `OPS-007`'s declined full
  alerting/log-aggregation stack ("it ends at 'logs are structured and correlatable'"). `SETUP-021`'s
  recent-errors ring buffer (README lines 355–365) is the most recently built adjacent piece, and its own
  README note (line 365) already states it deliberately does not reopen `OPS-007`'s scope — `ADMIN-001`
  needs the same discipline, which the AC's own explicit out-of-scope line already enforces.
- **File-overlap check, done by reading the target area, not assumed from the module name.** `ADMIN-001`
  touches only `services/gateway-api`: `src/app/main.py` (new lifespan hook), a new module for the polling
  task + webhook POST (naming left to the Tech Lead, following `system.py`'s own "one disjoint module per
  distinct concern" precedent already established by `tenants.py`/`diagnostics.py`/`audit_log.py`), and
  `services/gateway-api/README.md`/`infra/README.md` (documentation, per the AC's own fourth checkbox). No
  other in-flight or immediately-next-sprint story touches `main.py` or `system.py`.

## Sequencing call: ADMIN-001 only, ADMIN-005 deferred again

- **ADMIN-001 has no dependency on any other open backlog story.** Its own `Depends on:` line names only
  `SETUP-020` (already shipped, the aggregate health endpoint it polls). Nothing about the added
  polling-mechanism design work changes that — it's new surface within one already-live module, not a new
  dependency on unbuilt capability.
- **ADMIN-005 (self-serve API key rotation) is excluded again, independently re-evaluated, not just carried
  from sprint-58's deferral.** Its own backlog rationale is unchanged since the last pass: "the lockout-guard
  design needs real care, so it doesn't rank above the epic's other, lower-risk stories" (backlog line 580).
  Its AC requires a real design decision (enforcing "mint-then-confirm-then-revoke" as the *only* reachable
  path) plus a new tenant-facing "My API Keys" page (backlog lines 557–578) — meaningfully more design/UI
  surface than `ADMIN-001`, and now, with `ADMIN-001` itself turning out to need its own new
  polling-mechanism design work, bundling a second story with its own separate, real design risk into the
  same sprint would stack two non-trivial judgment calls into one sprint for no scheduling benefit (the two
  stories share no files or mechanism). Nothing in this pass's code re-read changes the lockout-guard risk
  the backlog already flagged. Deferred, not dropped — see "Next" below.
- **Net call: ADMIN-001 alone, this sprint.** This narrows sprint-58's tentative "could pair with the start
  of Epic B" framing to a single story, given the added design surface this file's verification surfaced —
  a smaller, cleaner sprint is the right response to "this story turned out to be bigger than the roadmap
  note said," not a reason to pad the sprint with a second heavy story to compensate.

## Stories in scope

1. **ADMIN-001** — Narrow, single-signal notification on health-state transition.
   - Modules touched: `services/gateway-api` only — `src/app/main.py` (new `lifespan` context manager
     launching one `asyncio` background task at process start, replacing no existing behavior), a new
     router-adjacent module owning the polling loop + webhook POST (module boundary decision left to the
     Tech Lead, following the existing "one disjoint module per distinct concern" precedent), and
     `services/gateway-api/README.md` plus `infra/README.md` documentation updates (the AC's own fourth
     checkbox).
   - No dependency on any other open story this sprint (sprint is single-story).
   - **Scope decisions carried into the ticket, decided here so the Tech Lead doesn't have to reopen them**:
     - **Mechanism**: an in-process `FastAPI` `lifespan`-launched `asyncio` task, sleeping/waking on a fixed
       interval (interval value is the Tech Lead's implementation call — not specified by the AC — but must
       be disclosed in the README once chosen), calling the same aggregate-health logic `GET /system/health`
       already exposes (reuse that logic directly — e.g. factor `get_system_health`'s body into a callable
       both the route and the polling task call — never duplicate the four-way aggregation a second time,
       per this repo's DRY convention).
     - **State**: single-instance, in-memory `previous_status` only — no Redis/DB-backed state store. This
       is a deliberate scope decision (see verification section above), not an oversight; a restart simply
       resets the baseline rather than misfiring a spurious transition. Revisit only if this platform moves
       to a multi-replica `gateway-api` deployment (not currently planned or triggered).
     - **Env var**: `MONITORING_WEBHOOK_URL`, optional, unset by default, same disclosed-optional convention
       `NARRATIVE_API_URL` already uses in `services/reporting-service/src/app/subscriber.py` — when unset,
       the polling task may still run (to keep `previous_status` warm) but must never attempt an HTTP POST,
       and the feature must stay fully inert (no behavior change, no error, no log noise) with the env var
       unset.
     - **Payload**: fixed shape exactly as the AC states — `{"event": "health_transition", "previous_status":
       ..., "current_status": ..., "at": ...}` — no additional fields, no schema versioning beyond what the
       AC specifies.
     - **Delivery discipline**: no retry/backoff/queueing — a single best-effort POST with a short timeout;
       a failed delivery (timeout, connection error, non-2xx) is logged via the existing `OPS-006` structured
       logging convention and dropped — it must never block, delay, or crash the health-evaluation path
       itself, and must never affect `GET /system/health`'s own existing behavior/response shape (that route
       stays exactly as it is; the polling task reuses its logic, not its route).
     - **Explicitly out of scope, per the AC's own fourth checkbox — carry into the ticket verbatim**: no
       escalation policy, no multiple channels/recipients, no acknowledgement/snooze mechanism, no
       paging-service integration (PagerDuty/Opsgenie/etc.). One URL, one event shape, fire and forget.
     - **Transition definition**: "healthy" means all four sub-checks (`gateway-api` own DB,
       `validation-service`, `reporting-service`, `ingestion-service`) report `"ok"`; any sub-check reporting
       `"degraded"` or `"unreachable"` counts as the aggregate being in the non-healthy state, per the
       existing three-way vocabulary `_downstream_health_status`/`_own_health_status` already define in
       `system.py` — the Tech Lead's ticket should state the exact healthy/non-healthy boundary condition
       explicitly rather than leave it implicit, since the AC's "all-healthy to any-degraded/unreachable"
       phrasing already implies this collapsing of the three-way status into a two-way transition signal.
   - Per `implementation-plan.md` section 2's module boundary rule: this stays entirely inside
     `gateway-api`'s own boundary — no other service's code or schema is touched, and the webhook POST target
     is an external operator-configured URL, not another service in this platform.

## Module/dependency note for the Tech Lead (implementation-plan.md sections 2 and 6)

`services/gateway-api` (trigger #5) is already live — no trigger-firing question. `ADMIN-001` proposes no new
service, no new `libs/*` package, and touches no other service's module boundary. It does add one new
*kind* of runtime behavior to this service (a recurring in-process background task, via `lifespan`) that
`gateway-api` has not had before — flagged explicitly here as new operational surface (the container now
does something on a timer, not just in response to requests) worth a one-line README note beyond the AC's
own fourth checkbox, so a future reader of `gateway-api/README.md` understands why the service now has a
background task at all.

## Stories explicitly deferred

- **ADMIN-005** (self-serve API key rotation) — deferred again, not dropped, per the backlog's own stated
  rationale (lockout-guard design risk, backlog line 580) plus a new tenant-facing "My API Keys" page —
  real, separable complexity that should not be bundled into a sprint where the one in-scope story already
  turned out to carry its own new-mechanism design work. See "Next" below.
- **ADMIN-004** (tenant-facing usage/quota view) — already `Won't` in the backlog itself (no quota/plan/
  rate-limit mechanism exists anywhere in the platform); not reconsidered here, consistent with the
  backlog's own reasoning, same as sprint-58's note.
- Everything else in `backlog-trust-and-admin-ops.md` not in scope this sprint: all of Epic B (`RPT-001/002/
  004`; `RPT-003` already done Sprint 55), all of Epic D (`ONB-001/002`; `ONB-003` already `Won't`) —
  deferred per the backlog's own overall sequencing lean (Epic A/C ahead of Epic B/D), not dropped. Epic A
  (`TRUST-001` through `TRUST-005`) is fully shipped as of Sprint 57; Epic C's `ADMIN-002`/`003` are fully
  shipped as of Sprint 58.

## File-overlap / concurrent-work risk

- **Single-story sprint — no cross-story file overlap risk exists this sprint.**
- `services/gateway-api/src/app/main.py` is touched by `ADMIN-001` (new `lifespan` hook) — confirmed no
  other in-flight or immediately-next-sprint story is known to touch this file; the last story to touch it
  was `ADMIN-002-01`'s router registration (Sprint 58, already merged), which does not conflict with adding
  a `lifespan=` argument to the existing `FastAPI(...)` construction.
- `services/gateway-api/src/app/routers/system.py` is read (its aggregation logic is reused, not
  duplicated) by `ADMIN-001`'s polling task — whether the Tech Lead's ticket extracts a shared callable out
  of `get_system_health` or imports/calls it directly is an implementation choice, but either way this file
  is touched only by this story this sprint.
- `services/gateway-api/README.md` and `infra/README.md` are touched by `ADMIN-001`'s documentation
  checkbox only — no other known concurrent edit to either file this sprint.

## Definition of done for this sprint

- `ADMIN-001`'s acceptance criteria (verbatim from `docs/product/backlog-trust-and-admin-ops.md`) are
  checked off in its ticket.
- Required tests, specifically:
  - A test proves a genuine healthy-to-degraded/unreachable transition fires **exactly one** webhook POST
    with the fixed payload shape (`event`/`previous_status`/`current_status`/`at`).
  - A test proves a poll that does **not** change aggregate status (healthy-stays-healthy, or
    degraded-stays-degraded) fires **zero** webhook POSTs — this is the AC's own "never on every poll"
    requirement and needs its own explicit test, not just inferred from the transition test.
  - Both transition directions are covered: healthy → degraded/unreachable, and the reverse recovery
    transition, degraded/unreachable → healthy.
  - A test proves a failed webhook delivery (simulated timeout or connection error) is logged via the
    existing `OPS-006` structured-logging convention and does not raise/crash/block the health-evaluation
    path — the polling task must survive a bad delivery and continue on its next interval.
  - A test proves that with `MONITORING_WEBHOOK_URL` unset (the default), the feature stays fully inert: no
    HTTP POST is attempted, no new error/log noise is introduced, and `GET /system/health`'s own existing
    response behavior is byte-for-byte unchanged from before this story.
- Positioning check (`CLAUDE.md`) explicitly re-verified in review: this addition is framed as operational
  monitoring of the platform's own infrastructure health, not a trading/market signal or prediction feature
  — trivially satisfied here (the payload carries only `gateway-api`'s own service-health status), but
  stated for the record per this repo's standing review convention.
- No new UI is added — `dashboard-web` is untouched by this story, consistent with the AC.
- `services/gateway-api/README.md` and `infra/README.md` updated to document `MONITORING_WEBHOOK_URL`,
  the fixed payload shape, the polling mechanism now running inside `gateway-api` (new operational surface,
  per the module/dependency note above), and the explicit "deliberately minimal notification primitive, not
  a monitoring/alerting subsystem — revisit when a real trigger fires" framing the AC's own fourth checkbox
  requires, matching the same framing `SETUP-023`/`OPS-007` already use for the fuller, still-declined
  version.
- `docs/product/backlog-trust-and-admin-ops.md`'s `ADMIN-001` entry marked done with its acceptance-criteria
  boxes checked, pointing to its ticket file(s).
- `docs/tickets/README.md` gets a new Sprint 59 section (Tech Lead updates this when tickets are
  created/closed, per this repo's standing convention — not done by this sprint plan itself).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`) after
  the ticket is Tech-Lead-verified done, before sign-off. QA scope should specifically, independently verify,
  against the real local Docker stack (not just unit-test-mocked repositories/HTTP clients): that stopping
  and restarting a downstream service (e.g. `validation-service`) actually produces one real webhook call to
  a test receiver, that leaving all services healthy across multiple polling intervals produces zero calls,
  that recovery (bringing the downstream service back) produces exactly one more call for the reverse
  transition, that a webhook receiver returning an error or being unreachable does not disrupt
  `gateway-api`'s own health or the polling task's continued operation on the next interval, and that
  `GET /system/health`'s existing response shape/behavior is unaffected by any of this.

## Next (explicitly not this sprint, roadmap note for continuing this backlog)

With `ADMIN-001` shipped, Epic C (Admin/Ops Maturity) has one story remaining: `ADMIN-005` (self-serve API
key rotation), deferred here for the reasons stated above. **Sprint 60 (tentative)**: `ADMIN-005` is the
natural next candidate to close out Epic C, but given its own backlog-flagged lockout-guard risk (enforcing
"mint-then-confirm-then-revoke" as the *only* reachable path, with no single-step "replace my key" action
that could revoke-before-confirm), the Tech Lead's ticket breakdown for `ADMIN-005` should get a `/grilling`
pass on that specific flow before implementation starts, per this platform's standing convention of using
`/grilling` proactively on blocking-decision tickets — this is exactly that shape of decision (a design
choice that's hard to safely reverse once a tenant-facing UI exists around it), not a case to defer the
stress-test until after code is written. That sprint could also pair `ADMIN-005` with the start of Epic B
(`RPT-001`, PDF export) if the requester wants to shift focus and `ADMIN-005` alone doesn't fill the sprint
— that scope call belongs to the Product Owner/requester, not preempted here. Sprint 60's own PM pass should
re-verify these citations against then-current code before handing off to the Tech Lead, same as this one
was.
