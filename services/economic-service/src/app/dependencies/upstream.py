"""ECON-004: DI seam (implementation-plan.md section 7) for
`UpstreamValidationResultClient`.

Kept as its own module (`dependencies/upstream.py`), separate from
`dependencies/repositories.py` -- documented choice per this ticket's Design
section ("added to `dependencies/repositories.py` -- implementer's choice,
document which"). `repositories.py` is scoped to ECON-002's DB-backed
`EconomicInputRepository`/health-check `Engine` providers; this provider has
no DB/Engine dependency at all (the mock client is pure in-memory fixture
data), so a separate module keeps that file's existing scope untouched
rather than growing it with an unrelated concern.

Single responsibility, mirroring `repositories.py`'s own docstring: give
route handlers a `Depends()`-injectable provider typed against
`UpstreamValidationResultClient`, so handlers depend on the interface, never
a concrete class.

**Hard rule (README.md's trigger-#11 override disclosure, binding for every
future ticket against this service): this provider must never grow a
conditional/env-var branch between `MockValidationResultClient` and a
hypothetical real client.** Wiring a real client is its own new,
separately-authorized ticket -- never a quiet edit to this function.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.upstream_client import MockValidationResultClient, UpstreamValidationResultClient


def get_upstream_client() -> UpstreamValidationResultClient:
    return MockValidationResultClient()


UpstreamValidationResultClientDep = Annotated[
    UpstreamValidationResultClient, Depends(get_upstream_client)
]
