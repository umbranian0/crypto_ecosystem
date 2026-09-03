# Sprint 25 — Run submission safety (validation-service guardrail + dashboard-web guided submission)

Sprint goal: a submitted run configuration that would generate an unreasonable number of splits is
rejected with a clear `422` before any computation starts, regardless of which client submits it
(dashboard-web, a direct `gateway-api`/`curl` caller, or a pilot's own script), and the dashboard-web
run form shows the user the real dataset context and a live split-count estimate so they rarely reach
that rejection in the first place.

Backlog source: `docs/product/backlog-run-submission-safety.md` (RSS-001 through RSS-005).

Stories in scope, in execution order:

1. **RSS-004** — Server-side split-count guardrail on `POST /runs` (`validation-service`) [Must].
   Sequenced first, ahead of the dashboard UX stories, per the backlog's own explicit sequencing
   recommendation: it is the only story that structurally stops the incident regardless of caller
   (dashboard, direct API client, `curl`), it has no dependency on anything else in this backlog, and
   if only one story lands this sprint it must be this one. Not reordered by priority alone — it is
   also the only Must story with zero upstream dependency, so dependency order and priority order agree
   here.
2. **RSS-001** — Show the selected stored dataset's real row count and date range on the run form
   (`dashboard-web`) [Must]. No dependency on RSS-004 or on any other story; architecturally
   independent work in a different service (`dashboard-web` vs. `validation-service`), so it can run in
   parallel with RSS-004 if the squad has the capacity to do so — noted here explicitly rather than
   silently forced into a single-file sequence.
3. **RSS-002** — Live, client-side "approximately N splits" estimate as fields are edited
   (`dashboard-web`) [Must]. Sequenced after RSS-001 because it reads the `data-row-count` attribute
   RSS-001 adds to the dataset `<option>` elements — a real dependency, not a priority artifact (both
   are Must).
4. **RSS-005** — Document the guardrail and its provisional threshold in `validation-service`'s README
   [Should]. Sequenced after RSS-004 because it documents that story's actual shipped constant/rationale
   — cannot be written accurately before RSS-004's cap value and code comment exist.
5. **RSS-003** — Server-computed exact split count when start/end narrows a stored dataset
   (`dashboard-web`) [Should]. Sequenced last: it depends on both RSS-001 and RSS-002 (needs the row-count
   display and the live-estimate UI already in place to extend/label against), and its own acceptance
   criteria explicitly permit the Tech Lead to decide, before build, whether a new server endpoint is
   justified here or should be deferred until one exists for another reason — this sprint includes it in
   scope but does not force a particular technical answer to that question.

Stories explicitly deferred: none from this backlog — all 5 stories (RSS-001–005) are in scope. Note on
capacity: team size/velocity was not specified for this sprint. Given the backlog's small total scope
(5 stories, touching only two already-scaffolded modules, none requiring new infra) and this repo's own
precedent of sizing a sprint to a backlog's natural epic/dependency boundary rather than a numeric point
capacity (e.g. Sprint 17's eight-item hardening wave, Sprint 23/24's 13-story split by epic), all 5 are
included here rather than held back on an unstated assumption about velocity. If real capacity turns out
to be lower once the Tech Lead breaks these into tickets, defer the two Should stories first (RSS-003,
then RSS-005) — never RSS-004, RSS-001, or RSS-002, which are Must.

Out of scope (per the backlog's own Scope section, not re-litigated here): making `POST /runs`
asynchronous; retroactively touching the two runs already stuck computing from today's incident; any
change to `generate_splits`/`run_validation_protocol`'s own math.

## Open questions — resolved or explicitly carried forward, not silently decided

- **OQ-1 (real timing data from today's incident)**: NOT resolved this session — this PM planning
  session has no shell/database access to run `docker compose exec postgres psql` against
  `validation.runs` for the two runs' current `status`/`completed_at`. Carried forward as an open
  action: **before RSS-004's cap is finalized in code review**, whoever has stack access should check
  those two runs' real outcome (finished, still running, or timed out) and record the observed
  duration-per-N-splits data point in `services/validation-service/README.md` per RSS-005's acceptance
  criteria. This is not a blocker for starting RSS-004's implementation (the cap is explicitly
  provisional either way) but it should inform final sign-off on the cap value before merge.
- **OQ-2 (the 500-split cap itself)**: NOT adjusted — carried forward as the backlog's own provisional
  value, explicitly because OQ-1 (the only source of real evidence that could revise it) could not be
  checked in this session. RSS-004 ships with the cap at **500**, named as a constant, with a comment
  citing this backlog's OQ-1/OQ-2 and stating it is a reasoned placeholder pending real timing data —
  exactly as the backlog specifies. Do not treat this sprint plan as having confirmed 500 with evidence;
  it has not.
- **OQ-3 (`purge_gap_hours` row-offset vs. calendar-hour naming mismatch)**: deferred, not scheduled in
  this sprint. This is a pre-existing naming/semantics gap in `generate_splits`, out of this backlog's
  own stated scope (fixing it changes `generate_splits`'s public contract; this backlog only adds a
  check before invoking existing math), and both RSS-002's client estimate and RSS-004's server check
  must use — and this sprint's stories do use — the same "as literal row-offset" semantics the code
  actually implements today, so nothing in this sprint is blocked by leaving the name as-is. Recommend
  the Product Owner add it to a future backlog as a small, standalone documentation/rename ticket, per
  the backlog author's own recommendation — not bundled into this sprint.

Definition of done for this sprint:
- RSS-004, RSS-001, RSS-002 (all Must) complete with every acceptance criterion checked against the
  actual diff, including RSS-004's three required test cases (incident input → `422`; exactly-at-cap →
  accepted; cap+1 → rejected) and its proof that the check runs before `run_validation_protocol` for at
  least one input per `dataset_reference` mode.
- RSS-005 and RSS-003 (Should) complete, or explicitly re-flagged with reason if not — RSS-003 in
  particular may legitimately close as "deferred by Tech Lead cost call" per its own acceptance criteria
  without that counting as an incomplete Must.
- `services/validation-service/README.md` (RSS-005) and `services/dashboard-web`'s own README/contract
  notes (per this repo's standing documentation convention) both updated to describe the new behavior.
- No change to `generate_splits`/`run_validation_protocol`'s own math; no new asynchronous job/polling
  architecture introduced.
- Full `services/validation-service` and `services/dashboard-web` test suites re-run with zero
  regressions.
- OQ-1's real timing data recorded in `services/validation-service/README.md` if obtained before this
  sprint closes; if not obtained, the README and this sprint file both state plainly that the cap
  remains an unverified placeholder, not silently presented as confirmed.
