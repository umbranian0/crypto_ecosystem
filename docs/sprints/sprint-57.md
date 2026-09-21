# Sprint 57 — Epic A (Trust & Transparency), slice 2: permanent methodology panel + demo page + "not beating naive is expected" reframe (TRUST-001 → TRUST-005 → TRUST-002)

Sprint goal: a reader of any run's results or generated audit report — regardless of run status, split
count, or DM outcome — sees the leakage-aware protocol's fixed parameters stated permanently (not
dependent on one chart's caption rendering), sees "the model did not beat naive" framed as the expected,
scientifically valid outcome this platform's own research established, and can reach the thesis's own
real leaky-vs-purged numbers from within the product — closing the three concrete, narrowly-scoped
completeness gaps `sprint-56`'s roadmap note flagged as this epic's remainder.

Backlog source: `docs/product/backlog-trust-and-admin-ops.md` — `TRUST-001` (Should), `TRUST-005`
(Should, reuses `TRUST-001`'s shared-wording precedent), `TRUST-002` (Should, independent). This file
re-verifies `sprint-56`'s tentative "Next" sketch against current code (including `sprint-56`'s own
changes to `validation_audit.html.jinja`) rather than carrying it over on trust, per that sketch's own
stated caveat.

## Verification of the backlog's cited findings (done independently, not taken on trust)

- `services/dashboard-web/src/app/templates/run_detail.html` (read in full): confirmed today's structure.
  The status table (lines 9–22) and `headline_verdict_summary` paragraph (lines 32–34) render
  unconditionally; everything from "Per-split validation results" onward — including the DM-verdict
  chart (`_dm_verdict_chart.html`, included at line 54) whose caption is today's only place naming DM/
  Harvey — sits inside `{% if splits %}` (line 37) and is skipped entirely for a run with zero splits
  (not-yet-completed, failed-before-first-split, etc.). This confirms `TRUST-001`'s AC exactly:
  `dashboard-web` has no always-visible methodology statement today, and the panel must be placed outside
  the `{% if splits %}` block — logically beside the status table, not inside the per-split section — to
  satisfy "not gated on `{% if splits %}`."
- There is **no** `better_count`/`worse_count` Jinja conditional anywhere in `run_detail.html` — confirmed
  by reading the full file. `headline_verdict_summary` (the closest existing "verdict" surface) is a
  pre-built string returned by `charting.py`'s `build_headline_verdict_summary(run, splits)` (grepped and
  read in full, lines 421–456): it computes `better_count` in Python via the same `_verdict_category`
  helper `build_dm_verdict_chart` uses, then returns one of two fixed-shape sentences (`"Beat Naive0 on
  {better_count}/{total} splits."` or the no-client-model variant) — it returns `None` outright for a
  zero-split run, never assembling a `better_count == 0`-across-existing-splits sentence today. **Real
  finding for the Tech Lead, not previously stated in the backlog's own AC**: `TRUST-005`'s "same
  condition" in `dashboard-web` is a Python-side condition inside/beside `build_headline_verdict_summary`
  (extend that function's return value, or a sibling function called the same place), not a template-side
  `{% if better_count == 0 %}` block like `reporting-service`'s. The two services' `TRUST-005` changes are
  shaped differently (Python string-builder vs. Jinja conditional) even though the sentence's wording must
  be identical — worth stating explicitly in the ticket so it isn't assumed to be a one-line template
  edit in both places.
- `services/dashboard-web/src/app/routers/help.py` (read in full): confirmed the exact pattern
  `TRUST-002` must mirror — `GET /help/concepts` is a standalone `APIRouter()` in its own
  single-concern router file (this repo's router-per-concern convention, explicitly documented in this
  file's own docstring), a pure `templates.TemplateResponse(request, "help_concepts.html", {})` call, no
  session/auth dependency, no downstream service call. `TRUST-002`'s `/help/leakage-demo` is a second
  route on this same `help.py` router (or a sibling file following the identical pattern — Tech Lead's
  call), returning static content the same way — no new mechanism.
- `services/reporting-service/src/app/templates/validation_audit.html.jinja` (read in full, current state
  — i.e., already including `sprint-56`'s shipped "2.5. Reproducibility statement" subsection at lines
  42–55): confirmed section 2 ("Leakage-protocol parameters," lines 32–40) states the run's own parameter
  *values* (horizon, purge gap, split count) but never names Diebold-Mariano or the Harvey correction —
  exactly the gap `TRUST-001`'s AC describes. Confirmed section 2.5 (reproducibility) now sits immediately
  after section 2 and before section 3 (results table) — so `TRUST-001`'s methodology content, per its own
  AC ("extends section 2"), belongs *before* 2.5, not between 2.5 and 3, to avoid sandwiching the
  reproducibility statement between two unrelated additions. **Open question surfaced for the Tech Lead,
  not resolved here** (a PM sequencing/scope note, not a design decision): today's whole "Status" branch
  (lines 24–29) explicitly omits section 2 onward for a non-`"completed"` run, on the stated rationale
  "no fabricated or placeholder metrics" — but the four methodology facts `TRUST-001` adds are static
  protocol facts, not run-computed metrics, so they don't share that rationale for being withheld. Whether
  the methodology panel should also render inside the non-completed "Status" branch (fully matching
  `dashboard-web`'s "regardless of run status" framing) or stay inside the completed-only `else` (matching
  today's section 2's own gating, which is what the AC literally says to extend) is a real design call the
  ticket needs to make explicitly, not one this sprint plan should preempt.
- Confirmed section 5 ("Statistical accuracy vs. economic value," line 156) is the existing permanent
  disclaimer `TRUST-001`'s AC says not to duplicate — distinct content (accuracy-vs-economic-value, not
  protocol mechanics), no overlap risk if `TRUST-001` lands in/near section 2 as scoped.
- Confirmed section 4 ("Verdict," lines 117–154) is exactly where `TRUST-005` lands: `{% set better_count
  = ... %}` (line 119) and the `{% if better_count == 0 %}` branch (line 143) already exist and already
  compute the exact condition the story needs — `TRUST-005`'s `reporting-service` change is a pure,
  contained one-sentence template insertion inside an already-existing conditional, no new Jinja logic.
- `docs/da-tese-ao-produto.md` section 1.3 (read in full): confirmed real, citable numbers for `TRUST-002`
  — e.g. 1h: Naive0 MAE 0.003627 vs. OLS MAE 0.003683 (+1.55%), OLS DA 51.33%, DM 0 better/4 worse vs.
  Naive0; 6h: OLS MAE +4.64% vs. Naive0, DA 52.51% (the platform's own headline "best directional accuracy
  observed" figure per `CLAUDE.md`), DM 4 better/18 worse; 24h: OLS MAE +5.96% vs. Naive0, DA 50.80%, DM
  14 better/22 worse. Section 1.2's own experimental-design table (purge gap 24h, rolling-origin
  walk-forward, train-fold-only preprocessing) is the source for the "what the purge-gap/train-only-fit
  protocol protects against" side of the story's required honest, descriptive (not fabricated-re-run)
  "leaky" column. No numbers need to be invented — section 1.3 has everything the AC requires.

## Sequencing call: all three stories in one sprint, ordered TRUST-001 → TRUST-005 → TRUST-002

Not a straight carry-over of the tentative sketch — re-justified against what was actually verified above:

- **TRUST-001 before TRUST-005 is a real, if soft, dependency — not just a file-overlap grouping.**
  `TRUST-005`'s own AC text says it "reus[es] the same wording precedent `TRUST-001` establishes for
  shared cross-service copy." `TRUST-001`'s AC requires the four-facts methodology wording to be "one
  shared constant... authored once... kept identical by a shared test/fixture in each service" (the
  `FHS-004` `CAVEAT_SENTENCE` precedent). If `TRUST-005` shipped first, its own one-sentence addition
  would have to invent that same shared-constant-plus-same-text-test mechanism from scratch, and
  `TRUST-001` would then either duplicate it under a second name or have to retrofit `TRUST-005`'s
  already-shipped mechanism — real rework risk either way. Sequencing `TRUST-001` first means `TRUST-005`
  reuses one already-established mechanism (module/constant location, same-text test shape) instead of
  the sprint accidentally producing two independently-invented "shared wording" patterns in the same two
  services. This is the "obviously safer order" the sketch's own framing pointed at, now confirmed against
  actual AC text rather than assumed from priority order.
- **TRUST-001 and TRUST-005 also share literal file/region overlap** (`dashboard-web`'s `run_detail.html`
  and `reporting-service`'s `validation_audit.html.jinja`, both touched by both stories, per the
  verification above) — reinforces, but is not by itself, the reason for the order; the shared-mechanism
  dependency above is the stronger reason.
- **TRUST-002 has zero file overlap with either** (a new route + new template + two outbound links from
  `TRUST-001`'s panel and from `/help/concepts` — it reads from `TRUST-001`'s panel, doesn't touch its
  file beyond adding a link, so it can be built any time `TRUST-001`'s panel markup is stable enough to
  add a link into). It is sequenced **last**, not because anything blocks it, but because its one real
  precondition — a rendered `TRUST-001` panel to link *from* — exists cleanly only once `TRUST-001` is
  done, and because it's the more separable unit of work if this sprint needs to shed scope mid-flight.
- **Net call: keep all three in one sprint**, ordered `TRUST-001 → TRUST-005 → TRUST-002`. All three are
  Should-priority, each individually small (a shared-constant + panel in two templates; a one-sentence
  addition in an already-existing conditional in two places; one new static route + template + two
  links), and none is large enough on its own to justify a dedicated sprint — consistent with how
  `sprint-56` bundled two related Should stories rather than splitting them. If the Tech Lead's ticket
  breakdown finds `TRUST-001`'s "shared-constant-plus-same-text-test" mechanism is heavier to stand up
  correctly across two independent services than this plan assumes, `TRUST-002` (fully independent, zero
  rework risk if deferred) is the correct story to push to a follow-up sprint first — not `TRUST-005`
  (which would then either wait on `TRUST-001` regardless or duplicate its mechanism, the exact outcome
  this ordering exists to avoid).

## Stories in scope, in execution order

1. **TRUST-001** — Permanent, standalone methodology disclosure panel (not just a chart caption).
   - Modules touched: `services/dashboard-web` (`run_detail.html` gains an always-visible panel, placed
     outside `{% if splits %}` — verified above as a real gap, not an assumed one) and
     `services/reporting-service` (`validation_audit.html.jinja` gains an equivalent subsection extending
     section 2, positioned before section 2.5's reproducibility statement per the verification above; the
     completed-only-vs-also-non-completed placement question is flagged above for the ticket to resolve
     explicitly).
   - Must sit strictly first: `TRUST-005` reuses the shared-wording mechanism this story establishes (see
     sequencing call above) — not a data dependency like `TRUST-003 → TRUST-004`, but a real
     mechanism-reuse dependency, stated explicitly rather than left implicit.
   - Constraint to carry into the ticket: the four fixed protocol facts (rolling-origin walk-forward,
     purge gap, mandatory Naive0/NaiveLast baselines, DM+Harvey correction) are authored once as text and
     kept identical across both services by a same-text unit test in each service (mirroring `FHS-004`'s
     `CAVEAT_SENTENCE` precedent) — not a cross-service import, per implementation-plan.md's module
     boundary rule (no service imports another service's code).

2. **TRUST-005** — Reframe "model didn't beat naive" copy as the expected, first-class scientific finding.
   - Modules touched: `services/reporting-service` (one sentence inside the already-existing
     `{% if better_count == 0 %}` branch of section 4's "Overall" paragraph — confirmed, no new Jinja
     logic needed) and `services/dashboard-web` (the equivalent sentence, but — per the verification
     above — added on the Python side, in or beside `charting.py`'s `build_headline_verdict_summary`,
     since that function already computes `better_count` and today only returns a "beat naive on N/M
     splits" sentence with no branch for the "N is zero" case; this is a different code shape than
     `reporting-service`'s template-side change, stated explicitly so it isn't assumed to be a matching
     one-line template edit in both services).
   - Sequenced after `TRUST-001`: reuses that story's shared-constant/same-text-test mechanism for the
     added sentence's wording (see sequencing call above).
   - Constraint to carry into the ticket: the added sentence is additive context only — the existing "did
     not beat naive" / "Naive0 performed significantly better" language stays exactly as-is in both
     services, per the AC's explicit "does not soften or hide the actual verdict" line.

3. **TRUST-002** — Static "leaky vs. purged walk-forward" side-by-side demo using the thesis's own numbers.
   - Module touched: `services/dashboard-web` only (new route, e.g. `/help/leakage-demo`, on the existing
     `help.py` router or a sibling file following its exact pattern — verified above: no session/auth
     dependency, no downstream service call, same `TemplateResponse` render as `/help/concepts`; a new
     template with the thesis's real section-1.3 numbers, verified above and ready to use verbatim; a link
     added into `TRUST-001`'s new panel and into `/help/concepts`).
   - No data/mechanism dependency on `TRUST-001`/`TRUST-005` — sequenced last only because linking *from*
     `TRUST-001`'s panel is cleaner once that panel's markup exists, and because it's the safest story to
     defer first if this sprint needs to shed scope (see sequencing call above).
   - Constraint to carry into the ticket: the "leaky" side is descriptive/didactic (what the purge-gap/
     train-only-fit protocol protects against), never a fabricated re-run of the thesis under a leaky
     protocol — no such re-run exists or is in scope, per the AC.

## Module/dependency note for the Tech Lead (implementation-plan.md sections 2 and 6)

All three stories touch only already-built, already-live modules — no trigger-firing question here:
`services/dashboard-web` (trigger #8) and `services/reporting-service` (trigger #7) both fired long ago,
and nothing in this sprint proposes a new service or a new `libs/*` package. Per implementation-plan.md
section 2's module boundary rule: `reporting-service`'s methodology/verdict wording must be authored
independently within `reporting-service`'s own codebase (its own constant + its own same-text test), never
by importing `dashboard-web`'s equivalent constant or vice versa — the two services stay decoupled, kept
identical only by convention plus a same-text test in each, exactly as `TRUST-001`'s AC specifies.

## Stories explicitly deferred

- Everything else in `backlog-trust-and-admin-ops.md` not in scope this sprint: all of Epic B
  (`RPT-001/002/004`), all of Epic C (`ADMIN-001/002/003/005`), all of Epic D (`ONB-001/002`) — deferred
  per `sprint-55.md`'s original roadmap sketch and `sprint-56.md`'s carry-forward of it, not dropped.
  `TRUST-003`/`TRUST-004` are already done (Sprint 56). After this sprint, Epic A (Trust & Transparency)
  is fully shipped (`TRUST-001` through `TRUST-005` all done) — see "Next" below.

## File-overlap / concurrent-work risk

- `services/dashboard-web/src/app/templates/run_detail.html` and `services/reporting-service/src/app/
  templates/validation_audit.html.jinja` are each touched by **two** stories in this sprint (`TRUST-001`
  and `TRUST-005`) — the sequencing call above exists specifically to make that safe within one sprint
  (shared mechanism established once, reused once) rather than a risk to flag for a *future* sprint the
  way `sprint-56` flagged `validation_audit.html.jinja` for this one.
- No other in-flight or immediately-next-sprint story is known to touch these same four files
  (`run_detail.html`, `validation_audit.html.jinja`, `charting.py`, `help.py`) — confirmed by grep during
  verification above; nothing else in the backlog references them.
- `services/reporting-service/src/app/templates/validation_audit.html.jinja`'s section numbering: this
  sprint adds methodology content extending section 2 (before the already-shipped 2.5) and a sentence
  inside section 4 — the ticket should land both without leaving section numbering ambiguous for whatever
  touches this template next (same discipline `sprint-56` asked of itself for `TRUST-004`).

## Definition of done for this sprint

- `TRUST-001`'s, `TRUST-005`'s, and `TRUST-002`'s acceptance criteria (verbatim from
  `docs/product/backlog-trust-and-admin-ops.md`) are checked off in their respective tickets.
- A same-text unit test in `dashboard-web` and a same-text unit test in `reporting-service` prove the
  four-fact methodology wording (`TRUST-001`) is character-identical across both services' own constants —
  proving the "authored once, kept identical" AC, not merely asserting it.
- The same same-text-test mechanism (or an explicitly justified variant, if the Tech Lead finds one
  necessary) covers `TRUST-005`'s added sentence across both services.
- A test proves `dashboard-web`'s methodology panel and `reporting-service`'s methodology subsection both
  render for a zero-split and/or non-completed run (the specific gap `TRUST-001` exists to close) — not
  only for a completed, multi-split run.
- A test proves `TRUST-005`'s sentence renders only in the `better_count == 0` case in both services, and
  that the existing "did not beat naive" verdict language is unchanged (byte-identical apart from the
  addition) for that case.
- A test proves `/help/leakage-demo` renders the real section-1.3 numbers verified above (not placeholder
  or fabricated figures), and that both the link from `TRUST-001`'s panel and the link from
  `/help/concepts` resolve to it.
- Positioning check (CLAUDE.md) explicitly re-verified in review for all three: no wording in any of the
  three additions implies price prediction or a trading signal; `TRUST-002`'s page explicitly reinforces,
  not contradicts, the core finding (no model beat naive stably); `TRUST-005`'s sentence never implies a
  model *should* beat naive, only that not doing so is expected and valid.
- `services/dashboard-web/README.md` and `services/reporting-service/README.md` updated to record the new
  panel/subsection/sentence/route as shipped (README-current convention, per this repo's standing rule).
- `docs/product/backlog-trust-and-admin-ops.md`'s `TRUST-001`/`TRUST-002`/`TRUST-005` entries marked done
  with acceptance-criteria boxes checked, pointing to their ticket files.
- `docs/tickets/README.md` gets a new Sprint 57 section (Tech Lead updates this when tickets are
  created/closed, per this repo's standing convention — not done by this sprint plan itself).
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`) after
  all three tickets are Tech-Lead-verified done, before sign-off. QA scope should specifically,
  independently verify: the two same-text tests actually fail if either service's copy of the shared
  wording is edited out of sync (not just that they pass today); that the methodology panel truly renders
  regardless of run status/split count in both services (including the open placement question flagged
  above, whichever way the Tech Lead resolves it); and that `TRUST-002`'s numbers match
  `docs/da-tese-ao-produto.md` section 1.3 verbatim.

## Next (explicitly not this sprint, roadmap note for continuing this backlog)

Epic A (Trust & Transparency) is fully shipped once this sprint closes. Per the backlog's own scope
lean (Epic C, Admin/Ops Maturity, prioritized alongside Epic A ahead of Epics B/D): **Sprint 58
(tentative)** — start of Epic C (`ADMIN-*`), most likely `ADMIN-002` (operator action audit log, a
bounded, self-contained new table + two wired endpoints + a read-only settings page) and/or `ADMIN-003`
(surface crawl failure detail, a bounded, self-contained new column + response field + panel extension),
both independently schedulable with no cross-story file overlap, per the backlog's own sequencing note.
That sprint will need its own PM pass re-verifying those citations against then-current code before being
handed to the Tech Lead, same as this one was.
