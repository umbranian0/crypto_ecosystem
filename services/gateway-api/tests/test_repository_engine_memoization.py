"""ARCH-002: `app.dependencies.repositories._get_engine` must be memoized by
URL/db_path, not zero-arg (grooming decision #2, binding). A zero-arg cache
would return the same `Engine` after `monkeypatch.setenv(GATEWAY_API_DB_PATH,
...)` swaps the path mid-suite, silently pointing every other test at the
wrong file -- exactly the regression this file exists to catch.
"""

from __future__ import annotations

from app.dependencies.repositories import (
    _DB_PATH_ENV_VAR,
    get_api_key_repository,
    get_tenant_repository,
    get_user_repository,
)


def test_same_url_reuses_same_engine_across_dependency_resolutions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "same.db"))

    first = get_tenant_repository()
    second = get_tenant_repository()

    assert first._engine is second._engine


def test_different_url_returns_different_engine(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "one.db"))
    first = get_tenant_repository()

    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "two.db"))
    second = get_tenant_repository()

    assert first._engine is not second._engine


def test_engine_shared_across_repository_types_for_same_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(_DB_PATH_ENV_VAR, str(tmp_path / "shared.db"))

    tenant_repo = get_tenant_repository()
    user_repo = get_user_repository()
    key_repo = get_api_key_repository()

    assert tenant_repo._engine is user_repo._engine is key_repo._engine
