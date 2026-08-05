# crypto_ecosystem — Naive-First

Business case and eventual codebase evolving from a Master's thesis on Bitcoin return prediction. Full context: [docs/da-tese-ao-produto.md](docs/da-tese-ao-produto.md). Technical architecture (ingestion → storage → processing → validation engine → reports → frontend): [docs/solution-design.md](docs/solution-design.md). Code organization (microservices/module boundaries, build order, design patterns, DRY rules): [docs/implementation-plan.md](docs/implementation-plan.md). Delivery process (Product Owner → PM → Tech Lead → dev squad agents, with approval gates): [docs/process/agile-squad-workflow.md](docs/process/agile-squad-workflow.md).

Locked-in design assumptions (2026-08-05): local-first deployment (Docker Compose, cloud-portable), multi-tenant from day one (external pilot clients from the start), Python end-to-end with a server-rendered (FastAPI + HTMX/Jinja2) frontend for the MVP, monorepo with `libs/*` (shared, no I/O) and `services/*` (independently deployable). See solution-design.md section 1 and implementation-plan.md before deviating from these.

## Core finding (do not contradict this in any product copy or code)

Under leakage-free, purged walk-forward validation, no ML model (OLS, Random Forest, ARIMA, LSTM) beat a naive benchmark (Naive0) in a stable, statistically significant way across 1h/6h/24h Bitcoin return horizons. OLS came closest but still lost on average MAE/RMSE at every horizon, and even it had more "worse" than "better" Diebold–Mariano splits against Naive0 at nearly every horizon. Best directional accuracy observed: 52.51% (barely above chance).

## Product positioning (non-negotiable)

This is **not** a Bitcoin-prediction or trading-signal product. It is a **validation/audit infrastructure** for predictive models in crypto/financial markets — selling the rigor the thesis itself demonstrated (leakage detection, naive-first benchmarking, Diebold–Mariano testing, honest instability reporting), not alpha.

Never let a subsystem's README, code comments, or docs imply the system predicts prices or generates trading signals. Statistical accuracy ≠ economic value — always keep these separate (see docs section 1.5, 2.7).

## Folder layout (monorepo: `libs/` = shared, no I/O; `services/` = independently deployable; see implementation-plan.md section 3)

- `libs/naive_first_engine/` — Subsystem 1 core IP: rolling-origin walk-forward + purge gap + naive baselines + DM test. **Status: build now** (trigger #1, no dependencies). Everything else depends on it.
- `libs/common/` — shared tenant context, schemas, DB helpers. Planned, trigger #2.
- `libs/sdk/` — Subsystem 6 "bring your own model" client. Planned, trigger #9.
- `services/gateway-api/` — auth, tenant routing, public REST contract. Planned, trigger #5 (first pilot client).
- `services/ingestion-service/` — Subsystem 2: upload API + causal multimodal connectors (price, sentiment, on-chain). Planned, trigger #6.
- `services/validation-service/` — wraps `naive_first_engine` as a REST service. Planned, trigger #3.
- `services/reporting-service/` — Subsystem 4: audit/certification reports, B2B revenue line. Planned, trigger #7.
- `services/dashboard-web/` — Subsystem 3: SaaS continuous benchmark monitoring UI. Planned, trigger #8.
- `services/economic-service/` — Subsystem 5: transaction costs/slippage/portfolio sim. **Deferred** — only wire up for a model that already beats naive in `validation-service`; never claim profitability before that (trigger #11).
- `infra/` — Docker Compose + per-service Alembic migrations. Planned, trigger #4.
- `research/` — Phase 3 applied research (regime-sensitive models, broader model comparison, per-split explainability), always tested under the same protocol against naive.
- `docs/` — strategy (`da-tese-ao-produto.md`), architecture (`solution-design.md`), module/build plan (`implementation-plan.md`).

## Build order

Trigger-based, not calendar-based — see implementation-plan.md section 6 for the full table and the exact condition that justifies scaffolding each module. Don't create a service/lib before its trigger is true.

## When implementing anything here

- Any comparison of a model to a benchmark must default to naive-first (Naive0/NaiveLast) as the baseline, not an arbitrary model.
- Any "significant" claim on overlapping horizons needs the long-run variance correction (Harvey et al. 1997) — the thesis explicitly flagged this as unresolved; don't skip it in code that computes DM statistics.
- Preprocessing (scaling, imputation, feature selection) must be fit on the training fold only, per split — never globally. This is the exact leakage failure mode the whole business case is built on avoiding.
- No service imports another service's code — only `libs/*` are shared. Data access between services goes through that service's HTTP API only, never its DB schema directly.
- Keep code DRY within each module's own boundary (extract on second duplication); cross-module duplication gets pulled into a `libs/*` package, never copy-pasted across service boundaries. See implementation-plan.md sections 7 and 9 for the specific design patterns (Strategy, Repository, Adapter, Factory, Observer, DI, Template Method) and where each applies.
- Every module's README stays current on status/ownership/contract as it's built — this is how future sessions (and future you) pick the work back up without re-deriving context.
