"""ARCH-004: `db_path` is the shared `naive_first_common.testing` fixture,
mirrors `validation-service`'s own `tests/conftest.py`.
"""

from __future__ import annotations

from naive_first_common.testing import sqlite_db_path as db_path

__all__ = ["db_path"]
