# SETUP-004 — `infra`: bootstrap script brings up the full stack and lands the operator in the wizard

**Sprint**: 29. **Module**: `infra`. **Status**: done. **Priority**: Must.
**Depends on**: `SETUP-003` (the page it opens), `SETUP-030` (the Compose entry that starts
`dashboard-web`). **Blocks**: none — closing ticket of the sprint.
**Can run in parallel with**: nothing — runs last, per the sprint's own sequencing.

## Analysis

Per `backlog-first-run-setup-and-ops.md`'s `SETUP-004` story: this is the integration point the whole
epic exists to close — "one command" only becomes true end to end once the bootstrap script's last
step is "open a working wizard," not "print a command the operator still has to run by hand." Builds
directly on `infra/bootstrap.sh`/`.ps1` (`INF-015`), whose current final step is "print the
`provision_tenant.py` invocation" — that step must be **kept, not deleted**, per the sprint's DoD
("demote, don't delete," the same convention `infra/README.md` already applies to its own hand-run
sequences and to `INF-016`'s migrate script relative to the original one-off command).

## Design

**Pattern**: none newly introduced — pure orchestration script change, matching `INF-015`'s own
"pure orchestration, delegating entirely" design stance.

**Files touched** (scoped to `infra/` only):
- `infra/bootstrap.sh` / `infra/bootstrap.ps1` — after the existing step 4 (`docker compose up -d
  --build validation-service gateway-api`), add a new step: `docker compose up -d --build
  dashboard-web` (depends on `SETUP-030`'s Compose entry existing), then attempt to open the default
  browser at `http://localhost:${DASHBOARD_WEB_PORT:-8004}/` — bash: `xdg-open`/`open` (platform-
  conditional, falling back to printing the URL if neither exists, e.g. a headless CI runner);
  PowerShell: `Start-Process`. The existing step 5 (print the `provision_tenant.py` invocation) is kept
  immediately after, unchanged in content, re-labeled as the non-interactive/CI-friendly alternative
  path (a short comment/echo line stating this, not a removal).
- `infra/README.md`'s "First-boot bootstrap (INF-015)" section — extended (not duplicated into a
  second section) with the new step, and the "demote, don't delete" framing for the retained
  `provision_tenant.py`-print step, cross-referencing this ticket.

**DRY check note** (grepped `infra/bootstrap.sh`/`.ps1` before writing this ticket): no existing
browser-opening step exists anywhere in either script — this is genuinely new, not a duplicate of
anything. The `docker compose up -d --build <service>` invocation shape is already used three times in
step 4 (Postgres/Redis are step 1, `validation-service`/`gateway-api` are step 4) — this ticket's new
`dashboard-web` step reuses that exact invocation shape, not a fourth differently-flagged variant.

## Implementation acceptance criteria

- [x] The bootstrap script's new final step starts `dashboard-web` via Compose (after `SETUP-030`'s
  entry exists) and opens the default browser at `http://localhost:<dashboard-port>/` — or, on an
  environment with no way to launch a browser, prints that same URL instead of failing (never a
  non-zero exit purely because no browser could be opened).
- [x] The existing "print the `provision_tenant.py` invocation" step is kept, unchanged in its
  printed content, documented as the non-interactive/CI-friendly alternative.
- [x] Running the full script twice in a row against an already-initialized stack (i.e. after a first
  run's wizard has already created a tenant) produces no duplicate tenant and no non-zero exit — relies
  on Compose `up` being idempotent (unchanged), migrations being idempotent (`INF-016`, unchanged), and
  `SETUP-003`'s own `/setup` → `/login` redirect on an already-initialized system (this ticket adds no
  new idempotency logic of its own — its own Definition of Done is running the script twice and
  confirming exactly one tenant exists afterward via `gateway-api`'s `GET /setup/status`).

## Test acceptance criteria

- [x] This is an `infra`-level ticket with no `pytest` suite of its own (matching `INF-015`'s own
  precedent) — verification is a real, described dry run: run `infra/bootstrap.ps1` against a stack
  with no prior tenant, confirm the browser opens (or the URL is printed) at the wizard, manually
  complete the wizard, then run the script a second time and confirm (a) no non-zero exit and (b)
  `curl http://localhost:8000/setup/status` still reports `{"initialized": true}` with exactly one
  tenant present (verified via a direct DB check or `gateway-api`'s own state, not merely the second
  run's own exit code).

## Review acceptance criteria (Tech Lead verifies personally)

- Personally re-runs the bootstrap script twice in a row against a real Compose stack (not merely
  reading the script's source), confirming the double-run guarantee above.
- Confirms the `provision_tenant.py`-print step's exact printed text is unchanged from before this
  ticket (diff-verifiable) — "demote, don't delete" actually held, not silently reworded away.
- Confirms the browser-open step degrades to printing the URL rather than failing on an environment
  with no browser launcher (tested directly, e.g. by temporarily removing `xdg-open`/mocking
  `Start-Process`'s failure path, not merely asserted).

## Documentation acceptance criteria

- [x] `infra/README.md`'s bootstrap section documents the new final step and the retained
  `provision_tenant.py`-print step's demoted-not-deleted status.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-004` entry's acceptance-criteria
  boxes are checked and its status marked done.
