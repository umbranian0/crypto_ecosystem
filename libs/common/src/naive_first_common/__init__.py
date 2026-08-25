"""naive_first_common: shared cross-cutting concerns for Naive-First platform
services. See README.md for owns/does-not-own boundary and status.

Public API (LC-001: empty skeleton; populated by LC-002/LC-003, ARCH-001,
OPS-006).
"""

from __future__ import annotations

from naive_first_common.db import build_engine
from naive_first_common.logging import CorrelationIdMiddleware, configure_structured_logging
from naive_first_common.tenant_context import TenantContext, get_tenant_context

__all__ = [
    "TenantContext",
    "build_engine",
    "get_tenant_context",
    "configure_structured_logging",
    "CorrelationIdMiddleware",
]
