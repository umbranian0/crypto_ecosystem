"""GW-007: downstream-header-building seam.

Builds the headers `gateway-api` attaches to its own outbound HTTP calls to
internal services (`validation-service`, etc. -- the actual call is GW-008's
job, this ticket only defines the seam it will call).

Design decision (ticket Design section): `build_downstream_headers` takes
only GW-006's already-verified `TenantContext` -- never the inbound FastAPI
`Request`/its headers. An inbound request may carry its own `X-Tenant-Id`
from a malicious or confused caller; that value must never reach a
downstream service, so the function has no way to read it in the first
place. Keeping this as its own named function (rather than inlined at each
proxy call site) is the DRY point: every downstream call GW-008/GW-009 make
builds headers the same way, so "never forward the inbound header" holds by
construction, not by convention repeated per call site.
"""

from __future__ import annotations

from naive_first_common.logging import correlation_id_var
from naive_first_common.tenant_context import TenantContext


def build_downstream_headers(tenant: TenantContext) -> dict[str, str]:
    """Returns the exact header set gateway-api forwards to internal
    services: `X-Tenant-Id` sourced only from the verified `TenantContext`,
    plus `X-Correlation-Id` (OPS-006) sourced from the current request's
    `correlation_id_var` -- set by `CorrelationIdMiddleware` before any
    route handler runs, so validation-service's logs for the proxied call can
    be joined back to this request's own logs.
    """
    return {"X-Tenant-Id": tenant.tenant_id, "X-Correlation-Id": correlation_id_var.get()}
