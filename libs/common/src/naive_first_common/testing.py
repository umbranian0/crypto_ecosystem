"""Shared pytest test-fixture scaffolding (ARCH-004).

Extracted from validation-service's and gateway-api's
`tests/test_sqlite_repository.py` modules, which each defined a
byte-for-byte identical `db_path` fixture.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def sqlite_db_path(tmp_path) -> str:
    # A real file path (not :memory:) so this exercises the same
    # file-based-persistence code path production uses, while each test
    # still gets an isolated, disposable file under tmp_path.
    return str(tmp_path / "test.db")
