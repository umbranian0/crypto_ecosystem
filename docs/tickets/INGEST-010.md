# INGEST-010 (revised) — Repeatable, tenant-parameterized `seed_tenant.py` backfill CLI

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: todo (blocked only on the
founder's tenant-attachment decision, not on any other ticket). **Priority**: Must.
**Depends on**: `INGEST-002`, `INGEST-003`. Can run any time after those land.

## Analysis
Story: backlog `INGEST-010`, **revised** by solution-design.md section 8.6 and `CONTEXT.md`'s "Seed
data" glossary entry: this must be a repeatable, tenant-parameterized command, not a one-time migration
script. The historical `data/raw/_platform/...` CSV archive is one `--from` source option among others,
not a special-cased one-off migration — per the user's own instruction, the general capability is built
regardless of which tenant(s) get seeded first.

**Open founder decision, restated, NOT resolved by this ticket**: which tenant(s) get the existing
platform-wide historical CSVs attached at first-run time (every existing tenant vs. one designated
seed/demo tenant). This ticket's own Definition of Done includes recording the founder's actual choice
in the README — not defaulting to either option unstated. The `--tenant-id` CLI argument itself makes
either answer (or neither, yet) an ordinary invocation, not a design fork.

## Design
File: new `services/ingestion-service/scripts/seed_tenant.py`, mirroring `provision_tenant.py`'s
"standalone, operator-run, host-access-gated" convention. **DRY check**: writes via `INGEST-003`'s exact
`ConnectorRecordRepository` interface — no second CSV-parsing/DB-writing code path.

## Implementation acceptance criteria
- [ ] `seed_tenant.py --tenant-id <id> --source <source> --from <path-or-"platform-csv"> [--dry-run]` —
  `--tenant-id` and `--source` required, not defaulted to any hardcoded tenant.
- [ ] `--from platform-csv` reads `data/raw/_platform/<source>/{seed,incremental}/...` per
  `PROVENANCE.md`'s documented layout; `--from <arbitrary-path>` reads an arbitrary CSV, so a future
  non-platform seed source is the same operation, not a special case.
- [ ] Idempotent: upsert keyed on `(tenant_id, source, event_time)` (the hypertables' own PK) — running
  twice for overlapping ranges does not duplicate rows.
- [ ] `--dry-run` prints row counts per source/tenant without writing.
- [ ] `PROVENANCE.md`'s existing per-source caveats (raw/processed boundary for price, Kaggle-sentiment
  discontinuity, licensing-review-not-done flag) are copied into `ingestion-service/README.md`'s new
  backfill section — not lost in the move from file-based to DB-based storage.

## Test acceptance criteria
- [ ] Idempotency test: running twice against the same CSV range does not duplicate rows.
- [ ] `--dry-run` writes nothing (asserted against a real or fake repository call count of zero writes).

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms `--tenant-id` has no hardcoded default anywhere in the script.
- Confirms the repository call path is identical to `INGEST-003`'s, not a second implementation.

## Documentation acceptance criteria
- [ ] `services/ingestion-service/README.md`'s new backfill section records: the mechanism, the
  `PROVENANCE.md` caveats carried forward, and **the founder's actual tenant-attachment choice once
  made** — left explicitly marked "open, not yet decided" if this ticket ships before that decision
  lands, never defaulted silently.
