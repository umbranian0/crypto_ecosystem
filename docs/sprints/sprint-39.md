# Sprint 39 — Remaining Should/Could UAT findings (dashboard-web, gateway-api, validation-service)

Sprint goal: every remaining Should- and Could-priority finding from the 10-persona UAT review is
closed, so a run-detail reader gets an at-a-glance verdict and clean numbers, a power user can label,
paginate, and correctly bucket their runs, an external integrator gets a fully typed API contract, and
the accessibility/onboarding gaps flagged as lower-severity are closed out — completing the full UAT
backlog (`docs/product/backlog-uat-findings.md`) alongside the Must-tier sweep already shipped in
Sprint 35.

Backlog source: `docs/product/backlog-uat-findings.md` — UAT-003, UAT-004, UAT-006, UAT-007, UAT-008,
UAT-009, UAT-010 (Should), UAT-012, UAT-013, UAT-014 (Could). All ten are already prioritized/approved
in that file; nothing new is introduced here.

## Stories in scope, in execution order

Grouped into four parallel-safe tracks. Within a track, stories are strictly sequential due to file
overlap even where they are logically independent — same discipline as Sprint 35's Track A. Across
tracks, work can run concurrently.

**Track A — contract-only, `gateway-api`/`validation-service`, zero dashboard-web overlap:**
1. **UAT-007** — type `RunRequest.dataset_reference` in the OpenAPI schema. Touches
   `naive_first_common.contracts.RunRequest`. Sequenced first in this track because UAT-008 (Track C)
   also edits `RunRequest` and needs UAT-007's typing to land first, not concurrently — file-overlap
   ordering only, no logical dependency between the two stories' content.
2. **UAT-006** — fix `failure_reason` at its real source in `validation-service`. No file overlap with
   UAT-007 or anything else in this sprint; listed here only because it shares Track A's "no
   dashboard-web touch" property, not because it depends on UAT-007. Can run fully in parallel with
   UAT-007 if the Tech Lead prefers; grouped for narrative convenience only.

**Track B — run-detail synthesis chain (sequential, same files: `run_detail.html`, `app/charting.py`,
chart partials):**
3. **UAT-003** — headline verdict summary on `run_detail.html`, built from `app/charting.py`.
   Depends on UAT-001 (done, Sprint 35) for the placeholder-caveat wording. No dependency on anything
   in this sprint. Sequenced first in this track since it establishes the new headline element other
   `run_detail.html` edits (UAT-004, and later UAT-008 in Track C) should not clobber mid-flight.
4. **UAT-004** — fixed-precision rounding filter, applied across `run_detail.html`'s table, chart
   tooltips/labels, FHS-003's summary panel, and FHS-004's copy-summary export. Sequenced after UAT-003
   purely for file-ordering (`run_detail.html`, `app/charting.py`) — no logical dependency.
5. **UAT-013** — chart section titles become real `<h2>`/`<h3>` elements in `_error_chart.html`,
   `_dm_verdict_chart.html`, `_forecast_horizon_summary_panel.html`. Sequenced after UAT-004
   deliberately: UAT-004 just touched these same three partials to route values through the rounding
   filter — running UAT-013 after avoids two stories editing the same partials concurrently.

**Track C — power-user run management (sequential, same files: `run_new.html`, `runs_list.html`,
`run_detail.html`, shared `RunRequest` contract):**
6. **UAT-008** — optional `label` field on `RunRequest`, submission form, runs-list, and run-detail
   rendering. Depends on UAT-007 (Track A) for the `RunRequest` contract file — must not edit that
   model concurrently with UAT-007's typing change; sequence Track A item 1 to completion first. Also
   touches `run_detail.html`, so sequenced after Track B (items 3–5) finishes editing that file, to
   avoid a three-way concurrent edit. Tech Lead flag from the backlog itself carried forward: confirm
   whether this lands as a new `RunRequest` field or a `PATCH`-style rename-after-creation endpoint —
   that's a design call for the Tech Lead, not decided here.
7. **UAT-009** — pagination controls on `runs_list.html`. Sequenced after UAT-008 since both touch
   `runs_list.html`. Before starting, confirm DASH-122's actual shipped state (server-side
   limit/offset/total support) per the backlog's own note — this story assumes that groundwork exists
   and adds UI only.
8. **UAT-010** — hour-based (1h/6h/24h) bucket options on `/runs/horizon-summary`, additive alongside
   the existing day-based buckets (ADR-0007 stays authoritative, not superseded). No file dependency on
   UAT-008/UAT-009 identified from the backlog description — its own bucket-selector template and
   filtering code path are distinct from `runs_list.html`/`run_new.html`. Flag for the Tech Lead: verify
   at ticket-breakdown time whether `/runs/horizon-summary`'s bucket-selector template is in fact
   distinct from FHS-003's `_forecast_horizon_summary_panel.html` (touched by UAT-004 in Track B) — if
   it turns out to be the same partial, this story needs re-sequencing after Track B item 4, not before.

**Track D — accessibility/onboarding polish (sequential, same files: `base.html`, `run_new.html`):**
9. **UAT-012** — skip-to-content link, first focusable element in `base.html`. No dependency on
   anything else in this sprint. Sequenced before UAT-014 since both touch `base.html`'s nav/header
   region.
10. **UAT-014** — new plain-language `/help/concepts` page, linked from `base.html`'s nav and from
    `run_new.html`'s form. Sequenced after UAT-012 for `base.html` file-ordering, and after Track C item
    6 (UAT-008) for `run_new.html` file-ordering, since both add markup to that same form template.

## Stories explicitly deferred

None — this sprint closes the entire remaining backlog (all seven Should items and all three Could
items from `docs/product/backlog-uat-findings.md`). Nothing is left unscheduled after this sprint ships.

## File-overlap / concurrent-work risk (explicit)

- `RunRequest` (`naive_first_common.contracts`, mirrored in `gateway-api`'s local copy per its own
  README convention): UAT-007 then UAT-008, strictly sequential, not parallel.
- `run_detail.html` / `app/charting.py`: UAT-003 → UAT-004 → (later) UAT-008, strictly sequential.
- Chart partials (`_error_chart.html`, `_dm_verdict_chart.html`, `_forecast_horizon_summary_panel.html`):
  UAT-004 → UAT-013, strictly sequential. Possible additional overlap with UAT-010 — verify at
  ticket-breakdown time (see Track C, item 8's flag).
- `runs_list.html`: UAT-008 → UAT-009, strictly sequential.
- `run_new.html`: UAT-008 → UAT-014, strictly sequential.
- `base.html`: UAT-012 → UAT-014, strictly sequential.
- Tracks A, B, C, and D have no file overlap with each other except where Track C explicitly depends on
  Track A (UAT-007 before UAT-008) and Track D explicitly depends on Track C (UAT-008 before UAT-014) —
  those two cross-track orderings must be respected; everything else across tracks is parallel-safe.

## Dependencies (module boundaries, implementation-plan.md sections 2 and 6)

- All ten stories operate within already-built, already-triggered modules (`services/dashboard-web`,
  `services/gateway-api`, `services/validation-service`) — no module-boundary violation, no story here
  requires scaffolding a not-yet-triggered module.
- UAT-003 has a real data dependency on UAT-001 (done, Sprint 35) for the placeholder-caveat wording —
  not a concern for this sprint since UAT-001 already shipped, but recorded per this role's mandate to
  state dependency-driven ordering explicitly.
- UAT-007 → UAT-008 and UAT-008 → UAT-009 / UAT-008 → UAT-014 are file-sequencing dependencies, not
  logical/data dependencies — the Tech Lead may reorder within a track if there's a reason to, but
  should not run same-file stories concurrently.
- UAT-006 and UAT-010's tracing/verification notes from the backlog (confirm actual failing module for
  UAT-006; confirm DASH-122's shipped state for UAT-009; confirm partial-template identity for UAT-010)
  are carried forward as-is — this PM plan does not resolve them, they're implementation-time
  verification the Tech Lead/dev squad performs before or during ticket breakdown.

## Definition of done for this sprint

- All ten stories' acceptance criteria (as stated in `docs/product/backlog-uat-findings.md` for
  UAT-003/004/006/007/008/009/010/012/013/014) are checked off.
- Each story's own unit test (per its acceptance criteria) passes; full existing suite re-run with zero
  regressions, same discipline as prior sprints.
- `services/dashboard-web/README.md`, `services/gateway-api/README.md`, and
  `services/validation-service/README.md` updated with each shipped ticket's status/contract change, per
  this repo's standing convention.
- `docs/tickets/README.md` gains entries for all tickets opened against UAT-003/004/006/007/008/009/010/
  012/013/014 with dependency and status columns filled in, matching the existing table format.
- `docs/product/backlog-uat-findings.md`'s UAT-003/004/006/007/008/009/010/012/013/014 entries marked
  done with acceptance-criteria boxes checked and a pointer to the shipping ticket(s), matching the
  UAT-001/002/005/011 convention from Sprint 35.
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after all tickets in this sprint are done, before production sign-off — this sprint touches a published
  API contract (`RunRequest`, UAT-007/UAT-008) and multiple dashboard-web surfaces, so QA is required.

## Next (explicitly not this sprint)

- None from `docs/product/backlog-uat-findings.md` — this sprint is the final tranche of that backlog.
  Future sprints draw from whichever backlog the Product Owner next approves.
</content>
