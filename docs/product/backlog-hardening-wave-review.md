# Backlog review — next tier of deferred Should/Could items (disclosed-override wave)

Source read in full for this review: `docs/product/backlog-gateway-api.md` (GW-010, GW-011,
GW-013, GW-014, GW-017), `docs/product/backlog-infra.md` (INF-008, INF-010),
`docs/product/backlog-operability.md` (OPS-006), `docs/product/backlog-technical-upgrades.md`
(ARCH-005), `docs/product/backlog-validation-service.md` (VS-015, VS-017),
`docs/adr/0003-disclosed-trigger-override-pattern.md`, `docs/product/backlog-dashboard-web.md`
(for the exact "Explicit trigger override" wording convention this review reuses).

**Purpose.** The requester asked to re-evaluate every currently-deferred Should/Could item across
these five backlog files and decide, item by item, which ones make sense to pull forward now under
the same disclosed-override pattern already used for `gateway-api`, `dashboard-web`,
`reporting-service`, and `economic-service` (per `docs/adr/0003-disclosed-trigger-override-pattern.md`).
This document is that decision record. **Chosen approach**: write this standalone review file (rather
than only editing each backlog in place) so the full reasoning for all eleven items lives in one place
for the PM/Tech Lead to read once — *and* add a short, pattern-matching "Explicit trigger override"
disclosure directly to each pulled-forward item's own backlog entry (mirroring
`docs/product/backlog-dashboard-web.md`'s convention), so a future reader who only opens that one
backlog file still sees the override without needing to find this document. Items recommended to
stay held are *not* edited in their home backlog files — their existing deferral text is already
correct and current, and editing it would misrepresent this review as a rejection rather than what it
actually is (a "not yet" with named conditions).

**Working definition applied throughout.** Per the task's own framing, "safe to pull forward" means:
the *only* reason the item is currently deferred is "no real pilot client/traffic exists yet" — i.e.
pure engineering readiness with no analogous ethical/trust weight to `economic-service`'s trigger #11
override. "Needs more scrutiny" means the item has a real security, credential-lifecycle, or new-capability
dimension where speed itself is a risk factor, independent of whether a pilot client exists. Every
decision below states which bucket applies and why, rather than assuming the requester's own tentative
categorization is correct without re-checking the item's own text — as instructed.

---

## Category 1 — pull forward now (pure engineering readiness, no analogous ethical/trust weight)

### GW-017 — Locust load-test suite [Should -> pull forward]
Confirmed pure tooling: drives existing, already-shipped endpoints with mocked/seeded data, asserts
no hard SLA (explicitly "not a pass/fail gate"), and its own text already carries a disclosed-override
sentence ("No formal trigger... added at explicit user request, same disclosed-override treatment").
This item essentially already opted itself into this pattern; nothing about running a load generator
against the platform's own already-authenticated endpoints creates new risk. **Decision: pull forward.**
No additional care needed beyond what its own acceptance criteria already specify.

### INF-008 — MinIO service in Docker Compose [Should -> pull forward]
Confirmed pure infra scaffolding: stands up an empty container with credentials via env vars, same
pattern as the already-built `postgres`/`redis` services, and its own acceptance criteria explicitly
decline to invent bucket/prefix policy ahead of a real consumer ("no service currently reads or writes
to it"). No credential, auth, or data-exposure surface is created — MinIO's own default console/API
are bound the same way `postgres`/`redis` already are (INF-001/002 precedent: host-only binding
documented in `.env.example`). **Decision: pull forward.** Care: when wiring the compose service, apply
the same `127.0.0.1`-only host port binding `backlog-operability.md`'s "Areas checked with no real gap
found" section confirms for `postgres`/`redis`/`validation-service`, so this doesn't quietly reopen a
port-exposure gap the platform already closed elsewhere.

### INF-010 — TimescaleDB hypertable configuration [Could -> pull forward]
Re-checked against its own stated blocker: "no current story queries `split_results` as a time series
directly (the dashboard that would do this is trigger #8, not fired)." Trigger #8 has since fired (as
an explicit, disclosed override — `dashboard-web` exists and is built, per `backlog-dashboard-web.md`).
However, even with `dashboard-web` built, `DASH-004`'s own acceptance criteria route every read through
`validation-service`'s existing `GET /runs/{id}/splits` API, not a direct time-series SQL query against
`split_results` — so the *original* named blocker (a direct-query consumer) still doesn't exist. This
item is nonetheless safe to pull forward on independent grounds: it is a schema-level performance
optimization (partitioning column choice, hypertable conversion) that does not touch tenant isolation,
auth, or the leakage-aware protocol, and its own acceptance criteria require existing repository/query
behavior to remain unaffected. It is cheap, reversible, and has zero analogous ethical weight.
**Decision: pull forward**, but flagged for the PM: unlike the other Category-1 items, this one has no
current concrete consumer even after the trigger-#8 override, so scope it narrowly (the conversion
itself, proven not to break existing queries) rather than building any new time-series query surface
that still has no real caller.

### OPS-006 — Structured logging with request/tenant-correlation id [Could -> pull forward]
Confirmed pure observability/maintainability tooling: adopts a logging convention, adds a correlation
id via middleware, forwards it across the one existing proxy hop. Its own rationale states the only
reason it's not higher priority is "no live pilot client and no incident on record" — exactly the
"pure engineering readiness" bucket. It explicitly does not stand up a log-aggregation backend (kept as
a separate, larger, not-yet-justified decision — correctly still deferred, see below). **Decision: pull
forward.** Care: this item is a *precondition* other pulled-forward items benefit from — GW-014 (audit
logging) should be built to use OPS-006's structured convention as its foundation rather than
inventing a second, parallel logging shape; sequence OPS-006 first or alongside GW-014, not after.

### VS-015 — Object-storage-backed `DatasetSource` implementation [Should -> pull forward]
Confirmed to be the read-side Adapter implementation only, behind an already-built interface (VS-005),
with acceptance criteria that explicitly forbid it from writing to or owning any part of the object
storage prefix. Its named blocker was "`ingestion-service`'s upload API and processed-zone writes
(trigger #6), not yet fired" — but `ingestion-service`'s connectors have, in fact, already been pulled
forward this session (per `backlog-operability.md`'s own note: "pulled forward on 2026-08-05 at
explicit user request"), and `infra`'s MinIO service is being pulled forward in this same wave
(INF-008 above). Building VS-015's read adapter now is legitimate engineering readiness — the same
"build the interface's second implementation now, swap via DI, no call-site change" pattern already
used successfully for VS-004 -> VS-013. **Decision: pull forward.** Care, stated explicitly so it isn't
silently overclaimed: pulling this forward makes the *adapter* real; it does not mean a real,
tenant-scoped `processed/{tenant_id}/...` zone is actually populated with real pilot data yet — that
still depends on `ingestion-service` actually writing there, which is a separate, not-yet-confirmed
fact this story must not assume into existence. State that distinction in the story's own README
update, mirroring the same discipline INF-008's own item states for MinIO having "no real consumer yet."

---

## Category 2 — needs scrutiny; judged individually, not rubber-stamped

### GW-010 — API-key revocation [Should -> pull forward, with care]
**Recommend: build now.** This looked at first like a credential-lifecycle item deserving the same
caution as GW-011/GW-013, but on closer read it is materially lower risk than those two: the hard
part (a revocation flag, and GW-006's auth check already refusing revoked keys) is already built and
already tested (`GW-004`'s acceptance criteria explicitly proves "a revoked key's hash still resolves
to a record with `revoked_at` set"). What's missing is only the *path that sets the flag* — and GW-005's
existing precedent (operator-only provisioning, not public self-service) is the exact model to reuse.
Leaving a real, already-provisioned tenant's leaked/rotated key permanently valid because no revocation
path exists is itself a real operational risk today (GW-005 has already been used to provision at least
one operator test tenant) — not a hypothetical one being built ahead of need. **Specific care required**:
keep this strictly an operator-facing path (CLI script or an operator-gated endpoint, mirroring GW-005's
own "not a public sign-up flow" framing), not a tenant self-service revocation endpoint — self-service
revocation auth (proving the caller is entitled to revoke *this* key) is a materially different, harder
problem this story should not silently absorb. Do not add any caching layer to the revocation check that
would reintroduce a window where a revoked key stays valid.

### GW-011 — JWT-based session auth [Should -> hold]
**Recommend: hold.** Re-checked against its own named consumer: `dashboard-web` was in fact pulled
forward this session (trigger #8 override, `backlog-dashboard-web.md`) — but that backlog's own
decision 3 explicitly chose GW-006's API-key mechanism for `DASH-002`'s login screen, *not* JWT, and
its Won't-list (`DASH-107`) explicitly declines JWT as out of scope, deferring it back to gateway-api's
own backlog. So the one consumer that exists today has already looked at this option and picked the
other one. Building session-token issuance/verification (signing key management, token expiry,
algorithm choice, the `alg: none`-class of bugs that historically plague ad hoc JWT implementations)
with zero real caller to validate the design against is exactly the kind of "rushing a real security
mechanism ahead of need" this task's framing warns about — a wrong default here (e.g. a signing key
that isn't rotated, or a session lifetime with no revocation path once VS-010-equivalent tenant
resolution depends on it) is more expensive to unwind later than the API-key equivalent, because
sessions get embedded in client behavior (browser cookies, cached tokens) in a way a revocable API key
does not. **Hold** until either `libs/sdk` (trigger #9) or an actual browser-session use case
supersedes what GW-006 + DASH-002 already deliver — at that point this becomes a real design task with
a real consumer to validate against, not a speculative mechanism.

### GW-013 — Rate limiting / abuse protection [Could -> hold]
**Recommend: hold.** Its own rationale already states the precise reason this is genuinely different
from Category 1: "with zero real external traffic yet, there is no observed abuse pattern to defend
against." That is not merely "no pilot exists" scheduling convenience — rate-limit design (thresholds,
per-key vs. per-tenant granularity, response to bursty-but-legitimate batch usage like a pilot backfilling
historical runs) calibrated against zero real traffic risks two failure modes that are both worse than
not building it yet: (a) a threshold set too low that blocks a real pilot's first legitimate burst of
usage (undermining the exact "prove leakage-aware rigor to a first real client" goal every other module
in this wave is building toward), or (b) a false sense of DoS protection from a naively-tuned limiter
that doesn't actually stop a real abuse pattern once one is observed, while getting checked off as "done."
**Hold** until at least one real caller (even an internally-provisioned test client generating realistic
traffic shape, not just a Locust smoke run) produces an actual request pattern to calibrate against —
note GW-017 (pulled forward, Category 1) is a reasonable *source* of that calibration data once run, so
sequence GW-013 to genuinely follow GW-017's first real output, not build them in the same sprint.

### GW-014 — Auth event audit logging [Could -> pull forward, with care]
**Recommend: build now.** Re-checked against the "real security/trust dimension" concern the task
raises for this bucket: the actual scope here — logging key issuance, revocation, and failed-auth
attempts with `tenant_id`/timestamp/outcome, explicitly *never* raw keys/secrets — is a narrower,
lower-risk version of "what gets logged" than the framing implies. It doesn't create a new credential
surface (unlike GW-011) and doesn't require a new decision under uncertainty (unlike GW-013's threshold
tuning) — it's an append-only record of events that already happen (GW-006's auth check, GW-005/GW-010's
provisioning/revocation). Given the platform's own core positioning is an *audit* product
(`da-tese-ao-produto.md` sections 2.3.4/2.4), having no record of who could access what is a real,
thematically-relevant gap independent of whether a pilot client exists yet to ask for it. **Specific
care required**: build this directly on OPS-006's structured-logging convention (pulled forward above)
rather than inventing a second logging shape; do not stand up log retention/shipping to any external
system as part of this story (that remains correctly out of scope, matching OPS-007's own still-held
"no aggregation backend" decision) — this stays "structured local log line," not "compliance-grade
retained audit trail," until a real auditor or compliance conversation defines actual retention
requirements.

### ARCH-005 (remaining half: LC-009 signed/verified internal tenant-header propagation) [Should -> hold]
**Recommend: hold**, distinct from GW-015 itself which was already correctly marked Won't-this-backlog
and handed to `libs/common`'s own LC-009. What's being evaluated here is whether *that* follow-up
(LC-009/GW-015's actual cryptographic design — signed internal tokens, mTLS, or equivalent) should be
pulled forward now. Re-checked the actual current exposure: `validation-service`'s port is already
bound to `127.0.0.1` only (ARCH-005's own AC2, marked partially addressed 2026-08-09), and
`validation-service` is architecturally not internet-facing (`gateway-api` is the sole internet-facing
service, per implementation-plan.md section 2) — so today's actual exploitable surface requires either
a misconfiguration or same-host/same-Docker-network access, not a remote attacker. Given that, the
urgency is lower than the story's own docstring language ("real today, not hypothetical") makes it
sound in isolation. This is squarely the task's "needs real cryptographic verification design, not just
a doc update" case: choosing and correctly implementing a signed-header or mTLS scheme is genuine
security engineering (key management, rotation, failure-mode behavior when verification fails) — doing
it hastily under a "keep pace with the other overrides" mandate is a worse outcome than leaving the
current, already-disclosed, already-network-mitigated interim in place a while longer. **Hold on full
implementation.** If the requester wants to make progress here without accepting that risk, the
narrower, genuinely-safe thing to pull forward instead would be a **design spike only** (evaluate
signed-header vs. mTLS vs. Compose-internal-network-only enforcement, document a recommendation, no
running code) — flagged here as an option, not committed to, since the requester didn't ask for a new
story to be invented.

### VS-017 — Client-supplied prediction column as a `Baseline`-interface Strategy [Could -> pull forward, with an added acceptance criterion]
**Recommend: build now, with one addition.** This is genuinely a new capability, not hygiene, as the
task flags — but re-checked against the platform's actual guardrails: it does not touch the
leakage-aware split/purge-gap protocol at all (client predictions are supplied for the already-defined
test windows, never used to re-derive splits), the naive baselines remain structurally mandatory
(VS-019's Won't already blocks any bypass, and VS-017's own AC repeats this), and no arbitrary client
code execution is introduced (VS-018's Won't already blocks that, and VS-017's own AC repeats it too).
The one real risk this review surfaces that VS-017's existing acceptance criteria don't yet name: a
client could submit a "prediction" series for the test period that was itself produced with knowledge
of the actual test-period outcomes (i.e., the *client's own* process leaked, not this platform's) — the
audit's honest job is to score whatever is submitted against Naive0/NaiveLast, not to certify the
client's forecasting process was itself leakage-free. That distinction is core to this platform's
non-negotiable positioning (`da-tese-ao-produto.md` — validation/audit, not a certification of a third
party's methodology) and isn't currently written into VS-017's own acceptance criteria or report
language. **Decision: pull forward, with an added acceptance criterion**: any report/response surface
built on top of a client-supplied prediction run must state explicitly that the platform validates the
*comparison* (client series vs. naive baselines, honestly computed), not the *provenance* of the
client's predictions — so a future reader (or client) doesn't mistake "beat Naive0 in this audit" for
"this platform certifies your model didn't leak." This is a wording/scope addition to VS-017's existing
acceptance criteria, not a new story.

---

## Summary table

| ID | Item | Bucket | Decision | Key care condition (if any) |
|---|---|---|---|---|
| GW-017 | Locust load-test suite | 1 | Pull forward | none beyond existing AC |
| INF-008 | MinIO in Compose | 1 | Pull forward | keep host-only port binding |
| INF-010 | TimescaleDB hypertables | 1 | Pull forward | scope narrowly, no new query surface |
| OPS-006 | Structured logging + correlation id | 1 | Pull forward | build first; GW-014 depends on it |
| VS-015 | Object-storage `DatasetSource` | 1 | Pull forward | don't overclaim ingestion-service actually populates the zone |
| GW-010 | API-key revocation | 2 | Pull forward | operator-only path, no self-service, no caching window |
| GW-011 | JWT session auth | 2 | Hold | no real consumer chose it (dashboard-web chose API keys); revisit at libs/sdk or real session need |
| GW-013 | Rate limiting | 2 | Hold | needs real traffic shape to calibrate against; revisit after GW-017 produces data |
| GW-014 | Auth event audit logging | 2 | Pull forward | build on OPS-006; no external retention/shipping yet |
| ARCH-005 (LC-009 half) | Signed internal tenant propagation | 2 | Hold | current exposure already network-mitigated; consider a design-spike-only alternative if requested |
| VS-017 | Client-supplied prediction Strategy | 2 | Pull forward | add AC on "audits comparison, not provenance" positioning language |

Total: 9 pull-forward, 2 hold.
