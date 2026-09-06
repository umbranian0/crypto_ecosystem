# DASH-120 — `run_new_submit`'s 422 redisplay loses the stored-dataset dropdown

**Status**: done. Found live, same investigation session as DASH-119, while
manually reproducing a real user's split-cap rejection.

## Analysis

Every error branch in `POST /runs/new` (`services/dashboard-web/src/app/routers/runs.py`,
`run_new_submit`) that redisplays `run_new.html` after a validation failure --
missing dataset reference, invalid inline JSON, invalid horizon/purge_gap/
train_window/test_window/step, or gateway-api's own `422` (most commonly
RSS-004's "exceeds 500 splits" guardrail) -- hardcoded `"datasets": []` in the
template context instead of re-fetching the tenant's real stored-dataset list
via the existing `_fetch_ingestion_datasets` helper (`run_new_form`'s own
fetch, DASH-108/DASH-111).

Effect: any user submitting a run against a **stored dataset** who hits *any*
validation error saw the "Stored dataset" fieldset collapse to "No ingested
datasets yet -- run a crawl first" -- even though they had one, and even
though `values.dataset_reference_source` (their prior selection) was
correctly preserved in the redisplay's `values` dict. The dropdown itself
just never had that option to select, silently discarding the choice and (as
a direct consequence) preventing RSS-002's live split-count estimator from
having anything to compute against on redisplay, since it depends on the
dropdown's `data-row-count` attribute.

Reproduced against the real running stack: a stored-dataset run submission
computing 39,550 splits (real `binance_price_btcusdt_1h` dataset, 79,180
rows) correctly got gateway-api's `422` rejection, but the redisplayed page
showed "No ingested datasets yet" instead of the dropdown with the dataset
re-selected.

## Design

Fix scope: `run_new_submit` only, `services/dashboard-web/src/app/routers/runs.py`.
Open one `httpx.Client` at the top of the function (previously opened only
around the final downstream `/runs` call) so every error-return path,
including the two that occur before any client existed, can call
`_fetch_ingestion_datasets(client, headers)` and pass the real list instead
of `[]`. No second fetch implementation -- reuses the existing DASH-111
helper `run_new_form` already shares with `datasets_list`. No change to
`run_new_form` (`GET /runs/new`) itself, which already fetched correctly.

DRY check: grepped for other hardcoded `"datasets":` occurrences in this
module before fixing -- all four were in this one function, no fifth
copy elsewhere.

## Implementation acceptance criteria

- [x] All four `422`-redisplay branches in `run_new_submit` re-fetch and pass
      the real stored-dataset list instead of `[]`.
- [x] No change to `run_new_form`'s existing (already-correct) fetch.
- [x] No second `_fetch_ingestion_datasets`-equivalent implementation added.

## Test acceptance criteria

- [x] Existing 422-path tests (`test_run_new_submit_no_dataset_reference_redisplays_form`,
      `..._invalid_inline_json_redisplays_form`, `..._invalid_horizon_redisplays_form`,
      `..._422_from_gateway_api_redisplays_form`) updated to answer
      `GET /ingestion/datasets` and assert the dataset survives the redisplay.
- [x] New regression test `test_run_new_submit_split_cap_422_preserves_stored_dataset_selection`
      reproduces the exact real-world scenario (RSS-004-shaped 422, stored
      dataset reference) and asserts the option is both present and
      re-`selected`.
- [x] Full `services/dashboard-web` suite passes: 229 passed, 5 deselected
      (e2e), zero regressions.

## Live verification (per the updated `/qa-validation` skill, DASH-119's own
follow-up)

Reproduced directly against the real running stack (not just the test
suite): restarted the local `dashboard-web` process from the real repo
checkout, issued a temporary diagnostic API key for the tenant that owns the
real oversized dataset, and replayed the exact failing form submission via
curl. Before the fix: dropdown collapsed to "No ingested datasets yet" (`git
stash` confirmed old behavior). After the fix: the response includes the
full re-rendered `<option value="binance_price_btcusdt_1h" ... selected>`
with its real `data-row-count="79180"` attribute intact, alongside the
`422` error text. Diagnostic API key revoked after verification; no
production data modified.

## Documentation

- [x] This ticket.
- [x] `docs/tickets/README.md` (Sprint/ticket index).
- [x] `services/dashboard-web/README.md` status block.
