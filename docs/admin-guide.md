# Admin guide — tenants, API keys, and platform access

Practical reference for operating this deployment: how to log in as yourself, how to log in as
operator/admin, and how to manage tenants and their API keys. Written 2026-09-13, current state of the
platform's Sprint 32 close-out. For the underlying design decisions, see
`docs/product/backlog-first-run-setup-and-ops.md` (Epic B) and each service's own README.

## 1. Two separate identities on this platform

This platform has two distinct kinds of session, deliberately kept separate (not merged, per
`SETUP-010`'s own design note):

| | Tenant session | Operator session |
|---|---|---|
| Login page | `/login` | `/operator-login` |
| Credential | A tenant's own API key | The shared `OPERATOR_TOKEN` |
| Cookie | `session_id` | `operator_session_id` |
| Can see | Only that tenant's own runs/datasets | Every tenant (list/create/revoke), environment facts, monitoring |
| Cannot do | Manage other tenants | Submit/view validation runs (no tenant context) |

You will normally want **both**: your own tenant session to actually submit and view validation runs,
and an operator session when you need to manage tenants/keys or check platform-wide monitoring.

## 2. Your tenant (day-to-day testing)

- **Dashboard**: http://localhost:8004
- **Tenant**: "Vasil admin" (tenant_id `0e7a4e5d71c44467997980437d2b798d`)
- **API key**: `ZbKyPoU-1cAC2gcRHUcauG-ZxnGHHhfoKUV0qtjp5oo` — log in at http://localhost:8004/login,
  paste this into the "API key" field. This key does not expire and was not created as a diagnostic
  key — it's yours to keep using.
- Already has a real, full-history dataset ingested: `binance_price_btcusdt_1h` (79,418 rows,
  2017-08-17 to 2026-09-13). Six example validation runs already exist under this tenant at three
  horizons (7/15/30-day) — see `docs/experiments/2026-09-13-btc-1h-multi-horizon-validation.md` for
  the full writeup, or just browse `/runs` after logging in.
- **If you ever lose this key**: it cannot be recovered (raw keys are never stored, only a hash — see
  §5). Log in as operator instead and issue a new key for the same tenant (§4).

## 3. Operator/admin login

- **Login page**: http://localhost:8004/operator-login
- **Token**: `naive_first_operator_dev_token` (configured in the `gateway-api` container's
  `OPERATOR_TOKEN` environment variable — this is a local-dev value baked into `infra/.env`/Compose,
  not something to reuse if this platform is ever deployed somewhere with real stakes)
- This is a single shared secret, not a per-person account — anyone who has it has full operator
  access. There is currently no way to tell which admin action was taken by which human (a disclosed,
  deliberate stopgap — see `services/gateway-api/README.md`'s `SETUP-010` section for the exact
  reasoning and the named trigger for building real per-admin accounts).
- Once logged in, you land on `/monitoring` (per-service health, recent errors, run throughput).

## 4. Managing tenants as operator

Once logged in as operator (§3), go to **http://localhost:8004/settings/tenants**. From there you can:

- **List** every tenant and their API keys (metadata only — id, created/revoked timestamps; a raw key
  value is never shown again after creation, by design).
- **Create a tenant**: enter a name, submit. The new tenant's first raw API key is shown **exactly
  once**, with a "copy this now" warning — if you navigate away without copying it, it's gone for good
  and you'd need to issue a new key for that tenant instead (same as below).
- **Revoke a key**: instantly invalidates it (checked fresh on every request, no caching window —
  confirmed this session under live testing).

There is currently no way to delete a tenant outright, or to rotate/reveal an existing key's value —
revoking and creating a new key is the only supported "I need a fresh credential" path. This matches
`provision_tenant.py`'s/`revoke_api_key.py`'s original CLI-only design, now also reachable from the
browser via the same underlying functions (`/settings/tenants` and `/tenants` are "two front doors to
the same function," not a second implementation).

### The same thing via API, if you prefer curl

```bash
OP="naive_first_operator_dev_token"

# List all tenants
curl -H "X-Operator-Token: $OP" http://localhost:8000/tenants

# Create a tenant (raw key shown once in the response)
curl -X POST -H "X-Operator-Token: $OP" -H "Content-Type: application/json" \
  http://localhost:8000/tenants -d '{"tenant_name": "Some New Tenant"}'

# Revoke a key
curl -X POST -H "X-Operator-Token: $OP" \
  http://localhost:8000/tenants/<tenant_id>/api-keys/<key_id>/revoke
```

## 5. Key-handling facts worth knowing

- Raw API keys are **never persisted anywhere** — only a SHA-256 hash. This is why a lost key can't be
  "looked up," only replaced.
- Revocation takes effect on the **very next request** — no cache, no grace period.
- Tenant data isolation is enforced at the **database layer** (Postgres row-level security), not just
  filtered in application code — one tenant's API key genuinely cannot read another tenant's rows, even
  if there were an application-layer bug (defense in depth).

## 6. Known current limitations (disclosed, not oversights)

- **The operator token itself has no in-UI way to be discovered or rotated** — it's a secret you set in
  `infra/.env` before first boot, same category as a database password. A UI to reveal it would
  contradict this platform's own "never render a secret" rule (`SETUP-015`), so this is a deliberate
  gap, not a bug.
- **No security headers** (CSP/HSTS/X-Frame-Options) are set yet — acceptable for this platform's
  current local-only exposure, flagged in the backlog for whenever it's exposed beyond localhost.
- **A 10-persona usability review** (2026-09-13) found a real, corroborated issue worth knowing about
  before you interpret results: a run's "Model" column is actually always the `NaiveLast` baseline
  unless you separately supply a real candidate model's predictions — it is not "no comparison,"
  but it's also not a trained model unless you provided one. A fix to make this clearer in the UI is
  queued (`docs/product/backlog-uat-findings.md`, stories UAT-001/UAT-002) but not yet built. Until
  then: when a run has no explicitly submitted model, read "Model" as "NaiveLast."

## 7. If a service isn't responding

All services run as Docker containers (`naive-first-*`, see `docker ps`) plus Postgres/Redis/MinIO.
If something seems stale (a page 404s that shouldn't, or behavior doesn't match a recent change),
rebuild and restart from `infra/`:

```bash
cd infra
docker compose build
docker compose up -d
```

This was necessary at least once this session — Docker images don't rebuild automatically when source
changes, so a container can silently keep serving old code after a fix lands. If in doubt, rebuild.
