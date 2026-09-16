# Sprint 52 — `research/`: wider real-data window + no-new-dependency ensemble candidate (MR-012, MR-013 -> MR-014)

Sprint goal: two more of the thesis's remaining research gaps get closed on real `binance_price_btcusdt_1h`
data — the MR-008/MR-009 real-data window gets widened to include more market regimes (MR-012), and a
genuinely new, sklearn-only stacking-ensemble model class gets tested under the same leakage-safe protocol
(MR-013) — with both outcomes, and the explicit GRU/Transformer `torch`-dependency deferral decision,
documented in `research/README.md` and the ticket index (MR-014).

Backlog source: `docs/product/backlog-model-research.md`, "Extension: wider real-data window and a
no-new-dependency ensemble candidate (MR-012 onward)" section (MR-012, MR-013, MR-014 — the entire scope
of this extension; no other stories are in scope).

## Sequencing decision: MR-012 and MR-013 run as two parallel tracks, not a linear chain

This matches Sprint 40's DASH-128/MR-002 parallel pairing, not Sprint 47's forced MR-008 -> MR-009 -> MR-011
linear chain. Reasoning, stated explicitly rather than left implicit:

- **No real dependency edge exists between MR-012 and MR-013.** MR-013's own "Depends on" line lists
  MR-004, MR-005, MR-008, MR-009 — all already done — and does *not* list MR-012. Its acceptance criteria
  explicitly accept either the existing MR-008/MR-009 window *or* MR-012's wider window ("or MR-012's wider
  window, if it has landed first"), which is the backlog itself disclaiming a hard ordering requirement.
  Sprint 47's MR-009, by contrast, could not have run without MR-008's real-data pipeline existing first —
  that is a genuine same-artifact extension. Here, the two stories produce independent artifacts.
- **No file overlap.** MR-012 is explicitly scoped as a data-window change only — its own AC requires
  `research/models/*.py` to stay untouched (`git status --porcelain research/models` empty). MR-013 is
  exactly the inverse: it adds a new `research/models/stacking_ensemble.py` and touches no data-window
  logic. Two Tech Lead tracks can proceed without touching each other's files, same as Sprint 40's
  dashboard-web/research split (though here both tracks happen to live in the same module, `research/`,
  which Sprint 40's pairing did not).
- **Different risk/complexity profiles justify running them in parallel rather than gating one on the
  other's calendar slot.** MR-012 is low-risk, confirmatory breadth (reuses MR-008/MR-009's pipeline
  unchanged, "Should" priority). MR-013 is the harder story in this extension — a new leakage failure mode
  to guard against (meta-learner overfit-on-base-predictions), "Could" priority. Forcing MR-013 to wait on
  MR-012 would delay a Should-priority, low-risk story's landing for no dependency reason, and forcing
  MR-012 to wait on MR-013 would delay confirmatory breadth behind the extension's riskiest story. Running
  them in parallel avoids both false holds.
- **The one coordination point is explicit, not silent:** if MR-013 has not landed by the time MR-012's
  wider window is ready, MR-013 runs against the original MR-008/MR-009 window per its own AC's fallback
  clause; if MR-012 lands first, MR-013 should prefer the wider window since it is strictly more
  informative for the same protocol, at the Tech Lead's discretion once both tracks' actual landing order
  is known. This is not a case where "prefer the wider window if available" turns into a hidden hard block
  on MR-013 — MR-013 must not silently wait for MR-012 past its own track's readiness.
- **MR-014 depends on both regardless of order** and is sequenced last in both tracks' completion, per its
  own stated dependency and this backlog's unbroken MR-011/MR-005/MR-006 documentation precedent.

## Pre-read findings that shape this plan

- `docs/tickets/README.md`'s `research/` (MR-*) tracking table: MR-001 through MR-009 and MR-011 all done
  (most recent: MR-011, Sprint 47). No MR-012/013/014 rows exist yet — this sprint adds them.
- MR-012's stated dependencies (MR-008, MR-009) are both done.
- MR-013's stated dependencies (MR-004, MR-005, MR-008, MR-009) are all done; MR-012 is *not* a listed
  dependency (see sequencing decision above).
- MR-014 depends on both MR-012 and MR-013 (this sprint, sequenced last, after both tracks close).
- Module boundary: this entire sprint lives inside `research/` (plus `research/README.md` and
  `docs/product/backlog-model-research.md` status updates) — no `libs/naive_first_engine` change, no
  `services/validation-service`/`ingestion-service` code change (MR-012 reuses the existing
  `research/`-owned HTTP client against `ingestion-service`'s already-shipped `GET
  /datasets/{source}/series` route, per its own AC; MR-013 reuses the already-shipped base models and
  `scikit-learn`, already a `research/pyproject.toml` dependency), consistent with every prior MR-* story's
  module scope.
- **Binding, restated per the backlog's own header**: no story here may touch, weaken, or shortcut
  `libs/naive_first_engine`'s leakage-safety machinery. No product surface may assert price-prediction
  capability unless a real, Harvey-corrected significant DM win is actually observed. A "no improvement on
  real data" result is a complete, valuable outcome for both MR-012 and MR-013, not a failed story.
- **GRU/Transformer dependency deferral is explicitly out of scope for this sprint** — the backlog's own
  header defers adding `torch`/`tensorflow` and flags it for a separate, future requester/PM sign-off
  decision. This sprint does not authorize that dependency addition; MR-014 only records the deferral
  decision that has already been made, it does not re-open it.

## Explicit compute-budget scoping decision for MR-012 (binding on the Tech Lead)

Restating the backlog's own AC rather than leaving it to implementation-time judgment: MR-012's widened
date range must stay within the same CPU-only, sub-5-minute compute ceiling MR-008 disclosed — it is a
deliberate, disclosed trade-off (a materially longer window than MR-008's 209 days), not "use the full
~78,500-row/~9-year history," which MR-008 already declined for compute-budget reasons. If a wider window
still cannot fit that ceiling, the bound and the reason must be disclosed explicitly in the ticket and
`research/README.md`, exactly as MR-008 itself required. Same purge-gap values as MR-008 (`purge_gap=6` for
1h/6h) and MR-009 (`purge_gap=24` for 24h) carry over unchanged — no purge-gap narrowing to fit more splits
into the compute budget.

## Explicit leakage-guard requirement for MR-013 (binding on the Tech Lead)

MR-013's meta-learner must be fit strictly on the training fold's own out-of-sample base-model predictions
(e.g. a train-fold-internal holdout split), never on the base models' in-sample training predictions — this
is a new leakage failure mode relative to MR-004/MR-005 (base-model-overfit leaking into the meta-learner),
and MR-013's own AC requires a unit test that asserts this explicitly. No new dependency may be added to
`research/pyproject.toml` — `sklearn.linear_model` is already available via the existing `scikit-learn`
dependency.

## Stories in scope

Two parallel tracks, then a shared closing story:

**Track A — MR-012** (Should): widen the real-data window MR-008/MR-009 used, re-run
`LightGBMBaseline`/`RegimeHMMBaseline` at 1h/6h/24h, same pipeline, zero new model code. Runs independently
of Track B; only depends on already-done MR-008/MR-009.

**Track B — MR-013** (Could): new sklearn-only stacking-ensemble `Baseline` combining `LightGBMBaseline` +
`RegimeHMMBaseline`, meta-learner fit train-fold-only with an explicit leakage guard. Runs independently of
Track A; only depends on already-done MR-004/MR-005/MR-008/MR-009. Uses MR-012's wider window if it has
landed by the time MR-013 runs its protocol pass, otherwise falls back to the existing MR-008/MR-009
window, per its own AC.

**Closing story — MR-014** (Must): document both tracks' outcomes in `research/README.md` (new section
matching the MR-004/MR-005/MR-006/MR-008/MR-009 format) and the ticket index, including the GRU/Transformer
`torch`-dependency deferral decision as an explicit, dated record. Runs last because it depends on both
MR-012 and MR-013's actual results — it cannot be written before both exist.

## Stories explicitly deferred

- A `torch`/`tensorflow`-based GRU/Transformer candidate — explicitly deferred by the backlog's own header,
  not scoped as a story in this extension at all. Any future decision to add that dependency needs its own
  explicit requester/PM sign-off, separate from this sprint.

No other stories from this backlog section are deferred — MR-012, MR-013, and MR-014 are the entire scope
of this extension.

## Definition of done for this sprint

- MR-012's acceptance criteria (as stated verbatim in `docs/product/backlog-model-research.md`) are checked
  off: widened, explicitly disclosed date range/row count within the same compute ceiling; same HTTP-client
  data path (no new connector, no `IngestionServiceDatasetSource` import); `pct_change().dropna()` applied;
  same purge-gap values as MR-008/MR-009; `research/models/*.py` untouched; DM-vs-Naive0 verdict counts
  reported for all three horizons; hard gate restated and honored.
- MR-013's acceptance criteria are checked off: `Baseline`-protocol-compliant stacking ensemble
  implementation; meta-learner fit train-fold-only with a unit test enforcing the leakage guard; base models
  re-instantiated/refit per split; zero new `research/pyproject.toml` dependency; run at 1h/6h/24h against
  the same or MR-012's wider real-data window; hard gate restated and honored.
- MR-014's acceptance criteria are checked off: `research/README.md` gains a new MR-012/MR-013 section in
  the existing structural format (what was run, scoping decisions, verdict counts per horizon, any bug
  found/fixed); `docs/tickets/MR-012.md` and `MR-013.md` written in the existing Outcome-section format; the
  hard gate restated in `research/README.md`'s new section itself; the GRU/Transformer deferral decision
  recorded as an explicit, dated decision; any "no improvement on real data" result stated explicitly as a
  further independent confirmation of the thesis's core finding, not buried.
- `libs/naive_first_engine` and `services/validation-service` suites re-run with zero regressions (neither
  module is touched by this sprint's scope).
- `docs/product/backlog-model-research.md`'s MR-012/MR-013/MR-014 entries marked done with
  acceptance-criteria boxes checked, pointing to their ticket files, any scope-bound (date range/row count,
  meta-learner choice) disclosed in the entry itself.
- `docs/tickets/README.md`'s `research/` (MR-*) tracking table and a new Sprint 52 section added, matching
  the existing table format (see Sprint 47's entry for the closest precedent).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`) after
  all three tickets are Tech-Lead-verified done, before sign-off. QA scope should mirror Sprint 47's MR-008/
  MR-009/MR-011 precedent (no live-deploy rebuild needed, `research/` has no service/API surface) but should
  independently re-confirm: the purge-gap/train-fold-only-fit boundary held on both the widened window
  (MR-012) and the new ensemble's meta-learner (MR-013), the disclosed date-range/row-count bound for MR-012
  is genuine and matches what's documented, MR-013's leakage-guard unit test actually exercises the failure
  mode it claims to guard against (not a trivial always-pass assertion), the Harvey correction is applied at
  24h for both tracks, and no README/UI copy anywhere asserts price-prediction capability unless a real,
  Harvey-corrected significant DM win was actually produced.

## Next (explicitly not this sprint)

- If MR-012 and/or MR-013 produce a genuine, Harvey-corrected significant DM win over Naive0 on real data
  (an open, uncertain outcome — not assumed here), that should prompt an explicit follow-up conversation
  with the Product Owner about product-copy implications before any customer-facing surface changes — not
  something for the Tech Lead or dev squad to action unilaterally under this sprint's scope.
- Any future GRU/Transformer (`torch`/`tensorflow`) candidate remains deferred pending its own explicit
  requester/PM sign-off on the new dependency — not authorized by this sprint.
- No further MR-* stories are currently backlogged beyond MR-014; this sprint closes the "wider real-data
  window and no-new-dependency ensemble candidate" extension as currently approved.
