from __future__ import annotations

from naive_first_common.testing import sqlite_db_path  # noqa: F401 (registers fixture)


def test_sqlite_db_path_returns_file_path_under_tmp_path(sqlite_db_path, tmp_path) -> None:
    assert sqlite_db_path == str(tmp_path / "test.db")
