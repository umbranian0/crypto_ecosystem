# DASH-118 — Richer progress display, replacing the three-state badge

**Module**: `services/dashboard-web`. **Depends on**: `INGEST-024`/`025`/`026`/`027` and `GW-028` (all
done, Sprint 23 — the progress/`updated_at` fields this ticket reads) and `DASH-116` (run immediately
before this ticket, same file `_crawl_status_panel.html` — sequenced last specifically to avoid two
stories concurrently editing that partial, per `docs/sprints/sprint-24.md`).

## Analysis

Covers `docs/product/backlog-crawl-lifecycle-control.md`'s `DASH-118` story (Should priority). The
backend already returns `rows_fetched_so_far`/`updated_at` on `GET /connectors/{source}/status`
(`INGEST-024`), forwarded unmodified through `GET /ingestion/connectors/{source}/status`
(`GW-028`, confirmed pass-through, no gateway-api code change needed) — both fields are `null` for
`blockchain_info_*` sources while running (`INGEST-027`'s documented before/after-only progress
ceiling), never a fabricated `0`. `dashboard-web`'s own `_fetch_crawl_statuses` (`operator.py`) already
spreads the full forwarded status dict (`**status_response.json()`) into each entry, so
`rows_fetched_so_far`/`updated_at` are already present on `crawl_statuses` entries today with zero
fetch-side code change — this ticket is a render-side addition only.

Hard acceptance criteria from `docs/sprints/sprint-24.md`, restated as binding: progress column shows a
plain "no live progress for this source" string for blockchain.info sources — never a blank cell or a
fabricated zero; no progress-display copy implies a prediction/forecast of remaining time or rows
(CLAUDE.md's core positioning rule applies here even though this is an operational, not modeling,
surface — e.g. no "ETA," no "time remaining," no "estimated completion").

## Design

**Pattern**: none from implementation-plan.md section 7 applies. Progress-string formatting is plain
presentation logic; per this repo's own convention (e.g. `_crawl_trigger_result.html`'s server-built
copy), format the display string in Python (`operator.py`) rather than in Jinja, so it is directly unit
testable without a template-render harness.

**Files touched** (scoped to `services/dashboard-web` only):
- `services/dashboard-web/src/app/routers/operator.py` — new `_format_progress(entry: dict, now:
  datetime) -> str` helper, called from `_fetch_crawl_statuses` to add a `progress_display` key to each
  entry before it's returned (single call site serves both `monitoring()`'s initial render and
  `crawl_status_fragment`'s polling render, since both already share `_fetch_crawl_statuses` unmodified —
  no second progress-formatting implementation for the two call sites).
- `services/dashboard-web/src/app/templates/_crawl_status_panel.html` — new "Progress" column in the
  table header and one `<td>{{ entry.progress_display }}</td>` per row.
- `services/dashboard-web/tests/test_monitoring.py` (or a new `tests/test_crawl_progress.py`, dev
  agent's call, consistent with this file's existing test-file-per-concern precedent) — unit tests for
  `_format_progress` directly, plus template-render assertions.
- `services/dashboard-web/README.md` — new "Progress column (DASH-118)" subsection.

**DRY check note** (grepped `_fetch_crawl_statuses`/`_crawl_status_panel.html` before writing this
ticket): `_fetch_crawl_statuses` is extended, not duplicated — both `monitoring()` and
`crawl_status_fragment()` already call this one function and will pick up `progress_display` for free.
The existing `status` column/cell is left rendering `entry.status` verbatim (already a distinct literal
string per status value, satisfying the sprint's "equally clear labels, not folded into an ambiguous
reuse" requirement by construction — no restyling is required by the acceptance criteria, and none is
added, to keep this ticket's diff minimal and reduce collision risk with any future styling ticket).

## Implementation acceptance criteria

- [x] `_format_progress(entry, now)`: if `entry.get("rows_fetched_so_far")` is `None` (blockchain.info
      sources, or any source with no progress data yet recorded), returns the literal string
      `"no live progress for this source"` — never an empty string, never `"0 rows"`.
- [x] If `rows_fetched_so_far` is present (not `None`), returns a string containing the row count and a
      relative "updated Ns ago" (or Nm/Nh ago for longer gaps) derived from `updated_at`, e.g.
      `"143000 rows fetched so far, updated 3s ago"`. `updated_at` is parsed via
      `datetime.fromisoformat`; `now` is injected as a parameter (not read via `datetime.now()` inside the
      helper) so the function is deterministically unit-testable without monkeypatching the clock.
- [x] If `rows_fetched_so_far` is present but `updated_at` is missing/unparseable (a defensive case, not
      expected from a correct backend), the helper still returns the row count without fabricating a time
      phrase — degrade gracefully, never raise, never silently show a wrong "ago" value.
- [x] No returned string anywhere contains any of: "eta", "estimated completion", "time remaining",
      "prediction", "forecast" (case-insensitive) — a direct, literal check against CLAUDE.md's
      never-imply-prediction rule for this specific helper's output space, not just the static template
      text.
- [x] `_crawl_status_panel.html`'s new "Progress" column renders `entry.progress_display` for every row,
      including `queued`/`cancelling`/`cancelled`/`failed` rows (a source with no progress data at any
      status shows the same honest "no live progress for this source" or whatever `_format_progress`
      computed for its actual `rows_fetched_so_far`/`updated_at` values — no status-based special-casing
      inside the template itself, only inside `_format_progress`).
- [x] Existing three status values' (`queued`/`completed`/`failed`) visual treatment is otherwise
      unchanged; `running`/`cancelling`/`cancelled` continue to render as their own literal strings (no
      new CSS/styling introduced by this ticket beyond the new column).

## Test acceptance criteria

- [x] Unit tests for `_format_progress` directly (no HTTP/template layer needed for these): `None` rows
      count → the exact honest-absence string; a present row count + recent `updated_at` → contains the
      row count and a small "ago" value; a present row count + missing/malformed `updated_at` → contains
      the row count, does not raise.
- [x] A test proves none of the banned prediction/forecast/ETA words appear in any `_format_progress`
      output across the tested input cases (a non-tautological, literal string-absence check).
- [x] A template/route-level test proves a `blockchain_info_*`-shaped stubbed status response (progress
      fields `null`) renders "no live progress for this source" in `GET /monitoring`'s response body, and
      a Binance-shaped stubbed response (progress fields present) renders the row count.
- [x] Tech Lead's own re-run (superseding the dev agent's earlier, mid-session snapshot which had
      observed one transient failure in unrelated, concurrently-edited `RAV-003` files this ticket never
      touches): `uv run pytest -q` → **167 passed, 5 deselected, 0 failed** — zero regressions, the
      concurrent-session file had since settled.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Confirmed `_format_progress` is called exactly once, inside `_fetch_crawl_statuses` — not
      duplicated in `monitoring()`/`crawl_status_fragment()` (both already share that one function).
- [x] Read both branches' literal copy — neither implies a prediction/forecast/remaining-time claim;
      confirmed against the explicit banned-word list and by direct reading.
- [x] Confirmed `now: datetime` is a required parameter, never read via `datetime.now()` inside the
      function body.
- [x] Live-stack verification performed as part of this sprint's combined final proof (see Sprint 24
      outcome, `docs/tickets/README.md`).
- [x] Full test suite run directly: 167 passed, 5 deselected, 0 failed.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md` gains a "Progress column (DASH-118)" subsection documenting:
      the new `progress_display` field's computation (`_format_progress`, single call site in
      `_fetch_crawl_statuses`), the honest-absence string and which sources trigger it
      (`blockchain_info_*`, per `INGEST-027`), and an explicit restatement of the no-prediction-implied
      constraint so a future editor of this column doesn't casually add an ETA.
