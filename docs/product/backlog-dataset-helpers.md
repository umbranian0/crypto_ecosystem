# Backlog — dataset repair helpers and horizon/parameter suggestion helpers

Source: `CLAUDE.md` (root — non-negotiable positioning: this is validation/audit infrastructure,
never a prediction/trading-signal product; nothing below computes or implies an "optimal" horizon
or any accuracy/profitability claim), `docs/implementation-plan.md` (module boundary map, section 2;
trigger table, section 6 — both `ingestion-service` and `validation-service`/`dashboard-web` have
already fired, so every story here is ordinary roadmap work on an existing module, not a new
trigger override), `docs/product/backlog-run-submission-safety.md` (RSS-001–005, read in full — the
live client-side split estimate and the server-side `MAX_SPLIT_COUNT=500` upper-bound guardrail
already ship; no story here re-derives that formula or duplicates that UI surface),
`docs/product/backlog-first-run-setup-and-ops.md` (SETUP-015, read for cross-reference — a read-only
Settings panel for service config, a different kind of "helper" than what's proposed here, no overlap),
`libs/naive_first_engine/src/naive_first_engine/splitting.py` (`generate_splits`, both branches, read
in full), `services/validation-service/src/app/dataset_source.py` (`InlineOrLocalFileDatasetSource`,
`ObjectStorageDatasetSource`, `IngestionServiceDatasetSource`, `CompositeDatasetSource`, read in
full), `services/validation-service/src/app/routers/runs.py` (`create_run`, read in full — confirms
exactly what RSS-004's guardrail does and does not check), `services/ingestion-service/src/app/routers/datasets.py`
and `src/app/repositories/postgres_repository.py` (`read_series`, `_TABLE_SPECS`, read in full — confirms
what's enforced at the DB layer vs. left to the caller), `services/dashboard-web/src/app/templates/run_new.html`
(the shipped `computeEstimatedSplits()` client-side estimator, read in full).

## What's actually already true in the code (read, not assumed)

This backlog exists to add *new* helpers on top of what's already there — so the first job is being
honest about the current baseline, since several things a naive reading of the user's request might
assume are "missing" already exist, and one real gap exists that neither `RSS-004` nor anything else
currently catches:

1. **Stored (ingestion-service) datasets already can't have exact-duplicate-timestamp rows.**
   `price_ohlcv`/`onchain_metric`/`sentiment_score` are keyed on `(tenant_id, source, event_time)`
   (`INGEST-002`, cited in `postgres_repository.py`'s own module docstring) — this is a DB-enforced
   invariant, not something a new "repair" feature needs to detect for that path. Duplicate-timestamp
   risk is real only for `validation-service`'s **other two** `DatasetSource` implementations
   (`InlineOrLocalFileDatasetSource`'s local-file/inline modes, and `ObjectStorageDatasetSource`),
   which parse arbitrary CSV/JSON with no such constraint.
2. **Sorting already happens silently today, with no disclosure.** `InlineOrLocalFileDatasetSource._build_series`
   calls `.sort_index()` on every load, unconditionally — a non-monotonic input is already
   "auto-fixed" before any validation math runs, but nothing in the response or the dashboard tells
   the user their data was out of order. That's a real, already-shipped silent auto-fix that predates
   this backlog; the honest move is disclosing it going forward, not adding a second one.
3. **Exact full-row duplicate rows (same timestamp AND same value) are silently kept, not flagged or
   deduped**, for the local-file/inline/object-storage paths — `_build_series` builds a `pd.Series`
   with whatever index it's given; a repeated `(timestamp, value)` pair just becomes two positions in
   the series with the same value, silently inflating `row_count` and the position-based splitter's
   window math.
4. **A same-timestamp-different-value conflict (a real data-quality problem, not a mechanical
   duplicate) is entirely unhandled** — `pd.Series` accepts a non-unique `DatetimeIndex` without
   complaint, and nothing downstream (the splitter operates positionally, not by looking up unique
   timestamps) would ever surface this to the user.
5. **No gap/frequency-consistency check exists anywhere** — for any dataset source. A dataset with a
   week-long hole in the middle, or one that silently switches from hourly to daily spacing partway
   through, loads and validates exactly like a clean one.
6. **RSS-004's guardrail only checks the upper bound.** Re-reading `create_run` confirms it: `if
   split_count > MAX_SPLIT_COUNT: raise 422`. There is no corresponding check for `split_count == 0`
   (e.g. `train_window` alone already exceeds the dataset's row count) — that configuration is
   accepted, `run_validation_protocol` is called with an empty split list, and the run is persisted
   as `status="completed"` with zero `split_results` rows and no error anywhere in the chain. This is
   a real, previously-undocumented gap this session's reading found — not a duplicate of RSS-004,
   which explicitly scoped itself to the incident's *runaway* case, not the *empty* case.
7. **Nothing today proposes parameter values.** RSS-002 answers "how many splits would *this*
   configuration produce" reactively, as the user types. Nothing computes "*given this dataset's row
   count, here is a configuration that would work*" proactively. That's genuinely new scope, not an
   extension of RSS-002/004's reactive estimate — it must not be built by duplicating or replacing
   `computeEstimatedSplits()`, only by sitting next to it.

## Scope

**In scope**: two epics.

- **Epic A — Dataset repair/validation helpers.** Mechanically-safe detection (and, where genuinely
  safe, conservative disclosed auto-fix) of dataset problems that are currently silently assumed away
  or silently already "fixed" with no disclosure, across `validation-service`'s three `DatasetSource`
  implementations and `ingestion-service`'s stored-dataset read path.
- **Epic B — Horizon/parameter suggestion helpers.** A proactive, computed suggestion for
  train/test/step values given a selected dataset's known row count, sitting beside (never
  replacing) RSS-002's reactive live estimate and RSS-004's server-side cap.

**Out of scope, stated explicitly:**
- Any auto-fix requiring a substantive judgment call on the user's behalf — outlier removal,
  interpolation/imputation of gaps, automatic timestamp-frequency correction, or picking "the"
  horizon for a dataset. See the Won't-fix stories (DH-090/091/092) for the reasoning on each.
- Re-deriving, replacing, or duplicating RSS-002 (`computeEstimatedSplits()`)'s live-estimate UI or
  RSS-004 (`MAX_SPLIT_COUNT`)'s server-side upper-bound guardrail. DH-005 below extends RSS-004's
  existing check with a second, independent condition (`== 0`, not `> MAX_SPLIT_COUNT`) rather than
  touching its existing logic.
- Any change to `naive_first_engine.splitting.generate_splits`'s own math or `libs/naive_first_engine`'s
  public contract — every story here operates strictly before that function is called (same
  "add a check before invoking existing math" boundary RSS-004 already held itself to).
- Building a general data-quality/anomaly-detection subsystem. Every story below names a specific,
  narrow, mechanically-checkable condition; nothing here proposes a generic "data quality score."

## Stories

### Epic A — Dataset repair/validation helpers

### DH-001 — Disclose the sort-on-load that already happens silently [Must]
**As** a user submitting a run against a local file path or inline payload **I want** to be told when
my dataset's rows were reordered by timestamp before validation ran **so that** an out-of-order
source (which can indicate a wrong file, a corrupted export, or an upstream bug) isn't silently
masked by behavior that already exists today with no visibility.

Acceptance criteria:
- [ ] `InlineOrLocalFileDatasetSource._build_series` (and `ObjectStorageDatasetSource`, which reuses
  it) records whether `.sort_index()` actually changed row order (compare the index before/after, or
  check `is_monotonic_increasing` before sorting) and returns that fact alongside the built `Series` —
  a small, additive return-shape change (e.g. a `was_reordered: bool` field on a thin wrapper/namedtuple),
  not a new parameter that changes the existing `DatasetSource.load(reference) -> pd.Series` contract
  for every other caller; exact shape is a Tech Lead call, but no existing call site may be forced to
  start handling a two-tuple it doesn't care about.
- [ ] `POST /runs`'s response/run-detail record surfaces this as a plain fact when true (e.g. a
  `warnings: ["dataset rows were not in timestamp order and were sorted before validation"]` field on
  `RunDetailResponse` or equivalent) — never silently dropped, never escalated to a hard failure (a
  reordered-but-otherwise-valid dataset is still a valid dataset to validate).
- [ ] `dashboard-web`'s run-detail page renders this warning when present, in the same visual register
  already used for other non-fatal, disclosed conditions on that page (not styled as an error).
- [ ] No behavior change to the actual sort itself — this story is disclosure-only, not a new decision
  about whether to sort.

Leakage/honesty check: sorting by timestamp before validation is not a leakage risk in itself (the
splitter needs a sorted index and always assumed one); the risk this story closes is a different one —
a user unknowingly submitting a corrupted/mis-ordered file and getting a result that looks like a
clean run. No claim about accuracy or horizon quality is made or implied.
New scope vs. extension: extends `validation-service` (`dataset_source.py` module already exists and
owns exactly this parsing logic) — not new module scope.
Depends on: none

### DH-002 — Detect and disclose exact full-row duplicate timestamps (local-file/inline/object-storage only) [Should]
**As** a user submitting a run against a local file, inline payload, or object-storage reference **I
want** exact duplicate `(timestamp, value)` rows detected and removed before validation, with the
count and an example shown to me **so that** an accidental double-paste or a duplicated export line
doesn't silently inflate my row count or distort window math, without me having to notice it myself.

Acceptance criteria:
- [ ] `_build_series` (or a helper it calls) detects rows that are identical on both timestamp and
  value, drops all but the first occurrence, and reports the number of rows dropped — this is the one
  auto-fix in this backlog classified as mechanically safe enough to apply automatically: a byte-identical
  repeated row carries no additional information, and dropping it cannot change what the surviving
  data says.
- [ ] The drop is disclosed the same way as DH-001's warning (additive field on the load result,
  surfaced on `RunDetailResponse` and the run-detail page) — e.g. `"dropped 3 exact-duplicate rows
  before validation"` — never a silent count-only log line invisible to the user.
- [ ] Explicitly scoped to `InlineOrLocalFileDatasetSource`/`ObjectStorageDatasetSource` only — stored
  ingestion-service datasets already cannot have this problem (see finding #1 above; the DB's
  `(tenant_id, source, event_time)` primary key already prevents an exact duplicate write), so no
  redundant check is added to `IngestionServiceDatasetSource`.
- [ ] A dataset that becomes too short to run *after* dedup (e.g. drops below `train_window +
  purge_gap + test_window`) surfaces the existing "0 splits" condition (DH-005) using the
  post-dedup row count, not the original — the guardrail must see the same series the protocol
  actually runs against.

Leakage/honesty check: dropping a byte-identical duplicate row uses zero information the user's own
uploaded data didn't already contain twice — it is the one case in this backlog where "safe to
auto-fix" is true by construction, not by judgment call. No claim beyond "these rows were identical
and now appear once" is made.
New scope vs. extension: extends `validation-service`'s existing `dataset_source.py` module.
Depends on: DH-001 (shares the same warnings-plumbing change to `RunDetailResponse`)

### DH-003 — Detect and block same-timestamp-different-value conflicts, never auto-resolved [Must]
**As** a user submitting a run against a local file, inline payload, or object-storage reference **I
want** two rows sharing a timestamp but disagreeing on value to stop my submission with a clear error
naming both conflicting values **so that** the platform never silently picks one of two contradictory
readings on my behalf.

Acceptance criteria:
- [ ] After DH-002's exact-duplicate dedup runs, `_build_series` checks whether any timestamp still
  appears more than once (`index.duplicated()` on the deduped series) — if so, raises
  `DatasetSourceError` (the existing exception type every malformed-input case in this module already
  raises) naming the conflicting timestamp and both differing values, not just a row count.
- [ ] This is a **hard failure**, not a warning and not an auto-resolution (not "keep the first," not
  "average them," not "keep the last") — which of two contradictory readings for the same instant is
  correct is a substantive judgment call about the user's own data, not a mechanical one this platform
  should make silently.
- [ ] `POST /runs` surfaces this the same way any other `DatasetSource.load` failure already surfaces
  today (`status="failed"`, `failure_reason` naming the conflict) — no new error-handling path
  invented, reusing `create_run`'s existing `except Exception` branch around `dataset_source.load`.
- [ ] A test covers: two rows, same timestamp, different values → `DatasetSourceError` naming both
  values; two rows, same timestamp, same value → DH-002's dedup handles it silently-but-disclosed
  instead, never reaching this check.

Leakage/honesty check: this story's entire purpose is refusing to make a judgment call that would
otherwise be invisible to the user — the platform must never look like it "handled" a genuine data
conflict when it actually just picked a side.
New scope vs. extension: extends `validation-service`'s `dataset_source.py`.
Depends on: DH-002

### DH-004 — Gap/frequency-consistency report for a selected dataset, read-only [Could]
**As** a user about to submit a run **I want** to see whether my selected dataset has any gaps or a
change in row spacing before I submit, without the platform silently filling or interpolating
anything **so that** I can make an informed decision about whether the dataset is fit for the horizon
I'm about to validate, or fix it upstream first.

Acceptance criteria:
- [ ] `ingestion-service` gains a narrow, read-only endpoint (e.g.
  `GET /datasets/{source}/gap-report`, tenant-scoped the same way `read_series` already is) that
  computes the modal (most common) interval between consecutive rows for the requested source/range
  and reports: the modal interval, the count of gaps wider than some multiple of it (a documented
  constant, e.g. 3x), and the count of intervals narrower than it (a frequency inconsistency, not just
  a hole) — a report, never a mutation, never touching the stored rows.
- [ ] `dashboard-web`'s run-submission form shows this report for the selected stored dataset (extends
  RSS-001's existing dataset-summary display, doesn't replace it), labeled plainly as informational —
  e.g. "12 gaps wider than 3x the typical spacing found in this range" — with no submission block tied
  to it: a gappy dataset is still the user's data to validate if they choose to, this is visibility,
  not a gate.
- [ ] Explicitly out of scope in this story: any local-file-path or inline-payload equivalent (their
  row count/spacing is only knowable once loaded server-side inside `validation-service`, a
  materially bigger scope than the one new read endpoint this story adds against `ingestion-service`'s
  already-stored, already-indexed data) — flagged as a future story if requested, not built here.
- [ ] No auto-fix of any kind — no interpolation, no synthetic row insertion, no automatic exclusion of
  the gappy region from the run. See DH-090 (Won't) for why.

Leakage/honesty check: a read-only report about the user's own already-ingested data introduces no
new information into the validation protocol itself and computes nothing from data the user doesn't
already have — it is strictly informational, and does not touch `naive_first_engine`.
New scope vs. extension: genuinely new endpoint on `ingestion-service` (module already exists,
trigger already fired — this is ordinary roadmap work on it, not a new override) plus an additive
dashboard-web display; not a change to any shipped RSS-00x story.
Depends on: none

### Epic B — Horizon/parameter suggestion helpers

### DH-005 — Reject (or flag) a configuration that would produce zero splits [Must]
**As** `validation-service` (the same service RSS-004 already made the sole enforcement point for
split-count sanity) **I want** to also reject a configuration that would compute exactly `0` splits,
the same way RSS-004 already rejects one that computes too many **so that** a run never silently
completes with a "completed" status and zero actual results, indistinguishable from a real
(if uninteresting) zero-signal finding.

Acceptance criteria:
- [ ] `create_run`'s existing `split_count = len(generate_splits(...))` computation (already present
  for RSS-004) gains a second condition immediately alongside the existing `> MAX_SPLIT_COUNT` check:
  `if split_count == 0: raise HTTPException(422, ...)` — reusing the exact same already-computed
  `split_count` value, not a second, independent computation that could disagree with the first.
- [ ] The `422` message states plainly that this configuration produces no splits and suggests the
  concrete cause where derivable (`train_window + purge_gap_hours + test_window` compared against the
  dataset's actual row count) — e.g. "this dataset has 340 rows; train_window (360) + purge_gap (0) +
  test_window (40) = 400 exceeds that, so 0 splits would result. Reduce train_window/test_window or
  choose a dataset with more rows."
- [ ] This is additive to RSS-004's existing guardrail, not a rewrite of it — a test proves both
  conditions still fire independently and correctly at their own boundaries (`0` splits → `422`;
  `1..MAX_SPLIT_COUNT` splits → accepted; `MAX_SPLIT_COUNT + 1` → `422` via the pre-existing check).
- [ ] `dashboard-web`'s `computeEstimatedSplits()` (RSS-002) is extended with one more rendered state:
  when the live estimate is exactly `0`, render a distinct message ("this configuration would produce
  no splits — widen the dataset's range, reduce train/test window, or reduce purge gap") in the same
  `form-status-warn` styling already used for the over-cap case, instead of the current "Approximately
  0 split(s) estimated" wording, which reads as a valid-but-uninteresting result rather than the
  rejection it actually is server-side.

Leakage/honesty check: this is a request-shape guardrail, identical in nature to RSS-004's — it
inspects nothing about outcomes, uses no future information, and makes no claim about any horizon's
accuracy; it only prevents a run from silently reporting "completed, 0 splits" as if that were a
meaningful null result.
New scope vs. extension: extends `validation-service`'s existing RSS-004 guardrail code
(`services/validation-service/src/app/routers/runs.py::create_run`) and `dashboard-web`'s existing
RSS-002 estimator (`run_new.html`'s `computeEstimatedSplits()`) — not a new module, and explicitly
not a duplicate of either (it adds the one boundary condition neither currently checks).
Depends on: none (does not require DH-001–004)

### DH-006 — Suggested train/test/step values for a selected stored dataset [Should]
**As** a user who has selected a stored dataset but doesn't know what train/test/step/purge-gap values
to try **I want** the form to compute and display one reasonable, valid combination for that dataset's
row count **so that** I have a working starting point to explore the validation protocol against my
data, instead of guess-and-check against RSS-004's cap or DH-005's floor.

Acceptance criteria:
- [ ] `dashboard-web`'s run-submission form gains a `computeSuggestedParameters()` function, adjacent
  to (not replacing) RSS-002's `computeEstimatedSplits()`, that — given the selected dataset's
  `row_count` (already in the DOM per RSS-001) and a target split count (a documented constant, e.g.
  "aim for at least 10 splits, prefer the smallest `step` that achieves it without exceeding
  `MAX_SPLIT_COUNT`") — computes one concrete `(train_window, test_window, step, purge_gap_hours)`
  tuple satisfying `1 <= floor((row_count - train_window - purge_gap_hours - test_window) / step) + 1
  <= MAX_SPLIT_COUNT`, using the exact same formula RSS-002 already implements (imported/shared from
  the same script block, not a second hand-derived copy).
- [ ] The suggestion is presented with an explicit "Use these values" button that fills the four
  fields (does not auto-submit) — the user always sees and can edit the filled values before
  submitting, exactly like any other form autofill; nothing submits on their behalf.
- [ ] The suggestion's own default target split count and the train:test window ratio it assumes are
  documented, named constants (not magic numbers), with a one-line rationale comment — flagged as a
  reasonable placeholder needing PM/Tech Lead confirmation before merge, the same "provisional, not a
  measurement" disclosure RSS-004's `MAX_SPLIT_COUNT` already modeled.
- [ ] **Copy is explicit, in the UI and in code comments, that this is "a computed starting point for
  exploring this dataset under the leakage-free validation protocol" and never "the recommended
  horizon," "the optimal window," or anything implying an accuracy, profitability, or trading
  implication** (CLAUDE.md's core positioning rule). No wording anywhere in this story's deliverable
  may pair a suggested value with any claim about how well a model would perform using it.
- [ ] When no stored dataset is selected (same precondition RSS-002 already uses), the suggestion area
  is hidden — this story does not attempt to suggest parameters for a local-file-path or inline-payload
  reference whose row count isn't known client-side (same boundary RSS-002 already drew).
- [ ] This story does not change what `POST /runs` accepts or validates — it only pre-fills form
  fields the user can still edit freely; DH-005 and RSS-004 remain the actual enforcement, exactly as
  RSS-002's own precedent already established for the reactive estimate.

Leakage/honesty check: the suggestion is computed purely from the dataset's row count (a property of
the whole dataset, known before any split is drawn) and a fixed target-split-count constant — it uses
no information about outcomes, no per-split result, and no future data relative to any individual
split; it is exploration tooling, not a claim that the suggested horizon or window has any predictive
value. This is the single point in this backlog most likely to be misread as "the platform recommends
a trading horizon" if the copy is loose — the AC above is deliberately strict about the wording for
that reason.
New scope vs. extension: genuinely new client-side capability in `dashboard-web` (`run_new.html`),
but explicitly built as a sibling to RSS-002's existing estimator, sharing its formula and its
`MAX_SPLIT_COUNT` constant rather than re-deriving either — not a modification of RSS-002/004's own
acceptance criteria or shipped behavior.
Depends on: RSS-001, RSS-002 (both already shipped)

### DH-007 — Server-computed suggestion for an exact row count under a narrowed date range [Could]
**As** a user who has narrowed a stored dataset with a start/end date **I want** DH-006's suggestion to
use the exact post-filter row count instead of the whole source's count **so that** the suggested
values are accurate for what I'm actually about to submit, the same accuracy gap RSS-003 already named
for the live estimate.

Acceptance criteria:
- [ ] This story is explicitly gated on RSS-003 landing first (or being deliberately superseded) —
  it reuses whatever exact-row-count mechanism RSS-003 introduces (a dry-run endpoint, or a documented
  decision to defer) rather than inventing a second one; if RSS-003 is deferred, this story is deferred
  with it and DH-006's whole-source approximation remains the only suggestion available for a narrowed
  range, clearly labeled as such (same "estimate vs. exact" labeling discipline RSS-003 already
  specifies for RSS-002).
- [ ] No other behavior change beyond swapping which row count DH-006's computation reads from.

Leakage/honesty check: unchanged from DH-006 — this story only improves the accuracy of the row count
input to the same formula, not what the formula does or claims.
New scope vs. extension: extension of DH-006, contingent on RSS-003.
Depends on: DH-006, RSS-003

### Won't-fix (explicitly declined, with reasoning)

### DH-090 — Auto-interpolate or auto-fill detected gaps [Won't, this backlog]
**As** a user with a gappy dataset **I want** the platform to fill the gaps for me.

Rationale: **Won't.** Interpolating or synthesizing rows to fill a gap injects information the
original data never contained — for a chronologically-ordered, leakage-sensitive validation protocol,
manufacturing a value for a missing timestamp is a modeling decision (what interpolation method? what
assumption about the underlying process?) dressed up as a mechanical repair. This is exactly the kind
of substantive judgment call CLAUDE.md's leakage-avoidance principle and this backlog's own scope
section rule out doing silently on a user's behalf. DH-004's gap *report* is the correct-sized version
of this idea — visibility without a decision made for the user.
Depends on: none

### DH-091 — Auto-drop outlier/anomalous-looking rows [Won't, this backlog]
**As** a user with a dataset that has some suspicious-looking spikes **I want** the platform to clean
them for me.

Rationale: **Won't.** "Suspicious-looking" is a statistical judgment call with real consequences for
what a validation result means — a real market shock and a data-entry error can look identical in a
single-column time series, and this platform's entire value proposition (per CLAUDE.md) is *auditing*
whether a model's apparent skill is real, not quietly editing the ground truth it's audited against.
Silently dropping rows a user didn't ask to have dropped is also a leakage-adjacent risk in its own
right: it changes what "the dataset" means between what the user thinks they submitted and what was
actually validated, with no disclosure. If this is ever revisited, it must ship as a *disclosed,
reviewable, opt-in* flag naming exactly which rows and why — never automatic.
Depends on: none

### DH-092 — Auto-choose "the" horizon or window for a dataset [Won't, this backlog]
**As** a user who doesn't know what horizon to validate **I want** the platform to just pick one for
me.

Rationale: **Won't**, and this is the one rejection tied directly to CLAUDE.md's core finding, not
just a leakage/judgment-call concern: this platform's own thesis-derived result is that no horizon
was found where an ML model beat naive-first in a stable way, and the platform's entire positioning is
refusing to imply predictive/trading value. A feature that "picks the horizon for you" is one short
step from reading as "here's the horizon that works" — the exact claim this product must never make.
DH-006's suggestion helper is deliberately scoped to stop at "a valid combination that produces enough
splits to explore the protocol," never "the best" or "the recommended" anything — see DH-006's own AC
on required wording. This story is the version of that idea that crosses the line, and is declined
outright rather than narrowed.
Depends on: none

## Summary

| Priority | Count | IDs |
|---|---|---|
| Must | 3 | DH-001, DH-003, DH-005 |
| Should | 2 | DH-002, DH-006 |
| Could | 2 | DH-004, DH-007 |
| Won't | 3 | DH-090, DH-091, DH-092 |

Sequencing note for the PM/Tech Lead: **DH-005 has no dependency on anything else in this backlog and
is the highest-value Must** — it closes a real, previously-undocumented gap in RSS-004's own guardrail
(a silent "completed, 0 splits" run) using code that already exists, the same "cheapest correct fix"
shape RSS-004 itself was. DH-001→DH-002→DH-003 form a natural sequence inside `dataset_source.py`
(disclosure infrastructure, then the one safe auto-fix, then the one hard-block) and should be
sequenced together. DH-006 is the epic's actual "helper" deliverable in the sense the request named,
but depends on RSS-001/002 (already shipped) and should ship after DH-005 so the suggestion helper
and the zero-split guardrail agree on the same lower bound rather than being tuned independently.
