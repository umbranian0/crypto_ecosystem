# Sprint 45 — Tenant historical-data backfill (ingestion-service / gateway-api)

Sprint goal: every existing tenant has the platform's full historical CSV data copied into their
`ingestion` schema rows, and every tenant created from now on gets the same data automatically at
provisioning time.

Backlog source: `docs/product/backlog-ingestion-pipeline-integration.md` (INGEST-010, INGEST-029)

Stories in scope:
1. **INGEST-010** — one-time backfill (`seed_tenant.py --all-existing-tenants`) copying
   `data/raw/_platform/...` CSVs into every existing tenant's `ingestion` schema rows.
   Dependencies (INGEST-002, INGEST-003) confirmed **done** per `docs/tickets/README.md`
   (`INGEST-002` done, `INGEST-003` done). No longer blocked — founder's tenant-attachment
   decision resolved 2026-09-15 (copy to every tenant, no demo-tenant special case). Sequenced
   first because INGEST-029 explicitly reuses this story's write path and idempotency guarantee.
2. **INGEST-029** — provisioning-time hook so every new tenant gets the same historical data
   automatically, via a new internal `ingestion-service` endpoint called from `gateway-api`'s
   `provision()`. Dependencies confirmed done: INGEST-010 (sequenced immediately before it in this
   sprint), SETUP-002 (done) and SETUP-011 (done) — both existing tenant-creation front doors this
   hook attaches to. Sequenced second: per the story's own text, it "invokes the exact same write
   path INGEST-010/seed_tenant.py already uses," so INGEST-010's script must exist as working code
   first, not just as an approved backlog entry.

Stories explicitly deferred: none in this unit — both INGEST-010 and INGEST-029 are Must priority
and both are unblocked; no reason to hold either back.

Sequencing/dependency note for the Tech Lead: this is a strict two-story chain, not a
priority-ordering choice — INGEST-029 is not schedulable in parallel with INGEST-010 because its
acceptance criteria require reusing INGEST-010's actual write path, not a re-implementation of it.
Do not split these across two Tech Lead batches without preserving that order.

Explicit call-outs for the Tech Lead (Product Owner already deferred these to Tech Lead judgment,
not decided by this sprint plan):
- INGEST-029's new internal `ingestion-service` endpoint (e.g. `POST
  /internal/seed-platform-history`) and its exact call site inside `gateway-api`'s `provision()`
  (synchronous vs. fire-and-forget) are the Tech Lead's call per the story's own acceptance
  criteria — this sprint plan does not prescribe either.
- INGEST-029's degraded-path requirement (tenant creation must succeed even if the historical-seed
  call fails) needs a concrete logging/retry story in the ticket breakdown — flagged so it isn't
  lost when the story is split into tickets.
- Both stories touch `services/ingestion-service` only on the read/write-path side; INGEST-029
  additionally touches `services/gateway-api`'s `provisioning.py` — confirm ticket boundaries
  respect the module split (a ticket should not span both service directories).

Definition of done for this sprint: all acceptance criteria in INGEST-010 and INGEST-029 checked
off, both scripts/endpoints covered by passing tests (including cross-front-door parity for
INGEST-029: `scripts/provision_tenant.py` and `POST /tenants` produce identical seeded data),
`services/ingestion-service/README.md` and `services/gateway-api/README.md` updated per each
story's own doc-sync acceptance criteria, and `docs/tickets/README.md` updated to reflect both
tickets as done.
