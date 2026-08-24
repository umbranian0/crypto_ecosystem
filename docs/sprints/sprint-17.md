# Sprint 17 — Hardening wave: eight disclosed-override pull-forwards across `gateway-api`, `infra`, cross-cutting operability, and `validation-service`

Sprint goal: the eight Should/Could items the 2026-08-24 hardening-wave review pulled forward under
the disclosed-override pattern (`docs/adr/0003-disclosed-trigger-override-pattern.md`) all land —
`gateway-api` gains key revocation, structured auth-event audit logging, and a Locust load-test
suite; `infra` gains a MinIO container and TimescaleDB hypertables on `split_results`; the platform
adopts a cross-service structured-logging/correlation-id convention; and `validation-service` gains a
real object-storage `DatasetSource` adapter and a client-supplied-prediction `Baseline` Strategy —
without silently reordering or dropping the review's own named care conditions.

Backlog source: `docs/product/backlog-hardening-wave-review.md` (decision record) plus each item's
own home file, read directly for its `Depends on:` line, acceptance criteria, and "Explicit trigger
override (2026-08-24)" note: `docs/product/backlog-gateway-api.md` (`GW-010`, `GW-014`, `GW-017`),
`docs/product/backlog-infra.md` (`INF-008`, `INF-010`), `docs/product/backlog-operability.md`
(`OPS-006`), `docs/product/backlog-validation-service.md` (`VS-015`, `VS-017`).

## Pre-planning checks performed (stated explicitly, not assumed)

- `docs/sprints/` directory listing confirms files through `sprint-16.md` only, and `sprint-16.md`'s
  own text records that its number was already reassigned once due to a shared-scratchpad
  filename collision with a parallel PM task (`sprint-15.md` went to `DASH-005` instead). This sprint
  is therefore sequenced as **Sprint 17**. Per that same file's own lesson, this sprint's draft
  content was composed directly against a uniquely-named scratchpad file, not a shared/generic name,
  to avoid repeating that collision.
- Each of the eight items' own `Depends on:` line (or equivalent "Depends on" text) read directly
  from its home backlog file, not inferred from priority or the review document's summary table:
  - `GW-010`: "Depends on: GW-006." Done (Sprint 05).
  - `GW-014`: "Depends on: GW-006, OPS-006." `GW-006` done (Sprint 05); `OPS-006` is in this sprint —
    `GW-014` cannot start until `OPS-006` lands, exactly the cross-item dependency the requester
    flagged.
  - `GW-017`: "Depends on: GW-008, GW-009." Both done (Sprint 05).
  - `INF-008`: "Depends on: none."
  - `INF-010`: "Depends on: INF-005." Done (Sprint 06).
  - `OPS-006`: "Depends on: none."
  - `VS-015`: "Depends on: VS-005." Done (Sprint 03).
  - `VS-017`: "Depends on: VS-006." Done (Sprint 03).
- `docs/implementation-plan.md` sections 2 and 6 re-read: all four touched modules
  (`gateway-api`, `infra`, `validation-service`, plus cross-cutting operability) already have their
  respective triggers fired (trigger #3 `validation-service`, #4 `infra`, #5 `gateway-api`) or are
  themselves the subject of this wave's own disclosed override — no story here scaffolds a new
  module or crosses an unfired trigger boundary; every story extends an already-built module.
- **Additional cross-item dependency found, beyond the one the requester named** (`OPS-006` →
  `GW-014`): `GW-014`'s own acceptance criteria require logging "key issuance, revocation, and
  failed-auth attempts." Key issuance already has a real code path (`GW-005`'s
  `scripts/provision_tenant.py`) and failed-auth already has one (`GW-006`'s
  `dependencies/auth.py`) — both done, both instrumentable today. **Revocation does not** — no
  revocation code path exists anywhere in `gateway-api` yet; that path is exactly what `GW-010`
  builds this sprint. `GW-014`'s own `Depends on:` line does not list `GW-010`, but its acceptance
  criteria cannot be satisfied without `GW-010`'s revocation path existing to instrument. This is
  called out explicitly rather than silently reordered around: **`GW-014` is also practically blocked
  on `GW-010`, not only on `OPS-006`.**
- File-collision check performed directly against each story's likely file targets, reading each
  item's own acceptance criteria (mirroring this repo's `GW-016`/`GW-018` precedent, Sprint 14):
  - `GW-010` and `GW-014` both touch `gateway-api`. `GW-010`'s own care condition names an
    operator-only path "mirroring GW-005's... framing" — i.e. most likely a standalone CLI script
    (like `scripts/provision_tenant.py`), not a new router, though its acceptance criteria also allow
    an operator-gated endpoint; either way it is a new file or a narrow addition, not an edit to
    `dependencies/auth.py`. `GW-014` needs to instrument three call sites: `GW-005`'s existing script,
    `GW-006`'s existing `dependencies/auth.py`, and `GW-010`'s new revocation path — meaning `GW-014`
    will edit a file `GW-010` creates. **Real risk, not hypothetical**: do not delegate `GW-010` and
    `GW-014` to concurrent dev agents; `GW-010` must complete and be verified before `GW-014` starts,
    independent of the formal-dependency question above.
  - `OPS-006` touches both services' entry points (`main.py` middleware/correlation-id wiring in each
    of `gateway-api` and `validation-service`, plus `validation-service`'s `events.py` for the one
    existing log call) — a strict precondition for `GW-014`'s own logging convention. Given `GW-014`
    also needs to touch `gateway-api`'s auth/routing layer, **`OPS-006` is sequenced strictly before
    `GW-014`, not merely "alongside" it** as the review's own softer wording allowed — the stricter
    reading is chosen here specifically because of the same-service file-collision risk with `GW-010`
    and `GW-014`, not because the review's guidance was wrong.
  - `GW-017` (new `loadtest/` directory only) and `VS-017` (`validation-service`'s `runs.py` + a new
    `Baseline`-Strategy wrapper file) have no file overlap with anything else in this sprint —
    confirmed safe to parallelize from the start.
  - `INF-008` (`infra/docker-compose.yml` only) and `INF-010` (a `validation-service`-side migration
    converting `split_results` to a hypertable, distinct from `INF-008`'s compose-file edit) do not
    share a file — confirmed safe to parallelize with each other and with `OPS-006`/`GW-017`/`VS-017`.
  - `VS-015` (`validation-service`'s `dataset_source.py` + a new adapter class) does not share a file
    with `VS-017` (`runs.py` + a new wrapper class) or `OPS-006` (`main.py`/`events.py`) — confirmed
    safe to parallelize with both on file grounds.
- **Practical (not formal) dependency found**: `VS-015`'s own care condition says it makes the
  read-side *adapter* real without claiming a populated processed zone exists. To test that adapter
  against something resembling the real target (rather than only a mocked S3-compatible client), a
  running MinIO instance is the natural target — the same "build against the real thing once it
  exists" discipline this repo already applied to `VS-013` against real Postgres (Sprint 06) and to
  `GW-018` against `INF-018`'s Compose wiring (Sprint 14). `VS-015`'s own `Depends on:` line names
  only `VS-005`, so this is **not** a formal blocker — `VS-015` can be built and unit-tested (mocked
  client) without `INF-008`. It is nonetheless sequenced after `INF-008` in this plan so its
  realistic/integration-level testing has a real target to run against, mirroring the `GW-018`/
  `INF-018` precedent's own "practically wants, doesn't strictly require" framing.
- No team size/velocity given. Sized against precedent: eight stories across four modules, one real
  two-hop dependency chain (`OPS-006` → `GW-010` → `GW-014`) plus five genuinely independent stories —
  closer in shape to Sprint 06's cross-module debt sprint than to a single-module sprint; kept as one
  combined sprint (see reasoning below) rather than split by module.

## Why one combined sprint, not several parallel-module sprints

Considered splitting this into up to four module-scoped sprints (`gateway-api`, `infra`,
cross-cutting operability, `validation-service`), mirroring how this repo has sometimes run
single-module sprints (Sprint 03, Sprint 05). **Decision: one combined sprint**, for three reasons
specific to this batch, not as a default posture:

1. The review itself named a real cross-module dependency (`OPS-006` → `GW-014`) and this planning
   pass found a second one (`GW-010` → `GW-014`, practical) — splitting `gateway-api` and
   cross-cutting operability into separate sprints would either force `gateway-api`'s sprint to stall
   mid-sprint waiting on a different sprint's output, or require an artificial ordering between two
   sprint files that a single sprint's own Round structure expresses more directly.
2. Five of the eight stories are mutually independent by file and by dependency — this is the same
   shape Sprint 06 used (a debt sprint bundling independent module-level cleanup across
   `gateway-api`/`infra`/`libs` in one file, sequenced internally by round, not by separate sprint
   files per module).
3. The batch is a single, already-reviewed decision (`backlog-hardening-wave-review.md`) rather than
   several independently-prioritized backlog passes — keeping it as one sprint file keeps the
   review's own cross-item reasoning (the care conditions, the OPS-006/GW-014 note) attached to one
   place the Tech Lead reads once, matching this role's own "handoff without re-reading everything"
   goal.

The one place this sprint still enforces real separation is *within* execution: `gateway-api`'s three
stories are not run concurrently with each other where file risk exists (`GW-010`/`GW-014`), matching
Sprint 14's `GW-016`/`GW-018` precedent of serializing same-service, same-file-risk stories inside one
sprint rather than assuming a single sprint means unconstrained parallelism.

## Sequencing decision (stated explicitly, dependency-first, not by priority)

A naive priority-first read would put `INF-008`/`VS-015` (Should) and `GW-014` (Could) all at
whatever order their own labels suggest without regard to the chain above. That would be wrong for
`GW-014` specifically: **`GW-014` is Could-priority but is hard-sequenced last** because it is
formally blocked on `OPS-006` (Could) and practically blocked on `GW-010` (Should) — a lower- or
equal-priority label does not exempt a story from the dependency it actually has. No other story in
this batch has its priority-order silently overridden.

1. **Round 1 (parallel — five stories, confirmed independent of each other and of everything later in
   this sprint by both `Depends on:` line and file-overlap check)**:
   `INF-008` [Should, `infra`], `INF-010` [Could, `infra`], `OPS-006` [Could, cross-cutting —
   `gateway-api` + `validation-service`], `GW-017` [Should, `gateway-api`], `VS-017` [Could,
   `validation-service`].
2. **Round 2 (parallel — two stories, each depends only on Round 1 output or earlier-done work)**:
   `VS-015` [Should, `validation-service`] — practically wants `INF-008`'s MinIO container for
   realistic adapter testing (not a formal blocker, sequenced here anyway). `GW-010` [Should,
   `gateway-api`] — formally independent of `OPS-006`, but sequenced after Round 1 to avoid a
   concurrent edit inside `gateway-api` while `OPS-006`'s own `gateway-api`-side middleware change is
   still landing, and because `GW-014` (Round 3) needs both `OPS-006` and `GW-010` done before it can
   even start.
3. **Round 3 (solo)**: `GW-014` [Could, `gateway-api`] — the last story to run, blocked on `OPS-006`
   (formal) and `GW-010` (practical, both this sprint), and given exclusive access to `gateway-api`'s
   auth/routing files rather than run alongside any other `gateway-api` story.

Net order: Round 1 (`INF-008`, `INF-010`, `OPS-006`, `GW-017`, `VS-017` in parallel) → Round 2
(`VS-015`, `GW-010` in parallel) → Round 3 (`GW-014` solo).

## Stories in scope, in execution order

1. `INF-008` [Should, `infra`] — `minio` service in `infra/docker-compose.yml`. Depends on: none.
   Round 1.
2. `INF-010` [Could, `infra`] — `split_results` converted to a TimescaleDB hypertable. Depends on:
   `INF-005` (done). Round 1.
3. `OPS-006` [Could, cross-cutting] — structured logging + request/tenant-correlation id adopted as
   the platform-wide convention in both `gateway-api` and `validation-service`. Depends on: none.
   Round 1. **Precondition for `GW-014` (Round 3).**
4. `GW-017` [Should, `gateway-api`] — Locust load-test suite against key endpoints. Depends on:
   `GW-008`, `GW-009` (done). Round 1.
5. `VS-017` [Could, `validation-service`] — client-supplied prediction column as a `Baseline`-interface
   Strategy, plus the review's added acceptance criterion on comparison-vs-provenance framing.
   Depends on: `VS-006` (done). Round 1.
6. `VS-015` [Should, `validation-service`] — object-storage-backed `DatasetSource` implementation.
   Depends on: `VS-005` (done). Round 2 — practically wants `INF-008` (Round 1) landed for realistic
   testing, not a formal blocker.
7. `GW-010` [Should, `gateway-api`] — API-key revocation, operator-only path. Depends on: `GW-006`
   (done). Round 2 — sequenced after Round 1 to avoid concurrent `gateway-api` edits alongside
   `OPS-006`, and because `GW-014` needs this story's own revocation path to exist first.
8. `GW-014` [Could, `gateway-api`] — auth event audit logging, built on `OPS-006`'s convention.
   Depends on: `GW-006` (done), `OPS-006` (this sprint, Round 1) — plus the practical dependency on
   `GW-010` (this sprint, Round 2) found during this planning pass. Round 3, solo.

## Stories explicitly deferred

Per the review's own Category-2 holds — not reconsidered or reopened here, carried forward unchanged
from `docs/product/backlog-hardening-wave-review.md`:

- `GW-011` (JWT-based session auth) — Hold. No real consumer chose it (`dashboard-web`'s `DASH-002`
  already chose GW-006's API-key mechanism, and its own Won't-list `DASH-107` declines JWT). Revisit
  at `libs/sdk` (trigger #9) or a real browser-session use case.
- `GW-013` (Rate limiting / abuse protection) — Hold. No real traffic shape exists to calibrate
  thresholds against; revisit after `GW-017` (in scope this sprint) produces real request-pattern
  data — explicitly **not** scheduled in the same sprint as `GW-017`, per the review's own note.
- `ARCH-005` (remaining half: `LC-009` signed/verified internal tenant-header propagation) — Hold on
  full implementation. Current exposure is already network-mitigated (`validation-service` bound to
  `127.0.0.1` only, not internet-facing). A design-spike-only alternative was named as an option by
  the review but not requested by the requester here, so it is not scheduled in this sprint either.

## Definition of done for this sprint

- Every acceptance-criteria checkbox in `GW-010`, `GW-014`, `GW-017`, `INF-008`, `INF-010`, `OPS-006`,
  `VS-015`, `VS-017`'s backlog entries is checked, not left implicitly assumed satisfied.
- Each story's own **care condition**, carried forward from the review, is verifiably true in the
  shipped result, not merely stated as intent (see Handoff section below for the full list, restated
  per item so the Tech Lead does not have to re-derive them from the review document).
- `GW-010` and `GW-014` are never delegated to concurrent dev agents; `GW-010`'s diff is verified
  complete before `GW-014` starts, mirroring Sprint 14's `GW-016`/`GW-018` precedent.
- `OPS-006` lands (and is verified) before `GW-014` starts — not merely "alongside" — given the
  file-collision risk identified above.
- `uv run pytest` (or each service's documented workaround for this repo's OneDrive-sync issue)
  passes with zero regressions in `gateway-api` and `validation-service`; `INF-008`/`INF-010` are
  verified against the real, live Compose stack, not by config review alone.
- `services/gateway-api/README.md`, `services/validation-service/README.md`, and `infra/README.md`
  are each updated to reflect their respective new stories, consistent with this repo's own
  "READMEs stay current" convention.
- `docs/tickets/README.md` gains all eight tickets under their respective existing module sections.
- No story in this sprint builds anything from the explicitly-deferred list above (`GW-011`, `GW-013`,
  `ARCH-005`'s `LC-009` half) — this sprint does not reopen or start any of them.

## Handoff to Tech Lead

- **Sprint file**: `docs/sprints/sprint-17.md`
- **Sprint goal**: land all eight hardening-wave pull-forward items across `gateway-api`, `infra`,
  cross-cutting operability, and `validation-service` — API-key revocation, structured auth-event
  audit logging, a Locust load-test suite, MinIO in Compose, TimescaleDB hypertables, a
  platform-wide structured-logging/correlation-id convention, an object-storage `DatasetSource`
  adapter, and a client-supplied-prediction `Baseline` Strategy — while preserving every care
  condition the review attached to each item.
- **Ordered story list**:
  1. `INF-008` [Should] — MinIO in Compose. No dependency. Round 1.
  2. `INF-010` [Could] — `split_results` hypertable. Depends on `INF-005` (done). Round 1.
  3. `OPS-006` [Could] — structured logging + correlation id, both services. No dependency. Round 1.
     Precondition for `GW-014`.
  4. `GW-017` [Should] — Locust suite. Depends on `GW-008`/`GW-009` (done). Round 1.
  5. `VS-017` [Could] — client-supplied prediction `Baseline` Strategy. Depends on `VS-006` (done).
     Round 1.
  6. `VS-015` [Should] — object-storage `DatasetSource`. Depends on `VS-005` (done); practically wants
     `INF-008`. Round 2.
  7. `GW-010` [Should] — API-key revocation. Depends on `GW-006` (done). Round 2.
  8. `GW-014` [Could] — auth event audit logging. Depends on `GW-006` (done), `OPS-006` (this sprint).
     Practically also depends on `GW-010` (this sprint) — its own acceptance criteria require logging
     revocation events, and no revocation code path exists until `GW-010` builds one. Round 3, solo.
- **Dependency/risk notes**:
  - `GW-014`'s formally-stated dependency (`OPS-006`) and this planning pass's own additionally-found
    practical dependency (`GW-010`) both must be satisfied before `GW-014` starts. Do not schedule
    `GW-014` in parallel with either.
  - `GW-010` and `GW-014` both touch `gateway-api` and carry real same-service file-collision risk
    (`GW-014` needs to instrument whatever file `GW-010` creates for the revocation path) — do not
    delegate to concurrent dev agents, same category of risk this repo already flagged for
    `GW-016`/`GW-018` in Sprint 14.
  - `OPS-006` also touches `gateway-api`'s entry-point/middleware files — sequenced strictly before
    `GW-014` (not merely "alongside," which the review's own wording would have allowed) specifically
    because of this file-collision risk, not because the review's softer phrasing was wrong.
  - `GW-013` (rate limiting) is explicitly deferred and should not be scheduled in this same sprint as
    `GW-017` even though `GW-017` is in scope — the review's own reasoning is that `GW-013` should
    follow `GW-017`'s *first real output* (a future sprint decision), not run concurrently with it.
  - This sprint's eight tickets are all traceable to `docs/product/backlog-hardening-wave-review.md`
    — cite that document (not just each item's own backlog entry) if any acceptance criterion's
    rationale needs re-deriving mid-sprint.

### Care conditions carried forward from the review — restated per item, non-optional

1. **`GW-010`** (API-key revocation): operator-only path (CLI script or operator-gated endpoint,
   mirroring `GW-005`'s "not a public sign-up flow" framing) — never a tenant self-service revocation
   endpoint. No caching layer on the revocation check that could reintroduce a window where a revoked
   key stays valid.
2. **`GW-014`** (auth event audit logging): build directly on `OPS-006`'s structured-logging
   convention rather than inventing a second, parallel logging shape. No raw keys/secrets in any log
   line. Do not stand up log retention/shipping to any external system — stays "structured local log
   line," not a compliance-grade retained audit trail, until a real auditor/compliance conversation
   defines retention requirements.
3. **`GW-017`** (Locust load-test suite): no additional care beyond its own existing acceptance
   criteria — the review found none needed. Keep the "not a pass/fail gate" framing (no hard SLA
   asserted or gated on).
4. **`INF-008`** (MinIO in Compose): apply the same `127.0.0.1`-only host port binding already used
   for `postgres`/`redis`/`validation-service` — do not reopen the port-exposure gap the platform
   already closed elsewhere. State plainly in `infra/README.md` that no service currently reads or
   writes to it yet.
5. **`INF-010`** (TimescaleDB hypertables): scope narrowly to the conversion itself, proven not to
   break existing query behavior — do not build any new time-series query surface, since no real
   caller for one exists yet even with `dashboard-web`'s trigger #8 fired.
6. **`OPS-006`** (structured logging + correlation id): does not stand up a log-aggregation backend
   (that remains `OPS-007`'s own still-declined scope) — this story's scope ends at "logs are
   structured and correlatable," not "logs are centrally searchable." It is the precondition `GW-014`
   builds on — must land (and be verified) before `GW-014` starts.
7. **`VS-015`** (object-storage `DatasetSource`): pulling this forward makes the read-side *adapter*
   real; it must not be presented or documented as meaning a real, tenant-scoped
   `processed/{tenant_id}/...` zone is actually populated with real pilot data — that still depends on
   `ingestion-service` actually writing there, a separate, not-yet-confirmed fact. State this
   distinction explicitly in `services/validation-service/README.md`'s own update for this story,
   mirroring `INF-008`'s own "no real consumer yet" discipline.
8. **`VS-017`** (client-supplied prediction `Baseline` Strategy): the naive baselines remain
   structurally mandatory (never optional or skippable, per `VS-019`'s Won't); no arbitrary client
   code execution is introduced (per `VS-018`'s Won't); and — the review's own added acceptance
   criterion — any report/response surface built on top of a client-supplied prediction run must state
   explicitly that the platform validates the *comparison* (client series vs. naive baselines,
   honestly computed), not the *provenance* of the client's predictions. Do not let "beat Naive0 in
   this audit" be presented or read as "this platform certifies your model didn't leak."
