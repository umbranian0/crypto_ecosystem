# Backlog — Installation/setup process ("stand up a fresh instance correctly and repeatably")

Source: `CLAUDE.md` (root positioning constraints — not directly load-bearing for infra/bootstrap
mechanics, but confirms this backlog introduces no product/UI scope of its own);
`docs/implementation-plan.md` sections 6 (trigger-based build order — no story here touches
`ingestion-service` connector configuration (trigger #6, already fired and built, but its *connector
config UI* is `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-013`'s territory, not this
backlog's) or introduces a metrics/alerting stack (that belongs in
`docs/product/backlog-trust-and-admin-ops.md`'s `ADMIN-001` if warranted, not here, per this task's own
explicit instruction); `infra/README.md` (read in full — the authoritative, currently-accurate narrative
of every Compose service, the bootstrap sequence, and every previously-found "real, disclosed infra gap"
this file already tracks in the same honest style this backlog continues); `infra/bootstrap.ps1` and
`infra/bootstrap.sh` (read in full, side by side — confirmed byte-for-byte parity in structure: 6
numbered steps each, same fail-loud convention, same "demote don't delete" final message); `infra/.env.example`
(read in full — confirms every secret already carries an inline disclosure comment, e.g. `OPERATOR_TOKEN`'s
"insecure dev-only default... change it in a real deployment," the same convention `BOOT-001` below
extends into the provisioning step itself); `docs/product/backlog-first-run-setup-and-ops.md` (full text
— confirms `SETUP-001`-`004`/`010`-`012`/`015`/`020`-`022`/`030`/`034`/`035` are done, and critically that
`SETUP-031`/`032`/`033` (Epic D, "Portability") are still open, unchecked Must/Could stories already
covering the broader "audit hardcoded assumptions" and "single documented command on a genuinely fresh
machine" asks — this backlog does not duplicate either, see the "Relationship to `SETUP-031`/`032`/`033`"
note below).

## Scope

This backlog is **operator-facing infrastructure-startup process** scope only: "does `infra/bootstrap.sh`/
`.ps1` reliably take a genuinely fresh checkout to a correctly-configured, verifiably-healthy running
stack." It is deliberately **not** `docs/product/backlog-first-run-setup-and-ops.md`'s territory (that
backlog covers in-product tenant/operator UI features — the setup wizard's own screens, Settings pages,
the Monitoring page's UI) and not `docs/product/backlog-trust-and-admin-ops.md`'s territory (product
upgrades, admin/ops UI maturity). Two concrete, evidence-based gaps anchor this backlog (`BOOT-001`/
`BOOT-002`); a third (`BOOT-003`) is a smaller, related finding from the same file-reading pass.

**Relationship to `SETUP-031`/`032`/`033` (`backlog-first-run-setup-and-ops.md` Epic D), stated
explicitly so nothing here is read as a duplicate**: those three stories are still open (unchecked
acceptance criteria as of this writing) and already own the *broader* portability audit ("every literal
filesystem path... audited and fixed," `SETUP-031`) and the *end-to-end proof* that one documented
command works on a genuinely fresh machine (`SETUP-032`). `BOOT-001`/`BOOT-002` below are **narrower,
concrete implementation gaps** found by directly reading `infra/bootstrap.ps1`/`.sh`/`infra/README.md`/
`infra/.env.example` — they are exactly the kind of finding `SETUP-031`'s own audit and `SETUP-032`'s own
fresh-machine dry run are structured to surface and fix. Whichever backlog's tickets get scheduled first,
the Tech Lead should treat `BOOT-001`/`BOOT-002` and `SETUP-031`/`032` as the same body of work from two
different entry points, not duplicate it. This backlog's own stories are written narrowly enough (one
concrete script step each) that they can be picked up standalone, ahead of or instead of `SETUP-031`/`032`
being scheduled as a whole, without conflicting with them.

**A related, but explicitly *not* re-scoped, finding for the Tech Lead's awareness**: `infra/README.md`'s
own "Applying a new migration (INF-016)" section already discloses that `infra/migrate.sh`/`.ps1` "fails
loudly... if a service's `.venv` doesn't exist yet (create it first, e.g. `cd services/<service>; uv
sync`)." On a genuinely fresh clone that has never run `uv sync` for `validation-service`/`gateway-api`,
`infra/bootstrap.sh`/`.ps1`'s step 3 (`infra/migrate.sh both`) would fail for exactly this reason. This is
almost certainly one of the concrete things `SETUP-032`'s own Definition of Done (an actual dry run
against "no cached `.venv`") will surface and need to fix — it is named here for visibility, not
re-ticketed as a fourth `BOOT-*` story, since `SETUP-032` already owns "fresh machine, no cached `.venv`"
as a named condition in its own acceptance criteria.

**Out of scope, per this task's own explicit instruction**: `ingestion-service` connector configuration
(a *product* config surface, `SETUP-013`'s territory, separately Won't-status pending trigger #6's config
UI ask, not an installation-process concern) and any metrics/alerting stack (see
`docs/product/backlog-trust-and-admin-ops.md`'s `ADMIN-001` instead, which already re-evaluates and
scopes the one narrow escalation warranted today — this backlog introduces no second alerting story).

## Prioritization scheme

MoSCoW, the same convention every other backlog file in `docs/product/` already uses.

---

## Stories

### BOOT-001 — Auto-provision `infra/.env` from `infra/.env.example` when missing [Must] — **Status: done, see `docs/tickets/BOOT-001.md`**

As a developer or pilot-deployment operator bringing this stack up for the first time, I want
`infra/bootstrap.sh`/`.ps1` to create `infra/.env` from `infra/.env.example` automatically when it's
missing, so that "copy `infra/.env.example` to `infra/.env`... before starting anything" (`infra/README.md`'s
own current instruction) is no longer a manual, easy-to-forget, error-prone step standing between a fresh
clone and a working stack.

**Real gap, confirmed directly**: `infra/README.md` states plainly, ahead of the bootstrap section, "Copy
`infra/.env.example` to `infra/.env`... before starting anything" — a manual step with no automation and
no check. Neither `bootstrap.sh` nor `bootstrap.ps1` references `.env`/`.env.example` anywhere in their
current 6-step sequence (confirmed by reading both scripts in full) — a fresh clone with no pre-existing
`infra/.env` would have every `docker compose` invocation in the script fall back to `docker-compose.yml`'s
own hardcoded defaults for any variable not otherwise set in the shell environment, silently diverging
from the "one documented command, one documented config source" story `infra/README.md` otherwise tells.

Acceptance criteria:
- [x] A new step 0 (renumbering the existing 6 steps to 7) in both `infra/bootstrap.sh` and
  `infra/bootstrap.ps1`: if `infra/.env` does not exist, copy `infra/.env.example` to `infra/.env`
  verbatim (byte-for-byte, not regenerated/re-templated) and print a clear message naming the file just
  created.
- [x] If `infra/.env` already exists, this step is a silent no-op (never overwrites an existing file, even
  if it appears to differ from `.env.example` — drift detection, if wanted, is `BOOT-003`'s territory, not
  this story's) — the same "never destroy operator-set state" discipline `SETUP-004`'s idempotency
  guarantee already models for tenant data.
- [x] The printed message, when a fresh `.env` was just created, explicitly names which values are known,
  disclosed-insecure dev-only defaults that should be changed before any non-local deployment —
  enumerating the same values `.env.example`'s own inline comments already flag individually
  (`OPERATOR_TOKEN`, `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`, `INGESTION_CREDENTIAL_ENCRYPTION_KEY`,
  `INGESTION_INTERNAL_TOKEN`) — this step surfaces that existing disclosure at the moment it matters most
  (first boot), it does not invent new secret-strength policy.
- [x] Both scripts implement this identically in structure (same step, same message shape, same
  file-existence check), maintaining the byte-for-byte parity `infra/bootstrap.sh`/`.ps1` already have
  today — a `sh -c '[ -f infra/.env ]'`-equivalent check on the bash side, a `Test-Path`-equivalent check on
  the PowerShell side.
- [x] `infra/README.md`'s own "Copy `infra/.env.example` to `infra/.env`... before starting anything"
  instruction is updated to state this now happens automatically as part of `infra/bootstrap.sh`/`.ps1`'s
  first step, with the manual copy kept documented as the fallback for anyone running services
  individually without the bootstrap script (same "demote, don't delete" convention `infra/README.md`
  already applies to its own hand-run sequences).
- [x] Running the full script twice in a row (second run against an already-created `.env`) produces no
  change to `infra/.env` and no error — the same idempotency bar `SETUP-004`'s own live-verified
  two-runs-in-a-row test already set for this script.

Rationale for priority: Must — this is one of the two concrete, explicitly named real gaps this backlog
exists to close; without it, "one command on a fresh machine" is still not true, since that one command
depends on a config file the command itself never creates.
Depends on: none

### BOOT-002 — Post-startup health verification for every started service, not just Postgres [Must] — **Status: done, see `docs/tickets/BOOT-002.md`**

As a developer or operator running `infra/bootstrap.sh`/`.ps1`, I want the script to wait for and verify
`validation-service`, `gateway-api`, and `dashboard-web` to actually report healthy before declaring
success, and to fail loudly naming the specific service if one doesn't, so that "the bootstrap script
succeeded" is a real, checked claim about the whole stack, not just about Postgres being up and the
`docker compose up -d` commands having been issued.

**Real gap, confirmed directly**: today's step 2 already does exactly this correctly for `postgres` (a
bounded retry loop polling `docker inspect --format '{{.State.Health.Status}}'`, failing loudly on
timeout). Steps 4 and 5 (`docker compose up -d --build validation-service gateway-api`, then `docker
compose up -d --build dashboard-web`) do not wait for or check anything beyond the `docker compose`
command's own exit code — a container that starts and then immediately crashes, or one whose application
process is up but its own `/health` check would report `503` (e.g. a database-connectivity failure), would
not be caught; the script proceeds straight to opening the browser at a URL that may not actually be
serving a working page yet. There is no final "validate the result" step anywhere in either script.

Acceptance criteria:
- [x] A new step, inserted after `dashboard-web` is started and before the browser-open step (renumbering
  accordingly, and composing with `BOOT-001`'s new step 0 — final step count and numbering is the Tech
  Lead's call, but the *order* must be: env provisioned -> postgres/redis up+healthy -> migrations ->
  app services started -> **all app services verified healthy** -> browser opened), polls each of
  `validation-service`'s, `gateway-api`'s, and `dashboard-web`'s own `GET /health` endpoint (using each
  service's documented host port — `VALIDATION_SERVICE_PORT`/`GATEWAY_API_PORT`/`DASHBOARD_WEB_PORT`, same
  env vars `infra/.env`/`.env.example` already define) in a bounded retry loop, mirroring step 2's existing
  `postgres` healthy-wait pattern (same max-attempts/sleep-interval shape, not a new polling mechanism
  invented from scratch).
- [x] On any one service failing to report healthy (non-`200`, connection refused, or timeout) within the
  bounded retry window, the script fails loudly (non-zero exit) with a message naming the specific service
  that didn't come up — not a generic "something failed" message, and not silently continuing to the
  browser-open step regardless.
- [x] `dashboard-web`'s own `/health` check already makes a real call to `gateway-api`'s `/health`
  (`DASH-008`, per `infra/README.md`'s own existing documentation) — this story's new step relies on that
  existing behavior rather than re-implementing a second cross-service check; polling `dashboard-web`'s
  `/health` last (after `validation-service`/`gateway-api` are already confirmed) gives the clearest
  failure attribution if something is wrong.
- [x] A success message ("all services healthy") is printed only once every service in this new step has
  passed — the existing "opening the setup wizard" step 6 message stays, but now only fires after this
  new verification step passes, not immediately after the `docker compose up` commands return.
- [x] Both `bootstrap.sh` and `bootstrap.ps1` implement this step identically in structure (same services
  checked, same retry bound, same failure-naming convention) — maintaining the existing byte-for-byte
  parity between the two scripts.
- [x] `infra/README.md`'s "First-boot bootstrap (INF-015)" section is updated to document the new step
  (and the renumbered step count) in its existing numbered-list format.

Rationale for priority: Must — this is the second of the two concrete, explicitly named real gaps this
backlog exists to close; without it, a bootstrap run that silently leaves one service unhealthy still
reports the same "success, opening browser" outcome as a genuinely healthy run, which is exactly the kind
of false-positive a "stand up a fresh instance correctly and repeatably" promise cannot tolerate.
Depends on: none (composes with, but does not require, `BOOT-001` — the two can be built/reviewed
independently and merged in either order; final step renumbering just needs to account for both)

### BOOT-003 — Warn (don't auto-fix) on drift between an existing `infra/.env` and `infra/.env.example` [Could]

As a returning developer whose `infra/.env` predates a variable added to `infra/.env.example` since
(e.g. a new service's required env var), I want the bootstrap script to warn me that my `.env` is missing
keys `.env.example` now defines, so that I find out at bootstrap time rather than via a confusing runtime
failure in whichever service silently falls back to a default or fails to start.

Acceptance criteria:
- [x] After `BOOT-001`'s existence check (this story only runs when `infra/.env` already exists — a freshly
  auto-provisioned one is by definition not drifted), the script compares the set of variable *names*
  (left-hand side of each `KEY=value` line) present in `infra/.env.example` against those present in
  `infra/.env`, and prints a warning listing any keys present in the example file but missing from the
  real one.
- [x] **Warn only, never auto-edit `infra/.env`** — this story does not append missing keys, does not
  merge files, and does not change any existing value; an operator's own file is never silently rewritten,
  the same "never destroy operator-set state" discipline `BOOT-001` already commits to.
- [x] A missing-keys warning does not fail the script (non-zero exit) — it's advisory only, since a
  missing key might be genuinely optional (e.g. `NARRATIVE_API_URL`, already documented as "unset by
  default" in normal operation) and the script cannot distinguish "optional and intentionally unset" from
  "required and forgotten" without a second layer of metadata this story does not introduce.
- [x] Both scripts implement this identically in structure, same as every other story in this backlog.

Rationale for priority: Could — a real, disclosed nicety (fits the "reliably end up correctly configured"
ask) but lower-stakes than `BOOT-001`/`BOOT-002`: an operator hitting drift today gets a real, if less
friendly, runtime error from whichever service is missing its var, so this is a UX improvement on an
already-surfacing failure mode, not a silent-failure gap like the two Must stories above.
Depends on: BOOT-001 (reuses its existence-check step as the gate for when this one applies)

---

## Summary

| Priority | Count | IDs |
|---|---|---|
| Must | 2 | BOOT-001, BOOT-002 |
| Could | 1 | BOOT-003 |

**Explicit note for the requester/PM/Tech Lead**: this backlog is intentionally small (three stories) —
per this task's own instruction, only the two named real gaps plus one directly-adjacent finding from the
same read-through are scoped here; `SETUP-031`/`032`/`033` (already open in
`backlog-first-run-setup-and-ops.md`) remain the right place for the *broader* fresh-machine portability
audit and its own cross-platform CI verification. See the "Relationship to `SETUP-031`/`032`/`033`" note
above for exactly how these two backlogs' scopes relate, and the disclosed-but-not-re-ticketed
`.venv`-before-`migrate.sh` finding, which is almost certainly something `SETUP-032`'s own fresh-machine
dry run will need to fix as part of doing that story properly.
