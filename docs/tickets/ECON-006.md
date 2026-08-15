# ECON-006 — No profitability language outside the gated computation path

**Status: done** — Tech Lead verified directly: read `scripts/check_profitability_language.py`, `tests/test_profitability_language.py`, the full rewritten `README.md`, and `routers/simulations.py`'s new `summary`/`description`. Independently re-ran the full suite (**50 passed, 0 failed**) and personally reproduced the drift-detection demonstration end-to-end (not just trusted the dev agent's report): injected `"# This model is profitable and beats the market."` into `src/app/models.py`, confirmed the check fails with exit code 1 and reports both hits (`models.py:91: forbidden term 'profitable'`, `models.py:91: forbidden term 'beats the market'`), reverted via the pre-injection backup, confirmed `git diff --stat src/app/models.py` shows zero diff (exact restoration), and confirmed the check passes clean again (exit 0) with the full suite back at 50/50.

## Analysis
Story: ECON-006 (Must), `docs/product/backlog-economic-service.md`. Depends on: ECON-001 (done), ECON-005 (its doc-sync grep check needs ECON-005's guard/route code to exist to scan). Constraining docs: CLAUDE.md ("Never let a subsystem's README, code comments, or docs imply the system predicts prices or generates trading signals. Statistical accuracy ≠ economic value — always keep these separate"), da-tese-ao-produto.md section 2.7. Covers backlog ECON-006's acceptance criteria in full. This is the prose-level complement to ECON-005's code-level gate — ECON-005 makes it structurally impossible to *return* a number; ECON-006 makes it impossible for *docs/comments/logs* to imply one exists, independent of whether the gate is ever satisfied.

**DRY check (performed before writing this ticket)**: `libs/naive_first_engine`'s NFE-018, `services/validation-service`'s VS-016, `libs/common`'s LC-005 doc-sync-check scripts were the precedent read for this ticket's grep-style check — reuse the "introspect the real thing, don't trust a comment" structure (AST-parsing for `naive_first_engine`'s zero-import constraint, live-app route introspection for `validation-service`, since `economic-service` is a running FastAPI app like `validation-service`). Do not invent a fourth structurally-different style without reason.

## Design
No GoF pattern from section 7 applies (this is a documentation/grep-check ticket, matching NFE-018/VS-016/LC-005's own Design sections, which name none). Files touched (`services/economic-service/` only):
- `README.md` — full rewrite (not a status-line edit) per the AC below.
- `scripts/check_doc_sync.py` (or piggyback on `tests/test_eligibility.py` — backlog allows either; implementer's choice, document which) — the grep-style profitability-language check.
- `tests/test_doc_sync.py` (if a separate script) or an addition to an existing test file.
- `src/app/main.py` / `src/app/routers/simulations.py` — FastAPI `summary`/`description` strings on `POST /simulations` (edit only, no new file).

**Scope of the grep check (binding, from the backlog)**: flag occurrences of "profitable"/"beats the market"/"alpha" (and reasonable near-synonyms the implementer identifies, e.g. "profit", "returns money", "makes money" — document the exact pattern list chosen) in any docstring, log message, or README line, **outside** ECON-005's own narrowly-scoped gated module (`src/app/eligibility.py`'s success-path code and its own necessarily-descriptive docstring are the one allowed exception — the module that computes `EligibleSimulationResult` is allowed to describe what it computes; everywhere else in the codebase is not).

## Implementation acceptance criteria
- [x] `services/economic-service/README.md` rewritten (not just status-line-updated) to state CLAUDE.md's own required framing explicitly: "statistical accuracy ≠ economic value," "never imply price prediction or trading signals," this service *will* compute cost/slippage-adjusted returns once — and only once — a real model earns that eligibility.
- [x] Grep-style check (script or test) confirming no docstring, log message, or README line outside `ECON-005`'s own gated success-path module contains language implying current profitability.
- [x] OpenAPI-level description strings on `POST /simulations` (FastAPI's `summary`/`description` fields) state the eligibility precondition in plain language — a caller reading `/docs` before calling the endpoint should understand why they'll likely get refused, without needing to read this ticket or the backlog.

## Test acceptance criteria
- [x] The grep-style check runs as a real pytest test (not just a standalone script nobody calls in CI) — confirms current repo state passes.
- [x] Drift-detection demonstration performed by the dev agent and reported: temporarily inject a forbidden word (e.g. "profitable") into a file outside the allowed module, confirm the check fails, revert, confirm it passes again — mirroring NFE-018/LC-005/VS-016's own precedent for proving the check actually detects drift, not just trivially passing on an empty pattern list.
- [x] `.venv\Scripts\python.exe -m pytest -q` passes with zero failures, no regression on prior tickets' tests.

## Review acceptance criteria
- Tech Lead will personally re-run the drift-detection demonstration (inject → confirm fail → revert → confirm pass), not trust the dev agent's report alone, matching this repo's own NFE-018/LC-005/VS-016 precedent.
- Tech Lead will read the full rewritten README directly and confirm it: (a) states both verified upstream facts (no model has ever beaten naive on this platform; VS-017 is unbuilt), (b) states ECON-004's hard mock-only rule for future tickets, (c) carries the "statistical accuracy ≠ economic value" framing in CLAUDE.md's own language, not softened.
- Tech Lead will open `/docs` (or read the FastAPI route decorator source directly) and confirm `POST /simulations`'s `summary`/`description` states the eligibility precondition in plain language.

## Documentation acceptance criteria
- [x] `README.md` full rewrite lands as part of this ticket (not deferred) — this IS the documentation acceptance criterion for this ticket, in addition to the Implementation AC above (both point at the same file/change; listed in both sections because the backlog treats "no profitability language" as both a code-adjacent and a documentation concern).

## Sequencing note
Runs last — depends on ECON-001 and ECON-005; its own grep check needs ECON-005's guard/route code to exist to scan for stray profitability language outside the one gated success path.

## Outcome

**Files created:**
- `services/economic-service/scripts/check_profitability_language.py` — the grep-style forbidden-profitability-language check (standalone script, mirrors NFE-018/LC-005/VS-016's script+pytest-wrapper structure).
- `services/economic-service/tests/test_profitability_language.py` — pytest entry point for the script above, plus targeted unit tests of the scan/allowlist logic itself.

**Files changed:**
- `services/economic-service/README.md` — full rewrite (not a status-line edit). Restructured under a new "What this service is" opening section carrying CLAUDE.md's own "statistical accuracy != economic value" / "never imply price prediction or trading signals" language verbatim, and stating this service *will* compute cost/slippage-adjusted returns once — and only once — a real model earns eligibility. Confirmed present: (a) both verified upstream facts ("No model has ever beaten naive on this platform" and "`VS-017` ... is itself deferred and unbuilt"), (b) ECON-004's hard mock-only rule (restated verbatim under "Why this service is being built ahead of its own trigger"), (c) all prior accurate technical content from ECON-001–ECON-005 (Scaffolding/Schema/Contracts/Upstream integration/eligibility gate), preserved and re-flowed under the new framing rather than deleted, plus a new closing "No profitability language outside the gate (ECON-006)" section describing this ticket's own check.
- `services/economic-service/src/app/routers/simulations.py` — added `summary`/`description` to the `@router.post("/simulations", ...)` decorator, stating the two-condition eligibility precondition in plain language and that every real call today refuses (verified live via `app.openapi()`).

**Decision: script + pytest wrapper, not a pytest-only test.** Mirrors the NFE-018/LC-005/VS-016 precedent this ticket's DRY check note points at — keeps the check runnable standalone (`python scripts/check_profitability_language.py`, exit code 0/1) as well as via `pytest tests/test_profitability_language.py`.

**Exact forbidden-pattern list** (word-boundaried regex, case-insensitive), with reasoning for each, from `check_profitability_language.py`'s own module docstring:
- `profitable` — direct adjective claim.
- `profit` (bare noun/verb only — `\bprofit\b` does not match inside `profitability`, since there's no word boundary between "profit" and "ability"). Deliberately excludes "profitability" itself: that noun is this codebase's own established, correct vocabulary for describing the gate's purpose ("a profitability figure/column/output/computation/claim/field never exists yet") throughout `models.py`, `contracts.py`, `interfaces.py`, `eligibility.py`, and the old README.
- `alpha` — CLAUDE.md's own named term ("selling the rigor ... not alpha"). Zero current matches.
- `beats the market` / `beat the market` — CLAUDE.md's own phrase.
- `makes money` / `make money` — plain-language near-synonym named in the ticket.
- `returns money` / `return money` — plain-language near-synonym named in the ticket. Deliberately does NOT forbid the bare word "return(s)" — that is this codebase's normal, legitimate domain vocabulary (`cost_adjusted_return`, "cost/slippage-adjusted returns") used correctly dozens of times outside `eligibility.py`; only the "money" collocation asserts an actual monetary gain.
- `generate(s) real returns` — the exact assertion phrasing the ticket's own instructions used ("DOES generate real returns") to name the forbidden claim, distinct from the allowed conditional "will compute ... once eligibility" framing.

**How the concept-vs-claim line was drawn**: rather than a fuzzy negation-word heuristic (rejected — fragile, hard to audit, prone to both false positives and false negatives on a long line), the check uses a small, hand-curated, documented `_ALLOWED_EXCEPTIONS` list of exact substrings, each with an inline reason in the script, covering every current legitimate concept-discussion usage found by hand-grepping the codebase before writing the pattern list (per the ticket's DRY-check instruction). Currently two entries: (1) README.md's own CLAUDE.md-mandated disclaimer sentence ("must never be read as evidence the platform currently has a profitable model" — the exact concept-discussion use this whole ticket exists to permit), and (2) `contracts.py`'s quoted `"no profit"` string describing the serialization-bug failure mode `NotEligibleForSimulation`'s design prevents. This fails safe: any new, un-allowlisted "profit"/"profitable"/etc. mention is flagged for human review rather than silently passed by a loose heuristic.

**Scan scope**: `README.md` plus every `.py` file under `src/app`, excluding `src/app/eligibility.py` entirely (the ticket names the whole module — its module docstring and `compute_economic_simulation`'s own docstring — as the one allowed exception, so the script never opens that file).

**Drift-detection demonstration** (mirroring NFE-018/LC-005/VS-016 precedent): injected the line `# DRIFT-INJECTION TEST (ECON-006): this service is currently profitable.` into `src/app/models.py` (outside the allowed `eligibility.py` exception), immediately after the `Base` class definition.

Before revert, `python scripts/check_profitability_language.py`:
```
Forbidden profitability-claim language found outside src/app/eligibility.py's allowed exception:

  - src/app/models.py:40: forbidden term 'profitable' -- # DRIFT-INJECTION TEST (ECON-006): this service is currently profitable.

1 hit(s). Reword the line(s) above, or if this is a genuinely new legitimate concept-discussion use (mirroring the existing entries in _ALLOWED_EXCEPTIONS), add it there with a documented reason.
```
Exit code: `1`. `pytest -q tests/test_profitability_language.py` with the injection present: `1 failed, 5 passed` (the `test_no_profitability_claim_language_outside_eligibility_module` test failed with the same message).

After reverting `models.py` to its pre-injection content, `python scripts/check_profitability_language.py`:
```
No forbidden profitability-claim language found outside src/app/eligibility.py.
```
Exit code: `0`.

**Test count**: `.venv\Scripts\python.exe -m pytest -q` from `services/economic-service/` — **50 passed** (44 pre-existing from ECON-001–ECON-005, plus 6 new in `tests/test_profitability_language.py`). Zero regressions, zero failures.

**Acceptance criteria not met**: none. All Implementation/Test/Documentation acceptance criteria above are checked off and were personally verified (check run standalone and via pytest, drift demonstration performed and reported with literal output above, full suite run and passing, `/simulations`'s live `app.openapi()` schema inspected directly to confirm `summary`/`description` are present).
