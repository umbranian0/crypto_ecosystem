# API Guide

One-stop index of every HTTP API in this repo: where its interactive docs live, how to authenticate, and a working example. See [implementation-plan.md](implementation-plan.md) section 3 for how these services fit together, and each service's own README for implementation detail — this file is the "how do I actually call it" companion.

Bring the stack up first (see [../infra/README.md](../infra/README.md) for the full walkthrough):
```
docker compose -f infra/docker-compose.yml up -d --build validation-service gateway-api
```

## gateway-api — the public API

The only internet-facing service (per CLAUDE.md). Everything external clients call goes through here.

- **Swagger UI (interactive)**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Raw OpenAPI JSON**: http://localhost:8000/openapi.json

### Authenticating

There's no self-service sign-up — provisioning is an operator action (`scripts/provision_tenant.py`), since there's no real pilot client yet:
```
docker compose -f infra/docker-compose.yml exec gateway-api .venv/bin/python scripts/provision_tenant.py --name "My Tenant"
```
This prints a raw API key **once** — copy it immediately, only its hash is stored. Use it as either header (don't send both with a malformed `Authorization`, it's checked first and won't fall back):
```
Authorization: Bearer <key>
```
or
```
X-Api-Key: <key>
```

In Swagger UI: click the **Authorize** button (top of the page) and paste the key into either field — it then auto-attaches to every "Try it out" call, no per-request re-entry needed.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/runs` | Create a validation run (proxies to validation-service) |
| `GET` | `/runs/{run_id}` | Fetch a run's status/summary |
| `GET` | `/runs/{run_id}/splits` | Fetch a run's per-split walk-forward results |
| `GET` | `/health` | Liveness check, no auth |

### Example

```bash
curl -s -X POST http://localhost:8000/runs \
  -H "X-Api-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset_id": "btc-1h",
    "dataset_reference": {"path": "data/raw/_platform/price/binance_btcusdt_1h/seed"},
    "horizon": 1,
    "purge_gap_hours": 1,
    "train_window": 720,
    "test_window": 168,
    "step": 168
  }'
```

## validation-service — internal API, not internet-facing

Wraps `libs/naive_first_engine` as a REST API. Per CLAUDE.md, **gateway-api is the only internet-facing service** — this one is reachable only from the Docker Compose network (its host port is bound to `127.0.0.1` only, not the public interface) and trusts an `X-Tenant-Id` header with no cryptographic verification of its own (tracked, open gap: ARCH-005/LC-009). Don't call it directly from anything other than gateway-api or local dev/debugging.

- **Swagger UI (interactive, local dev only)**: http://localhost:8001/docs
- **Raw OpenAPI JSON**: http://localhost:8001/openapi.json

For actual use, go through gateway-api above — this is documented for local debugging/dev only.

## ingestion-service — no HTTP API yet

Status: connectors + raw-zone archive exist (`connectors/`, run standalone via `python -m connectors.binance_price` etc.), but the FastAPI app, upload endpoint, and Postgres schema are not built yet (ahead-of-trigger note in its own README). Nothing to document here until that lands.

## libs/naive_first_engine, libs/common — not services

Pure Python libraries, no HTTP surface. Consumed directly by validation-service/gateway-api's own code, not called over the network.
