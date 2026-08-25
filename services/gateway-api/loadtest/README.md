# loadtest (GW-017)

A [Locust](https://locust.io/) load-test suite driving `gateway-api`'s key endpoints (`POST /runs`,
`GET /runs/{id}`, `GET /runs/{id}/splits`, plus a deliberately-invalid-auth request) against a real
running Compose stack. **This is observability tooling for a human to read the Locust request-stats
output, not a CI gate** — no hard SLA/threshold is asserted anywhere in `locustfile.py`, and no
committed CI config invokes this suite. Read the numbers, don't automate a pass/fail on them.

## Prerequisites

1. Bring up the real stack (`postgres`, `redis`, `validation-service`, `gateway-api`) per
   [`infra/README.md`](../../../infra/README.md), e.g. `infra/bootstrap.sh` /
   `infra/bootstrap.ps1` from the repo root, or `docker compose -f infra/docker-compose.yml up -d
   --build validation-service gateway-api` after `postgres`/`redis` are healthy.
2. Provision a tenant + API key **inside the running `gateway-api` container**, the same
   containerized form `infra/README.md`'s own full-stack smoke test uses (not the host-`.venv` form
   documented in `services/gateway-api/README.md`'s own "Provisioning" section — that form writes
   to a different, host-local `gateway.db`, not the one the running container's app process reads):

   ```
   docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/provision_tenant.py --name "Load Test Tenant"
   ```

   Copy the raw API key printed on the `API key (shown once, not recoverable): ...` line — it is
   never recoverable after this point, so if it's lost, re-run the command to provision a fresh one.
3. Install `locust` in this service's own dev environment (already declared as a dev dependency —
   `uv sync` from `services/gateway-api` pulls it in), or `pip install locust` in whatever
   environment you're invoking `locust` from.

## Running it

From `services/gateway-api`, with the API key from step 2 above:

```
LOCUST_API_KEY="<raw key from provision_tenant.py>" locust -f loadtest/locustfile.py \
  --headless -u 5 -r 1 --run-time 30s --host http://localhost:8000
```

`--host http://localhost:8000` is `gateway-api`'s own host-published port (per
`infra/docker-compose.yml`'s `INF-004` entry) — this suite always drives load through
`gateway-api` as the public entry point, never `validation-service`'s own `8001` directly, since
`gateway-api` is the only internet-facing service (see this service's own README "Owns" note).

Drop `--headless --run-time 30s` and Locust starts its web UI (`http://localhost:8089` by default)
instead, if you'd rather watch live charts and drive the run interactively.

**Recommended starting points**: `-u 5 -r 1` (5 users, spawned at 1/second) for a first local run
against a single-container stack, working up from there. This stack has not been load-tested to
find a real ceiling yet — these are conservative starting values to get a first readable set of
request stats without immediately overwhelming a laptop-scale Compose deployment, not a
recommendation for any particular target throughput.

## Reading the results: `POST /runs` is not like the two `GET` endpoints

`POST /runs` and the two `GET` endpoints (`GET /runs/{id}`, `GET /runs/{id}/splits`) will show
materially different latency numbers in the Locust summary, and that difference is expected, not a
sign of a problem specific to `gateway-api`. `gateway-api`'s own role in all three requests is the
same thin proxy (authenticate → resolve tenant → forward via `httpx` → return the response
unmodified — see this service's README "Request routing to `validation-service`" section): the real
compute cost of `POST /runs` belongs to `validation-service`, not to `gateway-api` itself.
`validation-service`'s `POST /runs` (per its own `VS-006` contract) executes the full
leakage-aware validation protocol **synchronously**, inline in the request/response cycle — no
background worker or async job queue exists yet — so its response time reflects an actual walk-forward
validation run's execution cost, not just network/auth/proxy overhead. The two `GET` endpoints, by
contrast, are simple reads that return in roughly proxy-plus-database-lookup time. Don't average
`POST /runs`'s numbers together with the two `GET` endpoints' numbers when interpreting the summary
table — Locust already reports them as separate named requests (see `name=` in `locustfile.py`), so
read each endpoint's row on its own rather than looking at an aggregate across all of them.

## What each task does

- `create_run` (`POST /runs`) — submits the same small, deterministic inline `dataset_reference`
  payload `infra/README.md`'s own full-stack smoke test uses (an empty-rows dataset, so the run
  itself resolves quickly to a `status: "failed"` outcome inside `validation-service` — enough to
  exercise the full authenticate → route → execute → persist → respond path end-to-end without a
  slow synthetic dataset dominating every run of this suite).
- `get_run` / `get_run_splits` (`GET /runs/{id}`, `GET /runs/{id}/splits`) — read back the run ID
  captured from `on_start`'s own seed `POST /runs` call.
- `get_run_unauthenticated` — a distinct task issuing `GET /runs/{id}` with a deliberately invalid
  `Authorization` header, to observe `401` behavior (GW-006) under the same load, not folded into
  the authenticated tasks above.

The valid-path tasks read their API key exclusively from the `LOCUST_API_KEY` environment variable
— it is never hardcoded in `locustfile.py`, and the file never provisions a tenant/key itself; that
remains `provision_tenant.py`'s own job (see Prerequisites above).
