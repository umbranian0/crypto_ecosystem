# naive_first_sdk

**Status: planned (trigger #9 — create when a pilot client wants to submit predictions programmatically instead of via the dashboard upload form).**

Thin Python client wrapping `services/gateway-api` for external "bring your own predictions" clients. See [../../docs/da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 2.3.6 and [../../docs/implementation-plan.md](../../docs/implementation-plan.md) section 2.

**Owns**: HTTP client calls to the public gateway API only (upload predictions, trigger a run, poll status, fetch a report). No business logic, no direct DB/storage access, no validation logic — that all lives server-side so the protocol can't be bypassed by a client-side SDK bug.

**Does not own**: authentication storage beyond holding an API key the client provides; any of the validation/report logic itself.

**Contract**: mirrors `gateway-api`'s OpenAPI schema. Regenerate/verify against it whenever the gateway's contract changes — don't let the SDK's method signatures drift from the actual API.
