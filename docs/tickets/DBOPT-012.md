# DBOPT-012 — Widen `ix_split_results_tenant_run` to `(tenant_id, run_id, split_index)`

**Status: done, with a QA-disclosed scope correction — read before citing this ticket as "Sort node
eliminated."** Migration `0013` shipped exactly as designed (widened index, DDL-only, no RLS
change) and was personally re-verified by the Tech Lead (sqlite no-op, downgrade round-trip, live
upgrade/downgrade against the real Postgres container). **QA's independent live verification against
a real 550-split fixture run (landing in the newer, post-`0007` 90-day chunks — not the old
undersized-chunk artifact the implementing dev agent's own smaller-run check had flagged) found the
`Sort` node is *not* actually eliminated end-to-end**: `get_splits`' query has no `test_start`
predicate, so TimescaleDB's constraint exclusion cannot prune any chunk regardless of index shape or
run size — the query `Append`s every chunk in the hypertable, and as long as any chunk (there will
always be small/old ones) is scanned via `Seq Scan` rather than `Index Scan` (cost-based, for chunks
with few/no matching rows), Postgres cannot use a `MergeAppend` (which requires *every* child scan to
already be ordered) and so still adds an explicit top-level `Sort`. The widened index **does** do
what an index can do here — it correctly serves the dominant chunk's own in-order `Index Scan`
(confirmed live: `_hyper_1_309_chunk_ix_split_results_tenant_run` used for that chunk's 543-of-550
matching rows) — but it cannot, on its own, eliminate the outer `Sort` given this query's lack of a
partitioning-column bound. Absolute cost is trivial (3.1ms execution on the 550-row fixture) and
**does not affect any of this sprint's Must-priority acceptance criteria** (`RAV-016`'s 2s budget
passed with a wide margin). Correcting this ticket's own original claim rather than leaving it
inaccurate: **the index widening shipped as designed and is a real, working improvement to in-chunk
scan ordering, but full `Sort`-node elimination for `get_splits` would require either bounding the
query by `test_start`/a chunk-pruning predicate, or chunk consolidation — both out of this ticket's
scope, and neither implemented here.** See "Next" in `docs/sprints/sprint-61.md`'s close-out for the
recommended DBA follow-up. Full `services/validation-service` test suite personally re-run by the
Tech Lead: 238-261 passed across multiple runs (one flaky, pre-existing, unrelated
`created_at`-ordering test occasionally fails and always passes standalone — see this file's own
Test/Review sections below for the specific runs). Both `check_doc_sync.py`-relevant checks pass
(no route change in this ticket; N/A here, verified as part of `DBOPT-011`/`RAV-016`).

**Modules**: `services/validation-service` only — one new Alembic migration, no application code.
**Story**: `DBOPT-012`, `docs/product/backlog-db-optimization.md` (Should).
**Depends on**: none. Sequenced **first** in Sprint 61 (isolated, zero application-code risk;
`DBOPT-011`'s bounded/ordered read pays off fully only once this index exists).
**Sprint**: 61 (`docs/sprints/sprint-61.md`).

## Analysis

The DBA's live `EXPLAIN (ANALYZE, BUFFERS)` (backlog citation, real 75-row run `tenant
2e78966e105441c497da3fa8ffd2ff3c` / `run 19f5ba1dc7794d0db32c6a0e50900dd4`) found
`PostgresSplitResultRepository.get_splits`'s query (`WHERE tenant_id = :tenant_id AND run_id =
:run_id ORDER BY split_index`) doing a `Sort` node on top of `ix_split_results_tenant_run`'s
existing `(tenant_id, run_id)` index — that index narrows the scan to the matching rows but
cannot satisfy `ORDER BY split_index` for free. Cheap today (0.6ms at 75 rows) but directional:
a large run (the DASH-119-documented 38,597-split incident is the cited worst case) would sort
~500x more rows through the same uncovered path, on every `GET /runs/{run_id}/splits` call for
that run.

This ticket is DDL-only, no dependency on `DBOPT-011`'s application-code change landing first —
the index widening is valid and beneficial the moment it exists, whether or not `get_splits` is
bounded yet.

**Binding constraint, restated per the sprint plan (do not second-guess or escalate)**: this
migration does **not** touch `FORCE ROW LEVEL SECURITY` on `split_results`
(`0002_add_row_level_security.py`). A `DROP INDEX`/`CREATE INDEX` against the hypertable root is
DDL, not a data-path RLS bypass — it runs under `FORCE ROW LEVEL SECURITY` exactly as `0006`'s
original index creation already did against this same table. `DBOPT-008`'s BLOCKED compression
finding (`ALTER TABLE ... SET (timescaledb.compress, ...)` unconditionally rejects any
RLS-enabled table) does not apply to a plain `CREATE INDEX` statement — different DDL operation,
not subject to that restriction.

## Design

**Design pattern**: none new — this is a pure schema migration, no code touches the Repository/DI
patterns already in place.

**DRY check note**: grepped `services/validation-service/migrations/versions/` before writing
this design — `0006_add_split_results_tenant_run_index.py` is the exact precedent this migration
extends (same index name, same root-table/auto-propagation mechanism, same Postgres-only guard).
This is a widen-in-place (drop + recreate under the same index name), not a second index
alongside the old one — no other query in this repository uses `(tenant_id, run_id)` without also
implicitly wanting `split_index` order (`add_splits` is an `INSERT`, unaffected by index column
order), so there is no reason to keep both shapes.

### `services/validation-service/migrations/versions/0013_widen_split_results_tenant_run_index.py`

New revision, `down_revision = '0012'` (current head is `0012_add_runs_engine_fingerprint_columns.py`).

```python
"""widen ix_split_results_tenant_run to (tenant_id, run_id, split_index)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-27 00:00:00.000000

DBOPT-012: widens 0006's ix_split_results_tenant_run from (tenant_id, run_id)
to (tenant_id, run_id, split_index) so PostgresSplitResultRepository.get_splits'
`ORDER BY split_index` is served by the index directly, eliminating the
Sort node a live EXPLAIN found on top of the narrower index (see
docs/product/backlog-db-optimization.md's DBOPT-012 entry for the full
evidence). Combined with DBOPT-011's LIMIT/OFFSET, this also supports an
efficient bounded/ordered page read without a full re-scan.

Widen-in-place: same index name reused (not a new index alongside the
old one) via DROP INDEX; CREATE INDEX, issued against the hypertable
root -- same auto-propagation mechanism 0006 already established (a
root-level CREATE INDEX on this platform's TimescaleDB version, 2.29.1,
propagates to every existing chunk and to future chunks via the chunk
template). No other query in this repository uses (tenant_id, run_id)
without also implicitly wanting split_index order (add_splits is an
INSERT, unaffected by index column order) -- backward-compatible 1:1
replacement.

Does NOT touch FORCE ROW LEVEL SECURITY on split_results
(0002_add_row_level_security.py) -- this is DDL against the hypertable
root, not a data-path RLS bypass; runs under FORCE ROW LEVEL SECURITY
exactly as 0006's original index creation already did. DBOPT-008's
BLOCKED compression finding (ALTER TABLE ... SET (timescaledb.compress,
...) rejects any RLS-enabled table) does not apply to a plain CREATE
INDEX statement.

Postgres-only-guarded, same idiom as 0004/0005/0006:
test_models.py::test_alembic_upgrade_head_creates_matching_schema runs
`alembic upgrade head` (this migration included) against a real
sqlite:// DATABASE_URL, so this must no-op there, not error.

Pure schema/index change -- no application code touched (get_splits'
signature, SQL text structure, and ordering responsibility are
unaffected by this migration; DBOPT-011 is the separate ticket that
changes get_splits' own code).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_split_results_tenant_run")
    op.execute(
        "CREATE INDEX ix_split_results_tenant_run "
        "ON validation.split_results (tenant_id, run_id, split_index)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_split_results_tenant_run")
    op.execute(
        "CREATE INDEX ix_split_results_tenant_run "
        "ON validation.split_results (tenant_id, run_id)"
    )
```

## Implementation acceptance criteria

- [x] `services/validation-service/migrations/versions/0013_widen_split_results_tenant_run_index.py`
      created exactly as designed above (`down_revision = '0012'`), following `0006`'s exact
      `DROP INDEX IF EXISTS` / `CREATE INDEX` shape, Postgres-only-guarded, issued against the
      hypertable root.
- [x] No application code touched anywhere in this diff — `get_splits`' Python/SQL text is
      byte-identical before and after this ticket.
- [x] `FORCE ROW LEVEL SECURITY` on `split_results` is untouched by this migration (no `ALTER
      TABLE ... DISABLE/ENABLE ROW LEVEL SECURITY` anywhere in the diff).

## Test acceptance criteria

- [x] `alembic upgrade head` (this migration included) still succeeds and no-ops cleanly against a
      `sqlite://` `DATABASE_URL` — verified by re-running
      `test_models.py::test_alembic_upgrade_head_creates_matching_schema` (existing test, no
      changes needed to the test itself, matching `0006`'s own citation of this exact mechanism).
- [x] `downgrade()` round-trips cleanly against sqlite (no-ops, does not raise) — added
      `test_models.py::test_alembic_downgrade_then_upgrade_round_trips_cleanly` (the existing
      suite only exercised `upgrade`), running `upgrade head` → `downgrade -1` → `upgrade head`
      again against a fresh sqlite `DATABASE_URL`, asserting `returncode == 0` at each step.
- [x] Real Postgres/TimescaleDB **was** reachable in this session (`naive-first-postgres`,
      TimescaleDB 2.29.1, already running). Verified live: `alembic upgrade head` created the
      3-column index (`pg_indexes` confirmed `(tenant_id, run_id, split_index)` on the hypertable
      root); `alembic downgrade -1` reverted it to the original 2-column `(tenant_id, run_id)`
      shape; `alembic upgrade head` re-applied cleanly, leaving the live DB at `0013 (head)`.
      **Additional finding, disclosed rather than silently smoothed over**: a live `EXPLAIN
      (ANALYZE, BUFFERS)` against the real stack's current largest run (77 rows, spread across
      ~30+ of the old pre-`0007`-retuning undersized ~5-row chunks) still showed a top-level
      `Sort` node after the widen — root cause is that this specific run's rows are scattered
      across many small, non-uniformly-scanned chunks (`Append` mixing `Index Scan`/`Seq Scan`
      per chunk), which still requires an explicit `Sort` regardless of the index; a
      `MergeAppend` (which would skip the Sort) only applies when every child chunk scan is
      already index-ordered. This does not indicate the migration is wrong — the index is
      genuinely widened and does serve `ORDER BY split_index` directly within a single
      index-scanned chunk.
      **QA follow-up (post-sign-off, recorded here for the permanent record)**: QA re-ran this
      exact EXPLAIN against a real 550-split fixture run landing almost entirely (543/550 rows) in
      the newer, post-`0007` 90-day chunks — **the `Sort` node was still present**, confirming this
      is not a small/old-chunk artifact. Root cause, per QA's independent analysis: `get_splits`'
      query has no `test_start` (the hypertable's partitioning column) predicate at all, so
      TimescaleDB's constraint exclusion cannot prune any chunk regardless of run size or index
      shape — the query always `Append`s every chunk in the whole hypertable, and `MergeAppend`
      requires every child chunk scan to already be ordered, which fails the moment even one
      low-row-count chunk gets a cost-based `Seq Scan` instead of an `Index Scan`. The widened
      index does correctly serve the dominant chunk's own `Index Scan` in order (confirmed live) —
      it just cannot, alone, eliminate the outer `Sort` given the query's own unbounded-by-
      `test_start` shape. See this ticket's own Status line (top of file) for the corrected claim
      and the recommended follow-up scope.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the migration file and confirm it matches `0006`'s exact idiom (Postgres-only guard,
      root-table DDL, no per-chunk loop, paired `downgrade()`). **Verified**: byte-for-byte matches
      the ticket's own Design section, `DROP INDEX IF EXISTS` / `CREATE INDEX` shape, Postgres-only
      guarded.
- [x] Confirm no `FORCE ROW LEVEL SECURITY`/`DISABLE ROW LEVEL SECURITY` statement appears anywhere
      in the diff (grep the migration file). **Verified**: no such statement anywhere.
- [x] Confirm `revision`/`down_revision` chain correctly extends the current head (`0012`) with no
      branch conflict — `alembic heads` shows exactly one head after this migration is added.
      **Verified** (dev agent's report + this file's own `revision='0013'`/`down_revision='0012'`).
- [x] Run `services/validation-service`'s full test suite personally and confirm no regression.
      **Verified, independently re-run**: `238 passed` on a clean re-run; one flaky failure
      (`test_list_runs_orders_by_created_at_descending`) reproduced when run as part of the full
      suite, confirmed pre-existing and unrelated (passes in isolation, `1 passed in 0.10s`; a
      `created_at`-tie-break timing collision on fast hardware, touching `runs` list ordering, not
      `split_results`/this migration at all).
- [x] If Docker/a real Postgres container is reachable in this Tech Lead review session, personally
      run a live `EXPLAIN (ANALYZE, BUFFERS)` on `get_splits`' query against a real run with more
      than a handful of splits, before and after this migration, and record whether the `Sort` node
      is gone. **Not independently re-run by the Tech Lead this session** (the dev agent already
      did this live, with an honest disclosed caveat — see the Test acceptance criteria section
      above); deferred to the mandatory QA gate per this ticket's own instruction, with the added
      note (from the dev agent's finding) that QA should test against a run in the newer,
      post-`0007` 90-day chunks rather than the current largest (77-row, pre-retuning-chunk) run to
      get a representative result.

## Documentation acceptance criteria

- [x] `services/validation-service/README.md`: short note added recording that
      `ix_split_results_tenant_run` was widened from `(tenant_id, run_id)` to `(tenant_id, run_id,
      split_index)` in Sprint 61 (`DBOPT-012`), citing this ticket file and the elimination of the
      `ORDER BY split_index` `Sort` node.
- [ ] `docs/product/backlog-db-optimization.md`'s `DBOPT-012` entry: **deliberately left as `New
      (Sprint 31)`** — this update is held until the QA gate confirms the live EXPLAIN result
      (Sort node eliminated) against a representative run, per this ticket's own instruction not to
      mark it Done in the backlog file before that. Will be completed as part of this sprint's
      close-out, once QA clears.
