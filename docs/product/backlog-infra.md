# Backlog — infra

Source: `docs/da-tese-ao-produto.md` (section 2.1, positioning — not directly load-bearing here but confirms nothing in this backlog authorizes trading/signal claims), `docs/solution-design.md` (section 5 deployment/service table, section 5.1 hosting decision), `docs/implementation-plan.md` (section 2 module boundary map, section 3 repo layout, section 5 data ownership/schema-per-service, section 6 trigger #4, section 9 DRY rules), `infra/README.md`, `services/validation-service/README.md` (interim SQLite, VS-013/VS-014 blocked), `services/gateway-api/README.md` (interim SQLite, GW-012 blocked), `libs/common/README.md`, `services/validation-service/alembic.ini` + `migrations/env.py` + `migrations/versions/0001_create_validation_schema.py`, `services/gateway-api/alembic.ini` + `migrations/env.py` + `migrations/versions/0001_create_identity_schema.py`, `docs/product/backlog-validation-service.md` (VS-013, VS-014 in full), `docs/product/backlog-gateway-api.md` (GW-012 in full).

## Scope

**Why this backlog exists now, stated plainly.** Implementation-plan.md section 6 trigger #4 ("create `infra/docker-compose.yml` + Postgres") is defined to fire "the same moment" as trigger #3 (`validation-service`). Trigger #3 fired several sprints ago — but trigger #4 did not actually fire alongside it. Both `validation-service` and `gateway-api` shipped instead on an interim, file-based SQLite backend, an explicit and disclosed judgment call recorded in both services' own backlogs (`backlog-validation-service.md` decision 2, `backlog-gateway-api.md` decision 2) and READMEs. `infra/README.md` has sat at "planned" since. This is not being written now because the trigger condition retroactively became true — it didn't fire on schedule, and this backlog does not pretend otherwise. It is being written because the platform owner has explicitly scheduled a debt sprint to build `infra/` now, specifically to unblock the Should stories that have been piling up waiting on it: `VS-013` (Postgres-backed validation-service repositories), `VS-014` (Redis Streams `run.completed` publisher), and `GW-012` (Postgres-backed identity repositories + RLS).

**In scope**: the three real infra pieces named in solution-design.md section 5's service table — `postgres` (`timescale/timescaledb` image), `minio`, `redis` — as `infra/docker-compose.yml` services; wiring the two services that actually exist as code (`validation-service`, `gateway-api`) into that same compose file as real, runnable containers; making Postgres and Redis concretely reachable with documented connection strings, so that `VS-013`, `VS-014`, and `GW-012` become buildable rather than perpetually blocked.

**Out of scope**: `ingestion-service`, `reporting-service`, `dashboard-web` — none of these exist as code yet (triggers #6–#8 haven't fired), and `infra/README.md`'s own standing rule is "don't add a compose file with services that don't exist as code." The solution-design.md section 5 table's `api`/`worker` rows are conceptual placeholders from before the module split in implementation-plan.md existed as code — they are **not** built here as a new generic container; `api` is superseded by the real `services/gateway-api` + `services/validation-service`, and `worker` (Prefect agent) has no concrete consumer yet (no flows are defined outside `validation-service`'s own synchronous request handling) so it is not stood up speculatively. Also out of scope: actually implementing `VS-013`/`VS-014`/`GW-012` (see decision 2 below), cloud/Heroku deployment (solution-design.md section 5.1 — a separate, later hosting decision, not this local-first Compose work), and TimescaleDB hypertable configuration (no query pattern needs it yet).

### Explicit scope decisions (per the instruction not to assume silently)

1. **This backlog's Must scope *does* include wiring `validation-service` and `gateway-api`'s Dockerfiles and Compose service definitions — `docker compose up` is expected to run the real services, not just the infra pieces around them.** Neither service has a `Dockerfile` yet (checked: `services/validation-service/Dockerfile` and `services/gateway-api/Dockerfile` don't exist; only `pyproject.toml` does). The alternative — infra ships Postgres/Redis/MinIO containers but the two real services still run manually outside Compose — would leave the debt sprint's own stated purpose unmet: `VS-013`/`GW-012`'s acceptance criteria ("point Alembic at a real DB", "swap the DI-wired repository, prove no call-site changes") are only concretely verifiable if the service and the database are reachable from the same environment. `infra/README.md`'s own "will hold" list already commits to `gateway-api`/`validation-service` as compose services. Deferring Dockerfile authorship to each service's own backlog would reproduce exactly the "planned but never built" gap this debt sprint exists to close. Note for the PM/Tech Lead: the `Dockerfile`s physically live under `services/validation-service/` and `services/gateway-api/` (implementation-plan.md section 3's repo layout assigns each service its own), but authorship here is about closing the compose-wiring gap, not about relitigating who owns runtime business logic in those directories — no story below touches either service's application code.
2. **This backlog's Must scope does *not* include `VS-013`, `VS-014`, or `GW-012` themselves.** Those are fully-specified Should stories already written, with their own acceptance criteria, inside `backlog-validation-service.md` and `backlog-gateway-api.md` — re-specifying them here would fork a single story across two backlogs, which implementation-plan.md section 9's DRY convention (and the cross-service "no service imports another service's internals" rule, by analogy) argues against. This backlog's job is narrower and prior: make the infra those three stories are blocked on actually exist and be reachable, so their own authors can execute them unmodified. Concretely, this backlog proves Postgres accepts each service's already-written Alembic migration (a connectivity/schema smoke test — see INF-005) without performing the DI swap, RLS policy authorship, or Redis-Streams publisher implementation those three stories still own. **Recommendation to the PM**: schedule `VS-013`, `VS-014`, and `GW-012` into the same debt sprint as this backlog — they are unblocked by it, not obsoleted by it, and none of their acceptance criteria are satisfied by infra work alone.
3. **`VS-014` is treated as unblocked by this backlog's Redis story (INF-002), even though implementation-plan.md section 6 nominally ties Redis Streams to trigger #7 (`reporting-service`), not trigger #4.** `VS-014`'s own scope is the *publisher* side only (`validation-service` writing to a stream) — it has no dependency on `reporting-service` existing as a subscriber to be implemented and tested; it only needs a real, reachable Redis instance to write to, which is what solution-design.md section 5's service table (and this backlog's INF-002) actually provides. The full pub/sub loop (a subscriber consuming what `VS-014` publishes) genuinely still waits on trigger #7 — that half is correctly out of scope here and not claimed as delivered.

## Stories

### INF-001 — PostgreSQL + TimescaleDB service in Docker Compose [Must]
**As** the Naive-First platform **I want** a `postgres` service (`timescale/timescaledb` image) defined in `infra/docker-compose.yml` **so that** `validation-service` and `gateway-api` have a real, reachable operational database instead of interim SQLite files.

Acceptance criteria:
- [ ] `infra/docker-compose.yml` defines a `postgres` service using the `timescale/timescaledb` image (matching solution-design.md section 5's table), with a fixed container port mapped to the host for local access from outside Compose (e.g. `psql`, a migration run from a service's own `.venv`).
- [ ] A named, persistent Docker volume is attached so data survives `docker compose down` (not `down -v`) — parity with the durability SQLite already provided ("state survives a process restart") that this backlog must not regress.
- [ ] Credentials and connection details are supplied via environment variables (not hardcoded in the compose file), documented in `infra/README.md` and a checked-in `.env.example`.
- [ ] `docker compose up postgres` starts successfully and accepts a plain `psql` connection using the documented credentials, verified manually as part of this story's Definition of Done.

Rationale for priority: this is the direct, named blocker for `VS-013` and `GW-012` — neither story is buildable without a real Postgres instance to target, and this is the trigger-#4 deliverable those two stories cite by name as their blocking dependency.
Depends on: none

### INF-002 — Redis service in Docker Compose [Must]
**As** the Naive-First platform **I want** a `redis` service defined in `infra/docker-compose.yml` **so that** `validation-service`'s Redis Streams `run.completed` publisher (`VS-014`) has a real broker to write to.

Acceptance criteria:
- [ ] `infra/docker-compose.yml` defines a `redis` service (`redis` image, matching solution-design.md section 5), with a fixed container port mapped to the host.
- [ ] Connection details (host, port, and any auth) are supplied via environment variables, documented in `infra/README.md` and `.env.example`.
- [ ] `docker compose up redis` starts successfully and accepts a plain `redis-cli PING` using the documented connection details.
- [ ] Documentation in `infra/README.md` states explicitly that this Redis instance unblocks `VS-014`'s publisher-side work now, ahead of trigger #7 (`reporting-service`'s subscriber side) — per scope decision 3 above, so a future contributor doesn't read "Redis exists" as "the full `run.completed` pub/sub loop is wired end-to-end."

Rationale for priority: named blocker for `VS-014`; small, low-risk, and — per implementation-plan.md section 4 — this is infra already committed to for the task queue/event bus, not a new piece being pulled forward.
Depends on: none

### INF-003 — `validation-service` wired into Docker Compose as a real, runnable container [Must]
**As** a developer running this stack locally **I want** `validation-service` to have a working `Dockerfile` and a `docker-compose.yml` service definition connected to `postgres` and `redis` **so that** `docker compose up` runs the real service against real infra instead of requiring it to be started manually outside Compose.

Acceptance criteria:
- [ ] `services/validation-service/Dockerfile` exists, builds the service per its existing `pyproject.toml` (`uv`-managed, per implementation-plan.md section 9), and starts the FastAPI app.
- [ ] `infra/docker-compose.yml` defines a `validation-service` entry (`build: ../services/validation-service`) that starts after `postgres` is accepting connections (see INF-009) and after `redis` if `VS-014` has landed by the time this ships (env-var driven, not a hard code dependency — `validation-service` must still run standalone against SQLite/no-Redis for unit tests, per its README's stated interim-is-still-supported stance).
- [ ] `DATABASE_URL` and Redis connection env vars are passed through from the same `.env`/`.env.example` INF-001/INF-002 introduced, using the internal Compose network hostname (e.g. `postgres:5432`), not `localhost`.
- [ ] `docker compose up validation-service` starts the container successfully and `POST /runs`/`GET /runs/{id}` respond over the container's exposed port, using the service's existing (SQLite-backed, until `VS-013` lands) behavior — this story does not require `VS-013` to be done first; it only requires the container to run and be reachable.
- [ ] No change is made to any file under `services/validation-service/src/` — this story is packaging/wiring only, not application logic (respects the "does not own business logic" boundary this backlog holds itself to).

Rationale for priority: without this, Postgres/Redis existing in Compose doesn't achieve the debt sprint's actual goal — `VS-013`/`VS-014` need the service itself runnable in the same environment as the infra it will be pointed at, not just infra sitting unconnected.
Depends on: INF-001, INF-002

### INF-004 — `gateway-api` wired into Docker Compose as a real, runnable container [Must]
**As** a developer running this stack locally **I want** `gateway-api` to have a working `Dockerfile` and a `docker-compose.yml` service definition connected to `postgres` and to `validation-service` over the internal Compose network **so that** `docker compose up` runs the full two-service chain end-to-end.

Acceptance criteria:
- [ ] `services/gateway-api/Dockerfile` exists, builds the service per its existing `pyproject.toml`, and starts the FastAPI app.
- [ ] `infra/docker-compose.yml` defines a `gateway-api` entry (`build: ../services/gateway-api`) that starts after `postgres` is accepting connections.
- [ ] `VALIDATION_SERVICE_URL` is set to the internal Compose network hostname (`http://validation-service:8000`, per `gateway-api`'s README, which already documents this env var with a `localhost` default for non-Compose local dev) — proving service-to-service reachability inside the Compose network, not just each container starting independently.
- [ ] `DATABASE_URL` is passed through using the internal Compose hostname, same pattern as INF-003.
- [ ] `docker compose up` (full stack) allows a request through `gateway-api` to reach `validation-service` and get a real response (e.g. provision a test tenant per the existing `scripts/provision_tenant.py`, then call `POST /runs` through `gateway-api` and confirm it proxies successfully) — this is the end-to-end smoke test that the two real services are actually wired together, not just present in the same compose file.
- [ ] No change is made to any file under `services/gateway-api/src/` — packaging/wiring only.

Rationale for priority: same reasoning as INF-003, plus this is the story that actually proves the two real services can talk to each other inside Compose — the part of "docker compose up runs the real stack" that's easiest to silently skip.
Depends on: INF-001, INF-003

### INF-005 — Verify both services' existing Alembic migrations run against the Compose Postgres [Must]
**As** the Naive-First platform **I want** `validation-service`'s and `gateway-api`'s already-written Alembic migration sources (`0001_create_validation_schema.py`, `0001_create_identity_schema.py`) confirmed to run successfully against the real `postgres` service from INF-001 **so that** `VS-013` and `GW-012` start from "migrations are proven to work here," not "migrations have never touched a real database."

Acceptance criteria:
- [ ] With `DATABASE_URL` pointed at the Compose Postgres instance, `alembic upgrade head` run from `services/validation-service/` succeeds and creates the `runs`/`split_results` tables with all columns from `0001_create_validation_schema.py` (already confirmed to define `tenant_id` on both tables — this story verifies execution, not schema correctness, which VS-002 already settled).
- [ ] Same for `services/gateway-api/` and `0001_create_identity_schema.py` (`tenants`/`users`/`api_keys`).
- [ ] Both services' schemas coexist in the same Postgres instance without collision, per implementation-plan.md section 5's schema-per-service model (verify: both migrations applied in the same database, table names/namespaces don't clash — note neither migration currently targets a named Postgres schema/namespace beyond the default `public`, which is fine for two services today but is flagged here as a note for whoever writes `VS-013`/`GW-012`, since section 5's "schema-per-service" language may mean an actual Postgres `CREATE SCHEMA` per service by the time a third service's migrations need to coexist).
- [ ] This story explicitly does **not** implement `VS-013`/`GW-012`'s Postgres-backed repository classes or RLS policies — it only proves the migration source is executable against real infra, which is as far as this backlog's boundary goes (scope decision 2).

Rationale for priority: this is the concrete, checkable version of "infra exists and is reachable" for the specific thing `VS-013`/`GW-012` need most — both stories' own acceptance criteria assume the migration "just" needs pointing at a real DB; this story is what makes that assumption true rather than aspirational.
Depends on: INF-001, INF-003, INF-004

### INF-006 — Persistent volumes for Postgres and Redis [Must]
**As** a developer running this stack locally **I want** Postgres and Redis data to survive `docker compose down`/restart **so that** local development doesn't lose run/tenant data every time the stack is stopped, matching the durability the interim SQLite files already provided.

Acceptance criteria:
- [ ] Named Docker volumes are declared for `postgres` (data directory) and `redis` (if persistence is enabled — `appendonly`/RDB snapshot, a deliberate choice documented in `infra/README.md` rather than left to the image default).
- [ ] A round-trip test (write data, `docker compose down` without `-v`, `docker compose up`, data still present) is part of this story's Definition of Done.

Rationale for priority: small and cheap, but without it every `docker compose down` silently regresses the durability guarantee `validation-service`'s and `gateway-api`'s READMEs already promise today via SQLite — a real usability/trust regression if skipped.
Depends on: INF-001, INF-002

### INF-007 — `infra/README.md` and `.env.example` reflect actual, built state [Must]
**As** a future contributor — human or Claude — **I want** `infra/README.md` updated from "planned" to the real current state, and a checked-in `.env.example` listing every environment variable the compose stack needs **so that** nobody mistakes this backlog's output for still-aspirational, and nobody has to reverse-engineer required env vars from the compose file.

Acceptance criteria:
- [ ] `infra/README.md`'s status line no longer reads "planned" — it states what's actually running (`postgres`/`timescaledb`, `redis`, `minio` per INF-008, `validation-service`, `gateway-api`), links to this backlog, and states plainly (mirroring the wording pattern already used in `validation-service`'s and `gateway-api`'s READMEs) that this was built as an explicit debt-sprint decision after trigger #4 didn't fire on schedule alongside trigger #3 — not a claim that the trigger fired on time.
- [ ] `.env.example` at the repo root or under `infra/` lists every variable INF-001–INF-004 introduced (`DATABASE_URL` shape, Redis host/port, MinIO credentials if INF-008 ships), with comments distinguishing "used inside Compose network" values from "used for local, non-Compose dev" values (the same distinction `gateway-api`'s README already draws for `VALIDATION_SERVICE_URL`).
- [ ] `infra/README.md` explicitly states that `ingestion-service`, `reporting-service`, and `dashboard-web` are still not wired into compose and names their triggers (#6, #7, #8) as the reason, so the next contributor doesn't wonder if that was an oversight.

Rationale for priority: documentation-for-scaling is a repo-wide convention (implementation-plan.md section 8), and this specific backlog exists partly *because* a stale README ("planned") let the infra gap go unnoticed for several sprints — closing that loop is part of the fix, not an optional add-on.
Depends on: INF-001 through INF-006

### INF-008 — MinIO service in Docker Compose [Should]
**As** the Naive-First platform **I want** a `minio` service defined in `infra/docker-compose.yml`, matching solution-design.md section 5's service table **so that** the object-storage piece of the platform exists in the local stack ahead of `ingestion-service` needing it.

Acceptance criteria:
- [ ] `infra/docker-compose.yml` defines a `minio` service (`minio/minio` image) with a persistent volume and credentials via env vars, same pattern as INF-001/INF-002.
- [ ] `docker compose up minio` starts successfully and the MinIO console/API is reachable on its documented port.
- [ ] `infra/README.md` states plainly that no service currently reads or writes to it — `ingestion-service` (trigger #6) is the first real consumer and hasn't been built yet — so this story stands the container up without inventing bucket/prefix policy ahead of a real consumer defining its own needs.

Rationale for priority: named in solution-design.md section 5's table and cheap to add alongside INF-001/INF-002, but — unlike Postgres/Redis — nothing in this debt sprint's stated trigger (`VS-013`/`VS-014`/`GW-012`) actually depends on it; downgraded from Must because no current story is blocked without it.
Depends on: none

### INF-009 — Compose healthchecks and startup ordering [Should]
**As** a developer running this stack locally **I want** `postgres`/`redis` healthchecks and `depends_on: condition: service_healthy` on the services that need them **so that** `validation-service`/`gateway-api` don't fail on startup by racing Postgres's boot time.

Acceptance criteria:
- [ ] `postgres` and `redis` services declare a `healthcheck` (e.g. `pg_isready`, `redis-cli PING`).
- [ ] `validation-service` and `gateway-api` declare `depends_on` with `condition: service_healthy` against `postgres` (and `redis` for `validation-service`, once `VS-014` lands).
- [ ] `docker compose up` from a cold start (no containers running) succeeds without manual retries, verified as this story's Definition of Done.

Rationale for priority: real usability improvement for local dev, but INF-003/INF-004 are functional without it (a developer can just retry `docker compose up` once) — worth doing in the same sprint but not a hard blocker for `VS-013`/`VS-014`/`GW-012`.
Depends on: INF-001, INF-002, INF-003, INF-004

### INF-010 — TimescaleDB hypertable configuration [Could]
**As** the Naive-First platform **I want** `split_results` (and any future time-series-heavy table) converted to a TimescaleDB hypertable **so that** direct time-series queries over metrics history perform well once that access pattern exists.

Acceptance criteria:
- [ ] A migration or setup script converts the relevant table(s) to hypertables, with the partitioning column chosen and documented.
- [ ] Existing repository/query behavior is unaffected (hypertables remain queryable via plain SQL).

Rationale for priority: solution-design.md section 3.2 names this as conditional ("if queried directly rather than via Parquet") — no current story queries `split_results` as a time series directly (the dashboard that would do this is trigger #8, not fired); doing this now would be speculative, per implementation-plan.md's own "don't scaffold before something concrete needs it" principle.
Depends on: INF-005

### INF-011 — `ingestion-service` / `reporting-service` / `dashboard-web` Compose wiring [Won't]
**As** the Naive-First platform **I want** the remaining three services from solution-design.md's architecture eventually wired into `docker-compose.yml` **so that** the full platform runs as one stack.

Rationale for priority: **Won't, this backlog.** None of these three exist as code — `infra/README.md`'s own standing rule is "don't add a compose file with services that don't exist as code," and their respective triggers (#6, #7, #8) haven't fired. Revisit as a new infra story the moment any one of them is actually scaffolded.
Depends on: none (blocked on triggers #6/#7/#8, not on anything in this backlog)

### INF-012 — Cloud/Heroku deployment wiring [Won't]
**As** the Naive-First platform **I want** the Compose services deployable to Heroku (managed Postgres/Redis add-ons, per solution-design.md section 5.1) **so that** the platform can be hosted for real pilot clients instead of running only on a laptop.

Rationale for priority: **Won't, this backlog.** Solution-design.md section 5.1 already scopes this as a distinct, later hosting decision ("Heroku... minimal drift from local dev") — conflating it with this local-first debt sprint would blur two different pieces of work with different risk profiles (a laptop-only Compose stack vs. a real hosted, credentialed environment). Revisit once there's an actual pilot client to host for (same gating logic `gateway-api`'s own backlog decision 1 already applies to itself).
Depends on: none

### INF-013 — `VS-013`, `VS-014`, `GW-012` implementation [Won't]
**As** the Naive-First platform **I want** the Postgres-backed repositories, RLS policies, and Redis Streams publisher this infra unblocks **so that** `validation-service` and `gateway-api` actually stop depending on SQLite.

Rationale for priority: **Won't, this backlog** — per scope decision 2 above, these three stories are already fully specified with their own acceptance criteria in `docs/product/backlog-validation-service.md` and `docs/product/backlog-gateway-api.md`. Duplicating them here would fork ownership of a single piece of work across two backlogs. This backlog's job ends at "infra exists, is reachable, and the existing migration sources run against it" (INF-005) — the PM should schedule `VS-013`/`VS-014`/`GW-012` into the same debt sprint as this backlog's Must stories, not fold them into this document.
Depends on: INF-001 through INF-006 (all three are blocked on this backlog's Must scope, per their own backlogs' stated dependency)
