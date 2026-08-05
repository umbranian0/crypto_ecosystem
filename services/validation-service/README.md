# validation-service

**Status: planned (trigger #3 — create as soon as `naive_first_engine` needs to run against a real dataset via an API call instead of a local script).**

Wraps [`libs/naive_first_engine`](../../libs/naive_first_engine/README.md) as a REST service. See [../../docs/solution-design.md](../../docs/solution-design.md) section 3.4 and [../../docs/implementation-plan.md](../../docs/implementation-plan.md).

**Owns**: the `validation` Postgres schema (`runs`, `split_results` — see solution-design.md section 4), triggering/executing validation runs, emitting the `run.completed` event (Redis Streams) on finish.

**Does not own**: the validation algorithm itself (that's `naive_first_engine`), dataset storage (`ingestion-service`), or report rendering (`reporting-service`).

**Design notes**:
- Data access goes through a Repository layer (`ValidationRunRepository`, `SplitResultRepository`) — see implementation-plan.md section 7 — so schema-per-service can later become DB-per-service without touching call sites.
- Any client-model wrapper beyond the naive baselines (e.g. running a client-supplied prediction column through the same protocol) is a Strategy implementation of the same interface used by `naive_first_engine.baselines`, not a special case.
- Run execution follows the Template Method already encoded in `naive_first_engine`: split → baseline → metrics → DM test, fixed order, no shortcuts.

**Contract**: FastAPI service; OpenAPI schema is the source of truth once implemented. Expected endpoints: `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/splits`.
