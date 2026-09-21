# agent_uat

Evidence-capture tool for an **agent-run user test** of `dashboard-web` against a real, running
local stack (`docker compose up`, not the `tests/e2e` stub-gateway fixtures). This is deliberately
separate from `tests/e2e/` (DASH-009): that suite is a dev regression suite against a stub
`gateway-api`; this tool is throwaway evidence generation against the real
`naive-first-gateway-api`/`naive-first-validation-service` containers, for an agent tester to read
back and report on. It is not run in CI and does not assert anything itself.

## What it does

For each step of a scenario (`scenarios/tenant.json`, `scenarios/admin.json`):

1. Drives the real browser (Selenium, same headless-Chrome-via-Selenium-Manager setup
   `tests/e2e/conftest.py` already established -- no second driver-setup mechanism).
2. Saves a screenshot + the rendered HTML to `evidence/<run_id>/<step_name>.png` / `.html`.
3. If the step names a `verify_against` API call, fetches that raw JSON from `gateway-api`
   directly (bypassing the UI) and saves it alongside as `<step_name>.api.json`.
4. Writes `evidence/<run_id>/manifest.json` -- one entry per step, with paths to all three
   artifacts plus a mechanical `field_diffs` list (values `extract_fields` pulled off the
   rendered HTML vs. the same field read off the raw API JSON) so an agent reviewing the run
   doesn't have to eyeball every number by hand.

An agent tester then `Read`s each screenshot + manifest and writes up findings (broken flow,
confusing copy, positioning-rule violation per CLAUDE.md, or a `field_diffs` mismatch) --
same output shape as this repo's `qa` agent already produces for a sprint. **`AGENT_BRIEF.md`
(same directory) is what you hand that agent** -- it defines what to look for and how to report
it; this README only covers running the capture.

## Usage

Requires the real stack running (`docker compose up` in `infra/`) and a provisioned tenant API
key + `OPERATOR_TOKEN` (same env var `gateway-api`'s README documents).

```
.venv\Scripts\python.exe scripts\agent_uat\run_scenario.py ^
    --scenario scenarios\tenant.json ^
    --base-url http://127.0.0.1:8004 ^
    --gateway-url http://127.0.0.1:8000 ^
    --api-key <tenant's raw API key>

.venv\Scripts\python.exe scripts\agent_uat\run_scenario.py ^
    --scenario scenarios\admin.json ^
    --base-url http://127.0.0.1:8004 ^
    --gateway-url http://127.0.0.1:8000 ^
    --operator-token %OPERATOR_TOKEN%
```

Each invocation writes a fresh `evidence/<timestamp>-<scenario name>/` directory; nothing is
overwritten or cleaned up automatically -- delete old runs manually once reviewed.

## Scope / non-goals

- Not a correctness oracle on its own -- `field_diffs` only catches the UI silently diverging
  from what the API actually returned (a rendering bug); it says nothing about whether the
  underlying validation math is right (that's `naive_first_engine`'s own test suite's job).
- Does not create/provision tenants or set `OPERATOR_TOKEN` -- both are prerequisites, same as
  any other manual walk of this stack (see `infra/README.md`).
- Never asserts pass/fail itself and is not wired into `pytest`/CI -- an agent (or a human)
  reading the evidence is what turns this into a verdict.
