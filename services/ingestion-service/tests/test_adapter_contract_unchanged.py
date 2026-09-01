"""Structural regression test (INGEST-006): proves INGEST-003/004/005's
DB-integration work was additive to the `IngestionSource` Adapter contract,
not a rewrite-in-disguise.

Introspection-based, same spirit as `NFE-018`/`LC-005`'s doc-sync checks, but
scoped to a single method signature rather than a whole module's public
surface: `IngestionSource.fetch` must still be exactly
`fetch(self, since: datetime) -> FetchResult`.
"""
from __future__ import annotations

import inspect
import typing
from datetime import datetime

from connectors.base import FetchResult, IngestionSource


def test_fetch_signature_is_unchanged() -> None:
    signature = inspect.signature(IngestionSource.fetch)
    # `connectors/base.py` uses `from __future__ import annotations`, so
    # annotations are unevaluated strings at introspection time -- resolve
    # them via `get_type_hints` rather than comparing to string literals.
    hints = typing.get_type_hints(IngestionSource.fetch)

    assert list(signature.parameters) == ["self", "since"]
    assert signature.parameters["since"].default is inspect.Parameter.empty
    assert hints["since"] is datetime
    assert hints["return"] is FetchResult


def test_fetch_is_still_the_sole_abstract_method() -> None:
    assert IngestionSource.__abstractmethods__ == frozenset({"fetch"})
