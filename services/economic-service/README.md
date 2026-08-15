# economic-service

**Status: scaffolded (trigger #11 not fired). Sprint 13's ECON-006 is documentation/grep-check polish on top of ECON-001 through ECON-005 — no behavior change.**

Formerly `economic-module/`. See [../../docs/solution-design.md](../../docs/solution-design.md) and [../../docs/da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) sections 2.3.5, 2.6 (phase 4), 2.7.

## What this service is — read this section before touching any code here

**Statistical accuracy != economic value.** A model that beats Naive0 on MAE/RMSE/directional-accuracy under `naive_first_engine`'s leakage-free, purged walk-forward protocol has *not thereby* been shown to have real economic value — transaction costs, slippage, and turnover can erase a statistically real edge entirely. `economic-service` is the infrastructure that will compute that cost/slippage-adjusted answer — **but only once, and only after**, a real client model has already earned the statistical result `validation-service` alone can certify. Nothing in this service's code, comments, logs, or documentation may ever imply price prediction or trading signals, and this README's own existence must never be read as evidence the platform currently has a profitable model — see `CLAUDE.md`'s own binding language and `ECON-006`'s doc-sync check (below), which mechanically enforces exactly that rule against every docstring, log message, and README line in this service outside its own one gated computation module.

Today, that "only once" condition **cannot be met at all** — see the next section.

## Why this service is being built ahead of its own trigger

`docs/implementation-plan.md` section 6's trigger #11 is not a scheduling convenience like `gateway-api`'s trigger #5 or `dashboard-web`'s trigger #8. It is `CLAUDE.md`'s own explicit ethical/business-honesty boundary: *"only wire up for a model that already beats naive in `validation-service`; never claim profitability before that."* `docs/da-tese-ao-produto.md` section 2.7 states the same rule and requires that statistical accuracy and economic value stay visibly separate. Sprint 13 (`docs/sprints/sprint-13.md`, `docs/product/backlog-economic-service.md`) is a **disclosed, user-authorized override** of that trigger, not a silent skip of the build-order rule — this service exists this sprint only because every story in it produces **zero externally-observable capability**: no endpoint built here can ever return a real profitability number, by construction.

**Two verified upstream facts, carried forward from the backlog's own override note (`docs/product/backlog-economic-service.md`), not re-derived here:**

1. **No model has ever beaten naive on this platform.** Every real run to date in `validation-service` compares Naive0 against NaiveLast (see `validation-service/README.md`'s "Data model" section) — never a real client-supplied predictive model.
2. **`VS-017` ("client-supplied prediction baseline") is itself deferred and unbuilt** in `validation-service`. Until it ships, there is no code path anywhere on this platform that could even produce a real client-model DM verdict. This means there is currently **no gate to fail or pass** — the capability the gate would check does not exist upstream.

`ECON-004` makes the only upstream integration a disclosed mock fixture (`source="mock_fixture"`, never `"live"`); `ECON-005` is the code-level, structural proof of this service's inertness — not merely a documented promise of it (see "The structural eligibility gate" below).

**Hard rule for every future ticket against this service (ECON-004's own binding decision):** no ticket may wire a real `httpx` call to `validation-service`'s real base URL, and no `VALIDATION_SERVICE_URL`-style env var may be read anywhere in this service's code, until (a) `VS-017` ships in `validation-service` **and** (b) a real run produces a genuine, Harvey-corrected, statistically significant outperformance verdict. Even then, wiring the real client is its own new, separately-authorized ticket reviewed with the same scrutiny as `ECON-005` — never a quiet edit to the mock client.

## Ownership boundary

**Will own** (once a real gate-pass exists): the `economic` Postgres schema (inputs only — fee schedules, slippage models, simulation configs; never a persisted profitability-output table, see `ECON-002`/`ECON-010`'s own deferral), transaction-cost/slippage/turnover modeling, realistic portfolio simulation — applied only to models that have already passed `validation-service` for real.

**Does not own**: any statistical validation logic (that's `naive_first_engine`/`validation-service` — this service reads a DM verdict, it never recomputes or second-guesses one), dataset storage (`ingestion-service`), report rendering (`reporting-service`). Its absence must be visible in every `reporting-service` report until a real gate-pass exists (see the mandatory disclaimer in the `naive-first-audit` skill).

## Scaffolding (ECON-001)

`uv`-managed FastAPI skeleton matching this repo's established per-service shape:

```
src/app/
├── __init__.py
├── main.py            # FastAPI app + GET /health
├── routers/
├── dependencies/
└── repositories/
tests/
```

`GET /health` was upgraded by ECON-002 from the ECON-001 hardcoded `{"status": "ok"}` placeholder to a real DB-connectivity check (mirroring `validation-service`'s/`gateway-api`'s OPS-005-01/02 precedent: a cheap `SELECT 1` against a memoized `Engine`, and a generic `503 {"status": "unhealthy", "detail": "database unreachable"}` on failure with no raw exception/connection-string leakage) — see "Schema (ECON-002)" below.

No `Dockerfile`/Compose wiring yet — this sprint is scaffolding-only and does not touch `infra/`.

**Tests**: `.venv\Scripts\python.exe -m pytest -q` (Windows) from this directory. Environment note: this repo directory sits inside a OneDrive-synced folder, causing intermittent `uv sync`/file-write failures unrelated to code — the working pattern used to build this service was `python -m venv .venv` then `.venv\Scripts\python.exe -m pip install -e . -e ../../libs/common pytest httpx`, matching `validation-service`'s VS-001 documented workaround.

**CI**: `.github/workflows/ci.yml` does not yet include this module (added when this service graduates past scaffolding-only status against a real trigger).

**Dependency upgrades**: see [../../docs/dependency-upgrade-policy.md](../../docs/dependency-upgrade-policy.md) for this platform's cadence.

## Schema (ECON-002)

`src/app/models.py` defines the `economic` schema's three SQLAlchemy models: `FeeSchedule` (`fee_schedules`), `SlippageModel` (`slippage_models`), `SimulationConfig` (`simulation_configs`). All three carry `tenant_id` (non-nullable).

**Inputs-only, permanently — cross-reference `ECON-010`'s own Won't.** This schema stores simulation *assumption* records only: fee tiers, slippage-model parameters, and the config a would-be simulation would run against. It does **not** and will **never** contain a persisted computed-output table (a "results table" storing a P&L, net-return, or revenue figure) — such a table would imply a real number had legitimately been computed, which is exactly the question `ECON-005`'s structural eligibility gate exists to answer, not something this schema pre-empts. `tests/test_no_profitability_columns.py` is the **permanent regression guard** for this rule: it introspects `app.models.Base.metadata` programmatically (not a hardcoded list of today's column names) and fails if any table or column name matches one of a small set of computed-output-shaped substrings (see the test file itself for the exact list) — so a future column added anywhere in this module fails loudly, not silently.

`SimulationConfig.validation_run_id` is a plain opaque string column, **never** a SQLAlchemy `ForeignKey` — this service must never read `validation-service`'s DB schema directly (CLAUDE.md, `implementation-plan.md` section 5); the only legitimate way to reference a `validation-service` run is by the string id that service's own REST API hands out. (`SimulationConfig.fee_schedule_id`/`slippage_model_id` *are* real FKs — those reference rows in this same schema, which `implementation-plan.md` section 5 does not forbid.)

**Backend choice, documented per this ticket's Design section**: **SQLite-only** for this ticket, not dual-backend — the backlog explicitly does not require dual-backend on day one, and SQLite-only keeps this sprint fully self-contained (no `infra/` dependency, no Postgres RLS wiring against real credentials). `src/app/repositories/sqlite_repository.py`'s `SQLiteEconomicInputRepository` is the sole interim implementation, behind the `EconomicInputRepository` Protocol (`src/app/repositories/interfaces.py`, zero `sqlalchemy` import, `tenant_id`-first parameters, plain `@dataclass(frozen=True)` records). A future `PostgresEconomicInputRepository` behind the same DI seam (`src/app/dependencies/repositories.py`) is the equivalent of `validation-service`'s own VS-013 — a separate, not-yet-authorized ticket.

**Migrations**: `migrations/` (Alembic, schema-qualified to `economic` via `version_table_schema`/`SET search_path`, mirroring `validation-service`'s own INF-005-driven `version_table_schema` pattern — Postgres-only, no-op on SQLite). `migrations/versions/0001_create_economic_schema.py` creates the three tables; `migrations/versions/0002_add_row_level_security.py` authors (but does not yet enforce against real non-superuser credentials — that's a later infra ticket, per `validation-service`'s own INF-014 precedent) the same `FORCE ROW LEVEL SECURITY` + `tenant_id`-keyed policy pattern `validation-service`/`gateway-api` already use.

`DB path`: `ECONOMIC_SERVICE_DB_PATH` env var, defaulting to `./economic.db` (gitignored).

See `docs/tickets/ECON-002.md` for full acceptance criteria and outcome.

## Contracts (ECON-003)

`src/app/contracts.py` defines this service's first Pydantic wire contracts. Kept **local to `economic-service`**, not promoted to `libs/common/src/naive_first_common/contracts.py` — backlog decision 3 (`docs/product/backlog-economic-service.md`): only one consumer exists today (this service itself), so sharing now would be speculative generality ahead of `implementation-plan.md` section 9's DRY rule, which extracts on second duplication, not in anticipation of one.

- **`SimulationRequest`** — `run_id: str`, `fee_schedule_id: str`, `slippage_model_id: str`. No numeric field on the request; a return figure only ever appears on the success response path.
- **`UpstreamValidationResult`** — `source: Literal["mock_fixture", "live"]`, `dm_statistic: float`, `dm_pvalue: float`, `dm_verdict: str`. Mirrors `validation-service`'s own `split_results` row shape (its README "Data model" section) — this service reads a DM verdict, it never recomputes or second-guesses one. `source` is a `Literal`, not a bare `str`, so a typo can't silently defeat ECON-005's `"live"`-only gate check. Harvey-correction status is folded into `dm_verdict`'s own string vocabulary (e.g. `"significant_outperformance_harvey_corrected"`) rather than a separate boolean field. Consumed by ECON-004 (mock client) and ECON-005 (eligibility gate) by name — do not redefine this class elsewhere.
- **`EligibleSimulationResult`** — `run_id: str`, `cost_adjusted_return: float`, `slippage_adjusted_return: float`, `total_cost_bps: float` (`>= 0`), `upstream_verdict: UpstreamValidationResult`. Success-path response only; only ever constructible when an upstream verdict has passed ECON-005's gate.
- **`NotEligibleForSimulation`** — `reason_code: str`, `message: str`, `upstream_verdict: UpstreamValidationResult | None`. Refusal-path response with **zero numeric fields of any kind** (no `float`, no `int`, no `Optional[float]`) — a genuinely separate class from `EligibleSimulationResult`, not the same class with nullable numeric fields defaulting to `None`. This is deliberate: a nullable-numeric-field design would let a serialization bug silently emit a value (e.g. `0.0`) that reads as "no result" instead of "not eligible" — exactly the fabricated/placeholder-number failure mode this backlog exists to prevent. The optional `upstream_verdict` field carries the DM statistic/p-value that caused the refusal (statistical evidence, not a computed-output figure), which is why its presence does not violate the "no numeric field" rule at the top level.

See `docs/tickets/ECON-003.md` for full acceptance criteria and outcome.

## Upstream integration (ECON-004) — mock-only, hard architectural rule

`src/app/upstream_client.py` defines `UpstreamValidationResultClient` (a `typing.Protocol`, one method: `get_result(tenant_id, validation_run_id) -> UpstreamValidationResult`) and its **sole implementation this sprint**, `MockValidationResultClient` — hardcoded fixture data only, `source="mock_fixture"` always, `dm_verdict="no_real_upstream_verdict_exists"` (deliberately not a plausible-looking DM result, so nobody mistakes it for a real finding). `src/app/dependencies/upstream.py` wires `get_upstream_client()`/`UpstreamValidationResultClientDep` — this provider must never grow a conditional/env-var branch toward a real client; wiring one is its own new, separately-authorized ticket.

**Hard rule, binding for every future ticket against this service**: no `httpx` import and no `VALIDATION_SERVICE_URL`-style environment variable read anywhere in this service's code, until (a) `VS-017` ships in `validation-service` and (b) a real run produces a genuine, Harvey-corrected, statistically significant outperformance verdict. `tests/test_upstream_client.py::test_upstream_client_module_has_no_httpx_import_and_no_url_env_var_read` is the permanent regression guard for this rule (AST-based: no `httpx`/`os` import anywhere in `upstream_client.py`). `tests/test_upstream_client.py::test_mock_client_is_the_only_di_wired_implementation` proves, by parsing every file under `src/app/` with `ast`, that `MockValidationResultClient` is the only class that actually implements `get_result` (the Protocol's own stub-bodied `get_result` — `...`, no real logic — is correctly excluded from that count) and that the real `Depends()` default (`get_upstream_client`) returns exactly that class.

See `docs/tickets/ECON-004.md` for full acceptance criteria and outcome.

## The structural eligibility gate (ECON-005)

`POST /simulations` (`src/app/routers/simulations.py`) takes ECON-003's
`SimulationRequest`, resolves an `UpstreamValidationResult` via ECON-004's DI
seam (`Depends(get_upstream_client)` -- never a direct instantiation), and
calls the single named guard function, `check_economic_eligibility`
(`src/app/eligibility.py`) -- and nothing else. The route handler never
imports or calls `compute_economic_simulation` (the pure cost/slippage
computation) directly; that function is called exclusively from inside
`check_economic_eligibility`'s own success branch. `POST /simulations`'s
OpenAPI `summary`/`description` (visible at `/docs`) state this precondition
in plain language, so a caller never needs to read this README or a ticket
to understand why a call will most likely refuse.

**The gate's exact two-condition logic, in prose**: `check_economic_eligibility`
refuses a request unless the conjunction of two independently-checked facts
both hold:

1. `result.source == "live"` (never `"mock_fixture"`) -- there must be a
   real upstream result at all, checked first.
2. `result.dm_verdict` starts with the literal prefix
   `"significant_outperformance"` (e.g.
   `"significant_outperformance_harvey_corrected"`) -- the client model must
   have beaten Naive0 with statistical significance, Harvey-corrected
   (NFE-012). Any other value -- `"not_significant"`, `"naive0_better"`, and
   ECON-004's own `"no_real_upstream_verdict_exists"` included -- fails this
   check.

Both facts are checked independently, fact 1 before fact 2, so the returned
`EligibilityDecision` (a tagged dataclass, not a bare boolean) distinguishes
*why* a request was refused: "no real upstream result" (fact 1 failed) from
"upstream result exists but did not beat naive" (fact 1 held, fact 2
failed) from "eligible" (both held). On refusal the router returns `409`
with `NotEligibleForSimulation` (zero numeric fields at its own top level,
per ECON-003); on success it returns `200` with the `EligibleSimulationResult`
`check_economic_eligibility` already computed on its own eligible branch.

Because `MockValidationResultClient` is this service's only real DI-wired
upstream client this sprint and always returns `source="mock_fixture"`
(ECON-004), fact 1 above can never hold through the real running service
today -- every real `POST /simulations` call, as actually deployed, refuses.
See `docs/tickets/ECON-005.md` for full acceptance criteria, the four
required tests, and the outcome.

## No profitability language outside the gate (ECON-006)

`src/app/eligibility.py` is the one module in this service allowed to
describe, in prose, what its own success branch computes (it is the only
code path that ever produces a real cost/slippage-adjusted number). Every
other file in this service — every other docstring, log message, and this
README itself — is checked mechanically, not just by convention, to make
sure it never implies the platform currently has demonstrated real
economic value it hasn't earned.

`scripts/check_profitability_language.py` (pytest entry point:
`tests/test_profitability_language.py`) scans `README.md` and every `.py`
file under `src/app` except `eligibility.py` against a small, curated,
documented forbidden-word list drawn from CLAUDE.md's own vocabulary for
this failure mode, plus plain-language near-synonyms, and fails if any
occurrence isn't covered by an equally curated, documented allowlist of
known-legitimate concept-discussion uses (e.g. this README's own
disclaimer two sections up, or `contracts.py`'s quoted description of the
serialization-bug failure mode it prevents). See the script's own module
docstring for the exact word list and the exact reasoning behind the line
it draws between discussing the concept of profitability in order to gate
it, and asserting the service currently has that property.

See `docs/tickets/ECON-006.md` for full acceptance criteria and outcome.
