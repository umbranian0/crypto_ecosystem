# Sprint 03 — services/validation-service (scaffolding, schema, repositories, endpoints, event interface, regression + failure handling)

Sprint goal: Stand up `services/validation-service` end-to-end on interim (non-Postgres, non-Redis, non-object-storage) backends — scaffolding, tenant-scoped schema, Repository-pattern data access, the three contract endpoints (`POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`), the `run.completed` event interface, and failure handling — so a caller can run `naive_first_engine` against a real dataset via an API call today, with every interim substitution swappable later without touching call sites.

Backlog source: docs/product/backlog-validation-service.md (11 of 12 Must-priority stories; VS-010 deferred — see below)

Stories in scope (execution order):

1. **VS-001** — Service scaffolding. Depends on: none. Literal first step — nothing else in this backlog has a package/app skeleton to live in until this exists.
2. **VS-002** — `validation` schema definition (`runs`, `split_results`). Depends on VS-001. Needs the skeleton in place; every downstream repository/endpoint/event story needs an agreed data shape first.
3. **VS-003** — Repository interfaces (`ValidationRunRepository`, `SplitResultRepository`). Depends on VS-002. Interfaces are defined against the schema, before either interim or future storage implementations exist.
4. **VS-004** — Interim in-memory/SQLite-backed repository implementation. Depends on VS-003. Concrete implementation of the just-defined interfaces; unblocks any endpoint that needs to persist/read data.
5. **VS-005** — `DatasetSource` abstraction + interim inline/local-file implementation. Depends on VS-001 only (not on VS-002/003/004 — it's an independent input-side abstraction). Sequenced here, immediately before VS-006, because VS-006 needs both this and VS-004 ready; no reason to delay it earlier since its only real dependency (VS-001) clears in step 1.
6. **VS-006** — `POST /runs` endpoint. Depends on VS-004, VS-005 — both now complete. This is the literal trigger condition for the whole service; nothing past this point can be built without it.
7. **VS-007** — `GET /runs/{id}` endpoint. Depends on VS-006. Read-side counterpart to the write endpoint; needs a persisted run to fetch.
8. **VS-008** — `GET /runs/{id}/splits` endpoint. Depends on VS-006. Same rationale as VS-007, for per-split data; sequenced alongside it since both depend only on VS-006 and nothing on each other.
9. **VS-009** — `run.completed` event publishing interface + interim implementation. Depends on VS-006. Wired into the `POST /runs` handler's completion path; needs that handler to exist first.
10. **VS-011** — Integration regression test: `POST /runs` round trip. Depends on VS-006, VS-008 — both now complete. Exercises the full write-then-read-splits path at the API boundary, so it must follow both endpoints it drives.
11. **VS-012** — Run failure/status handling. Depends on VS-006, VS-009 — both now complete. Failure handling must assert "no `run.completed` on failure," which requires VS-009's publisher to already exist to test against; sequenced last since it hardens the full flow (VS-006 through VS-009) rather than adding new surface area.

Stories explicitly deferred:
- **VS-010** (tenant context resolution via `libs/common`) — Must priority, but explicitly blocked per the backlog's own decision 1: `libs/common` has no backlog or code yet, only a README, so there is no minimal tenant-context module for this story to consume. The backlog itself frames this as "implemented against a placeholder that then gets thrown away" being explicitly disallowed — so it is not started this sprint. This service's own tenant-scoped schema/repository work (VS-002/003/004) proceeds independently, using an interim explicit `tenant_id` field (VS-006/007/008) until VS-010 can replace it. **Flag for the Product Owner: a separate, small `libs/common` backlog covering the minimal tenant-context module should be created so VS-010 has something to schedule against — it cannot be planned into any sprint until that backlog exists and ships.**
- **VS-013, VS-014, VS-015** (Postgres-backed repository, Redis Streams-backed publisher, object-storage-backed `DatasetSource`) — Should priority; each is explicitly blocked in the backlog on an infra trigger that hasn't fired (`infra/docker-compose.yml`+Postgres, trigger #4; Redis Streams via trigger #7; `ingestion-service`'s processed zone via trigger #6). Deferred, matching the Sprint 01→02 pattern of Shoulds moving to a later sprint.
- **VS-016** (OpenAPI/README contract sync check) — Should priority; valuable hygiene but not blocking any functional Must story. Deferred.
- **VS-017** (client-supplied prediction column as a `Baseline` Strategy) — Could priority; not required for this service's trigger condition. Deferred.

Definition of done for this sprint:
- All 11 in-scope Must stories' acceptance criteria are met as written in docs/product/backlog-validation-service.md.
- `uv run pytest` passes in `services/validation-service`, including VS-011's integration round-trip test (persisted/returned Naive0 MAE and DM verdict counts match `naive_first_engine`'s own regression reference numbers) and VS-004's/VS-012's unit tests (tenant-scoping isolation, failure-path status handling).
- `POST /runs` → `GET /runs/{id}` → `GET /runs/{id}/splits` works end-to-end against the interim SQLite repository (VS-004) and interim `DatasetSource` (VS-005), invoking `naive_first_engine.protocol.run_validation_protocol` unmodified.
- `run.completed` (VS-009) is published exactly once per successfully completed run and never for a failed run (VS-012), via the interim in-process/log publisher.
- Every table and repository method carries `tenant_id` explicitly (VS-002/003/004), even though tenant *resolution* (VS-010) is not yet wired in — the interim explicit `tenant_id` field on VS-006/007/008 is a documented stand-in, not a silent gap.
- All interim implementations (VS-004, VS-005, VS-009's publisher) are documented in the service README as interim, swappable-by-DI-only, with the blocked Should story that will eventually replace each one named explicitly — so a future contributor doesn't mistake any of them for final design.
- No code in this sprint touches `libs/naive_first_engine` (already done, Sprint 01+02), `services/ingestion-service`, `services/reporting-service`, `services/gateway-api`, `services/dashboard-web`, or `services/economic-service` — all out of scope per the backlog.
- This sprint does not start VS-010 — it remains explicitly blocked and unscheduled pending a `libs/common` backlog.
