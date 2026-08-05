# Implementation plan — microservices/modules architecture

> Companion to [solution-design.md](solution-design.md) (which covers *what* each layer does). This document covers *how the code is organized*: service boundaries, repo layout, inter-service contracts, and the order in which modules get created. Principle for this phase: **don't scaffold a service before something concrete needs it** — the folders below exist as named, bounded contexts with a defined contract, but many stay a README until their trigger condition (section 6) is hit.

---

## 1. Why service-per-subsystem, and why now

The subsystem split in the business case (docs section 2.3) already maps cleanly onto independent scaling/ownership boundaries:

- `validation-engine` is CPU-bound and stateless-per-run — scales by adding workers, has nothing to do with web traffic.
- `ingestion` is I/O-bound (uploads, exchange polling) and needs to run on a schedule independent of everything else.
- `reporting` is bursty (triggered by run completion) and produces documents, not JSON APIs.
- `dashboard`/`gateway` is the only piece that needs to be internet-facing and low-latency.

Splitting these into services from the start — even while everything runs on one laptop via Docker Compose — means each one can be deployed, scaled, or replaced independently later without a rewrite. It also directly serves the revenue model (docs section 2.4): `naive_first_engine` is designed to be extracted and licensed standalone, which only works if it was never entangled with web/DB code to begin with.

This is **not** "microservices for their own sake." Each boundary below was already implied by the subsystem split; this plan just makes the boundary real in code (own folder, own contract, own data ownership) instead of aspirational.

---

## 2. Module boundary map

| Module | Type | Bounded context (owns) | Talks to |
|---|---|---|---|
| `libs/naive_first_engine` | Library (no service) | Splitting, baselines, metrics, DM test — pure functions, zero I/O | Imported by `validation-service` only |
| `libs/common` | Library | Shared Pydantic schemas, tenant/auth context, DB session helpers | Imported by every service |
| `libs/sdk` | Library (published) | Python client for external users of `gateway-api` | External clients only, not imported by internal services |
| `services/gateway-api` | Service | Auth (JWT/API keys), tenant routing, request orchestration, public REST contract | Routes to all other services over HTTP |
| `services/ingestion-service` | Service | Upload API, market/sentiment connectors, raw-zone writes, data-quality gate | Owns `ingestion.*` schema + raw object storage prefix |
| `services/validation-service` | Service | Runs `naive_first_engine` against a dataset + config, persists per-split results | Owns `validation.*` schema; reads processed zone; emits `run.completed` event |
| `services/reporting-service` | Service | Renders audit reports from `validation.*` results, stores versioned reports | Owns `reporting.*` schema + report object storage prefix; triggered by `run.completed` |
| `services/dashboard-web` | Service | Server-rendered UI (FastAPI + HTMX/Jinja2) | Calls `gateway-api` only, no direct DB access |
| `services/economic-service` | Service (deferred) | Transaction cost/slippage/portfolio simulation | Owns `economic.*` schema; only triggered for models that already passed `validation-service` |

Rule: **no service reads another service's database schema directly.** Cross-service data access always goes through that service's API. This is what makes "split into separate DBs later" a non-event instead of a migration project.

---

## 3. Repo layout (monorepo, not polyrepo — for now)

```
crypto_ecosystem/
├── libs/
│   ├── naive_first_engine/        # pip-installable standalone, zero web deps
│   │   ├── src/naive_first_engine/
│   │   │   ├── splitting.py
│   │   │   ├── baselines.py
│   │   │   ├── metrics.py
│   │   │   ├── dm_test.py
│   │   │   └── report_schema.py
│   │   ├── tests/                 # includes regression tests vs thesis's published numbers
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── common/
│   │   ├── src/naive_first_common/
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── sdk/
│       ├── src/naive_first_sdk/
│       ├── pyproject.toml
│       └── README.md
│
├── services/
│   ├── gateway-api/
│   │   ├── src/app/                # FastAPI app: routers, auth, tenant middleware
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── ingestion-service/
│   ├── validation-service/
│   ├── reporting-service/
│   ├── dashboard-web/
│   └── economic-service/          # deferred, README only until triggered
│
├── infra/
│   ├── docker-compose.yml         # created when the first two services need to talk to each other
│   ├── migrations/                # one Alembic env per service schema
│   └── README.md
│
├── docs/
│   ├── da-tese-ao-produto.md
│   ├── solution-design.md
│   └── implementation-plan.md     # this file
│
├── research/                      # phase-3 applied research, unchanged
└── CLAUDE.md
```

Each service/lib directory, once real code exists in it, is independently: `pip`/`uv` managed (own `pyproject.toml`), independently testable (own `tests/`), independently containerized (own `Dockerfile`), and documented with an explicit API contract (FastAPI's auto-generated OpenAPI schema serves as the contract for services; a plain function signature list for libs).

---

## 4. Inter-service communication

- **Synchronous (request/response)**: plain REST over HTTP, called via `httpx`. `gateway-api` is the only service that talks to the outside world; it calls internal services directly by hostname inside the Docker network (`http://validation-service:8000/...`). No API gateway product (Kong/etc.) needed at this scale — FastAPI + a thin router is enough.
- **Asynchronous (events)**: a small set of domain events (`dataset.ingested`, `run.completed`, `report.generated`) published to **Redis Streams** (already needed for the task queue, so no new infra piece). `reporting-service` subscribes to `run.completed`; nothing subscribes to more than one hop away — keeps the event graph readable as it grows.
- Explicitly **not** using Kafka/RabbitMQ/gRPC yet — unjustified complexity at pilot scale. Revisit only if event volume or service count grows enough that Redis Streams' guarantees stop being sufficient (a real, observable trigger, not a preemptive choice).

---

## 5. Data ownership

Single Postgres + TimescaleDB instance for the pilot phase, but **schema-per-service** (`ingestion`, `validation`, `reporting`, `identity`, later `economic`) with no cross-schema foreign keys or joins in application code. Each service runs its own Alembic migrations against only its schema. This means moving a service to its own physical database later is a connection-string change, not a data-modeling project — the boundary already exists, it's just colocated.

Object storage (MinIO → S3) is prefixed the same way: `raw/{tenant_id}/...` owned by `ingestion-service`, `processed/{tenant_id}/...` also `ingestion-service` (post feature-engineering), `reports/{tenant_id}/...` owned by `reporting-service`.

---

## 6. Build order — trigger conditions, not a calendar

Per your instruction to create modules as they're needed, each module below has a **concrete trigger** rather than a fixed date. Don't scaffold the next one until its trigger is true.

| Order | Module | Trigger to create it |
|---|---|---|
| 1 | `libs/naive_first_engine` | Now — this is the core IP and has no dependencies. Build + unit test against the thesis's published numbers (docs section 1.3) as a regression suite. |
| 2 | `libs/common` (minimal: tenant context + shared schemas) | As soon as a second module needs to share a data shape — i.e. right when `validation-service` is scaffolded. |
| 3 | `services/validation-service` | As soon as `naive_first_engine` needs to be run against a real dataset via an API call instead of a local script. |
| 4 | `infra/docker-compose.yml` + Postgres | Same moment as #3 — a service needs somewhere to persist run/split results. |
| 5 | `services/gateway-api` + `identity` schema (auth) | As soon as more than one external caller needs access — i.e. the first pilot client, per your multi-tenant-from-day-one decision. Don't build auth before there's a second party to authenticate against. |
| 6 | `services/ingestion-service` | As soon as manually placing files for `validation-service` to read becomes the bottleneck — i.e. right after gateway-api exists and a real client needs to upload something. |
| 7 | `services/reporting-service` + Redis Streams | As soon as a validation run needs to produce a client-facing artifact instead of raw JSON — i.e. right after the first pilot audit is requested. |
| 8 | `services/dashboard-web` | As soon as a pilot client needs to see results without you manually sending them a file — i.e. second pilot client, or first client asking "where do I log in." |
| 9 | `libs/sdk` | As soon as a client wants to submit predictions programmatically instead of via the dashboard upload form. |
| 10 | Market/sentiment connectors inside `ingestion-service` | As soon as a client wants the platform to source ground truth instead of supplying it themselves. |
| 11 | `services/economic-service` | Only once a specific client model has already demonstrated stable outperformance in `validation-service` — never before, per the ethical boundary in docs section 2.7. |

---

## 7. Design patterns — where they earn their place

Patterns are applied only where they solve a concrete, already-visible problem in this design, not by default. Each one below is tied to the specific extension point it protects:

| Pattern | Where | Why it's justified here (not decorative) |
|---|---|---|
| **Strategy** | `naive_first_engine.baselines` (Naive0/NaiveLast) and any future model adapters in `validation-service` | New baselines or client-model wrappers must plug in without touching the splitter/DM-test code. One interface (`predict(train, test) -> Series`), swappable implementations. |
| **Repository** | Every service's data-access layer (`ingestion-service`, `validation-service`, `reporting-service`) | Keeps Postgres/object-storage specifics out of business logic, so schema-per-service (section 5) can move to a physically separate DB later by swapping the repository implementation, not rewriting call sites. |
| **Adapter** | `ingestion-service` connectors (exchange APIs, sentiment/on-chain sources) | Each external source has its own API shape; an `IngestionSource` interface (`fetch(since) -> RawRecords`) lets a new source (section 6, trigger #10) be added as one new adapter class, nothing else changes. |
| **Factory** | `reporting-service` report generator | Report "kind" may grow (audit report today, certification seal / continuous-monitoring digest later per docs section 2.6 phase 5) — a factory keyed on report type keeps `generate_report()` callers agnostic to which template renders. |
| **Observer / pub-sub** | Redis Streams events (`run.completed` → `reporting-service`, future `dataset.ingested` → quality-check trigger) | Already the mechanism chosen in section 4; named here explicitly so new subscribers are added, never new direct calls between services. |
| **Dependency Injection** | Every FastAPI service (`gateway-api`, `validation-service`, etc.) | FastAPI's `Depends()` is the DI mechanism — used for DB sessions, tenant context, and repository instances so handlers stay testable with fakes, no framework-specific test gymnastics. |
| **Template Method** | `naive_first_engine` validation run (`split → baseline → metrics → DM test`, fixed order, pluggable pieces) | The *order* of the leakage-aware protocol is non-negotiable (docs section 1.2); the pieces that vary (which model, which metric set) are the extension points. Encoding the fixed skeleton as a template method makes "you can't skip the purge gap" true by construction, not by convention. |

Deliberately **not** using yet (would be premature): CQRS, event sourcing, generic plugin/microkernel frameworks, ORMs with active-record patterns. Revisit only if a section-6 trigger surfaces a real need.

## 8. Documentation-for-scaling convention

Every module (lib or service), from the moment it has more than a README, keeps three things current so a future contributor — human or Claude — can extend it without re-deriving context:

1. **README.md**: purpose, what it owns/doesn't own, current status (planned / scaffolded / implemented), and a link back to this plan and to [solution-design.md](solution-design.md).
2. **API contract**: for services, FastAPI's generated OpenAPI schema is the source of truth (don't hand-maintain a duplicate); for libs, the public function signatures in the README stay in sync with the code — CI should fail if they drift (add a doc-check step once the first lib ships).
3. **ADRs (Architecture Decision Records)** in `docs/adr/NNNN-title.md` for any decision that reverses or narrows something in this plan (e.g. "we introduced Kafka because Redis Streams hit X limit at Y volume") — short, dated, one decision each, so the *why* survives even after the *what* changes.

## 9. Engineering conventions (apply from module #1 onward)

- **Python package manager**: `uv` (fast, single lockfile per module, no ambiguity about which env is active — matches the "many small independent packages" shape of this repo).
- **Every module ships tests before it ships an API** — `naive_first_engine` in particular must pass a regression test against the thesis's own numbers before any service is allowed to depend on it.
- **No service imports another service's code** — only `libs/*` are shared; if two services seem to need the same logic, that logic belongs in a lib, not copy-pasted.
- **DRY within a module's own boundary, always** — duplicated logic inside a single service/lib (e.g. two endpoints hand-rolling the same tenant-scoping query, two report templates repeating the same metrics-table markup) gets extracted to a shared function/class *within that module* as soon as it appears a second time. This is separate from cross-service DRY: never reach into another service's internals to avoid duplication (see previous bullet) — pull shared logic into a `libs/*` package instead if it's genuinely cross-cutting (e.g. tenant context, metric formatting used by both `dashboard-web` and `reporting-service` belongs in `libs/common`, not copy-pasted into each).
- **README per module** states: what it owns, what it does NOT own, its API contract (or public function list), and its current status (planned / scaffolded / implemented).
- **CLAUDE.md at repo root** stays the single source of truth for cross-cutting rules (naive-first-by-default, no leakage, no profitability claims) — module READMEs link to it rather than repeating it.
