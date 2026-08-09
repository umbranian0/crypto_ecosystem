# Sprint 06 — debt sprint: shared scaffolding cleanup + infra + Postgres/Redis migration (technical-upgrades, infra, validation-service, gateway-api)

Sprint goal: Stand up real Postgres/Redis infra in Docker Compose and land the two real services' Postgres-backed repositories (plus Redis publisher) on top of cleaned-up, de-duplicated shared scaffolding — so `validation-service` and `gateway-api` stop depending on interim SQLite and the debt this sprint exists to close (duplicated engine-bootstrap code, per-request engine instantiation, duplicated wire-contract models, "planned"-but-never-built infra) doesn't get baked into two independent Postgres implementations instead of fixed once.

Backlog source:
- `docs/product/backlog-technical-upgrades.md` — ARCH-001, ARCH-002, ARCH-003, ARCH-004
- `docs/product/backlog-infra.md` — INF-001 through INF-007
- `docs/product/backlog-validation-service.md` — VS-013, VS-014
- `docs/product/backlog-gateway-api.md` — GW-012

## Why one sprint spans four backlogs

This is an explicit user decision, not a PM re-prioritization. The four backlogs converge on the same underlying event: `infra/docker-compose.yml` + Postgres (implementation-plan.md section 6, trigger #4) is finally being built, several sprints after it was nominally supposed to fire alongside trigger #3. That single event is what unblocks VS-013, VS-014, and GW-012, all three of which have sat as blocked Shoulds in their own backlogs since Sprint 03/05. Running infra and the three consumer stories in separate sprints would either strand INF-001–INF-007 with nothing consuming them, or let VS-013/GW-012 get scheduled before the ARCH-001/002 cleanup they must sit on top of — which is the one sequencing mistake this plan is structured specifically to prevent (see Phase reasoning below).

## Phased execution plan

Stories are grouped into phases. Within a phase, stories may run in parallel (no dependency between them). Phases themselves are strictly ordered — a phase does not start until every story it depends on, in an earlier phase, is done.

### Phase 1 — Parallel foundation: shared scaffolding cleanup + base infra containers

Two independent tracks, safe to run at the same time because they touch disjoint files (application code vs. infra/compose):

**Track A — ARCH cleanup (application code)**
1. **ARCH-001** — Extract duplicated SQLite engine-building scaffolding (`_build_engine`) into `libs/common`. Depends on: none.
2. **ARCH-002** — Fix per-request DB engine instantiation (memoize engine construction once per process). Depends on: ARCH-001 (backlog's own stated dependency — "same files; naturally fixed together").
3. **ARCH-004** — Extract duplicated SQLite test-fixture (`db_path` pytest fixture) into a shared test-utility. Depends on: none per the backlog, but bundled into this same phase/track because it touches the exact same test files ARCH-001 touches (`test_sqlite_repository.py` in both services) — sequencing it here avoids VS-013/GW-012's Postgres test suites hand-copying a fixture that's about to be centralized.
4. **ARCH-003** — Move the gateway-api proxy wire-contract (RunRequest/RunResponse/etc.) into a shared `libs/*` package. Depends on: none. Genuinely independent of the rest of this sprint (different files — routers, not repositories/engines) — placed in Phase 1 because nothing blocks it from starting immediately, but it has no ordering relationship to Track A's engine work or to Track B; it could equally run later without affecting the critical path. Included in Phase 1 simply to front-load independent work rather than leave it idle.

**Track B — Base infra containers (no application code touched)**
5. **INF-001** — PostgreSQL + TimescaleDB service in Docker Compose. Depends on: none.
6. **INF-002** — Redis service in Docker Compose. Depends on: none.

Why Track A and Track B run together: INF-001/INF-002 stand up containers only — they don't reference application code, so they have zero file overlap with ARCH-001/002/004/003 and no reason to wait. Track A must internally sequence ARCH-002 after ARCH-001 (explicit backlog dependency), and ARCH-004 alongside ARCH-001 (file-overlap reasoning above); ARCH-003 has no ordering constraint against anything in this sprint.

### Phase 2 — Service containerization + migration verification

7. **INF-003** — `validation-service` wired into Docker Compose as a real, runnable container (Dockerfile + compose service). Depends on: INF-001, INF-002 (needs postgres/redis service definitions to exist in the same compose file for coherent wiring, and INF-002 specifically because `validation-service`'s compose entry is env-var-wired to start after redis if VS-014 has landed by the time it ships).
8. **INF-004** — `gateway-api` wired into Docker Compose as a real, runnable container. Depends on: INF-001, INF-003 (backlog's stated dependency — needs `validation-service` present to prove the two-service chain talks over the internal network).
9. **INF-005** — Verify both services' existing Alembic migrations run against the Compose Postgres. Depends on: INF-001, INF-003, INF-004 (backlog's stated dependency — needs the services' containers up to run `alembic upgrade head` from within the wired environment). **Confirmed independent of ARCH-001/002**: both services' `migrations/env.py` build their own engine via `engine_from_config(...)` against `app.models.Base.metadata` — this is a separate code path from the runtime engine-builder (`repositories/sqlite_repository.py`'s `_build_engine` that ARCH-001 is extracting). Migration verification does not sit on top of the ARCH-001/002 cleanup at all; it only needs Postgres to exist and be reachable, which Phase 1's Track B and this phase's container wiring already provide.

Why this phase is separate from Phase 1: INF-003/INF-004 need `postgres`/`redis` service definitions already present in the compose file (Phase 1, Track B) to reference; INF-005 needs the services actually running in Compose (this phase's own INF-003/INF-004) to execute `alembic upgrade head` against. None of INF-003/004/005 depend on the ARCH track, so they do not wait on Phase 1's Track A — they only wait on Phase 1's Track B, which is why this phase can start as soon as Track B (not necessarily Track A) finishes. In practice both tracks are expected to finish close together since they're small, but the dependency is real: Track A finishing late would not block Phase 2 from starting.

### Phase 3 — Infra polish (lightweight, near the end of the infra track)

10. **INF-006** — Persistent volumes for Postgres and Redis. Depends on: INF-001, INF-002.
11. **INF-007** — `infra/README.md` and `.env.example` reflect actual, built state. Depends on: INF-001 through INF-006 (backlog's stated dependency — the README documents the final, built state, so it has to come after everything it's documenting exists).

Why these are their own phase rather than folded into Phase 1/2: both are lightweight and low-risk (no new service surface, just durability config and documentation), but INF-007 in particular is explicitly a rollup that depends on the full INF-001–006 set per the backlog — it cannot be pulled earlier. Sequenced after Phase 2 rather than interleaved so the README documents the actually-finished infra state (containers wired, migrations verified) rather than a snapshot mid-build.

### Phase 4 — Postgres/Redis application work (the sprint's actual payoff)

12. **VS-013** — Postgres-backed repository implementation (`validation-service`). Depends on: ARCH-001/002/004 (Phase 1, Track A — must build on the cleaned-up shared engine-building/test-fixture scaffolding, not the old duplicated one) AND INF-001/INF-005 (a real, migration-verified Postgres to target, confirmed via Phase 2).
13. **GW-012** — Postgres-backed identity repository + row-level security (`gateway-api`). Same dependency shape as VS-013: ARCH-001/002/004 (Phase 1, Track A) AND INF-001/INF-005 (Phase 2).
14. **VS-014** — Redis Streams-backed `run.completed` publisher (`validation-service`). Depends on: INF-002 only (Phase 1, Track B) — independent of the ARCH/Postgres work entirely per `backlog-infra.md` decision 3. Listed in this phase for scheduling convenience (it's part of the sprint's "payoff" set) but has no dependency on VS-013/GW-012 or on Phase 3, and could technically start as early as Phase 2 once INF-002 (Phase 1) is confirmed working end-to-end (e.g. once `validation-service`'s container is up in INF-003 and can reach `redis`). Sequenced here rather than earlier purely because it shares a service (`validation-service`) with VS-013 and it's simpler for one dev-agent session to do both of that service's changes together — not because of a real blocking dependency.

**This phase is why the sprint is sequenced the way it is.** ARCH-001 (shared engine-builder) and ARCH-002 (fixed per-request instantiation) touch the exact same files VS-013 and GW-012 will extend to add Postgres support (`repositories/sqlite_repository.py` and `dependencies/repositories.py` in both services). If VS-013/GW-012 started before ARCH-001/002 landed, they would build Postgres repositories on top of the duplicated, per-request-instantiated scaffolding ARCH-001/002 exist to remove — turning one already-doubled piece of debt into four backend-specific copies of it, which is a strictly bigger job to unwind later than fixing it once now. Phase 4 is deliberately the last phase so both of its non-Redis stories start only after Phase 1's Track A (clean scaffolding) and Phase 2 (real, verified Postgres) are both done.

## Stories in scope, in execution order

| # | Story | Phase | Order reason |
|---|---|---|---|
| 1 | ARCH-001 | 1 (Track A) | No dependency; must complete before ARCH-002 and before VS-013/GW-012 |
| 2 | ARCH-002 | 1 (Track A) | Depends on ARCH-001 (same files) |
| 3 | ARCH-004 | 1 (Track A) | Bundled with ARCH-001 — same test files, avoid a fixture VS-013/GW-012 would otherwise hand-copy |
| 4 | ARCH-003 | 1 | Independent of everything; front-loaded since nothing blocks it |
| 5 | INF-001 | 1 (Track B) | No dependency; runs parallel to Track A (infra containers, no app code touched) |
| 6 | INF-002 | 1 (Track B) | No dependency; runs parallel to Track A |
| 7 | INF-003 | 2 | Depends on INF-001, INF-002 (needs postgres/redis defined in the same compose file) |
| 8 | INF-004 | 2 | Depends on INF-001, INF-003 (proves the two real services talk over the internal network) |
| 9 | INF-005 | 2 | Depends on INF-001, INF-003, INF-004; confirmed independent of ARCH-001/002 (migrations/env.py uses its own engine, not the runtime engine-builder) |
| 10 | INF-006 | 3 | Depends on INF-001, INF-002; lightweight, sequenced near the end of the infra phase |
| 11 | INF-007 | 3 | Depends on INF-001 through INF-006 (documents the finished state) |
| 12 | VS-013 | 4 | Depends on ARCH-001/002/004 (clean scaffolding to build on) AND INF-001/INF-005 (verified real Postgres) |
| 13 | GW-012 | 4 | Same dependency shape as VS-013 |
| 14 | VS-014 | 4 | Depends only on INF-002; grouped here for scheduling convenience (same service as VS-013), not a real blocking dependency |

## Stories explicitly deferred

None of the fourteen stories above are deferred — this sprint takes all Must-priority stories from `backlog-technical-upgrades.md` (ARCH-001/002/003) and `backlog-infra.md` (INF-001–007), plus ARCH-004 (Should, explicitly bundled per this sprint's own instruction), and the two blocked-Should stories (VS-013, GW-012) plus VS-014 (Should) that this backlog round exists to unblock.

Explicitly out of scope, not part of this sprint, deferred to a future round:
- **ARCH-005** (track validation-service's unauthenticated tenant-header trust as a hard network-isolation dependency) — Should; tracking/documentation story tied to LC-009, not part of the Postgres/infra critical path. Not requested for this sprint.
- **ARCH-006** — Won't, per its own backlog entry (rejected: no real duplicated logic to extract).
- **INF-008** (MinIO), **INF-009** (Compose healthchecks/startup ordering) — Should; not named in this sprint's scope by the user, and not blockers for VS-013/VS-014/GW-012.
- **INF-010** (TimescaleDB hypertable configuration) — Could; backlog itself says this is speculative until a real time-series query pattern exists.
- **INF-011/INF-012/INF-013** — Won't, per their own backlog entries.
- **GW-010, GW-011, GW-013, GW-014, GW-015** — deferred previously in Sprint 05; not part of this sprint's four named backlogs' in-scope story list.
- **VS-015 through VS-020** — not named in this sprint's scope; VS-015 remains blocked on trigger #6 (`ingestion-service`), VS-016/017 are Should/Could not requested, VS-018/019/020 are Won't.

## Definition of done for this sprint

- All fourteen in-scope stories' acceptance criteria are met as written in their source backlogs.
- `libs/common` exposes a single shared `build_engine(url, base)` helper; both services' repository modules call it instead of defining their own `_build_engine` (ARCH-001), and engine construction is memoized once per process in both services, proven by a test that two dependency resolutions in the same process reuse the same engine/session factory (ARCH-002).
- Both services' `test_sqlite_repository.py` suites use a shared `db_path` fixture instead of a hand-copied one (ARCH-004), and both suites pass unmodified in behavior.
- A shared Pydantic wire-contract module exists under `libs/*` for the run/split response shapes, imported by both `gateway-api`'s and `validation-service`'s routers wherever the shape is field-for-field identical (ARCH-003); `test_runs_routing.py`, `test_runs_endpoint.py`, `test_splits_endpoint.py` pass unmodified in behavior.
- `infra/docker-compose.yml` defines `postgres` (timescale/timescaledb), `redis`, `validation-service`, and `gateway-api` as real, runnable services with persistent named volumes for postgres/redis; `docker compose up` runs the full stack and a request proxied through `gateway-api` reaches `validation-service` and gets a real response.
- Both services' existing Alembic migrations (`0001_create_validation_schema.py`, `0001_create_identity_schema.py`) are confirmed to run successfully against the Compose Postgres instance, coexisting in the same database without collision.
- `infra/README.md` no longer reads "planned" — it states the real running state, and `.env.example` lists every environment variable the compose stack needs.
- `validation-service` and `gateway-api` each have a working Postgres-backed repository implementation behind their existing Repository interfaces, swappable via DI with no call-site changes (VS-013, GW-012); GW-012 additionally has row-level-security policies scoping every query to `tenant_id`; both services' interim SQLite implementations are retained for local/unit-test use.
- `validation-service` has a working Redis Streams-backed `run.completed` publisher behind its existing `EventPublisher` interface, swappable via DI with no call-site changes (VS-014), with the event payload shape documented.
- No story in this sprint touches `libs/naive_first_engine`, `services/ingestion-service`, `services/reporting-service`, `services/dashboard-web`, or `services/economic-service`.
