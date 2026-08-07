# Sprint 05 — services/gateway-api (scaffolding, identity schema, repositories, provisioning, auth, routing, failure handling)

Sprint goal: Stand up `services/gateway-api` end-to-end on an interim (non-Postgres) identity store — scaffolding, the `identity` schema, Repository-pattern data access, operator-facing tenant/API-key provisioning, API-key authentication, verified-tenant-context forwarding, and request routing (with failure handling) to `validation-service`'s real endpoints — so a caller can authenticate with an API key and get transparently proxied to `validation-service` today, with every interim substitution swappable later without touching call sites.

Backlog source: docs/product/backlog-gateway-api.md (all 9 Must-priority stories: GW-001 through GW-009)

Stories in scope (execution order):

1. **GW-001** — Service scaffolding. Depends on: none. Literal first step — nothing else in this backlog has a package/app skeleton to live in until this exists.
2. **GW-002** — `identity` schema definition (`tenants`, `users`, `api_keys`). Depends on GW-001. Needs the skeleton in place; every downstream repository/provisioning/auth story needs an agreed data shape first.
3. **GW-003** — Identity repository interfaces (`TenantRepository`, `UserRepository`, `ApiKeyRepository`). Depends on GW-002. Interfaces are defined against the schema, before either the interim or future Postgres-backed implementation exists.
4. **GW-004** — SQLite-backed repository implementation (interim). Depends on GW-003. Concrete implementation of the just-defined interfaces; unblocks any provisioning/auth story that needs to persist/read identity data.
5. **GW-005** — Tenant + API-key provisioning (operator-facing). Depends on GW-004. Needs a concrete repository to write to; this is the fixture-creation step that gives GW-006 something real to authenticate against.
6. **GW-006** — API-key authentication. Depends on GW-005. Needs a provisioned tenant + key to verify against; this is the literal auth mechanism named in this service's "owns" boundary.
7. **GW-007** — Verified `TenantContext` resolution + downstream forwarding. Depends on GW-006. Takes the identity GW-006 just verified and makes it forwardable; needs a verified identity to exist first.
8. **GW-008** — Request routing to `validation-service`'s real endpoints. Depends on GW-007. Needs verified, forwardable tenant context before any request can be proxied safely.
9. **GW-009** — Downstream failure handling (timeouts, connection errors). Depends on GW-008. Hardens the routing path GW-008 just built; sequenced last since it adds no new surface area, only failure-mode handling around the proxy calls that now exist.

This backlog's Must-priority dependency chain is confirmed strictly linear — each story's own "Depends on" line names exactly one predecessor, and every predecessor is itself in this list (GW-001←none, GW-002←GW-001, GW-003←GW-002, GW-004←GW-003, GW-005←GW-004, GW-006←GW-005, GW-007←GW-006, GW-008←GW-007, GW-009←GW-008). Unlike `validation-service`'s Sprint 03 (which had independent branches — e.g. VS-005 sequenced in parallel with VS-002/003/004, VS-007/VS-008 both hanging independently off VS-006), there is no parallel branch here: execution order is fully determined by dependency, with priority playing no role since all 9 in-scope stories are Must.

Stories explicitly deferred:
- **GW-010** (API-key revocation) — Should priority; important operational hygiene but not required to prove the core auth/routing path works end-to-end. Deferred, matching the Sprint 01→02/03→04 pattern of Shoulds rolling forward.
- **GW-011** (JWT-based session auth) — Should priority; its only named consumer (`dashboard-web`, trigger #8) and `libs/sdk` (trigger #9) don't exist yet. API-key auth (GW-006, Must) is the mechanism with an actual near-term caller. Deferred.
- **GW-012** (Postgres-backed identity repository + row-level security) — Should priority; explicitly blocked in the backlog on `infra/docker-compose.yml` + Postgres actually existing (trigger #4, not fired). Not build-able correctly until that trigger fires. Deferred.
- **GW-013** (Rate limiting / abuse protection) — Could priority; with zero real external traffic yet, there is no observed abuse pattern to defend against. Deferred.
- **GW-014** (Auth event audit logging) — Could priority; valuable for eventual audit/compliance positioning but not required for the core auth/routing path to function or be tested. Deferred.
- **GW-015** (Signed/verified internal tenant-identity propagation, LC-009 hardening handoff) — Won't (this backlog), per the backlog's own decision 3: this is explicitly `libs/common`'s LC-009 concern, flagged as a future follow-up round, not started or reopened here.

Binding sprint note for the Tech Lead (decision already made, not open for re-litigation this sprint):

- **GW-006's acceptance criteria says API keys are compared "against the stored hash" but does not name a hashing algorithm. Use SHA-256 for API-key hashing — not bcrypt/argon2/scrypt.** Reasoning: bcrypt/argon2/scrypt are slow, salted key-derivation functions designed to defend low-entropy, human-chosen secrets (passwords) against offline brute-force/dictionary attack. API keys issued by GW-005 are high-entropy, machine-generated random tokens — brute-forcing the key itself is already computationally infeasible regardless of hash speed, so a slow KDF buys no meaningful additional protection and only adds unnecessary CPU cost to every authenticated request (GW-006 runs on the hot path for every routed call). A fast, deterministic, unsalted cryptographic hash (SHA-256) is standard practice for high-entropy API-key storage — this is what GitHub, Stripe, and similar API-key-issuing services do for exactly this reason. This does not apply to any future password-based auth (GW-011's JWT session login, if it ever adds password credentials) — that remains a slow/salted KDF decision to make when/if that story is picked up, not overridden by this note.

Definition of done for this sprint:
- All 9 in-scope Must stories' acceptance criteria are met as written in docs/product/backlog-gateway-api.md.
- `uv run pytest` passes in `services/gateway-api`, including GW-004's revocation-hash test, GW-006's auth test coverage (valid/revoked/missing/malformed key; cross-tenant isolation proven at GW-008's routing layer), GW-008's cross-tenant `404` test, and GW-009's timeout/connection-refused/pass-through-failure tests.
- A caller can provision a tenant + API key (GW-005), authenticate with that key (GW-006), and have `POST /runs` / `GET /runs/{id}` / `GET /runs/{id}/splits` transparently proxied to `validation-service` (GW-008) with a verified `X-Tenant-Id` forwarded (GW-007) — end-to-end, against the interim SQLite identity store (GW-004).
- API keys are hashed with SHA-256 (this sprint's binding note); raw keys are never logged or persisted (GW-002, GW-005).
- This sprint makes no change to `libs/common/src/naive_first_common/tenant_context.py` or to any `validation-service` file (GW-007's explicit constraint) — verified by a diff/CI check scoped to `services/gateway-api/`.
- `services/gateway-api/README.md` is updated per GW-001 (status: scaffolded, built ahead of trigger #5), GW-004 (interim SQLite store, Postgres replacement named as GW-012), and GW-007 (interim network-topology-trust forwarding, hardening named as LC-009/GW-015) — no interim decision is left undocumented.
- No code in this sprint touches `libs/naive_first_engine`, `services/ingestion-service`, `services/reporting-service`, `services/dashboard-web`, `services/economic-service`, or `libs/sdk` — all out of scope per the backlog.
- GW-010 through GW-015 remain unscheduled/deferred as stated above — this sprint does not start any of them.
