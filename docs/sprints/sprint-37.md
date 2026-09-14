# Sprint 37 — Operator UI reachability (dashboard-web, gateway-api)

Sprint goal: an operator can discover and reach the already-working `/operator-login` flow entirely
by clicking through the rendered UI, and gets an immediate, unambiguous error if they typo the
`OPERATOR_TOKEN`, instead of either not knowing the route exists or getting a silent false-accept.

Backlog source: `docs/product/backlog-first-run-setup-and-ops.md` (SETUP-034, SETUP-035; see that
file's Addendum near line 697 for the live operator-reported gap these two stories close).

## Stories in scope, in execution order

1. **SETUP-034** (Must) — `dashboard-web`: `login.html` gains a secondary link to
   `/operator-login`; `base.html` gains a second, independently-gated operator `<nav>` block
   (`/settings/tenants`, `/settings/environment`, `/monitoring`, plus logout); new
   `POST /operator-logout` in `services/dashboard-web/src/app/routers/operator.py` reuses
   `OperatorSessionStore.delete` + `Response.delete_cookie` (same mechanism as `DASH-007`'s tenant
   logout). No change to `require_operator_session`, `OperatorSessionStore`, or the existing
   `POST /operator-login` handler logic — the backend mechanism (`DASH-113`, Sprint 18) already
   works; this story only makes it reachable. Sequenced first: no dependency, and SETUP-035 depends
   on the same file/route this story establishes.
2. **SETUP-035** (Should) — `gateway-api`/`dashboard-web`: `POST /operator-login` performs one lazy
   validation call against an existing operator-gated `gateway-api` endpoint (e.g. `GET /tenants`,
   `SETUP-011`) — same pattern `DASH-002` established for tenant login. `403` → invalid-token error
   redisplay; transport failure → generic "unreachable" error, never treated as valid. Sequenced
   second and explicitly after SETUP-034, not in parallel: both touch `POST /operator-login` and its
   template in `services/dashboard-web`, and this story is itself flagged in the backlog as
   depending on SETUP-034 for that reason (file-overlap dependency, not just priority).

## Stories explicitly deferred

- SETUP-036 — Won't, this backlog (per backlog file: distributing `OPERATOR_TOKEN` to a fresh
  operator conflicts with the existing "no secret rendered in the UI" rule established by SETUP-015).
  Not scheduled; excluded at the backlog level, not deferred by this sprint.
- No other SETUP items are in scope for this sprint; SETUP-034/035 are the only unblocked,
  Must/Should items from this backlog's operator-UI gap not already shipped in a prior sprint.

## Dependencies (module boundaries, implementation-plan.md sections 2 and 6)

- Both stories are `services/dashboard-web` (+ `services/gateway-api` for SETUP-035's validation
  call) — trigger #8/#5, already fired. No `libs/naive_first_engine` or `libs/common` involvement.
- SETUP-034 has no dependency; the backend mechanism it wires up to the UI (`DASH-113`) already
  shipped in Sprint 18.
- SETUP-035 depends on SETUP-034 for file/route ordering (same `POST /operator-login` handler and
  `operator-login.html` template) — this is a stated file-overlap dependency, not a reprioritization;
  SETUP-035 remains Should-priority and does not block SETUP-034.

## File-overlap / concurrent-work risk (explicit)

SETUP-034 and SETUP-035 both touch `services/dashboard-web/src/app/routers/operator.py` and the
`operator-login` template. Per this repo's established pattern for same-file story collisions
(Sprint 14, Sprint 24, Sprint 35), the Tech Lead should sequence these strictly one-at-a-time, not
across parallel dev-squad workstreams.

## Definition of done for this sprint

- Both stories' acceptance criteria (as stated in `docs/product/backlog-first-run-setup-and-ops.md`
  for SETUP-034/035) are checked off.
- Each story's own test (template-render test for the four cookie-presence combinations on
  SETUP-034; invalid-token and transport-failure redisplay tests on SETUP-035) passes; full existing
  suite re-run with zero regressions.
- `services/dashboard-web/README.md` updated: new operator nav block, `POST /operator-logout`
  contract, and removal/update of the "Known gaps" entry for `DASH-113`'s unvalidated-token behavior
  once SETUP-035 ships. `services/gateway-api/README.md` updated if SETUP-035's lazy-validation call
  needs documenting there.
- `docs/tickets/README.md` gains entries for SETUP-034 and SETUP-035 with dependency and status
  columns filled in, matching the existing table format (First-run setup section, Sprint 29/32/35
  precedent).
- `docs/product/backlog-first-run-setup-and-ops.md`'s SETUP-034/035 entries marked done with
  acceptance-criteria boxes checked and a pointer to the shipping ticket(s).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after both tickets are done, before production sign-off — this sprint ships real code touching
  operator authentication UX.

## Next (explicitly not this sprint)

- Should/Could-tier items elsewhere in `docs/product/backlog-first-run-setup-and-ops.md` not tied to
  this operator-UI gap (SETUP-015, 021, 022, 033) remain unscheduled for a future sprint.
