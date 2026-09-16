# Sprint 47 — `research/`: real BTC/USDT historical data extension (MR-008 -> MR-009 -> MR-011)

Sprint goal: `research/`'s already-shipped `LightGBMBaseline` (MR-004) and `RegimeHMMBaseline` (MR-005) —
previously tested only on a seeded synthetic series — get a second, independent, honestly-reported test
against real `binance_price_btcusdt_1h` data at all three of the thesis's original horizons (1h/6h/24h,
the last added by this extension), with the result documented in `research/README.md` and the ticket
index to the same rigor as every prior MR-* story.

Backlog source: `docs/product/backlog-model-research.md`, "Extension: real Bitcoin historical data
(MR-008 onward)" section (MR-008, MR-009, MR-011 — MR-010 is a documented "no separate story" decision,
not a real ticket, per that section's own text).

## Why a single sprint, not two

MR-009 strictly depends on MR-008 (same pipeline, same two models, same real dataset, just extending
horizon coverage) and MR-011 strictly depends on both (documentation of their combined outcome) — this is
a linear dependency chain, not two independent tracks, so there is no parallel-pairing opportunity like
Sprint 40's DASH-128/MR-002 or Sprint 42's MR-005/MR-007. The remaining question is whether the real-data
compute step (MR-008) deserves its own sprint, isolated from the horizon extension (MR-009) and
documentation (MR-011). Judgment call: keep it to one sprint, for reasons stated explicitly rather than
left implicit:

- **No new connector or infrastructure work.** `IngestionServiceDatasetSource` already exists and Sprint
  45 (INGEST-010/030, GW-030) already copied `binance_price_btcusdt_1h` to every tenant — this extension
  is a data-source swap onto an already-shipped pipeline (MR-004/MR-005's `Baseline` implementations,
  `config.extra_baselines`, `run_validation_protocol`), not new model code or new plumbing. That is a
  materially lower-novelty situation than Sprint 42's MR-005 (a genuinely new model class) or MR-008/009's
  own backlog rationale, which explicitly calls this "the lowest-friction, highest-information extension
  available."
- **MR-009 is additive scope on the same pipeline, not a second research question.** Once MR-008's
  real-data run against `IngestionServiceDatasetSource` exists, extending it to 24h is a horizon-loop and
  a Harvey-correction check, not new infrastructure — closer to Sprint 39's UAT-010 (additive parameter
  extension) than to a standalone modeling story.
- **Compute-budget risk is bounded and disclosed up front (see below), not open-ended** — the same
  light-compute discipline MR-004/MR-005/MR-008's own AC already impose (bounded date range/row count,
  fixed hyperparameters, CPU-only) keeps this from ballooning into a multi-sprint effort.
- **Splitting would separate MR-011 from a fresh memory of the actual run**, working against this
  project's own "docs and decisions always updated as part of the work, not a separate pass" convention —
  same reasoning Sprint 43 used to *defer* MR-006 until it could cover two models in one pass; here the
  opposite conclusion holds because MR-008/009/011 are one continuous thread, not two independent
  candidates.

If, once implementation starts, the Tech Lead finds MR-008's real-data run alone exceeds a light-compute
budget (e.g. the full ~7-year hourly series proves too large/slow for a CPU-only, minutes-not-hours run),
the correct move is to say so and split MR-009/MR-011 into a following sprint — not to silently expand
scope or compute to force MR-009 into this same sprint. This sprint file's own "explicitly deferred"
section states that fallback plainly so the Tech Lead doesn't have to guess.

## Pre-read findings that shape this plan

- `docs/tickets/README.md`'s `research/` (MR-*) tracking table: MR-001 through MR-007 all done (most
  recent: MR-007, Sprint 42). No MR-008/009/010/011 rows exist yet — this sprint adds them.
- MR-008's stated dependencies (MR-004, MR-005, MR-001, Sprint 45's INGEST-010/030/GW-030) are all done.
- MR-009 depends only on MR-008 (this sprint, sequenced immediately after).
- MR-011 depends on both MR-008 and MR-009 (this sprint, sequenced last).
- MR-010 is not a ticket — it is a documented backlog decision (MR-002's engineered features are already
  load-bearing inside `LightGBMBaseline`/`RegimeHMMBaseline`'s existing `predict()` implementations, so
  re-running those models on real data automatically exercises MR-002 on real data too, with no separate
  wiring). Nothing to schedule for it in this sprint.
- Module boundary: this entire sprint lives inside `research/` (plus `research/README.md` and
  `docs/product/backlog-model-research.md` status updates) — no `libs/naive_first_engine` change, no
  `services/validation-service` change (data flows through the already-shipped
  `IngestionServiceDatasetSource`/dataset-reference path, no new route needed), consistent with every
  prior MR-* story's module scope.

## Explicit compute-budget scoping decision for MR-008/MR-009 (binding on the Tech Lead)

Restating the backlog's own AC rather than leaving it to implementation-time judgment: if the real
`binance_price_btcusdt_1h` series (hourly since 2017-08-17 UTC, so tens of thousands of rows) requires
bounding to stay CPU-only and light-compute, the bound (date range and row count actually used) must be
disclosed explicitly in the ticket and `research/README.md`, exactly as MR-008's own AC already states —
this is compute-budget scoping, not a data-quality shortcut, and does not authorize skipping or narrowing
purge-gap enforcement, train-fold-only fitting, or the Harvey correction at 24h. If MR-009's 24h horizon
needs a wider purge gap than 1h/6h to prevent leakage across the longer target window, that decision must
be made explicitly and documented, not silently defaulted, per MR-009's own AC.

## Stories in scope, in execution order

1. **MR-008** — re-run `LightGBMBaseline`/`RegimeHMMBaseline` against real `binance_price_btcusdt_1h` data
   at 1h/6h, via the existing `IngestionServiceDatasetSource`/dataset-reference path, no new connector.
   Runs first because MR-009 and MR-011 both depend on it.
2. **MR-009** — extend the same real-data pipeline to 24h, Harvey-corrected (overlapping horizon). Runs
   second, strictly after MR-008, per its own stated dependency ("establishes the real-data pipeline this
   story extends").
3. **MR-011** — document both stories' outcomes in `research/README.md` (new section matching the
   MR-004/MR-005/MR-006 format) and the ticket index. Runs last because it depends on both MR-008 and
   MR-009's actual results — it cannot be written before they exist.

## Stories explicitly deferred

None from this backlog section — MR-008, MR-009, and MR-011 are the entire scope of the "real Bitcoin
historical data" extension (MR-010 is a decision record, not a schedulable ticket). If the Tech Lead finds
MR-008 alone exceeds a light-compute budget once real row counts are measured, MR-009 and MR-011 should be
pushed to a following sprint rather than compressed — see "Why a single sprint, not two" above for the
explicit fallback.

## Definition of done for this sprint

- MR-008's acceptance criteria (as stated verbatim in `docs/product/backlog-model-research.md`) are
  checked off: both models registered via `config.extra_baselines` and run through the unmodified
  `run_validation_protocol` against a real, returns-transformed `binance_price_btcusdt_1h` series pulled
  through `IngestionServiceDatasetSource`; purge-gap/train-fold-only-fit/DM-vs-Naive0 protocol unmodified;
  any date-range/row-count bound disclosed explicitly; DM-vs-Naive0 verdict counts reported for both
  models at both horizons; the hard no-price-prediction-claim gate restated and honored.
- MR-009's acceptance criteria are checked off: 24h treated as overlapping with Harvey correction applied
  (no shortcut statistic); same unmodified purge-gap/train-fold-only-fit protocol, any wider purge gap for
  24h decided and documented explicitly rather than defaulted; DM-vs-Naive0 verdict counts reported for
  24h alongside MR-008's 1h/6h numbers; same hard gate restated and honored.
- MR-011's acceptance criteria are checked off: `research/README.md` gains a "Real BTC/USDT data
  (MR-008/MR-009)" section in the same structural format as the existing MR-004/MR-005/MR-006 sections
  (what was run, exact scoping decisions, verdict counts per horizon, any bug found/fixed during review,
  using the same "Correction" subsection format if applicable); `docs/tickets/MR-008.md` and `MR-009.md`
  written in the same Outcome-section format as `MR-004.md`/`MR-005.md`; the hard gate restated in
  `research/README.md`'s new section itself; a "no improvement on real data" result (if that is the
  outcome) stated explicitly as a second, independent confirmation of the thesis's core finding, not
  buried.
- `libs/naive_first_engine` and `services/validation-service` suites re-run with zero regressions
  (neither module is touched by this sprint's scope, per every prior MR-* precedent).
- `docs/product/backlog-model-research.md`'s MR-008/MR-009/MR-011 entries marked done with
  acceptance-criteria boxes checked, pointing to their ticket files, any scope-bound (date range/row
  count) disclosed in the entry itself so the backlog record doesn't silently imply an unbounded run.
- `docs/tickets/README.md`'s `research/` (MR-*) tracking table and Sprint 47 section updated, matching the
  existing table format.
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`) after
  all three tickets are Tech-Lead-verified done, before sign-off. Given `research/` has no service/API
  surface and nothing here runs inside a deployed container, QA scope should mirror Sprint 41/42's MR-004/
  MR-005 precedent (no live-deploy rebuild needed) but should independently re-confirm: the purge-gap/
  train-fold-only-fit boundary held on real data exactly as on synthetic data, the disclosed date-range/
  row-count bound is genuine and matches what's documented, the Harvey correction is actually applied at
  24h (not merely claimed), and no README/UI copy anywhere asserts price-prediction capability unless a
  real, Harvey-corrected significant DM win was actually produced.

## Next (explicitly not this sprint)

- If MR-008/MR-009 produce a genuine, Harvey-corrected significant DM win over Naive0 on real data (an
  open, uncertain outcome — not assumed here), that would be a first for this research track and should
  prompt an explicit follow-up conversation with the Product Owner about product-copy implications before
  any customer-facing surface changes — not something for the Tech Lead or dev squad to action unilaterally
  under this sprint's scope.
- No further MR-* stories are currently backlogged beyond MR-011; this sprint closes the "real Bitcoin
  historical data" extension as currently approved.
