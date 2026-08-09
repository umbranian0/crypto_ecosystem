"""ARCH-002: `app.dependencies.repositories._get_engine` must be memoized by
URL/db_path, not zero-arg (grooming decision #2, binding). A zero-arg cache
would return the same `Engine` after `monkeypatch.setenv(VALIDATION_SERVICE_DB_PATH,
...)` swaps the path mid-suite, silently pointing every other test at the
wrong file -- exactly the regression this file exists to catch.
"""

from __future__ import annotations

from app.dependencies.repositories import (
    _DB_PATH_ENV_VAR,
    get_split_result_repository,
    get_validation_run_repository,
)


def test_same_url_reuses_same_engine_across_dependency_resolutions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "same.db"))

    first = get_validation_run_repository()
    second = get_validation_run_repository()

    assert first._engine is second._engine


def test_different_url_returns_different_engine(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "one.db"))
    first = get_validation_run_repository()

    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "two.db"))
    second = get_validation_run_repository()

    assert first._engine is not second._engine


def test_engine_shared_across_repository_types_for_same_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "shared.db"))

    run_repo = get_validation_run_repository()
    split_repo = get_split_result_repository()

    assert run_repo._engine is split_repo._engine
