# User Acceptance Testing (UAT) Guide

This is a step-by-step guide for manually exercising the Naive-First platform end-to-end, as a
human, outside of the automated test suites. It walks through the full loop the MVP was built to
support: log in, submit a validation run, see its audited results, generate a report, list your
runs, revoke a key, and confirm the operational basics (health checks, logging, load).

**Before you start**, two things worth knowing:

1. **This is validation/audit infrastructure, not a trading product.** Nothing in this guide will
   ever ask you to connect a real wallet or exchange account — see "What's deliberately not
   testable" at the end for the full list of things that don't exist yet, on purpose.
2. **Everything here runs locally against your own Docker Desktop.** No external service is
   contacted except container images being pulled the first time.

---

## 1. Prerequisites

- Docker Desktop installed and running.
- This repo cloned locally (you're reading this from inside it: `docs/UAT.md`).
- A terminal — PowerShell or Git Bash both work; commands below are given for both where they
  differ.
- `curl` available (ships with modern Windows/PowerShell; `curl.exe` if you have a PowerShell alias
  conflict).

Copy the example environment file once, before starting anything:

```
cp infra/.env.example infra/.env
```

(All values have working defaults — you don't need to edit anything to follow this guide.)

---

## 2. Bring the stack up

From the repo root, run the bootstrap script — this is the one-command path that brings up
Postgres/Redis, waits for them to be healthy, runs all migrations, and starts the two core app
containers:

```
# Git Bash / macOS / Linux
infra/bootstrap.sh

# PowerShell
infra/bootstrap.ps1
```

This is idempotent — safe to re-run any time (e.g. after a reboot) without side effects.

When it finishes, it prints the exact command to provision your first tenant (step 3) — you don't
need to run anything yourself yet.

**Bring up the remaining two services** (not part of bootstrap's own scope yet):

```
docker compose -f infra/docker-compose.yml up -d --build reporting-service minio
```

**Confirm everything is up and healthy:**

```
docker compose -f infra/docker-compose.yml ps
```

You should see six containers, all `Up` (and `healthy` where a healthcheck is defined):
`naive-first-postgres`, `naive-first-redis`, `naive-first-validation-service`,
`naive-first-gateway-api`, `naive-first-reporting-service`, `naive-first-minio`.

---

## 3. Provision your first tenant

This mints a real, one-time-visible API key. Run it **inside** the `gateway-api` container (it
needs to share that container's own database connection):

```
docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/provision_tenant.py --name "UAT Tenant"
```

You'll see output like:

```
Tenant created: id=<tenant-id>
API key (shown once, not recoverable): <raw-api-key>
```

**Copy the raw API key now** — it is never shown again, and it is never recoverable from the
database (only its hash is stored). If you lose it, provision a new tenant.

---

## 4. UAT via the API directly (`gateway-api`, port 8000)

This section uses `curl` so you can see the raw HTTP contract. Replace `<KEY>` with your raw API
key from step 3 everywhere below.

### 4.1 Health check

```
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok"}`, HTTP 200.

### 4.2 Submit a validation run

```
curl -s -X POST http://localhost:8000/runs \
  -H "Authorization: Bearer <KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "uat-dataset",
    "dataset_reference": {"type": "inline", "rows": []},
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 1,
    "test_window": 1,
    "step": 1
  }'
```

Expected: HTTP `201`, body `{"id": "<run-id>", "status": "..."}`. **Copy the run id.**

(An empty `rows: []` dataset will produce `status: "failed"` — that's the correct, honest
behavior for an empty dataset, not a bug. To see a real completed run with real per-split
metrics, submit a dataset with actual timestamped rows — see
`services/validation-service/README.md`'s "Dataset access" section for the exact
`dataset_reference` shapes accepted.)

### 4.3 Retrieve the run

```
curl -s http://localhost:8000/runs/<run-id> -H "Authorization: Bearer <KEY>"
```
Expected: HTTP `200`, the run's full detail (`status`, `dataset_id`, `horizon`, timestamps, etc.).

### 4.4 List your runs

```
curl -s "http://localhost:8000/runs?limit=20&offset=0" -H "Authorization: Bearer <KEY>"
```
Expected: HTTP `200`, `{"items": [...], "limit": 20, "offset": 0, "total": <n>}` — your run from
4.2 should appear, newest first.

### 4.5 View per-split results (only meaningful for a run with real data)

```
curl -s http://localhost:8000/runs/<run-id>/splits -H "Authorization: Bearer <KEY>"
```
Expected: HTTP `200`, a list of per-split metrics (`model_mae`, `naive0_mae`, `dm_statistic`,
`dm_pvalue`, `dm_verdict`, etc.) — this is the actual audit output: how the model compared to the
mandatory naive baseline, split by split.

### 4.6 Confirm tenant isolation (optional but worth doing once)

Provision a **second** tenant (step 3 again, different `--name`), then repeat 4.3 with the first
tenant's run id but the second tenant's key. Expected: HTTP `404` — cross-tenant access is
correctly refused, not merely hidden in the UI.

---

## 5. UAT via the dashboard (`dashboard-web`)

`dashboard-web` isn't wired into Docker Compose yet (it's still ahead of its own build trigger —
see its README), so run it directly on your host, pointed at the running `gateway-api` container:

```
cd services/dashboard-web
uv sync
uv run uvicorn app.main:app --app-dir src --port 8003
```

(On Windows without `uv run` working cleanly, use
`.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir src --port 8003` instead.)

Leave `GATEWAY_API_URL` unset — its default (`http://localhost:8000`) is already correct.

Open **http://localhost:8003/login** in a browser.

1. **Log in** with your raw API key from step 3. You should land on the "submit a run" page.
2. **Submit a run** — fill in the form (same fields as the API's `POST /runs` body). On success
   you're redirected to that run's detail page, showing its real status.
3. **View the runs list** — navigate to **http://localhost:8003/runs**. Your run should appear,
   newest first, linking to its detail page.
4. **Log out** — confirm you're redirected to `/login` and can no longer reach `/runs` without
   logging in again.

---

## 6. UAT the reporting flow (`reporting-service`, proxied through `gateway-api`)

Generate an audit report for the run from step 4.2:

```
curl -s -X POST http://localhost:8000/reports/generate \
  -H "Authorization: Bearer <KEY>" \
  -H "Content-Type: application/json" \
  -d '{"run_id": "<run-id>"}'
```
Expected: HTTP `201`, `{"id": "<report-id>", "status": "generated"}`.

Retrieve it:

```
curl -s http://localhost:8000/reports/<report-id> -H "Authorization: Bearer <KEY>"
```
Expected: HTTP `200`, a body including `content` — the rendered HTML report. Open that HTML string
in a browser (or save it to a file and open it) to see the human-readable audit report: run
status, per-split metrics table, and the mandatory statistical-accuracy-vs-economic-value
disclaimer.

**Known gap, not a bug**: reports are only generated on-demand via the call above — the
automatic "report gets created the moment a run finishes" path (`RS-006`) exists in the code but
isn't wired end-to-end yet. Don't expect a report to appear without calling
`POST /reports/generate` yourself.

---

## 7. UAT key revocation

Revoke the API key you've been using (run **inside** the `gateway-api` container, same pattern as
provisioning):

```
docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/revoke_api_key.py --key "<KEY>"
```
Expected output: `Revoked key id=... for tenant_id=... at <timestamp>`.

Confirm the key is now dead:

```
curl -s -i http://localhost:8000/runs -H "Authorization: Bearer <KEY>"
```
Expected: HTTP `401` — no delay, no caching window; revocation is effective on the very next
request. Provision a fresh tenant (step 3) to keep testing.

---

## 8. UAT structured logging

While the stack is running, tail both services' logs in another terminal:

```
docker compose -f infra/docker-compose.yml logs -f gateway-api validation-service
```

Trigger a request (e.g. repeat 4.1), and confirm each log line is a single-line JSON object with
`timestamp`, `level`, `logger`, `message`, and a `correlation_id` field. Submit a request through
`gateway-api` and confirm the **same `correlation_id`** appears in both `gateway-api`'s and
`validation-service`'s log lines for that request — proof the id is actually threaded through the
proxy hop, not just generated independently by each service.

---

## 9. UAT load testing (optional, Locust)

```
cd services/gateway-api
uv sync
LOCUST_API_KEY="<KEY>" uv run locust -f loadtest/locustfile.py --headless -u 5 -r 1 --run-time 30s --host http://localhost:8000
```

Expected: a summary table of request counts/latencies for `POST /runs`, `GET /runs/{id}`,
`GET /runs/{id}/splits`, and a deliberate invalid-auth check (expect these to show as `401`, not a
failure — that's the intended behavior being exercised). There is no pass/fail threshold — this is
observability tooling, not a gate.

---

## 10. Cleanup

Stop everything, keeping your data (Postgres/Redis/MinIO volumes) for next time:

```
docker compose -f infra/docker-compose.yml down
```

To wipe all data and start completely fresh next time:

```
docker compose -f infra/docker-compose.yml down -v
```

---

## What's deliberately not testable (and why)

- **No automated or "robo" trading.** This platform does not place trades, connect to a real
  exchange, or manage funds — real or simulated. It is validation/audit infrastructure. See
  `CLAUDE.md`'s "Product positioning" section.
- **`economic-service`'s `/simulations` and `/backtests` endpoints will always refuse.** Every
  call returns a `409`/`422` "not eligible" response by design — there is currently no code path
  anywhere on this platform that can produce a real, live, statistically-significant "model beat
  naive" result to compute a profitability figure against. This is intentional and structurally
  enforced, not a bug to report.
- **`ingestion-service`'s upload API isn't reachable via HTTP yet.** Its connectors exist and are
  tested, but the FastAPI wrapper/upload endpoint is still ahead of its own build trigger.
- **The automatic "report on run completion" path isn't wired end-to-end.** Use the manual
  `POST /reports/generate` call (section 6) instead.
- **No JWT/session-based login, no self-service rate limiting.** Auth is API-key only by design
  for this stage (see `docs/product/backlog-hardening-wave-review.md` for the reasoning).

If you hit an error anywhere in sections 1–9 above that isn't explained by this list, that's a
real bug worth reporting — please capture the exact command, the response body, and the relevant
`docker compose logs` output for the service involved.
