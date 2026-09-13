# Sprint 31 — Multimodal dataset fusion, architecture/leakage-posture gate (validation-service / naive_first_engine)

Sprint goal: a written, reviewed decision exists on where multi-source dataset assembly lives, what
each connector type's leakage/lag posture requires, and how timestamp alignment across mixed-
frequency sources must work — with zero fusion/join code written until that decision closes, the same
gate pattern FHS-001 (Sprint 27) and RAV-001 (Sprint 26) already established for this repo.

Backlog source: `docs/product/backlog-multimodal-dataset-fusion.md` (MDF-001 through MDF-005).

## Scope decision: this is a decision-work sprint, not a build sprint

MDF-001 and MDF-004 are explicitly flagged `[Must, blocking]` / `[Must, high scrutiny]` in the
backlog itself, and the backlog's own sequencing note states plainly: "nothing else here should be
estimated or ticketed until [MDF-001] closes." This is the same shape as FHS-001 (Sprint 27) and
RAV-001 (Sprint 26) — **flagging explicitly per the requester's ask: MDF-001's architecture/leakage-
posture questions are significant enough that the Tech Lead should treat MDF-001 as a distinct
blocking gate, not a ticket bundled into the same batch as build work.** Unlike FHS-001 (a UI/contract
design question) or DH's stories (no architecture gate at all), MDF-001/MDF-004 touch
`libs/naive_first_engine` — the platform's core IP — and leakage-safety of a new join surface, which
is a materially higher-risk decision than either prior gate.

**In scope this sprint (2 stories, both decision-work):** MDF-001, MDF-002.
**Explicitly not started this sprint:** MDF-003, MDF-004, MDF-005 (all build/analysis work gated on
MDF-001, and MDF-003/MDF-004 additionally gated on MDF-002).

This sprint's deliverable is two ADRs/README sections, not code. That is intentional — the backlog
states "no fusion or join code is written until [MDF-001] closes," and MDF-002 (alignment design)
depends on MDF-001's component-placement answer. A follow-up sprint (MDF-032 or next available number)
picks up MDF-003→005 once both decisions are written and reviewed.

## Stories in scope, in execution order

1. **MDF-001** — Decide the fusion architecture and leakage posture per connector type [Must,
   blocking]. No dependency. Sequenced first: hard gate, per the backlog's own instruction — nothing
   else in this backlog is estimated or ticketed until this closes.
2. **MDF-002** — Timestamp alignment / frequency-reconciliation design [Must]. Depends on MDF-001 (needs
   its component-placement answer). Sequenced second, within the same sprint since it is also
   decision-work with no code deliverable — the backlog notes MDF-002 "can proceed in parallel with
   early MDF-004 analysis," but MDF-004 itself depends on MDF-003's actual assembled shape (not
   built yet), so no MDF-004 work is meaningfully startable this sprint regardless.

## Stories explicitly deferred

- **MDF-003** (`Must`) — `validation-service` dataset assembly. Depends on MDF-001 and MDF-002, both
  in this sprint. Deferred to the next MDF sprint once both ADRs are written and reviewed — the
  backlog is explicit that no join code is written before MDF-001 closes, and MDF-002's design is
  itself a prerequisite input to how MDF-003 is even ticketed.
- **MDF-004** (`Must, high scrutiny`) — Confirm/extend `naive_first_engine`'s multi-column interfaces.
  Depends on MDF-001 and MDF-003 ("needs to know the actual shape MDF-003 assembles"). Deferred:
  cannot meaningfully start until MDF-003 exists, which is itself deferred out of this sprint.
- **MDF-005** (`Must`) — Positioning/copy discipline for multimodal results. Depends on MDF-003 ("needs
  the run/lineage data to render"). Deferred with MDF-003.

**Why not pull MDF-003 into this sprint as "starts once MDF-001 lands mid-sprint":** MDF-002 gates
MDF-003 too (alignment design is a prerequisite to correctly ticketing dataset assembly, not an
optional nice-to-have), and MDF-002 itself can't start until MDF-001's placement decision is known.
Sequencing two blocking decisions and then a Must-priority, multi-file build story in the same sprint
window risks exactly the "half-decided architecture, already mid-build" outcome the FHS-001/RAV-001
pattern exists to prevent. If the requester wants a tighter timeline, the Tech Lead can still begin
MDF-003 ticket-breakdown (not implementation) once MDF-001 alone closes, since the backlog scopes
MDF-002 as "proceed in parallel," but implementation code should not start until both decisions are
written and reviewed.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

MDF-001's decision determines whether this work is an extension of `validation-service` (trigger #3,
already fired) or new scope requiring a fresh module — the implementation-plan's trigger table has no
existing line item for "combine N datasets into one aligned input" (backlog finding #5), so MDF-001's
ADR must explicitly address whether this is a trigger-table gap being filled under an existing
service's scope, or a pull-forward against an un-fired trigger requiring the same ADR-0003-style
disclosure already used for prior ingestion-connector pull-forwards. **The Tech Lead's MDF-001 ticket
should treat "does this need a new module" as a real, open question, not a foregone conclusion** —
the backlog's own recommendation (extend `validation-service`) is a recommendation, not yet a decision.
MDF-002's alignment design must confirm the purge-gap protocol still runs on the combined-data risk
window (splitting happens strictly after alignment, never before) — this is the single point in this
sprint most directly tied to CLAUDE.md's leakage-avoidance rule and the reason MDF-004 (not this
sprint) is flagged high-scrutiny in the backlog: any resulting interface addition to
`libs/naive_first_engine` is the platform's core IP.

## File-overlap / concurrent-work risk

- Both stories are pure decision-work (ADR / dated README section) — no source files under
  `services/validation-service/src/`, `libs/naive_first_engine/src/`, or `services/dashboard-web/src/`
  are touched this sprint. No file-overlap risk with Sprint 30's in-flight DH-001/002/003/005/008 work
  (different module: `validation-service`'s `dataset_source.py`/`runs.py` vs. this sprint's
  ADR-only deliverable) or with any other currently uncommitted work shown in `git status`
  (dashboard-web crawl-cancellation/progress changes are untouched by this sprint).
- The likely output location — `services/validation-service/README.md` (per the backlog's stated
  preference, "matching this repo's existing pattern for scope decisions") or a new
  `docs/adr/000N-*.md` file — should be confirmed by the Tech Lead before drafting; either is
  consistent with this repo's precedent (ADR-0006, ADR-0007 both used the `docs/adr/` path recently
  for comparable scope/unit decisions).

## Definition of done for this sprint

- MDF-001: written decision states (a) where the join happens and whether that pulls a component
  forward against an un-fired trigger, with ADR-0003-style disclosure if so; (b) per-connector-type
  (price, on-chain, sentiment) documented publication/confirmation lag, revision risk, and resulting
  minimum safe purge-gap/alignment rule; (c) an explicit confirm-or-correct of whether
  `CompositeDatasetSource` already supports multi-field composition or is single-field-with-fallback
  only.
- MDF-002: design doc states, per source-pair, the resampling/alignment rule (never interpolating
  using a future-dated value); the missing-timestamp policy as a required per-run config choice, not
  a silent default; which source's clock is authoritative for the final aligned index and confirmation
  that this index feeds `generate_splits` unchanged, strictly before splitting; at least one worked
  example combining real data from two of the three existing connectors.
- Neither story touches `libs/naive_first_engine`, `services/validation-service/src/`, or any other
  source tree — verified via `git status` scoped to those paths before and after, same discipline
  prior sprints hold to.
- `docs/product/backlog-multimodal-dataset-fusion.md`'s MDF-001/002 entries marked done with
  acceptance-criteria boxes checked; MDF-003/004/005 left unchanged, noted here as "next," explicitly
  not startable as implementation until both ADRs are written and reviewed.

## Next (explicitly not this sprint)

- **MDF-003** — `validation-service` dataset assembly (build work), once MDF-001 and MDF-002 both
  close and are reviewed.
- **MDF-004** — `naive_first_engine` multi-column interface confirmation/extension (high-scrutiny,
  extra reviewer pass required per the backlog), once MDF-003's assembled shape is known.
- **MDF-005** — positioning/copy discipline for multimodal results, once MDF-003 defines the lineage
  data it renders.

## Outcome

Both ADRs reviewed by the Tech Lead and accepted as-is — no deficiency found against the DoD, no ADR
edits required.

- **MDF-001** (`docs/adr/0008-multimodal-fusion-architecture-and-leakage-posture.md`, `status: accepted`):
  states the join lives inside `services/validation-service` as a new `feature_dataset.py` module
  (sibling to `dataset_source.py`), with an explicit finding that this is *not* a pull-forward against
  an un-fired trigger (trigger #3 already fired) and no ADR-0003-style disclosure is required; documents
  per-connector-type (`BinancePriceConnector`/`BlockchainInfoConnector`/`RedditSentimentConnector`)
  publication/confirmation lag, revision risk, and minimum safe purge-gap/alignment rule in a table; and
  confirms (not corrects) that `CompositeDatasetSource` is single-reference-with-mode-dispatch only, not
  multi-field composition, read directly against `dataset_source.py`.
- **MDF-002** (`docs/adr/0009-multimodal-timestamp-alignment-design.md`, `status: accepted`): states a
  per-source-pair resampling/alignment rule keyed off each source's `fetched_at` (never a nominal
  timestamp, never a future-dated value); a required `missing_timestamp_policy` field with no silent
  default (`422` if omitted); confirms the target series' own index is authoritative and is fed to
  `generate_splits` unchanged, strictly before splitting (`splitting.py` requires no change); and
  includes a worked example combining real `binance_price_btcusdt_1h` and `blockchain_info_hash-rate`
  data over a four-hour window under `"drop_row"`.
- **No source touched.** `git status` was clean at review time and `git show fc7b7c0 --stat` confirms
  commit `fc7b7c0` ("Sprint 31 (in progress): MDF-001/002 fusion architecture and alignment ADRs
  drafted") changed exactly three files — the two ADRs and this sprint plan — zero lines under
  `libs/naive_first_engine`, `services/validation-service/src/`, or any other source tree.
- `docs/product/backlog-multimodal-dataset-fusion.md`'s MDF-001/002 entries are now marked
  "Status: Done (Sprint 31)" with acceptance-criteria boxes checked and a pointer to where each is
  satisfied in ADR-0008/0009 (matching the DH-item convention from Sprint 30). MDF-003 is now annotated
  "unblocked, next" — both of its blocking dependencies are closed. MDF-004/005 left unchanged.
- QA was not raised for this sprint: it is pure decision-work (two ADRs, no code, no leakage-sensitive
  logic executed, no lifecycle/state-machine change, nothing rendering a number to an end user) — the
  QA gate applies to shipped code, and none shipped this sprint. The next sprint that implements MDF-003
  (real join code against a leakage-sensitive surface) will require QA before sign-off.
- **Next**: MDF-003 (`validation-service` dataset assembly) is the priority story for the following MDF
  sprint, to be ticketed by the Tech Lead per ADR-0008's authorized location/shape once that sprint is
  planned.
