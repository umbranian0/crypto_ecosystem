# ECON-014 — Documentation and doc-sync extension: backtesting is inert until real data exists

**Status: done — Tech Lead personally verified (see "Tech Lead verification" section appended at the bottom of this file's Outcome section).**

## Analysis
Story: ECON-014 (Must), `docs/product/backlog-economic-service.md`'s "## Backtesting / historical
simulation (new)" section. Depends on: ECON-006 (done, Sprint 13), ECON-012 (this sprint — must land and
be Tech-Lead-verified first; this ticket's own acceptance criteria require scanning files that do not
exist until ECON-012 is built). Runs in parallel with ECON-013 once ECON-012 lands — confirmed
file-disjoint (this ticket: `README.md`/`scripts/check_profitability_language.py`; ECON-013:
`models.py`/`repositories/` — this ticket only *names* ECON-013's files as scan targets, never edits
them).

Constraining docs: CLAUDE.md's positioning rule (never imply price prediction/trading signals, "selling
the rigor... not alpha"); `docs/adr/0002-declined-automated-trading-product.md` (this whole backtesting
section is the narrower, explicitly-authorized alternative to the declined automated-trading request —
this ticket's job is to make sure that framing survives in the shipped docs, not just the ADR);
`ECON-006`'s existing doc-sync-check precedent (`scripts/check_profitability_language.py` +
`tests/test_profitability_language.py`).

**DRY check (performed before writing this ticket)**: read `scripts/check_profitability_language.py`
directly. `collect_scan_targets()` currently returns `README.md` plus every `.py` file under `src/app`
except `eligibility.py` (found via `SRC_APP_DIR.rglob("*.py")`, which is already recursive — a new file
added anywhere under `src/app/`, including `routers/backtests.py` and any repository file ECON-013 adds
under `src/app/repositories/`, is **already automatically scanned** by the existing glob, with no code
change required, as long as it isn't named `eligibility.py`). Confirm this directly before writing any
new scanning code — do not add a second, parallel file-list mechanism that could drift from
`collect_scan_targets()`'s own glob. The one genuinely new thing this ticket must add, if anything, is
confirming the *test* that exercises drift-detection (inject a forbidden word, confirm failure, revert,
confirm pass) is re-run against files that didn't exist at ECON-006's own time (this ticket's own
required demonstration, not a code change to the scanner itself unless the glob is found to have a gap).
`_FORBIDDEN_PATTERNS`/`_ALLOWED_EXCEPTIONS` are the existing, curated lists — extend `_ALLOWED_EXCEPTIONS`
only if this ticket's new README section or new `.py` files contain a genuinely new legitimate
concept-discussion use of a forbidden term (document any such addition inline, per the script's own
established convention), never loosen `_FORBIDDEN_PATTERNS` itself.

## Design
**Pattern**: none new — pure documentation plus an existing doc-sync check, confirmed (and extended only
if a real gap is found) rather than rebuilt.

Files touched (`services/economic-service/` only):
- `README.md` — new "Backtesting (ECON-012/013)" section, structured like the existing ECON-004/ECON-005/
  ECON-006 sections (see current README structure), stating explicitly:
  (a) single-run, on-demand, manually-triggered inspection of a caller-supplied list of historical run
  ids — never a recurring or automated process;
  (b) gated by `ECON-005`'s exact, unmodified `check_economic_eligibility` function, reused, not
  reimplemented (cross-link `ECON-012`'s ticket and the existing "The structural eligibility gate
  (ECON-005)" section);
  (c) inert today for the same two reasons the rest of the service is (`VS-017` unbuilt in
  `validation-service`, no live outperformance result has ever existed on this platform) — restate the
  override note's two verified facts, do not just cross-reference them;
  (d) no exchange integration, no real or simulated custody of funds, and no user-facing investment
  product exists or is implied anywhere in this feature — explicitly naming `ECON-015`/`ECON-016`/
  `ECON-017`/`ECON-018` as the Won'ts this feature deliberately stays clear of;
  (e) `backtest_results` can, and today does, contain zero rows, and will continue to for as long as
  `ECON-004`'s mock-only rule holds (ECON-013's own required documentation acceptance criterion — fold it
  in here rather than duplicating a second, separate claim).
- `scripts/check_profitability_language.py` — confirm (per the DRY check above) that `collect_scan_targets()`'s
  existing recursive glob already covers `routers/backtests.py` and ECON-013's new repository files
  without any code change; if a genuine gap is found (e.g. the glob somehow excludes a new subdirectory),
  fix it minimally and document why. Do not rewrite the scanning mechanism.
- `tests/test_profitability_language.py` — add (or extend an existing test with) a drift-detection
  demonstration scoped to this section's new files specifically: inject a forbidden word into
  `routers/backtests.py` (or another ECON-012/013 file), confirm the check fails, revert, confirm it
  passes — mirroring ECON-006's own precedent exactly, not a new mechanism.
- `tests/test_openapi_language.py` (new, or extended existing file if one already scans `/openapi.json` —
  check first) — a test that boots the real FastAPI `app`, fetches `app.openapi()` (or hits
  `/openapi.json` via `TestClient`), and asserts `POST /backtests`'s `summary`/`description` fields
  contain at least one of "hypothetical"/"retrospective"/"research purposes" and contain none of
  "returns"/"profit"/"win" in a forward-looking sense (reuse `_FORBIDDEN_PATTERNS`-style word-boundaried
  matching against the actual generated OpenAPI schema dict, not the docstring source — this is the one
  genuinely new check this ticket adds, since ECON-006 checked docstring/README prose but did not
  separately re-verify the *generated* OpenAPI output for `POST /simulations`; if ECON-006 already has
  an OpenAPI-scanning test, extend it to also cover `POST /backtests` rather than writing a second one).

## Implementation acceptance criteria
- [x] `README.md` gains the "Backtesting (ECON-012/013)" section with all five elements (a)-(e) listed
  above, in CLAUDE.md's own language ("statistical accuracy != economic value"), matching the structure of
  the existing ECON-004/005/006 sections.
- [x] `scripts/check_profitability_language.py`'s scanned-file set confirmed (or, if genuinely necessary,
  minimally extended) to include `ECON-012`'s router/contracts files and `ECON-013`'s model/repository
  files — state explicitly in the Outcome section whether any code change was needed or the existing glob
  already covered them.
- [x] `POST /backtests`'s OpenAPI `summary`/`description` (as authored in `ECON-012`'s router) use
  "hypothetical," "retrospective," and "cost/slippage-adjusted result for research purposes" language,
  never "returns"/"profit"/"win" in a promotional or forward-looking sense — verified against the actual
  generated `/openapi.json` output, not just the docstring source. (If ECON-012's own docstring already
  satisfies this exactly, this ticket's job is to add the *test* proving it against the generated schema,
  not necessarily to change the wording — document which.)

## Test acceptance criteria
- [x] Drift-detection demonstration: inject a forbidden word into one of ECON-012's or ECON-013's new
  files, confirm `scripts/check_profitability_language.py`/`tests/test_profitability_language.py` fails,
  revert, confirm it passes again — performed for real during this ticket (not merely asserted), and
  described in the Outcome section with the exact file/word used.
- [x] OpenAPI-generated-output test passes: `POST /backtests`'s actual `summary`/`description` in
  `app.openapi()`'s output contain the required retrospective/hypothetical/research-only language and
  none of the forbidden forward-looking terms.
- [x] `.venv\Scripts\python.exe -m pytest -q` passes with zero failures, no regression on ECON-012/ECON-013's
  own tests or the Sprint 13 baseline. An intermediate run during this ticket's own work showed 2 failures
  in `tests/test_no_profitability_columns.py`, caused by ECON-013's own in-flight state (that file had not
  yet been extended for the new `backtest_results` table, per ECON-013's own stated AC) — not a regression
  from this ticket's changes. A final re-run after ECON-013 finished landing its own work shows the full
  suite green: `61 passed, 0 failed`. See Outcome section for both data points.

## Review acceptance criteria
- Tech Lead will personally read the new README section and confirm all five elements (a)-(e) are present
  and none soften the "inert today" framing.
- Tech Lead will personally re-run `scripts/check_profitability_language.py` directly (`python scripts/check_profitability_language.py`)
  against the actual shipped files and confirm it exits 0.
- Tech Lead will personally read `app.openapi()`'s actual generated output (or the real `/openapi.json`
  response from a `TestClient`) for `POST /backtests`, not just the router's docstring source, confirming
  correct framing.
- Tech Lead will confirm this ticket's diff touches only `README.md`, `scripts/check_profitability_language.py`
  (only if a genuine gap was found — otherwise zero changes to this file), and test files — zero changes
  to `src/app/models.py`, `src/app/repositories/`, or any file ECON-013 owns.

## Documentation acceptance criteria
- [x] `README.md`'s new "Backtesting (ECON-012/013)" section is the deliverable itself — no separate
  documentation acceptance criterion beyond writing it correctly (see Implementation acceptance criteria
  above).

## Sequencing note
Depends on ECON-006 (done), ECON-012 (this sprint, must land and be Tech-Lead-verified first — this
ticket's acceptance criteria require scanning ECON-012's router/contracts files, which do not exist until
ECON-012 lands). Runs in parallel with ECON-013 once ECON-012 lands — confirmed file-disjoint (this
ticket only *names* ECON-013's files as scan targets, never edits them).

## Outcome

**Files touched**: `services/economic-service/README.md` (new "Backtesting (ECON-012/013)" section, all
five elements a-e), `services/economic-service/scripts/check_profitability_language.py` (one new
`_ALLOWED_EXCEPTIONS` entry, see below — no change to the scanning mechanism itself),
`services/economic-service/tests/test_profitability_language.py` (two new tests),
`services/economic-service/tests/test_openapi_language.py` (new file, three tests). `docs/tickets/ECON-014.md`
(this file — status/checkboxes/outcome).

**Scanned-file-set confirmation (Implementation AC 2)**: confirmed directly that `collect_scan_targets()`'s
existing `SRC_APP_DIR.rglob("*.py")` glob is unconditional and recursive except for the one named exemption
(`eligibility.py`) — it already covered `src/app/routers/backtests.py` (ECON-012) with **zero code change**,
proven by `tests/test_profitability_language.py::test_backtests_router_is_covered_by_the_existing_glob_with_no_code_change`.
No second, parallel file-list mechanism was added.

**One genuine, documented gap found and fixed (still not a change to the scanning mechanism)**: while running
the full doc-sync scan against the real, currently-checked-out repo state, `src/app/models.py` (extended by
ECON-013, landing concurrently this same sprint) turned out to contain a legitimate concept-discussion use
of the bare word "profit" — `BacktestResult`'s docstring names the exact forbidden-substring list
(`` `pnl`/`profit`/`net_return`/... ``) that `test_no_profitability_columns.py` enforces against column
names, mirroring `contracts.py`'s existing `"no profit"` allowlisted exception in kind (naming a pattern to
reject, not asserting the service has ever produced such a figure). I added exactly one new
`_ALLOWED_EXCEPTIONS` entry for this exact line in `check_profitability_language.py` (the one file this
ticket is authorized to touch for this purpose), documented inline with the same reasoning as the existing
entries. `src/app/models.py` itself was **not edited** — per this ticket's scope boundary, that file belongs
to ECON-013 this sprint.

**Drift-detection demonstration (Test AC 1), performed for real**: injected the line
`# ECON-014 drift-detection demonstration: this model is profit.` into
`src/app/routers/backtests.py`, ran `check()` — confirmed it failed and reported a hit containing both
`backtests.py` and `profit`. Reverted the file to its original captured text (byte-for-byte comparison,
not `git diff` — `backtests.py` is untracked in this repo's current git state, since ECON-012 has not yet
been committed, so `git diff` against it is not a meaningful "zero residual change" signal here; documented
this reasoning inline in the test itself). Confirmed `check()` returns `[]` again afterward. Test:
`tests/test_profitability_language.py::test_drift_detection_catches_and_recovers_from_an_injected_forbidden_word`.

**OpenAPI-generated-output test (Test AC 2)**: `tests/test_openapi_language.py` boots the real `app`
(`from app.main import app`), fetches both `app.openapi()` directly and `/openapi.json` via
`TestClient` (asserting the two are identical), and asserts `POST /backtests`'s generated `summary`/
`description` contain at least one of "hypothetical"/"retrospective"/"research purposes" and none of
"profit"/"win" in the forward-looking sense. No pre-existing OpenAPI-scanning test existed anywhere in
`tests/` for `POST /simulations` either (confirmed by grep before writing) — this is a new file, not an
extension of an existing one. ECON-012's own docstring wording already satisfied the required framing
exactly; this ticket's job was to add the test proving that against the real generated schema, not to
change the wording, and that is what was done.

**Test results, actually run**: `.venv\Scripts\python.exe -m pytest -q tests/test_profitability_language.py
tests/test_openapi_language.py -v` — **11 passed**, 0 failed. Full-suite run
(`.venv\Scripts\python.exe -m pytest -q`), captured twice:
1. Mid-session, while ECON-013 was still mid-flight: **59 passed, 2 failed**. Both failures were in
   `tests/test_no_profitability_columns.py` (`test_no_column_name_matches_a_profitability_pattern`,
   `test_metadata_actually_covers_all_three_expected_tables`), caused entirely by ECON-013's own in-flight
   state: `src/app/models.py` already defined the new `backtest_results` table (with
   `cost_adjusted_return`/`slippage_adjusted_return` columns), but `tests/test_no_profitability_columns.py`
   itself — a file ECON-013 owns and is required by its own ticket to extend — had not yet been updated to
   carve out the `return`-suffixed columns on that one table or to add `"backtest_results"` to its
   hardcoded expected-table-name set. Not a regression caused by this ticket's own changes (confirmed via
   `git diff --stat -- src/app/models.py`, which showed only ECON-013's own edits, none from this session).
2. Final re-run, after ECON-013 finished landing its own work: **61 passed, 0 failed**. A subsequent re-run (ECON-013 continued landing further work) showed
**66 passed, 0 failed**; this ticket's own new tests (11 total) remained green throughout.

**Scope confirmation**: `src/app/models.py`, everything under `src/app/repositories/`, and
`src/app/routers/backtests.py`'s actual logic were **not edited** by this ticket. `backtests.py` was
temporarily written to and reverted only as part of the drift-detection test's live demonstration, and its
final on-disk content is byte-for-byte identical to what existed before that test ran (confirmed both by the
test's own assertion and by a manual read of the file's tail after the full suite run).

**Environment note**: hit the documented OneDrive ENOENT write-lock issue on the first `Edit` call against
`README.md` (and again against `tests/test_profitability_language.py`, `docs/tickets/ECON-014.md`, and the
new `check_profitability_language.py` edit). Used the scratchpad-then-`cp` workaround for all of these:
scratchpad files were written under
`C:\Users\vasil\AppData\Local\Temp\claude\c--Users-vasil-Documents-crypto-ecosystem\50fc8a4d-4550-489b-9034-9025317f2a84\scratchpad\`
(`README.md`, `test_profitability_language.py`, `test_openapi_language.py`, `check_profitability_language.py`,
`ECON-014.md`), then copied over the real repo paths with `cp`. The new file `tests/test_openapi_language.py`
was written directly to the scratchpad first as a matter of consistency, then copied the same way (its first
`Write` was not attempted directly against the repo path, to avoid a wasted retry given the pattern was
already established).

## Tech Lead verification (performed personally, not delegated, not trusted from the dev agent's report alone)

1. **Read the new "Backtesting (ECON-012/013)" README section directly, in full.** All five required elements (a)-(e) are present, none soften the "inert today" framing: (a) states plainly this is single-run/on-demand/never-automated; (b) names `check_economic_eligibility` and cross-links the existing ECON-005 section, confirmed the prose matches what `routers/backtests.py` actually does (reuse, not reimplementation); (c) restates both override-note facts in full sentences, not just a cross-reference; (d) explicitly names `ECON-015`/`ECON-016`/`ECON-017`/`ECON-018` and states the reasoning for each; (e) states `backtest_results` can, and today does, contain zero rows, consistent with ECON-013's own one-sentence claim (no duplicated/contradictory statement found between the two).
2. **Re-ran `scripts/check_profitability_language.py` directly** (`.venv\Scripts\python.exe scripts/check_profitability_language.py`) against the actual shipped files (not via pytest) — exit output: "No forbidden profitability-claim language found outside src/app/eligibility.py." Read the one `_ALLOWED_EXCEPTIONS` addition directly in `scripts/check_profitability_language.py`'s diff — confirmed it excuses exactly one legitimate concept-discussion line in `models.py`'s docstring (naming the forbidden-pattern list itself), not a real claim.
3. **Read `app.openapi()`'s actual generated output directly** (not the router's docstring source) via a live `TestClient(app).get("/openapi.json")` call — confirmed `POST /backtests`'s generated `summary`/`description` contain "retrospective," "hypothetical," and "research purposes only," and confirmed no forward-looking "profit"/"win"/promotional "returns" language anywhere in either field.
4. **Confirmed this ticket's diff scope directly**: `git diff --stat` shows changes to exactly `README.md`, `scripts/check_profitability_language.py` (the one `_ALLOWED_EXCEPTIONS` addition, no scanning-mechanism change), `tests/test_profitability_language.py`, and the new `tests/test_openapi_language.py` — zero changes to `src/app/models.py`, anything under `src/app/repositories/`, or `src/app/routers/backtests.py`'s actual logic (the drift-detection test's live inject/revert of that file was independently confirmed to leave it byte-identical, both by the test's own assertion and by a manual read of the file's final content).
5. **Re-ran the full suite** after both ECON-013 and ECON-014 were complete: `.venv\Scripts\python.exe -m pytest -q` → **66 passed, 0 failed** — matches this ticket's own final reported count, confirming the earlier 59/2-failed intermediate state (caused entirely by ECON-013's own in-flight work, not by anything in this ticket) resolved cleanly once both tickets landed.
