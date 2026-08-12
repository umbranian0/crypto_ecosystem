# infra

**Status: built (INF-001–006 done).** `infra/docker-compose.yml` defines four real, running Compose
services — `postgres` (TimescaleDB, INF-001), `redis` (INF-002), `validation-service` (INF-003),
and `gateway-api` (INF-004) — plus persistence and migration verification against all of them
(INF-005/006, see below). See [docs/product/backlog-infra.md](../docs/product/backlog-infra.md)
for the full backlog this was built against.

**Why this exists now, stated plainly (mirroring the disclosure pattern `validation-service`'s and
`gateway-api`'s own READMEs use for their interim-SQLite decisions):** implementation-plan.md
section 6 trigger #4 ("create `infra/docker-compose.yml` + Postgres") is defined to fire the same
moment as trigger #3 (`validation-service`). Trigger #3 fired several sprints ago; trigger #4 did
not fire alongside it — `validation-service` and `gateway-api` shipped instead on an interim,
file-based SQLite backend (see those services' own READMEs and `backlog-validation-service.md` /
`backlog-gateway-api.md` decision 2 in each). This directory sat at "planned" since. It exists now
not because the trigger condition retroactively became true, but because the platform owner
explicitly scheduled a debt sprint to build it, specifically to unblock the Should stories that had
been piling up waiting on it: `VS-013` (Postgres-backed validation-service repositories), `VS-014`
(Redis Streams `run.completed` publisher), and `GW-012` (Postgres-backed identity repositories +
RLS). This README does not claim the trigger fired on time — it didn't.

**Not yet wired into compose, and this is deliberate, not an oversight:** `ingestion-service`,
`reporting-service`, and `dashboard-web` are not Compose services here. Per
implementation-plan.md section 6, each has its own not-yet-true trigger — `ingestion-service` is
trigger #6, `reporting-service` is trigger #7, `dashboard-web` is trigger #8 — none of which this
debt sprint's scope changes. `minio`/object storage is likewise absent (tracked separately as
INF-008, not part of this sprint). See
[../docs/solution-design.md](../docs/solution-design.md) section 5 for the full target service
list, and per-service Alembic migration environments under each service's own `migrations/`
directory (one per Postgres schema — `ingestion`, `validation`, `reporting`, `identity`, later
`economic` — see [../docs/implementation-plan.md](../docs/implementation-plan.md) section 5).

Copy `infra/.env.example` to `infra/.env` (or a repo-root `.env`) before starting anything —
every variable below has a working default, but the file also documents which values are
Compose-network values (service reaching service by Compose service name) versus local,
non-Compose-dev values (a service run directly on the host reaching a dependency via its
host-published port). The two are not interchangeable; see `.env.example` itself for both forms
of each variable.


## OPS-004 verification (2026-08-11/12)

The non-root (USER appuser) and port-binding changes to services/validation-service/Dockerfile, services/gateway-api/Dockerfile, and this file were verified end-to-end against the real stack, not just reviewed as source-correct: docker compose -f infra/docker-compose.yml build validation-service gateway-api succeeded; docker compose -f infra/docker-compose.yml up -d (full stack) succeeded with all four containers up/healthy; both services' /health returned 200 {"status":"ok"} from the host; the full-stack smoke test below (provision a tenant, POST /runs through gateway-api) was re-run and returned 201. This re-run was sequenced after VS-021 (see docs/tickets/VS-021.md) fixed a separate, real POST /runs 500 under genuine Postgres RLS enforcement (INF-014) -- so this smoke test now exercises only what OPS-004 itself tests (non-root/port-binding correctness), not that unrelated bug. See docs/tickets/README.md's Operability Sprint 09 subsection and docs/sprints/sprint-09.md for full detail.

## First-boot bootstrap (INF-015)

**This is the recommended way to bring the stack up, first-time or any time after.**
`infra/bootstrap.sh` (bash) / `infra/bootstrap.ps1` (PowerShell) run the whole sequence documented
section-by-section below in one command, in order, each step failing loudly (non-zero exit, a
message naming the failed step) rather than silently continuing:

1. `docker compose -f infra/docker-compose.yml up -d postgres redis`.
2. Wait for `postgres`'s own `pg_isready`-based healthcheck to report `healthy` (via `docker inspect
   --format '{{.State.Health.Status}}' naive-first-postgres`, bounded retry loop — not a new ad hoc
   `sleep`/port-probe), failing loudly if it never becomes healthy within the timeout.
3. Run migrations by calling INF-016's `infra/migrate.sh both` / `infra/migrate.ps1 -Service both` —
   this script does **not** re-derive the `alembic upgrade head` invocation itself, it delegates to
   that script entirely (see "Applying a new migration (INF-016)" below). If a service's migration
   fails, the bootstrap script stops here, non-zero exit, naming which service failed — it never
   proceeds to start the app containers against a partially-migrated database.
4. `docker compose -f infra/docker-compose.yml up -d --build validation-service gateway-api`.
5. Print (never run) the exact `provision_tenant.py` invocation as the final "next step" — tenant
   provisioning mints a real, one-time-visible API key, so this script deliberately stops short of
   minting one unattended (the printed command is the containerized form used in the "Full-stack
   smoke test (Definition of Done, INF-004)" section below, not `gateway-api/README.md`'s
   host-`.venv` form — the container this bootstrap script's own step 4 just started is the one
   whose Postgres-backed `identity` schema the provisioned tenant needs to land in).

Run it from the repo root:

```
infra/bootstrap.sh
# or, on Windows:
infra/bootstrap.ps1
```

Idempotent-safe against an already-up stack — each step is either already-satisfied Compose
`up -d` (no-ops for already-running containers), an already-passing healthcheck, an already-at-head
migration (INF-016's own idempotency), or a `--build` restart of the two app containers.

**What the script does, spelled out** (kept below for anyone bringing up one piece by hand, or
diagnosing which step of the script failed) — the per-service sections that follow are that same
sequence, unabridged:

## Postgres (INF-001)

`postgres` service, image `timescale/timescaledb:latest-pg16`, fixed host port `5432:5432`, named
volume `postgres-data` for the data directory. Credentials/connection details come entirely from
environment variables (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`) —
none are hardcoded in `docker-compose.yml`; defaults if unset: user/db `naive_first`, password
`naive_first_dev_password`, port `5432`.

**Design: one database, two schemas (not two databases).** Per `implementation-plan.md` section 5
this is a single Postgres + TimescaleDB instance for the pilot phase, schema-per-service, with no
cross-schema foreign keys or joins in application code. This keeps moving a service to its own
physical database later a connection-string change rather than a data-modeling project. INF-001's
scope is the container + one database + an init step that creates the `validation` and `identity`
schemas (the schemas VS-013/GW-012 currently need); pointing each service's own Alembic `env.py`
at its schema is scope owned by those tickets, not this one.

Schemas are created automatically on first container startup by the mounted init script
`infra/postgres-init/01-create-schemas.sql` (runs via the official image's
`/docker-entrypoint-initdb.d/` convention — only executes against a fresh, empty data volume).

Start it:

```
docker compose -f infra/docker-compose.yml up -d postgres
```

Verify:

```
docker exec naive-first-postgres psql -U naive_first -d naive_first -c '\dn'
```

Expected: a schema list including both `validation` and `identity` (plus the default `public`).

## Redis (INF-002)

`redis` service, image `redis`, fixed host port `6379:6379`. Connection is via a single
`REDIS_URL` env var (mirrors the `DATABASE_URL` convention — not split host/port/db vars); see
`infra/.env.example`.

**Scope note (important, do not read past this as "Redis pub/sub is wired end-to-end"):** this
ticket unblocks `VS-014` (`validation-service`'s Redis Streams-backed `run.completed` publisher —
the *publisher side only*) right now. It does **not** require, and does not include,
`reporting-service` (trigger #7, the *subscriber side*) existing yet. Redis being up here means
"a publisher can now connect to a real broker," not "the full `run.completed` pub/sub loop is
wired end-to-end" — that end-to-end loop still needs trigger #7's subscriber work.

Start it:

```
docker compose -f infra/docker-compose.yml up -d redis
```

Verify:

```
docker exec naive-first-redis redis-cli PING
```

Expected: `PONG`.

## validation-service (INF-003)

`validation-service` compose entry: `build.context` is `../services/validation-service`
(`services/validation-service/Dockerfile`), with `libs/common` and `libs/naive_first_engine`
pulled in via a named `additional_contexts: {libs: ../libs}` build context — the service's
`pyproject.toml` declares those as editable path dependencies at `../../libs/...`, outside the
service directory, so the Dockerfile mirrors the monorepo layout under `/repo` inside the image
and copies them in from that additional context. Host port defaults to `8001`
(`VALIDATION_SERVICE_PORT`), mapped to the container's `8000`.

Started after `postgres` (`depends_on: postgres: condition: service_healthy`). `redis` is not yet
a `depends_on` — VS-014 (the Redis Streams publisher) hasn't landed, so the running service doesn't
talk to Redis at runtime yet, even though `REDIS_URL` is already wired through.

Env vars (see `infra/.env.example`), both using internal Compose network hostnames rather than
`localhost`, and both env-var driven with in-Compose defaults rather than hardcoded:
- `DATABASE_URL` (from `VALIDATION_SERVICE_DATABASE_URL`, default
  `postgresql://naive_first:naive_first_dev_password@postgres:5432/naive_first`) — **not yet used
  by the app**: `validation-service` is still on its interim SQLite backend (VS-004); Postgres-backed
  repositories land in VS-013. This is purely wiring the env var through so it's ready when that ships.
- `REDIS_URL` (from `VALIDATION_SERVICE_REDIS_URL`, default `redis://redis:6379/0`) — same "not
  used until its consuming story lands" caveat as above (VS-014).

The service still runs standalone against SQLite/no-Redis outside Compose (e.g. `uv run uvicorn
app.main:app` from `services/validation-service/`, per that service's own README) — this Compose
entry is purely an additional way to run it, not a replacement.

Start it (brings up `postgres` first via `depends_on`):

```
docker compose -f infra/docker-compose.yml up -d --build validation-service
```

Verify:

```
curl http://localhost:8001/docs
```

Expected: the FastAPI Swagger UI HTML (or hit `/openapi.json` for the raw schema). `POST /runs` /
`GET /runs/{id}` are documented there too — see `services/validation-service/README.md` for their
request/response shapes (both require an `X-Tenant-Id` header per VS-010).

## gateway-api (INF-004)

`gateway-api` compose entry: `build.context` is `../services/gateway-api`
(`services/gateway-api/Dockerfile`), with `libs/common` pulled in via a named
`additional_contexts: {libs: ../libs}` build context — same pattern as `validation-service`
(INF-003), except `gateway-api` only depends on `naive_first_common` (not `naive_first_engine`),
so only `libs/common` is copied into the image. Host port defaults to `8000`
(`GATEWAY_API_PORT`), mapped to the container's `8000` (`validation-service` already took `8001`).

Started after `postgres` (`depends_on: postgres: condition: service_healthy`). `validation-service`
is deliberately not a `depends_on`: `gateway-api`'s own outbound HTTP calls (GW-009) already
translate a downstream connection failure/timeout into a `502`/`504` response, so there's no need
for a hard startup-ordering dependency between the two application services.

Env vars (see `infra/.env.example`), both env-var driven with in-Compose defaults rather than
hardcoded:
- `VALIDATION_SERVICE_URL` (from `GATEWAY_API_VALIDATION_SERVICE_URL`, default
  `http://validation-service:8000`) — the internal Compose network hostname. `gateway-api`'s own
  README already documents this env var with a `localhost` default for non-Compose dev; this
  Compose entry overrides it to reach `validation-service` by its Compose service name instead of
  its host-published port.
- `DATABASE_URL` (from `GATEWAY_API_DATABASE_URL`, default
  `postgresql://naive_first:naive_first_dev_password@postgres:5432/naive_first`) — **not yet used
  by the app**: `gateway-api` is still on its interim SQLite backend (GW-004); Postgres-backed
  repositories targeting the `identity` schema land in GW-012. This is purely wiring the env var
  through so it's ready when that ships — same "wired through but not yet consumed" situation
  INF-003 documented above for `validation-service`'s own `DATABASE_URL`.

The service still runs standalone against SQLite outside Compose (e.g. `.venv\Scripts\python.exe
-m uvicorn app.main:app` from `services/gateway-api/`, per that service's own README) — this
Compose entry is purely an additional way to run it, not a replacement.

Start the full stack (brings up `postgres` first via `depends_on`; `validation-service` isn't a
hard dependency of `gateway-api` but is needed for the smoke test below to have anything to proxy
to):

```
docker compose -f infra/docker-compose.yml up -d --build validation-service gateway-api
```

Verify the container is up on its own:

```
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`.

### Full-stack smoke test (Definition of Done, INF-004)

This is the concrete proof `gateway-api` and `validation-service` talk to each other inside the
Compose network, not just both being independently up. Provision a tenant using `gateway-api`'s
own fixture script (GW-005), run **inside** the running container so it shares the same
`gateway.db` the app process uses:

```
docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/provision_tenant.py --name "Smoke Test Tenant"
```

This prints a `Tenant created: id=...` line and an `API key (shown once, not recoverable): ...`
line — copy the raw key. Then call `POST /runs` through **`gateway-api`'s own exposed port**
(`8000`, not `validation-service`'s `8001`), using that key:

```
curl -s -X POST http://localhost:8000/runs \
  -H "Authorization: Bearer <raw key from above>" \
  -H "Content-Type: application/json" \
  -d '{"dataset_id":"smoke-test","dataset_reference":{"type":"inline","rows":[]},"horizon":1,"purge_gap_hours":0,"train_window":1,"test_window":1,"step":1}'
```

Expected: a `201` response with a real `{"id": ..., "status": ...}` body — proof the request was
authenticated by `gateway-api`, forwarded to `validation-service` over the internal Compose
network (`http://validation-service:8000`), executed there, and the response proxied back
unmodified in shape. See `services/gateway-api/README.md` / `services/validation-service/README.md`
for the full request/response contract.

## Migrations verified against Compose Postgres (INF-005)

Both services' *existing* Alembic migration sources (`0001_create_validation_schema.py` /
`0001_create_identity_schema.py`, both still targeting the default `public` schema — the
`validation`/`identity` schema-targeting `env.py` change is VS-013/GW-012's own scope, not this
ticket's) were run from the host against the real Compose `postgres` container (not from inside a
container), using each service's own `.venv` and:

```
DATABASE_URL=postgresql://naive_first:naive_first_dev_password@localhost:5432/naive_first python -m alembic upgrade head
```

(run from `services/validation-service/` and `services/gateway-api/` respectively; host port
`5432`, since alembic runs outside Docker here). Both succeeded individually and each service's
tables (`runs`/`split_results`, `tenants`/`users`/`api_keys`) were confirmed via `docker exec
naive-first-postgres psql -U naive_first -d naive_first -c '\dt public.*'`, including a
`tenant_id` column spot-check on `runs`/`split_results`.

**Finding — real, unresolved collision, not a false alarm:** running both `alembic upgrade head`
commands back-to-back against the same database is *not* currently safe. Both migrations hardcode
revision id `'0001'` with `down_revision = None`, and both `env.py`s write to the same default
`public.alembic_version` table (no schema-scoped version table yet — that's part of the
schema-targeting change owned by VS-013/GW-012). Whichever service migrates second finds
`version_num = '0001'` already stamped and, since Alembic matches purely on that string, treats
the database as already at its own head — its `upgrade()` never runs, silently, with no error.
Verified this is order-independent (reproduced with gateway-api first and with validation-service
first). Also needed `pip install psycopg2-binary` in both `.venv`s — neither service currently
declares a Postgres driver as a dependency, only `sqlalchemy`/`alembic`, since neither's app code
uses Postgres yet.

To get a full six-table verification snapshot (5 app tables + `alembic_version`) despite the
collision, `alembic_version` was dropped (via `psql`, bookkeeping table only — no data tables
touched) between the two runs, which is a manual workaround for verification purposes only, not a
fix. The actual fix (per-schema version tables) is expected to land naturally once VS-013/GW-012's
schema-targeting `env.py` change ships.

## Applying a new migration (INF-016)

`infra/migrate.sh <service>` (bash) / `infra/migrate.ps1 -Service <service>` (PowerShell) are the
single source of the `alembic upgrade head` invocation shown above — a developer adding a new
migration to `validation-service` or `gateway-api` should run one of these instead of re-deriving
INF-005's one-off command by hand (as had already happened at least three times across INF-005,
VS-013, and GW-012 before this script existed). `<service>` is `validation-service`,
`gateway-api`, or `both` (default `both` if omitted).

Both scripts, for each service given: `cd services/<service>`, build the migration-time
`DATABASE_URL` from `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_PORT`/`POSTGRES_DB` (env vars,
falling back to `.env.example`'s documented defaults, host `localhost` since this runs from the
host against the Compose-published Postgres port), and run `python -m alembic upgrade head` using
that service's own `.venv` interpreter (`.venv/bin/python` on POSIX, `.venv\Scripts\python.exe` on
Windows) — never a bare `python`/`alembic` that might resolve to some other environment.

**Always connects as `naive_first` (migration-time role, INF-014), never `naive_first_app`**
(runtime-only, no `CREATE`/ownership privileges — would fail at the first `CREATE TABLE`). The
`DATABASE_URL` scheme used is `postgresql+psycopg://`, not the bare `postgresql://` shown in
INF-005's original one-off command above: both services' `pyproject.toml` declare `psycopg` v3 as
their Postgres driver, not `psycopg2`, and SQLAlchemy's default dialect for a bare `postgresql://`
scheme resolves to `psycopg2`, which isn't installed in either `.venv`. Each service's own app code
(`dependencies/repositories.py`) already rewrites an incoming `postgresql://` `DATABASE_URL` to
`postgresql+psycopg://` before use; `alembic`'s `env.py` does not do that rewrite, so this script
supplies the explicit scheme directly.

Fails loudly, non-zero exit: a clear message (not a raw Python traceback) if a service's `.venv`
doesn't exist yet (create it first, e.g. `cd services/<service>; uv sync`), and Alembic's own
exit code/stderr propagate through unchanged on a real migration failure.

Idempotent by construction — delegates straight to `alembic upgrade head`, which itself already
no-ops once a service is at head, so running this against an already-migrated database (as with the
Compose Postgres instance right now) is safe and expected to do nothing.

Example, run from the repo root:

```
infra/migrate.sh both
# or, on Windows:
infra/migrate.ps1 -Service both
```

**Out of scope, by design**: no `alembic revision --autogenerate` helper and no CI/deploy-time
auto-migration hook — this script performs the same manual-but-easy action a developer already
decided to take; it does not decide *when* to run.

## Persistence verified across restarts (INF-006)

Both `postgres` and `redis` write to named Docker volumes so data survives `docker compose down`
(without `-v`) and container recreation — this was verified with a real round-trip test (write
data, `down`, `up`, confirm data still present).

- **Postgres**: named volume `postgres-data` mounted at `/var/lib/postgresql/data` (declared in
  INF-001). Standard Postgres WAL/durability applies; no extra configuration needed.
- **Redis**: named volume `redis-data` mounted at `/data`, and the service runs with
  `command: redis-server --appendonly yes`, enabling the append-only file (AOF) persistence mode.
  This was a deliberate choice over relying on the image's default RDB-snapshot-only behavior,
  since Streams entries written by `validation-service` (VS-014's `run.completed` publisher)
  should survive a restart with minimal data loss — AOF gives much smaller write-loss windows than
  periodic RDB snapshots.

Round-trip test performed for INF-006: inserted a probe row into Postgres and set a probe key in
Redis, ran `docker compose -f infra/docker-compose.yml down` (no `-v`), then
`docker compose -f infra/docker-compose.yml up -d postgres redis`, and confirmed both the probe
row and probe key were still present after the restart. Probe data was deleted afterward; the
containers were left running.
