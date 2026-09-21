# Sprint 56 — Epic A (Trust & Transparency), slice 1: per-run fingerprint + reproducibility statement (TRUST-003 → TRUST-004)

Sprint goal: every run created from this sprint forward persists a verifiable fingerprint of exactly
what produced it (`naive_first_engine` version + a deterministic hash of its own split config), and every
completed run's audit report states, in a checkable way, how to reproduce that exact result — closing the
gap where "this platform is auditable" was true of its methodology but not yet of its own run provenance.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md` — `TRUST-003` (Should) and `TRUST-004`
(Should, depends on `TRUST-003`). Both stories were already flagged, in `docs/sprints/sprint-55.md`'s
"Next" section, as the tentative first slice of Epic A for this sprint; this file re-verifies that sketch
against current code (see below) rather than carrying it over on trust.

## Verification of the backlog's cited findings (done independently, not taken on trust)

- `services/validation-service/migrations/versions/0008_add_runs_warnings_column.py` and
  `0009_add_runs_feature_lineage_column.py` (both read in full): confirmed the additive-migration pattern
  the backlog cites is real — a single `op.add_column('runs', sa.Column(...))` in `upgrade()`, mirrored by
  `op.drop_column` in `downgrade()`. One real nuance the backlog's citation glosses over, flagged for the
  Tech Lead: both existing precedents are `nullable=False, server_default='[]'` (they backfill every
  existing row with a real, non-null default). `TRUST-003`'s two new columns must instead be genuinely
  `nullable=True` with **no** `server_default` — the whole point of this story is that pre-migration runs
  stay honestly `null`, not backfilled with a fabricated value. Same "plain `ADD COLUMN`, portable type"
  idiom, different (and, here, deliberate) nullability/default shape — worth stating explicitly in the
  ticket so it isn't copy-pasted as `server_default='[]'`-equivalent by reflex.
- `services/validation-service/src/app/routers/runs.py` (read in full, `create_run` handler): confirmed
  the exact call site the AC refers to. The run row is created via `_persist_new_run(...)` at the point
  right after the price-level guardrail (currently line ~443, "Created before the try below (VS-012) so a
  run.id always exists..."), and `run_validation_protocol(series, run_config)` is invoked later, inside the
  following `try` block (currently line ~467). This confirms the AC is satisfiable exactly as written:
  `engine_version`/`config_fingerprint` can be computed and passed into `_persist_new_run`'s
  `run_repository.create_run(...)` call, which already runs strictly before `run_validation_protocol` —
  no reordering of the existing handler flow is required. `_persist_new_run`'s signature (`run_repository,
  tenant, request, warnings, feature_lineage=None`) will need the two new fields added the same way
  `feature_lineage` was added to it.
- `libs/naive_first_engine/pyproject.toml` (read in full): confirmed `version = "0.1.0"`, a real, bumpable
  string under `[project]` — exactly what the backlog cites as the `engine_version` source. Standard
  approach: read it from the installed distribution's metadata (`importlib.metadata.version(
  "naive_first_engine")`) rather than parsing the TOML file at runtime, so it stays correct if the
  installed wheel is ever pinned to a different build than the source tree — Tech Lead's call on the exact
  mechanism, but the value to read is confirmed real and confirmed to change on a real version bump.
- `libs/common/src/naive_first_common/contracts.py` (read in full): confirmed `RunDetailResponse`'s
  current shape (`id`, `tenant_id`, `dataset_id`, `horizon`, `purge_gap_hours`, `split_config`, `status`,
  `created_at`, `completed_at`, `failure_reason`, `warnings`, `has_client_model`, `feature_lineage`,
  `has_multimodal_features`, `label`) — no `engine_version`/`config_fingerprint` field exists yet. The
  existing fields all follow one convention worth reusing rather than reinventing: optional/derived fields
  default to a safe value (`[]`, `False`, `None`) so a validation-service response that temporarily omits
  a field during a rolling deploy doesn't break `gateway-api`'s/`dashboard-web`'s/`reporting-service`'s own
  `RunDetailResponse(**response.json())` reconstruction. `engine_version`/`config_fingerprint` should both
  be `str | None = None` on that same precedent — `None` reads correctly both as "not yet computed by an
  in-flight rolling deploy" and as "this run predates the migration," which is exactly the dual meaning
  `TRUST-004`'s null-handling AC needs.
- `services/reporting-service/src/app/renderers/validation_audit.py` and `src/app/generation.py` (both
  read): confirmed `reporting-service` never talks to `validation-service`'s database directly — `
  generation.py` calls it over HTTP (`httpx`) and reconstructs `run = RunDetailResponse(**run_response.
  json())` from the JSON response; `validation_audit.py`'s `ValidationAuditRenderer.render(run, splits, ...)`
  passes that same `RunDetailResponse` instance straight into the Jinja2 template as `run`. Net: once
  `TRUST-003` adds the two fields to `RunDetailResponse`, `reporting-service` needs **zero** renderer/
  generation code change to receive them — `run.engine_version`/`run.config_fingerprint` are simply
  available in the template context already. `TRUST-004`'s entire scope is template-only.
- `services/reporting-service/src/app/templates/validation_audit.html.jinja` (read in full): confirmed
  today's section 2, "Leakage-protocol parameters" (lines 32–40 as currently written), lists `Horizon`,
  `Purge gap (hours)`, and `Splits evaluated`, and is immediately followed by section 3, "Results table."
  Both sections sit inside the same `{% if run.status != "completed" %}...{% else %}...{% endif %}` guard
  that already omits every results-dependent section for a non-completed run. `TRUST-004`'s new
  reproducibility-statement subsection belongs inside that same `else` branch, positioned between today's
  section 2 and section 3, and should be renumbered as part of section 2 (a subsection) or a new section
  2.5/3, Tech Lead's call on exact heading numbering — the AC only requires "after section 2," not a
  specific number.
- Net: the backlog's own citations hold, with one correction surfaced above (the nullability/default shape
  of the two new columns is deliberately *not* identical to the `warnings`/`feature_lineage` precedent,
  even though the migration mechanics are).

## Why TRUST-003 strictly precedes TRUST-004 (not just priority order)

This is a real dependency, not a priority-list artifact: `TRUST-004`'s entire subsection is populated from
`engine_version`/`config_fingerprint`, fields that do not exist on `runs` or on `RunDetailResponse` until
`TRUST-003` ships. Building `TRUST-004`'s template branch first would mean rendering from fields that
don't exist yet — there is no partial-parallel path here (unlike, e.g., `sprint-57`'s tentative `TRUST-001`/
`TRUST-005` pairing, which is a file-overlap grouping of two independent stories, not a data dependency).
`TRUST-003` must be implemented, migrated, and populating real values at `POST /runs` time before
`TRUST-004`'s ticket can be verified against a real non-null fingerprint (its null-handling branch can and
should also be tested against a pre-migration run, which will exist naturally in any environment that had
runs before this sprint).

## Stories in scope, in execution order

1. **TRUST-003** — Per-run config/engine fingerprint for later re-verification.
   - Modules touched: `services/validation-service` (new migration `0012_...` adding `runs.engine_version`
     and `runs.config_fingerprint`, both nullable, no server default; `create_run`'s repository method and
     `_persist_new_run`/`create_run` handler in `runs.py` populate both before `run_validation_protocol` is
     invoked) and `libs/common` (`naive_first_common.contracts.RunDetailResponse` gains both fields,
     `str | None = None`).
   - Must sit strictly first: `TRUST-004` cannot be implemented or tested until these fields exist and are
     populated.
   - Constraint to carry into the ticket, stated explicitly per this sprint's own scope: **no retroactive
     fingerprinting of historical runs** — every run created before this migration stays `null` on both
     new fields, disclosed as a known, honest gap, never silently backfilled with a computed-after-the-fact
     value that would misrepresent what actually produced that run.
   - `config_fingerprint`'s hash must be over a canonicalized (stable key order) serialization of the run's
     own already-persisted `split_config` JSON, so the same logical config always hashes identically
     regardless of incidental key ordering.

2. **TRUST-004** — Auto-generated reproducibility statement per report.
   - Module touched: `services/reporting-service` only (`validation_audit.html.jinja` gains the new
     subsection after section 2; per the renderer trace above, no Python code change is needed in this
     service — the fields arrive on `run` automatically once `TRUST-003` is deployed).
   - Must handle a `null` `engine_version`/`config_fingerprint` gracefully: per this story's own AC and the
     "no retroactive fingerprinting" constraint above, a pre-migration run renders an explicit "not
     available for runs created before this platform tracked engine fingerprints" note — never a fabricated
     or inferred fingerprint standing in for a missing one.

## Module/dependency note for the Tech Lead (implementation-plan.md sections 2 and 6)

This sprint's two stories together touch **three separate modules**, each already built and live (no
trigger-firing question here — `validation-service` trigger #3, `libs/common` trigger #2, and
`reporting-service` trigger #7 all fired long ago):

- `services/validation-service` — new migration + `POST /runs` handler change.
- `libs/common` — `RunDetailResponse` contract extension (consumed by every service that imports it;
  confirmed no other consumer's existing field access breaks, since both new fields are additive and
  default to `None`).
- `services/reporting-service` — template-only change, reading the two new fields off the same
  `RunDetailResponse` it already reconstructs from `validation-service`'s HTTP response.

Per implementation-plan.md section 2's module boundary rule, each of these changes must land inside its
own module's own codebase — `reporting-service` must keep consuming the new fields only via the shared
`libs/common` contract and `validation-service`'s HTTP response (`generation.py`'s existing `httpx` call),
never by importing `validation-service`'s code or reading `validation.*` schema directly. Ticket breakdown
should reflect this as (at minimum) one ticket touching `validation-service` + `libs/common` together
(since the column and the contract field are one logical unit of work, `TRUST-003`), and a second,
independent ticket for `reporting-service` (`TRUST-004`), sequenced after the first is deployed.

## Stories explicitly deferred

- Everything else in `backlog-trust-and-admin-ops.md` not in scope this sprint: `TRUST-001`, `TRUST-002`,
  `TRUST-005`, all of Epic B (`RPT-001/002/004`), all of Epic C (`ADMIN-001/002/003/005`), all of Epic D
  (`ONB-001/002`) — deferred per `sprint-55.md`'s roadmap sketch, not dropped. See "Next" below for the
  tentative continuation; each future sprint still needs its own independent PM re-verification pass before
  being handed to the Tech Lead, same as this one was.

## File-overlap / concurrent-work risk

- No other in-flight or immediately-next-sprint story touches `services/validation-service/migrations/`,
  `services/validation-service/src/app/routers/runs.py`'s `create_run` handler, `libs/common/src/
  naive_first_common/contracts.py`, or `services/reporting-service/src/app/templates/
  validation_audit.html.jinja`. `sprint-57`'s tentative `TRUST-001`/`TRUST-005` pairing does touch this same
  template file next — worth flagging to the Tech Lead as a same-file-different-sprint heads-up (this
  sprint's new subsection should land in a way that doesn't require `sprint-57` to rebase around it
  awkwardly, e.g. don't leave the section numbering half-renumbered).

## Definition of done for this sprint

- `TRUST-003`'s and `TRUST-004`'s acceptance criteria (verbatim from `docs/product/backlog-trust-and-admin-ops.md`)
  are checked off in their respective tickets.
- A unit test proves `config_fingerprint` is deterministic (same `split_config` → same hash) and sensitive
  (a single differing value → a different hash) — per `TRUST-003`'s own AC.
- A test proves a run created before this migration renders/serves `engine_version`/`config_fingerprint`
  as `null`/`None` end-to-end (DB row → `RunDetailResponse` → template), never a fabricated value.
- A test proves a run created after this sprint's migration has both fields populated at `POST /runs` time,
  before `run_validation_protocol` runs (or at least present in the persisted row regardless of run
  outcome — Tech Lead's call on whether a failed run still gets a fingerprint, since the fields are computed
  before the protocol call and thus before failure is possible; if so, state this explicitly in the ticket).
- `reporting-service`'s reproducibility-statement subsection renders correctly for both a fingerprinted and
  a null-fingerprint completed run, positioned immediately after today's section 2 per the AC.
- `services/validation-service/README.md`, `libs/common/README.md` (or contracts-module-level docs), and
  `services/reporting-service/README.md` updated to record both fields/the new subsection as shipped
  (README-current convention, per this repo's standing rule).
- `docs/product/backlog-trust-and-admin-ops.md`'s `TRUST-003`/`TRUST-004` entries marked done with
  acceptance-criteria boxes checked, pointing to their ticket files.
- `docs/tickets/README.md` gets a new Sprint 56 section (Tech Lead updates this when tickets are
  created/closed, per this repo's standing convention — not done by this sprint plan itself).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`) after
  both tickets are Tech-Lead-verified done, before sign-off. QA scope should specifically, independently
  verify: the deterministic-hash claim; the "null only for pre-migration runs, never backfilled" claim (no
  code path computes a fingerprint for a run that predates the migration); and that the reproducibility
  statement never fabricates a fingerprint when the underlying fields are null.

## Next (explicitly not this sprint, roadmap note for continuing this backlog)

Per `sprint-55.md`'s own roadmap sketch (not re-verified against current code as part of this sprint's
scope — that re-verification is each future sprint's own job): **Sprint 57 (tentative)** — Epic A remainder,
`TRUST-001` (permanent methodology panel, touches `dashboard-web`'s `run_detail.html` and
`reporting-service`'s `validation_audit.html.jinja`) and `TRUST-005` (reframe "didn't beat naive" copy,
touches the same two files/templates), grouped for file-overlap reasons rather than a data dependency, plus
`TRUST-002` (static leaky-vs-purged demo page) as a third, independent story if sizing allows. That sprint
will need its own PM pass re-verifying those citations against then-current code (including this sprint's
own changes to `validation_audit.html.jinja`) before being handed to the Tech Lead.
