# CHORE-66-05 -- dashboard-web: honest "sample data" wording

**Status: done.** Sprint 66 item 1. Module: services/dashboard-web. After CHORE-66-04.

## Analysis
`POST /demo-run` (`src/app/routers/demo.py`) shows "Sample data is not loaded for this tenant. Ask your operator to seed it." when `binance_price_btcusdt_1h` is absent; the dataset list comes from materialized views refreshed every ~5 min, so a just-seeded tenant sees it falsely, and a genuine seed failure shows it too. `setup_key_reveal.html` line ~13 says "New tenants are loaded with sample data automatically", false on a checkout without the archive. Decision (orchestrator): honest wording, NOT refresh-on-seed.

## Design
String changes only. New demo copy covers both cases without claiming either, e.g. "Sample data for your tenant may still be loading (it can take up to about 5 minutes after tenant creation). Try again shortly; if it still does not appear, ask your operator." ONB-001 sentence softened: "...loaded automatically; it can take a few minutes to appear". Wording stays about validation protocol mechanics; no prediction/signal/value implication. DRY: if a message is defined once, edit once.

## Implementation AC
New copy in demo.py and setup_key_reveal.html; no behaviour change.

## Test AC
Update tests/test_demo_run.py (~line 129) and any test asserting the ONB-001 sentence (grep old strings across tests). Full dashboard-web suite green (Sprint 65 recorded "481 passed / 8 deselected"; find the deselect option in the README/pytest config).

## Review AC (TL)
Old strings gone across src, tests, docs; read diff; rerun suite.

## Documentation AC
services/dashboard-web/README.md (line ~2844 area) updated. TL marks the Sprint 62 "Known follow-up" note in docs/tickets/README.md resolved by wording.

## Rules
dashboard-web has no DB access; never run anything against live `naive_first`. Do not git commit. Stay in the module.
