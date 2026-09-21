# BOOT-002 — `infra`: post-startup health verification for every started service, not just Postgres

**Sprint**: 54. **Module**: `infra`. **Status**: done (full-Docker-stack dry run not verified — no
working Docker daemon in this environment; isolated stub-server verification done instead, see Test
section below). **Priority**: Must.
**Depends on**: `BOOT-001` (merge/file-region reasons only — new step 0 + 2–7 renumbering must already
be landed in both scripts before this ticket's implementation starts; this ticket does not depend on
any output `BOOT-001` produces). **Blocks**: none — closing ticket of the sprint.
**Can run in parallel with**: nothing — sequenced strictly after `BOOT-001` is Tech-Lead-verified done,
per `docs/sprints/sprint-54.md`'s "Sequencing decision" section (same-region edits to the same two
files would otherwise conflict).

## Analysis

Per `docs/product/backlog-installation-ops.md`'s `BOOT-002` story: today's step 2 (now step 3 after
`BOOT-001`'s renumbering) already correctly bounded-retry-polls `postgres`'s own Docker health status
before proceeding. Confirmed directly by reading both scripts: the steps that start
`validation-service`/`gateway-api` (today's step 4) and `dashboard-web` (today's step 5) do not wait
for or check anything beyond the `docker compose` command's own exit code — a container that starts
and then crashes, or whose app process is up but its own `/health` would report a failure (e.g. a DB
connectivity issue), is not caught; the script proceeds straight to opening the browser at a URL that
may not actually be serving a working page. There is no final "validate the result" step in either
script today.

Confirmed independently (not assumed) before writing this ticket, per the Tech Lead's own instruction:
- `services/validation-service/src/app/main.py:42` — `@app.get("/health", response_model=None)` exists.
- `services/gateway-api/src/app/main.py:75` — `@app.get("/health", response_model=None)` exists.
- `services/dashboard-web/src/app/main.py:124` — `@app.get("/health", response_model=None)` exists,
  and per `infra/README.md`'s "dashboard-web assistant (AI-003)" section, this handler already makes a
  real call to `gateway-api`'s own `/health` (`DASH-008`) — a `200` here is proof of Compose-network
  reachability end to end for `gateway-api`, not just "the container starts."
- `infra/.env.example` already defines `VALIDATION_SERVICE_PORT=8001`, `GATEWAY_API_PORT=8000`,
  `DASHBOARD_WEB_PORT=8004` — the exact three env vars this story's AC names. No new env var is
  needed.

This ticket covers all of `BOOT-002`'s acceptance criteria as stated verbatim in
`docs/product/backlog-installation-ops.md`.

**Constraint from the docs**: orchestration/packaging only, same module-boundary note as `BOOT-001`
(implementation-plan.md section 2) — this ticket calls each service's already-existing, unmodified
`GET /health`; it does not add or change one, and touches no `services/*` code.

## Design

**Pattern**: none newly introduced — same "pure orchestration script change" stance as `BOOT-001` and
`SETUP-004`. None of implementation-plan.md section 7's patterns apply to a shell/PowerShell
bounded-retry HTTP poll.

**Files touched** (scoped to `infra/` only — build against `BOOT-001`'s already-merged renumbering,
i.e. start from the real post-`BOOT-001` step count of 7, not the pre-sprint baseline of 6):
- `infra/bootstrap.sh` — insert a new step between "start `dashboard-web`" and "open the browser"
  (post-`BOOT-001` positions: dashboard-web start is step 6/7, browser-open is step 7/7 — this new
  step becomes step 7/8, browser-open becomes step 8/8; renumber accordingly). For each of
  `validation-service` (`VALIDATION_SERVICE_PORT`, default `8001`), `gateway-api`
  (`GATEWAY_API_PORT`, default `8000`), then `dashboard-web` (`DASHBOARD_WEB_PORT`, default `8004`) —
  in that order, `dashboard-web` last per the AC's own reasoning — bounded-retry `curl`
  `http://localhost:<port>/health`, mirroring step 2's existing postgres loop shape (same
  max-attempts/sleep-interval, i.e. reuse the `attempt`/`max_attempts=30`/`sleep 2` shape, not a new
  polling mechanism). On any one service failing to reach `200` within the bound, `fail` naming that
  specific service (not the others, not a generic message). Print an "all services healthy" success
  message only once all three pass; the existing "opening the setup wizard" step's message keeps
  firing only after this new step passes (already true by construction if this step precedes it and
  uses the same `fail`/non-zero-exit convention).
- `infra/bootstrap.ps1` — identical structural change: same three services in the same order, same
  retry-loop shape as the PowerShell postgres loop (`$attempt`/`$maxAttempts`/`Start-Sleep`), `curl`
  equivalent via `Invoke-WebRequest`/`Invoke-RestMethod` (whichever this script's existing conventions
  favor — postgres's own health check uses `docker inspect`, not an HTTP call, so this is the first
  HTTP poll in this script; pick the mechanism that lets a non-`200`/connection-refused/timeout all
  resolve to the same "not healthy yet" retry branch, then bounded failure), same
  `Fail-Step`/non-zero-exit convention.
- `infra/README.md` — "First-boot bootstrap (INF-015)" section: extend the numbered list again for the
  new step and the final 8-step count (composing with `BOOT-001`'s already-landed 2–7 renumbering).

**DRY check note** (grepped both scripts, post-`BOOT-001`, before writing this ticket): the only
existing health/readiness-wait logic in either script is the postgres loop (step 2, pre-`BOOT-001`
numbering) — its `attempt`/`max_attempts`/`sleep` shape (bash) and
`$attempt`/`$maxAttempts`/`Start-Sleep` shape (PowerShell) is the pattern this new step must mirror,
per the AC's own explicit instruction ("not a new polling mechanism invented from scratch"). No
existing HTTP-polling helper exists in either script to reuse beyond that shape (the postgres check
uses `docker inspect`, not HTTP) — the dev implementing this ticket should factor the "poll one
service's `/health`" logic into a single reusable shell function/PowerShell function defined once and
called three times (`validation-service`, `gateway-api`, `dashboard-web`), not copy-pasted three times
inline — this is the module's own DRY-on-second-duplication rule (implementation-plan.md section 9)
applying within this one ticket, since the same poll logic is needed three times in one change.

## Implementation acceptance criteria

- [x] A new step, inserted after `dashboard-web` is started and before the browser-open step (composing
  with `BOOT-001`'s already-landed renumbering — final count 8 steps), polls each of
  `validation-service`'s / `gateway-api`'s / `dashboard-web`'s own `GET /health` using each service's
  documented host port (`VALIDATION_SERVICE_PORT`/`GATEWAY_API_PORT`/`DASHBOARD_WEB_PORT`, falling back
  to each service's documented default — `8001`/`8000`/`8004` — matching how the existing dashboard
  port fallback is already handled in the browser-open step) in a bounded retry loop mirroring step 2's
  existing postgres shape (same max-attempts/sleep-interval).
- [x] On any one service failing to report healthy (non-`200`, connection refused, or timeout) within
  the bounded retry window, the script fails loudly (non-zero exit) with a message naming the specific
  service that didn't come up — never a generic message, never silently continuing to the browser-open
  step.
- [x] `dashboard-web` is polled last, after `validation-service` and `gateway-api` are already confirmed
  — relies on `dashboard-web`'s own existing `/health` → `gateway-api`/`/health` call (`DASH-008`)
  rather than re-implementing a second cross-service check.
- [x] A success message ("all services healthy" or equivalent) prints only once every service in this
  step has passed; the existing "opening the setup wizard" message only fires after this step passes.
- [x] Both `bootstrap.sh` and `bootstrap.ps1` implement this step identically in structure (same
  services checked, same order, same retry bound, same failure-naming convention) — maintaining
  byte-for-byte structural parity between the two scripts.
- [x] The poll-one-service logic is factored into one reusable function per script, called three times
  — not copy-pasted three times inline (DRY, per the Design note above).

## Test acceptance criteria

- [x] This is an `infra`-level ticket with no `pytest` suite of its own (matching `INF-015`/`SETUP-004`/
  `BOOT-001`'s own precedent). Verification is a real, described dry run.
- [x] Isolated verification (does not require the full app stack — only something answering HTTP on the
  right ports): run each script's new health-poll function/step against a local stub HTTP server bound
  to each of the three ports in turn — (a) returning `200` on `/health` immediately → step passes
  without exhausting retries; (b) never coming up (nothing listening) → step exhausts its retry bound
  and fails loudly, naming the specific service; (c) returning a non-`200` status → treated the same as
  "not healthy," not silently accepted. **Actually run** for both bash (`wait_for_service_health`) and
  PowerShell (`Wait-ForServiceHealth`), reimplementing each script's own function body verbatim against
  a one-off Python `http.server.BaseHTTPRequestHandler` stub bound to a test port, with
  `max_attempts`/`sleep` temporarily lowered (3/1s) for the two failure-path cases only, per this
  ticket's own testing instructions — real `bootstrap.sh`/`bootstrap.ps1` still use `max_attempts=30`/
  `sleep 2`/`Start-Sleep -Seconds 2` unchanged. All six cases (3 bash + 3 PowerShell) passed: (a) healthy
  reported immediately without exhausting retries, (b) connection-refused exhausted the 3-attempt bound
  and reported `step 7 (<service> did not become healthy within 3 attempts...)`, (c) a `503` response
  was treated identically to (b), not silently accepted.
- [ ] Full dry run against a real Docker stack: happy path (all three services healthy) reaches the
  "all services healthy" message and then the browser-open step; a deliberately-broken run (one app
  container stopped or killed before this step) fails loudly, names that specific service, and never
  reaches the browser-open step. **Not run** — no working Docker daemon available in this environment
  (Docker Desktop requires elevated privileges here, per this ticket's own explicit instruction not to
  attempt a full `docker compose` run). Left for the Tech Lead or a future session with a working Docker
  daemon to verify; the isolated stub-server verification above exercises the exact same function/step
  logic, just not against the real containers.

## Review acceptance criteria (Tech Lead verifies personally)

- Reads the real `git diff` for both `infra/bootstrap.sh` and `infra/bootstrap.ps1` — confirms the new
  step exists in both, in the right position (after dashboard-web start, before browser-open), confirms
  the final step count/numbering is identical between the two scripts, confirms no unrelated line
  changed.
- Confirms the failure path actually names the specific failing service (not a generic message) by
  reading the actual conditional/fail-call code, and where feasible, by reproducing a real failure (a
  stub server that never responds, or a real stopped container) and reading the literal failure output.
- Confirms `dashboard-web` is polled last and the other two are polled first, per the AC's own ordering
  rationale.
- Confirms the poll logic is a single reusable function per script (not three inline copies) — DRY
  check against the ticket's own Design note.
- Confirms both scripts remain structurally identical to each other after this change (same step count,
  same order, same message shapes, same failure-naming convention) — side-by-side read, same discipline
  `docs/sprints/sprint-54.md`'s own DoD requires.
- Confirms this ticket's changes compose correctly with `BOOT-001`'s already-landed step 0/renumbering
  — no leftover "Step N/7" labels, no gap or duplicate step number anywhere in either script.

## Documentation acceptance criteria

- [x] `infra/README.md`'s "First-boot bootstrap (INF-015)" section updated again for the new step and
  the final 8-step count, composing with `BOOT-001`'s already-landed edit (not overwriting it).
- [x] `docs/product/backlog-installation-ops.md`'s `BOOT-002` entry's acceptance-criteria boxes checked
  and status marked done, pointing to this ticket file.
- [x] `docs/tickets/README.md`'s Sprint 54 / `BOOT-*` section updated with this ticket and its status.
