# Sprint 36 — `validation-service` multi-source dataset assembly (MDF-003)

Sprint goal: a tenant can submit a `POST /runs` request that references multiple `{source, field}`
feature inputs and get back a run whose candidate-model input is a leakage-safe, per-ADR-0008/0009-
aligned multi-column feature table, while the naive-first baselines and target series remain exactly
as they are today.

Backlog source: `docs/product/backlog-multimodal-dataset-fusion.md` (MDF-003).

## Scope decision: single story, both blockers already closed

MDF-001 and MDF-002 are both **Done (Sprint 31)** — see `docs/adr/0008-multimodal-fusion-architecture-
and-leakage-posture.md` and `docs/adr/0009-multimodal-timestamp-alignment-design.md`, both `status:
accepted`. MDF-003 is therefore unblocked and is the only story in this sprint.

**In scope this sprint (1 story):** MDF-003 — `validation-service` dataset assembly for a multi-source
feature set [Must].

**Explicitly out of scope this sprint:** MDF-004 (naive_first_engine multi-column interface
confirmation) and MDF-005 (positioning/copy discipline for multimodal results). Both depend on MDF-003's
*actual assembled shape*, which does not exist until this sprint ships — the backlog's own dependency
chain (MDF-004 "needs to know the actual shape MDF-003 assembles"; MDF-005 "needs the run/lineage data
to render") and Sprint 31's own "Next" section both state this explicitly. Do not pull either into this
sprint's ticket breakdown.

## Stories in scope, in execution order

1. **MDF-003** — `validation-service` dataset assembly for a multi-source feature set [Must]. No
   dependency within this sprint (MDF-001/MDF-002 already closed in Sprint 31). Sole story this sprint.

## Stories explicitly deferred

- **MDF-004** (`Must, high scrutiny`) — Confirm/extend `naive_first_engine`'s multi-column interfaces.
  Depends on MDF-003's actual assembled shape (this sprint). Deferred to the sprint after this one, once
  MDF-003 ships and its shape is known. Flagged in the backlog as high-scrutiny, requiring an explicit
  extra reviewer pass focused on leakage safety since it may touch `libs/naive_first_engine` — the
  platform's core IP — the Tech Lead should not fold this into MDF-003's ticket even if the shape
  question comes up mid-implementation.
- **MDF-005** (`Must`) — Positioning/copy discipline for multimodal validation results. Depends on
  MDF-003's lineage data (this sprint). Deferred with MDF-004 to the following sprint.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6, and the
two accepted ADRs)

- MDF-003 must be built **exactly per ADR-0008 and ADR-0009's accepted decisions**, not re-derived:
  - The join lives inside `services/validation-service`, as a new `feature_dataset.py` module,
    sibling to the existing `dataset_source.py` — not a new service, not inside
    `CompositeDatasetSource` itself (confirmed single-reference-with-mode-dispatch only).
  - Alignment is per-source-pair, keyed off each source's `fetched_at` (never a nominal timestamp,
    never a future-dated value) — price-onto-price (zero additional lag), on-chain-onto-target
    (24h conservative floor), sentiment-onto-target (fetched_at substitution, no separate buffer).
  - `missing_timestamp_policy` is a **required** request field (`"drop_row"` /
    `"forward_fill_exhausted_as_null_then_drop"` / `"exclude_source"`) with **no default** — a request
    with feature references and no policy is rejected `422`. This is a hard acceptance-criterion, not a
    nice-to-have; do not let implementation slip toward a silent default.
  - The target series' own `DatetimeIndex` is authoritative and is what `generate_splits` receives,
    unchanged, strictly *after* alignment completes and *before* any split boundary is chosen. Alignment
    must never run after a split boundary is chosen — this is the single leakage-critical ordering
    constraint in this sprint.
  - `libs/naive_first_engine` (`Baseline` protocol, `dm_test.py`, `splitting.py`) is not to be modified
    by this story — both ADRs confirm no change is needed, and any change discovered to be needed belongs
    to MDF-004, not this sprint.
- This work sits adjacent to `libs/naive_first_engine`'s core IP (the platform's leakage-free validation
  claim) even though it does not modify that library directly — the per-fold preprocessing-fit
  verification and the alignment-before-splitting ordering are the two places this sprint's correctness
  is load-bearing for CLAUDE.md's non-negotiable leakage rule.

## Hard gates for this sprint (non-negotiable, per CLAUDE.md and this project's standing rules)

- **Per-fold, not global, preprocessing-fit verification is a hard gate.** Any scaling/imputation
  applied to feature columns must be fit on the training fold only, per split — matching MDF-003's own
  acceptance criteria ("verified by a test that a fold's fitted preprocessing parameters differ from
  another fold's and that no global fit path exists"). This is not satisfied by a passing test suite
  alone if that test doesn't specifically assert per-fold divergence and absence of a global-fit path.
- **QA sign-off (`qa` agent / `/qa-validation`) is mandatory before this sprint's story is considered
  done**, per this project's standing QA-gate rule (Sprint 30's precedent, and Sprint 31's own note that
  "the next sprint that implements MDF-003 — real join code against a leakage-sensitive surface — will
  require QA before sign-off"). The Tech Lead must raise QA after ticket(s) are implemented, before
  production sign-off — do not skip this the way Sprint 31 (correctly) did for its decision-only scope.

## Ticket assignment

- **VS-030** — `validation-service` dataset assembly for a multi-source feature set (MDF-003). Next free
  `VS-*` ticket number, confirmed against `docs/tickets/README.md` (last shipped: VS-029, Sprint 35;
  nothing newer landed since). No ticket-level dependencies — both blocking backlog stories (MDF-001,
  MDF-002) are already closed. The Tech Lead owns further ticket breakdown (e.g. whether VS-030 splits
  into sub-tickets for the request-shape change, the `feature_dataset.py` module, lineage persistence,
  and the preprocessing-fit test) — this sprint plan assigns the top-level ticket only.

## Definition of done for this sprint

- VS-030 implements all of MDF-003's acceptance criteria exactly as stated in
  `docs/product/backlog-multimodal-dataset-fusion.md` (search "### MDF-003"): multi-`{source,field}`
  request support with the target remaining exactly one return series; assembled multi-column feature
  table feeds only the candidate model's inference path, `Naive0`/`NaiveLast` unchanged; per-fold-only
  preprocessing fit, verified by a specific test per above; persisted dataset lineage distinguishing a
  multi-source run from a single-series run; fail-closed rejection of a run referencing a still-mid-crawl
  or data-quality-flagged source.
- Implementation matches ADR-0008 and ADR-0009's decisions exactly — no re-litigating component
  placement, alignment rule, or missing-timestamp-policy defaulting.
- `libs/naive_first_engine` is untouched — verified via `git status`/`git diff` scoped to that tree,
  same discipline Sprint 31 held to for the ADR-only work.
- QA sign-off obtained (`qa` agent) before this story is marked done in the ticket index.
- `docs/tickets/README.md` and `services/validation-service/README.md` updated to reflect VS-030's
  status/contract, and `docs/product/backlog-multimodal-dataset-fusion.md`'s MDF-003 entry marked done
  with acceptance-criteria boxes checked, pointing at VS-030.

## Next (explicitly not this sprint)

- **MDF-004** — `naive_first_engine` multi-column interface confirmation/extension [Must, high
  scrutiny], once MDF-003/VS-030's actual assembled shape is known and shipped.
- **MDF-005** — positioning/copy discipline for multimodal validation results [Must], once MDF-003/
  VS-030 defines the lineage data it renders.
