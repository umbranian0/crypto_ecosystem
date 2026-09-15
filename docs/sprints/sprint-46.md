# Sprint 46 — Raw per-point prediction storage, retention, and charting (validation-service / dashboard-web)

Sprint goal: a tenant can view a real predicted-vs-actual chart for any split of a completed run,
backed by newly-persisted raw per-point data that is bounded by a concrete, enforced retention
policy from day one.

Backlog source: `docs/product/backlog-run-analysis-visualization.md` (RAV-006, RAV-007, RAV-008)

Stories in scope:
1. **RAV-006** — persist raw per-point predicted/actual values per split (new schema change in
   `validation-service`), together with a concrete, implemented, tested retention/pruning policy
   (default: 90 days OR 20 runs per tenant/dataset, whichever is simpler — Tech Lead's call per the
   story's own acceptance criteria). Prerequisites (RAV-001/002/003) confirmed **done** per
   `docs/tickets/README.md`. Sequenced first — RAV-007 and RAV-008 both structurally require this
   data to exist.
2. **RAV-007** — expose the per-point data via a new/extended API surface in `validation-service`,
   proxied through `gateway-api`, respecting RAV-006's retention cutoff on reads. Depends on
   RAV-006 landing first (cannot be estimated or built against data that doesn't exist yet).
3. **RAV-008** — predicted-vs-actual chart per split in `dashboard-web`, built against RAV-007's
   endpoint. Depends on RAV-007.

Stories explicitly deferred: none in this unit — RAV-006/007/008 form one linear, already-approved
chain (all raised from Could to Should by the founder 2026-09-15) and all three are in scope.

Sequencing/dependency note for the Tech Lead: this is a strict three-story chain across two
services (`validation-service` for RAV-006/007, `dashboard-web` for RAV-008) — no parallelization
is possible; each story is a hard precondition for the next.

Explicit call-outs for the Tech Lead (deliberately left as Tech Lead decisions per the backlog's
own text, not resolved by this sprint plan):
- RAV-006's exact schema shape (new table vs. JSON/array column) is the Tech Lead's call.
- RAV-006's retention-enforcement mechanism — scheduled deletion/archival job vs. query-time
  cutoff — is the Tech Lead's call between the two options the story names; whichever is chosen
  must be real and tested (not just documented), per the story's own acceptance criteria.
- RAV-007's exact endpoint shape (new field on `GET /runs/{id}/splits` vs. a new
  `GET /runs/{id}/splits/{split_index}/points` endpoint) and pagination/granularity approach are
  the Tech Lead's call, sized against RAV-006's storage-growth estimate.
- RAV-006 requires a written storage-growth estimate (rows = tenants x runs x splits x
  test-window-length x baselines-per-split) as part of its own Definition of Done — flag this for
  the ticket breakdown so it isn't dropped as "just a nice-to-have."

Risk note not resolved by the Product Owner: this is the first schema change to
`validation-service`'s persisted data since the platform's core "no schema change without a named
retention/growth answer" gate was raised — RAV-006 answers it for itself, but the Tech Lead should
confirm the chosen retention mechanism doesn't conflict with any other pending schema/migration
work scheduled in parallel this sprint (none known to this PM at planning time, but not
independently re-verified against a live migration-in-flight check).

Definition of done for this sprint: all acceptance criteria in RAV-006, RAV-007, and RAV-008
checked off, including RAV-006's non-negotiable "old data actually excluded/removed" test (not
merely a docstring claim), `naive_first_common.contracts` updated with the new canonical response
shape (per RAV-007's own acceptance criteria, no hand-duplicated field list), positioning-language
checks passed on RAV-008's chart copy (no forecast/extrapolation language, per CLAUDE.md), and
`services/validation-service/README.md` / `services/dashboard-web/README.md` updated to reflect the
new capability.
