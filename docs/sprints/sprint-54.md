# Sprint 54 — `infra`: fresh-checkout bootstrap reliability (BOOT-001/BOOT-002)

Sprint goal: a developer or operator running `infra/bootstrap.sh`/`.ps1` against a genuinely fresh
checkout ends up with `infra/.env` auto-provisioned and every started application service
(`validation-service`, `gateway-api`, `dashboard-web`, not just `postgres`) verified actually healthy
before the script declares success and opens the browser — so "the bootstrap script succeeded" becomes
a real, checked claim about the whole stack, and "one command on a fresh machine" no longer silently
depends on a manual step the command itself never performs.

Backlog source: `docs/product/backlog-installation-ops.md` — `BOOT-001` and `BOOT-002` (both Must).
`BOOT-003` (Could) is read and considered but not scheduled this sprint — see "Deferred" below.

## Verification of the PO's cited findings (done independently, not taken on trust)

- `infra/README.md`: confirmed it states, ahead of the bootstrap section, "Copy `infra/.env.example`
  to `infra/.env` (or a repo-root `.env`) before starting anything" — a manual instruction with no
  accompanying automation or existence check. The "First-boot bootstrap (INF-015)" section's own
  numbered list (steps 1–7, including the demoted `provision_tenant.py` print) never mentions `.env`.
- `infra/bootstrap.sh` and `infra/bootstrap.ps1`: read in full, side by side. Confirmed byte-for-byte
  structural parity — both implement exactly six numbered steps (`Step 1/6` through `Step 6/6`,
  labelled identically in each script's own language): (1) `docker compose up -d postgres redis`,
  (2) bounded-retry `docker inspect` health-poll for `postgres`, (3) delegate to `migrate.sh`/`.ps1
  both`, (4) `docker compose up -d --build validation-service gateway-api` with no wait/verify beyond
  the compose command's own exit code, (5) `docker compose up -d --build dashboard-web`, same no-wait
  gap, (6) open/print the wizard URL. Confirmed neither script references `.env`/`.env.example`
  anywhere. Confirmed step 4/5 indeed do not poll any `/health` endpoint or container health status —
  the only health-wait logic in either script is step 2's `postgres` loop. Both scripts share the
  same `fail`/`Fail-Step` fail-loud convention and the same final "demoted, not deleted"
  `provision_tenant.py` print. `BOOT-002`'s gap description matches what's actually in both files.
- Net: both stories' "real gap, confirmed directly" claims hold up against the actual source, not just
  the backlog file's citation of it.

## Sequencing decision: BOOT-001 then BOOT-002, not parallel-eligible

Both stories are Must, have no acceptance-criteria dependency on each other's *output*, and the
backlog file itself states they "can be built/reviewed independently and merged in either order."
That is true in isolation — but both stories edit the same numbered-step sequence, in the same
region, of the same two files (`infra/bootstrap.sh`, `infra/bootstrap.ps1`), plus the same section of
`infra/README.md`:

- `BOOT-001` inserts a new step 0 at the top of both scripts and **renumbers every existing step, 6
  total to 7 total** — meaning every `"Step N/6"` echo/`Write-Host` line in both scripts changes, not
  just the first one.
- `BOOT-002` inserts a new health-verification step between "start `dashboard-web`" (today's step 5)
  and "open the browser" (today's step 6), and its own acceptance criteria explicitly say the final
  step count/numbering "is the Tech Lead's call, but... must account for both [BOOT-001 and
  BOOT-002]" — i.e. the story's own text anticipates composing with BOOT-001's renumbering, not
  standing alone.

If built as two independent, parallel branches against the current 6-step baseline, both would touch
nearly every `"Step N/6"` line in both files (BOOT-001 shifts all six; BOOT-002 touches at least
steps 5 and 6 and introduces a new one), producing a merge conflict across most of each script's body
rather than a clean line-level merge — and worse, a naive resolution could silently produce wrong
step numbers/order (e.g. two different steps both labelled "Step 6/7"). This is a same-region,
same-file conflict, not just a same-file conflict in disjoint areas (contrast with Sprint 29's
`SETUP-001`/`SETUP-010`, which touched the same file but genuinely disjoint code). **Decision:
sequence, one-then-the-other.** `BOOT-001` first, because it establishes the new baseline step count
(0–7) that `BOOT-002` needs to insert into cleanly; `BOOT-002` second, inserting its new step locally
near the end of that already-renumbered sequence. Do not start `BOOT-002`'s implementation until
`BOOT-001` is merged.

## Stories in scope, in execution order

1. **BOOT-001** — Auto-provision `infra/.env` from `infra/.env.example` when missing.
   - Files touched: `infra/bootstrap.sh`, `infra/bootstrap.ps1` (new step 0, existing steps 1–6
     renumbered to 2–7), `infra/README.md` ("Copy `infra/.env.example`..." instruction updated to
     state this now happens automatically, manual copy kept as the documented fallback for anyone
     running services individually without the bootstrap script; "First-boot bootstrap (INF-015)"
     section's numbered list updated for the new step 0/renumbering).
   - AC highlights: file-existence check only (`[ -f infra/.env ]` / `Test-Path`-equivalent) — never
     overwrites an existing `.env`, even if it looks drifted (drift detection is `BOOT-003`'s
     territory, not this story's); verbatim byte-for-byte copy, not re-templated; on fresh-create,
     prints a message naming the file created and explicitly enumerating the known disclosed-insecure
     dev-only defaults (`OPERATOR_TOKEN`, `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`,
     `INGESTION_CREDENTIAL_ENCRYPTION_KEY`, `INGESTION_INTERNAL_TOKEN`) that should be changed before
     any non-local deployment; identical structure in both scripts; running the full script twice in a
     row produces no change to `infra/.env` and no error (same two-runs-in-a-row idempotency bar
     `SETUP-004` already set).
   - Why first: establishes the new step-count baseline (7 steps) `BOOT-002` needs to insert into.

2. **BOOT-002** — Post-startup health verification for `validation-service`, `gateway-api`, and
   `dashboard-web`, not just `postgres`.
   - Files touched: `infra/bootstrap.sh`, `infra/bootstrap.ps1` (new step inserted after
     `dashboard-web` is started and before the browser-open step, composing with `BOOT-001`'s new step
     0 — final count is 8 steps, Tech Lead's call on exact numbering), `infra/README.md` ("First-boot
     bootstrap (INF-015)" section updated again for the new step and final step count).
   - AC highlights: bounded-retry poll of each of `validation-service`'s / `gateway-api`'s /
     `dashboard-web`'s own `GET /health`, using each service's documented host port
     (`VALIDATION_SERVICE_PORT` / `GATEWAY_API_PORT` / `DASHBOARD_WEB_PORT`), mirroring step 2's
     existing `postgres` retry-loop shape, not a new polling mechanism; on any one service failing to
     report healthy within the bound, fails loudly (non-zero exit) naming the specific service, never a
     generic message and never silently proceeding to open the browser; polls `dashboard-web` last
     (it already calls `gateway-api`'s own `/health`, per `DASH-008`, so ordering it last gives the
     clearest failure attribution); the existing "opening the setup wizard" success message only fires
     after this new step passes; identical structure in both scripts.
   - Depends on `BOOT-001` only for merge/file-region reasons (see Sequencing decision above), not on
     any output BOOT-001 produces — build against `BOOT-001`'s already-merged renumbering, not its
     unmerged branch.

## Story explicitly deferred

- **BOOT-003** — Warn (don't auto-fix) on drift between an existing `infra/.env` and
  `infra/.env.example` [Could]. Deferred, not scheduled this sprint. Reasoning: it is a real, cleanly
  composable follow-on to `BOOT-001`'s existence-check step (its own stated dependency), and nothing
  found during verification makes it unsafe to bundle in — but this sprint is deliberately scoped to
  the two named Must gaps only. Adding a third, lower-stakes story (an operator hitting drift today
  still gets a real, if less friendly, runtime error — not a silent failure like the two Musts above)
  widens the diff on the same two already-being-renumbered scripts for marginal near-term value, with
  no pilot client or incident currently driving urgency. Revisit in the next infra-scoped sprint,
  sequenced after `BOOT-001` is merged (its dependency is already satisfied at that point).

## File-overlap / concurrent-work risk

- `infra/bootstrap.sh` and `infra/bootstrap.ps1` — both stories touch the full numbered-step sequence
  of both files; this is the reason for the one-then-other sequencing decision above, not merely a
  note for parallel implementers to coordinate around.
- `infra/README.md`'s "First-boot bootstrap (INF-015)" section — touched by both stories in sequence
  for the same reason; expect two edits to this section's numbered list, not one.
- No other file in the repo is touched by either story. Neither story changes `infra/docker-compose.yml`,
  `infra/.env.example`, `infra/migrate.sh`/`.ps1`, or any `services/*` code.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

- Both stories live entirely inside `infra/` — orchestration/packaging only. Neither touches
  `libs/*` or any `services/*` application code; `BOOT-002`'s health checks call each service's
  already-existing, unmodified `GET /health` endpoint, they don't add or change one.
- `infra`'s own trigger (#4) already fired several sprints ago and the module is built; this sprint
  does not depend on any not-yet-built module and does not cross any unfired trigger.
- No leakage-aware protocol code (`naive_first_engine`, DM-test computation) is touched by either
  story.
- The disclosed-but-not-re-ticketed finding in `backlog-installation-ops.md` (fresh-clone `.venv`
  missing before `infra/migrate.sh both`'s step 3 would fail) is **not** in this sprint's scope — it
  is `SETUP-032`'s (already-open, separate backlog) territory, named here only so the Tech Lead isn't
  surprised by it if hit during this sprint's own live dry-run verification.

## Definition of done for this sprint

- `BOOT-001` and `BOOT-002`'s acceptance criteria (as stated verbatim in
  `docs/product/backlog-installation-ops.md`) are checked off in each ticket, in the order above.
- Both `infra/bootstrap.sh` and `infra/bootstrap.ps1` remain structurally identical to each other
  (same step count, same step order, same message shapes, same failure-naming convention) after both
  stories land — verified by a side-by-side read, the same way this sprint's own pre-read verified the
  pre-existing parity.
- A live dry run against a genuinely fresh Postgres volume (same discipline `SETUP-004`/`INF-018`'s
  prior sprints already established): first run creates `infra/.env` and reports all services
  healthy before opening the browser; second run (already-initialized stack, `.env` already present)
  is a no-op on `.env` and still reports all services healthy; a deliberately-broken service (e.g. one
  app container stopped before the health-check step) causes the script to fail loudly, naming that
  specific service, and never reaches the browser-open step.
- `infra/README.md` updated in place, in the same tickets that change the scripts' behavior — the
  "Copy `infra/.env.example`..." instruction and the "First-boot bootstrap (INF-015)" numbered list
  both reflect the final, composed step sequence.
- `docs/product/backlog-installation-ops.md`'s `BOOT-001`/`BOOT-002` entries marked done with
  acceptance-criteria boxes checked, pointing to their ticket files.
- `docs/tickets/README.md` gets a new Sprint 54 section (Tech Lead updates this when tickets are
  created/closed, per this repo's standing convention — not done by this sprint plan itself).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after both tickets are Tech-Lead-verified done, before sign-off. QA scope should specifically,
  independently verify: the two-runs-in-a-row idempotency claim for `BOOT-001` (no `.env` change, no
  error); that `BOOT-002`'s failure path actually fails loudly and names the right service (not merely
  that the happy path passes); and that both scripts remain structurally identical after both changes.

## Next (explicitly not this sprint)

- `BOOT-003` (env-drift warning) — see "Story explicitly deferred" above.
- `SETUP-031`/`032`/`033` (`backlog-first-run-setup-and-ops.md` Epic D — broader portability audit and
  fresh-machine dry run) remain open, separately-scoped stories this sprint does not duplicate or
  close; the Tech Lead should treat `BOOT-001`/`BOOT-002` and `SETUP-031`/`032` as the same body of
  work from two different entry points, per the backlog file's own note.
- `docs/product/backlog-trust-and-admin-ops.md` (Trust & Transparency, Reporting depth, Admin/Ops
  Maturity, Onboarding epics) is read and understood but deliberately not sequenced this pass — a
  separate PM planning pass covers it once this sprint ships.
