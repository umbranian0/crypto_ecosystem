"""naive_first_common: shared cross-cutting concerns for Naive-First platform
services. See README.md for owns/does-not-own boundary and status.

Public API (LC-001: empty skeleton; populated by LC-002/LC-003).
"""

from __future__ import annotations

from naive_first_common.tenant_context import TenantContext, get_tenant_context

__all__ = ["TenantContext", "get_tenant_context"]
