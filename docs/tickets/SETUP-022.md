# SETUP-022 — Basic operational signal: run throughput and failure rate

**Sprint**: 32. **Modules**: `services/gateway-api` (minimal, only if needed) and
`services/dashboard-web`. **Status**: todo. **Priority**: Should.
**Depends on**: `SETUP-020` (confirmed already satisfied, per `docs/sprints/sprint-32.md`'s own
finding — not a blocker). **Sequence**: land strictly after `SETUP-021` merges (both touch
`monitoring.html`/`operator.py`) to avoid a same-file collision.

## Analysis

Backlog `SETUP-022`: `/monitoring` shows total runs/% failed/% completed/% running over a recent
window, labeled explicitly **"validation-run throughput"** — never "model performance" or anything
implying a trading/prediction signal (CLAUDE.md's core positioning constraint — this ticket's single
highest-stakes requirement). Reuses `validation-service`'s/`gateway-api`'s existing `GET /runs` list
endpoint and `status` field; extend minimally only if that endpoint cannot cheaply answer "count by
status" already. No alerting/threshold behavior.

**Read directly before writing code**: `gateway-api`'s `GET /runs` (`runs.py`, GW-016) is
tenant-scoped and paginated (`limit`/`offset`), proxying `validation-service`'s own `GET /runs`
(VS-022). Confirm at implementation time whether the tenant-scoped nature of this call is acceptable
for an **operator-facing** page — it is: this signal is meant to be per-operator-visible platform
health, and there is no cross-tenant aggregate `GET /runs` today. **Resolve this exactly as the
backlog itself hints and state the resolution in writing, don't leave it ambiguous**: since this page
is reached via the operator gate (not a tenant session) but `GET /runs` requires a *tenant* API key
(`get_authenticated_tenant`, not `get_authenticated_operator`), this ticket cannot proxy an
operator-only call through the tenant-only `GET /runs` endpoint without a tenant credential the
operator doesn't have. The correct minimal extension (per the backlog's own "extend minimally if
needed" escape hatch) is a **new, narrow, operator-authenticated summary endpoint** on `gateway-api` —
not a duplicate of `GET /runs`'s full list contract, just a status-count aggregate across all tenants'
runs in a recent window. Document this as the ticket's one real design decision, not an
afterthought.

## Design

**Pattern**: none new — DI (`Depends()`), reusing `get_authenticated_operator`.

**Binding constraint for this sprint (Tech Lead instruction, overrides the backlog's own "extend
minimally if needed" framing): `services/validation-service/src/` is out of scope for Sprint 32 —
no file under it may be touched by this ticket, full stop.** This forces the "count client-side over
`GET /runs`" path, not a new `validation-service` method — resolved here, not left as an open choice
for the dev agent.

**Files touched**:
- `services/gateway-api/src/app/routers/system.py` (or a new small router, dev's choice, consistent
  with the "narrow standalone concern" precedent) — `GET /system/runs-summary`
  (`get_authenticated_operator`): aggregates run counts by status across all tenants for a recent
  window (e.g. last 24h, a fixed constant — no configurable window this ticket, per the "no
  alerting/threshold" scope constraint), returns `{"total": int, "completed_pct": float,
  "failed_pct": float, "running_pct": float}`. Computed by calling `validation-service`'s own existing
  `GET /runs` (via the already-existing `ValidationServiceClientDep`, GW-008/GW-018's precedent) with a
  large-enough `limit`/looped `offset` to cover the recent window across all tenants — **this requires
  `GET /runs` to be reachable without a single tenant's `X-Tenant-Id` scoping**; if `validation-service`'s
  real `GET /runs` is tenant-scoped only (confirm by reading `VS-022` directly), the operator-facing
  aggregate must instead loop `SETUP-011`'s own new `GET /tenants` (this sprint) to enumerate tenants,
  then call `GET /runs` once per tenant with that tenant's own header context reconstructed from
  `gateway-api`'s already-known internal state — **if neither path is workable without touching
  `validation-service`, the fallback is to compute the aggregate from whatever the current, unmodified
  `GET /runs` contract already exposes per call, accepting a stated, disclosed limitation (e.g. "reflects
  only tenants with at least one call surfaced this window" or a similarly honest caveat) rather than
  touching any file under `services/validation-service/src/`.** Document exactly which approach was
  taken and why in this ticket's Outcome — this is the one real design judgment call in this ticket.
- `services/dashboard-web/src/app/routers/operator.py`'s `monitoring()` — after the existing
  `/system/health` call, also call the new `/system/runs-summary` endpoint (unauthenticated-page
  concern: this call needs the operator credential, so it must be gated behind
  `require_operator_session`/`OperatorTokenHeaderDep`, **not** the page's existing no-auth design for
  the health rows — resolve this the same way `settings.py`/`settings_tenants.py` already do, by
  requiring the operator session for this one section while the rest of the page stays unauthenticated,
  OR by moving this specific panel to its own operator-gated sub-route/fragment if mixing auth
  requirements within one page handler proves awkward — dev's call, document which approach was taken).
- `services/dashboard-web/src/app/templates/monitoring.html` — new "Validation-run throughput" section
  (this exact label, verbatim — never "model performance"), landed after `SETUP-021`'s recent-errors
  section is already merged.
- `services/gateway-api/README.md` and `services/dashboard-web/README.md` — new sections.

**DRY check note**: reuses `get_authenticated_operator`/`OperatorTokenHeaderDep`/
`_call_downstream`/`_render_error_for_status` unmodified — no new auth mechanism, no new
transport-error pattern.

## Implementation acceptance criteria

- [ ] `/monitoring` shows total runs/% failed/% completed/% running over a fixed recent window,
  labeled explicitly **"validation-run throughput"** — this exact phrase, never "model performance,"
  "accuracy," "signal," or anything implying prediction quality.
- [ ] The underlying data is a real aggregate across recent runs' `status` field — not a fabricated or
  placeholder number.
- [ ] The endpoint(s) added are operator-authenticated; no tenant-only credential path is
  reused/exposed for this cross-tenant aggregate.
- [ ] No alerting/threshold/paging behavior is added anywhere in this ticket.

## Test acceptance criteria

- [ ] A test for the new `gateway-api` (and, if added, `validation-service`) endpoint(s): correct
  percentage math for a fixed set of fixture runs across all four states (`completed`/`failed`/
  `running`/queued-or-other, whatever the real status vocabulary is — confirm it by reading
  `validation-service`'s actual `status` values, don't assume), zero-runs-in-window renders `0`s not a
  divide-by-zero error, and operator-auth is enforced (`401`/`403` per each service's existing gate
  behavior).
- [ ] `services/dashboard-web/tests/test_monitoring.py` extended: mocks the new summary response,
  asserts the exact "validation-run throughput" label renders and that none of "model performance,"
  "prediction," "forecast," or "signal" appears anywhere on the page (extending the existing
  banned-word test, not a new one).
- [ ] Full affected suites run, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Personally checks the rendered page copy for the exact required label and the absence of any
  performance/prediction-implying language — this is the ticket's single highest-stakes review item,
  per CLAUDE.md.
- Confirms the aggregate is genuinely cross-tenant-safe (no tenant's individual run details are
  exposed by this endpoint — counts only).
- Confirms the chosen implementation path (client-side count over a paginated `GET /runs` fetch vs. a
  new `validation-service` method) is documented and reasonable at real Compose-stack data volumes.
- Re-runs all affected suites, confirms zero regressions.

## Documentation acceptance criteria

- [ ] `services/gateway-api/README.md` documents the new endpoint, the fixed window, the
  "validation-run throughput" framing, and the resolved tenant-enumeration approach (no
  `services/validation-service/src/` file touched, per this sprint's explicit scope boundary).
- [ ] `services/dashboard-web/README.md` documents the new `/monitoring` section.
- [ ] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-022` acceptance boxes checked, status
  marked done, citing this ticket.
