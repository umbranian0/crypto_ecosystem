"""ARCH-004: `db_path` is the shared `naive_first_common.testing` fixture,
re-exposed here under its historical local name so existing tests using the
`db_path` fixture argument keep working unmodified.
"""

from __future__ import annotations

from naive_first_common.testing import sqlite_db_path as db_path

__all__ = ["db_path"]
