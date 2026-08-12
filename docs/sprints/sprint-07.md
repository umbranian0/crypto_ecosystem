# Sprint 07 — RLS enforcement + repeatable migration/bootstrap tooling (infra)

Sprint goal: Make the RLS policies `VS-013`/`GW-012` already shipped actually enforced by the running services (not just proved in test), and replace the remaining hand-run, tribal-knowledge migration/bootstrap sequences with small, repeatable scripts — without leaving either script needing a follow-up refactor once the other lands.

Backlog source: `docs/product/backlog-infra.md` — INF-014, INF-015, INF-016 (INF-017 explicitly deferred, see below).

## Sequencing decision (stated explicitly, not left for the Tech Lead to infer)

**Order: INF-014 → INF-016 → INF-015.**

1. **INF-014 runs first, on its own.** It has no dependency on INF-015/016's content, and nothing in INF-015/016 needs INF-014's *code* to exist before they can be written in the abstract. But INF-015's own acceptance criteria requires its bootstrap script to invoke Alembic "using the **migration-time** role (see INF-014 — post-INF-014, this is `naive_first`, not the new runtime-only role)" — i.e., the bootstrap script's content is coupled to knowing INF-014's final role names, even though it isn't coupled to INF-014's implementation existing first in a build sense.

   Two ways to resolve that coupling were considered:
   - (a) Sequence INF-014 first, so INF-015/016 are written to reference the concrete, final role name (`naive_first` for migrations, `naive_first_app` for runtime) directly.
   - (b) Run INF-014 in parallel, and write INF-015/016 role-name-agnostic — e.g. reading the migration role from an env var (`MIGRATION_DATABASE_URL` or similar) that defaults sensibly, so the scripts never hardcode a role name and don't care which sprint-internal order INF-014 lands in.

   **Decision: (a) — sequence INF-014 first.** Reasoning: INF-014's acceptance criteria already commits to a concrete migration-role identity (`naive_first`, repurposed as migration-only) and a concrete new runtime role (e.g. `naive_first_app`) — this isn't an open design question INF-015/016 would need to abstract around, it's a fixed name INF-014 itself decides. Writing INF-015/016 against an env-var abstraction just to dodge a same-sprint ordering choice would add indirection for a coupling that's fully resolved by simply doing INF-014 first — a small, low-risk, independent story with no reason to be deferred. Running INF-014 in parallel would force INF-015/016's dev-agent to either guess the role names (risking exactly the "follow-up refactor" INF-016's own ticket text warns against, applied to INF-015 instead) or block mid-story waiting on INF-014 anyway, which is just serial execution with extra ceremony. Sequencing INF-014 first removes the ambiguity outright: by the time INF-015/016 are written, `naive_first` (migration-time) and the new runtime-only role are both real, named things to reference concretely.

2. **INF-016 before INF-015**, per INF-016's own acceptance criteria note: "once INF-015 ships, this story's script should be the thing INF-015 calls internally for its own migration step... sequence INF-016 before or alongside INF-015, not strictly after, to avoid INF-015 needing a follow-up refactor." This is a stated ordering preference inside INF-016's ticket text, not a formal `Depends on:` line (INF-016's formal dependency is only INF-005, already satisfied in Sprint 06), but it is honored here as a hard sequencing constraint: INF-015's bootstrap script is written to call INF-016's `infra/migrate.sh`/`infra/migrate.ps1` for its own migration step, rather than duplicating the `alembic upgrade head` invocation logic. Building INF-015 first would mean either re-deriving that invocation twice or refactoring INF-015 the moment INF-016 lands — exactly the rework the ticket text flags.

Net order: **INF-014, then INF-016, then INF-015.**

## Stories in scope, in execution order

1. **INF-014** [Must] — Non-superuser Postgres application role for `validation-service`/`gateway-api`, with the existing `naive_first` role repurposed as migration-only. Runs first: independent of INF-015/016 in a build sense, and its output (the final migration-role vs. runtime-role names) is what INF-015 needs to reference concretely, per the sequencing decision above. Depends on (per backlog, already satisfied prior to this sprint): INF-001, VS-013, GW-012.
2. **INF-016** [Should] — Repeatable "apply new migrations" command (`infra/migrate.sh <service>` / `infra/migrate.ps1 -Service <service>`), using the migration-time role INF-014 established. Runs second, ahead of INF-015, per INF-016's own ticket-text ordering note, so INF-015 can call it rather than duplicating its logic. Depends on: INF-005 (satisfied in Sprint 06); sequenced here (not strictly required by a formal dependency) ahead of INF-015 per the ticket's explicit ordering preference.
3. **INF-015** [Should] — First-boot bootstrap script that brings up Compose, waits for Postgres healthy, and runs both services' migrations — internally calling INF-016's script for the migration step, and using the migration-time role INF-014 named. Runs last: its content depends on both INF-014's final role names and INF-016's script existing to be called rather than duplicated. Depends on: INF-001, INF-002, INF-003, INF-004, INF-005 (all satisfied in Sprint 06); additionally sequenced after INF-014 and INF-016 within this sprint per the reasoning above.

## Stories explicitly deferred

- **INF-017** [Won't] — DB-backed operator/tenant configuration. Deferred per the backlog's own recorded decision: no concrete operator- or tenant-level behavior difference currently exists in the running platform for a settings table to serve; the two buckets of configuration found (bootstrap values, which are structurally DB-incompatible, and a single non-tenant-specific timeout default) don't warrant one. User has confirmed accepting the decline — not scheduled this sprint or any future one until a concrete per-tenant/per-operator behavior difference is identified (the backlog's own stated revisit trigger).

## Definition of done for this sprint

- The new non-superuser Postgres role (e.g. `naive_first_app`) exists via `infra/postgres-init/`, has exactly the runtime privileges the services need (`SELECT`/`INSERT`/`UPDATE`/`DELETE` on `validation.*`/`identity.*`) and no `CREATE`/ownership/`CREATEDB`/`CREATEROLE`; `naive_first` is repurposed as migration-only and keeps schema/table ownership.
- `infra/docker-compose.yml`'s `validation-service`/`gateway-api` `DATABASE_URL` (app-runtime) points at the new non-superuser role; `infra/.env.example` documents both roles and states which is used for migration vs. runtime.
- A real, end-to-end verification confirms cross-tenant isolation is enforced by Postgres RLS itself (not just application-level filtering) against the actual running app containers, per INF-014's acceptance criteria.
- `gateway-api`'s README "Known infra caveat" paragraph and `docs/tickets/README.md`'s Sprint 06 INF-014 flag are both updated to state the gap is resolved.
- `infra/migrate.sh` / `infra/migrate.ps1` runs `alembic upgrade head` for a named service or both, against the real Compose Postgres, using the migration-time role; documented as safe to run repeatedly; `infra/README.md` gains an "Applying a new migration" section pointing at it.
- `infra/bootstrap.sh` / `infra/bootstrap.ps1` runs Compose up, waits on Postgres healthy, then calls INF-016's migrate script (not a duplicated invocation) for both services using the migration-time role, then starts/restarts both services, fails loudly and non-zero on any step failure, and prints `provision_tenant.py`'s exact command as its final "next step" rather than auto-running it. `infra/README.md` leads with this script as the recommended first-boot path, with the prior hand-run sequence demoted underneath as "what the script does, spelled out."
- No change to any file under `services/validation-service/src/` or `services/gateway-api/src/` beyond what INF-014's role/DI wiring requires (no unrelated application logic touched).

## Handoff to Tech Lead

- Sprint file: `docs/sprints/sprint-07.md`
- Sprint goal: see above.
- Ordered story list: INF-014 (Must) → INF-016 (Should) → INF-015 (Should).
- Dependency/risk notes:
  - INF-014 has no code dependency on INF-015/016 but must land first in this sprint because INF-015's bootstrap script needs to reference INF-014's *final, concrete* role names (migration-time `naive_first`, new runtime-only role) — sequencing INF-014 first was chosen over writing INF-015/016 role-name-agnostic via env var, to avoid adding abstraction for a coupling a same-sprint ordering choice fully resolves.
  - INF-016 must land before or alongside INF-015, per INF-016's own ticket text, so INF-015's bootstrap script calls INF-016's migrate script internally instead of duplicating the `alembic upgrade head` invocation — building INF-015 first would force a follow-up refactor the moment INF-016 shipped.
  - INF-014's verification step requires temporarily disabling or reviewing the application-level tenant filter to prove RLS (not app-level filtering) is what's actually stopping cross-tenant reads — flag this to whoever executes it as a deliberate, temporary, reviewed change, not a permanent removal.
  - INF-017 is out of scope this sprint and not queued for any future sprint; no action needed unless a concrete per-tenant/per-operator behavior difference is later identified.
