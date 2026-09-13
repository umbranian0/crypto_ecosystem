# Sprint 35 — UAT disclosure/accessibility fixes (validation-service, dashboard-web, gateway-api)

Sprint goal: every Must-priority UAT finding from the 10-persona review is closed, so a reader of any
run — via the dashboard or the raw API contract — can no longer be misled about whether a real client
model beat Naive0, miss the raw-levels-vs-returns caveat, or lose a screen-reader-only disclosure.

Backlog source: `docs/product/backlog-uat-findings.md` (UAT-001, UAT-002, UAT-005, UAT-011, plus the
confirmed small `/monitoring` bug documented in that file's "Confirmed small bug" section).

## Stories in scope, in execution order

Two independent tracks can run in parallel; within the dashboard-web track, stories must run strictly
sequentially due to file overlap (see risk note below).

**Track A — dashboard-web disclosure chain (sequential, same files):**
1. **VS-029** (UAT-001, backend half) — add the `has_client_model`-style boolean field to
   `validation-service`'s `RunDetailResponse`/`SplitResultResponse`. No dependency; sequenced first in
   this track because DASH-125 needs the field to exist before it can render the honest label.
2. **DASH-125** (UAT-001, dashboard half) — `run_detail.html` "Model" column label, RAV-002/003 chart
   legends, FHS-003 summary panel, FHS-004 copy-summary export all inherit the placeholder disclosure.
   Depends on VS-029 (needs the real field, not an inferred one). Sequenced before DASH-126/127 because
   it touches `run_detail.html` first and establishes the disclaimer block layout the other two stories
   extend rather than fight over.
3. **DASH-126** (UAT-002) — static raw-levels-vs-returns notice on `run_new.html`, plus the same warning
   folded into `run_detail.html`'s existing disclaimer paragraph. Depends on DASH-125 for file-ordering
   only (both touch `run_detail.html`'s disclaimer block) — no data/logic dependency.
4. **DASH-127** (UAT-011) — `aria-label`/`aria-describedby` on every `data-tooltip` element, including
   the ones DASH-126 just added text to. Sequenced last in this track deliberately: it must run *after*
   DASH-126 so the accessible markup is added to the final tooltip text, not text that gets edited out
   from under it.

**Track B — independent, can run in parallel with Track A:**
5. **GW-029** (UAT-005) — fix `openapi.json`'s `X-Operator-Token` security-scheme leakage onto `/runs`
   and confirm `Authorization`/`X-Api-Key` schemes are actually wired via `Security()`. No dependency,
   `gateway-api` only, zero file overlap with Track A.
6. **DASH-124** (confirmed small bug, not a UAT-numbered story) — `/monitoring`'s login-prompt vs.
   transient-fetch-failure conflation in `monitoring.html`/`operator.py`: gate the login-prompt branch on
   `headers is none` instead of `crawl_statuses is none`. No dependency, touches `monitoring.html`/
   `operator.py` only — disjoint from every Track A file (`run_new.html`, `run_detail.html`, the chart
   partials). Can run at any point in the sprint, including fully in parallel with Track A.

## Stories explicitly deferred

None from this backlog's Must tier — UAT-001, UAT-002, UAT-005, UAT-011, and the confirmed small bug are
all in scope. Every Should/Could item in `docs/product/backlog-uat-findings.md` (UAT-003, UAT-004,
UAT-006 through UAT-010, UAT-012 through UAT-014) is explicitly out of scope for this sprint per this
session's "keep it simple, don't over-engineer" instruction — none of them is a dependency of any Must
item scheduled here, so deferring them does not block anything in this sprint.

## File-overlap / concurrent-work risk (explicit)

`DASH-125` (UAT-001), `DASH-126` (UAT-002), and `DASH-127` (UAT-011) all touch `run_detail.html`, and
`DASH-126`/`DASH-127` both additionally touch `run_new.html`. This is the same same-file-collision
pattern this repo has flagged before (GW-016/GW-018 in Sprint 14, DASH-116/117/118 in Sprint 24) — the
Tech Lead should sequence these three strictly one-at-a-time within Track A, not attempt to parallelize
them across separate dev-squad workstreams, even though they are logically independent stories. `DASH-124`
(the monitoring bug) and `GW-029` (UAT-005) are confirmed disjoint from Track A and from each other and
can run fully in parallel with Track A and with each other.

## Dependencies (module boundaries, implementation-plan.md sections 2 and 6)

- `VS-029` is a `validation-service` change only (trigger #3, already fired) — no engine change, no new
  computation, matches UAT-001's own acceptance criteria that `libs/naive_first_engine` stays untouched.
- `DASH-125` cannot start before `VS-029` ships the field it reads; this is a real data dependency, not
  just sequencing convenience — flagging explicitly per this role's mandate to state dependency-driven
  ordering rather than silently reorder.
- `DASH-126`/`DASH-127`'s ordering after `DASH-125` and each other is file-sequencing only, not a logical
  dependency — the Tech Lead may re-order DASH-126 and DASH-127 relative to each other if there's a
  reason to, but should not run them concurrently.
- `GW-029` and `DASH-124` have no dependency on anything else in this sprint or on each other.

## Definition of done for this sprint

- All five stories' acceptance criteria (as stated in `docs/product/backlog-uat-findings.md` for
  UAT-001/002/005/011, and as stated in that file's "Confirmed small bug" section for the monitoring fix)
  are checked off.
- Each story's own unit test (per its acceptance criteria) passes; full existing suite re-run with zero
  regressions, same discipline as prior sprints (DASH-119 through DASH-123 precedent).
- `services/validation-service/README.md`, `services/dashboard-web/README.md`, and
  `services/gateway-api/README.md` are updated with each shipped ticket's status/contract change, per
  this repo's standing convention (every ticket/sprint updates READMEs and the ticket index as part of
  the work, not a separate pass).
- `docs/tickets/README.md` gains entries for VS-029, DASH-124, DASH-125, DASH-126, DASH-127, GW-029 with
  dependency and status columns filled in, matching the existing table format.
- `docs/product/backlog-uat-findings.md`'s UAT-001/002/005/011 entries marked done with acceptance-
  criteria boxes checked and a pointer to the shipping ticket(s), matching the DH-item convention from
  Sprint 30.
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after all six tickets are done, before production sign-off — this sprint ships real code touching a
  disclosure-integrity surface (UAT-001/002/011) and a published API contract (GW-029), so QA is required,
  unlike the pure-ADR Sprint 31.

## Next (explicitly not this sprint)

- Should-tier UAT items (UAT-003, UAT-004, UAT-006 through UAT-010) and Could-tier items (UAT-012,
  UAT-013, UAT-014) remain in the backlog, unscheduled, for a future sprint once this Must-tier sweep
  ships and is QA-signed-off.
