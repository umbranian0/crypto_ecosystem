"""Smoke test baseline (GW-001): confirms the app package imports and the
FastAPI app is constructible, without depending on any endpoint/repository
work from later GW tickets. Mirrors validation-service's VS-001/NFE-001
approach: `uv run pytest` with zero real tests would exit non-zero (pytest
exit code 5 for "no tests collected"), so a minimal import smoke test is the
faithful "passing baseline" instead of a literal empty suite.
"""

from __future__ import annotations


def test_app_module_imports() -> None:
    from app.main import app

    assert app.title == "gateway-api"


def test_naive_first_common_importable_as_path_dependency() -> None:
    # Confirms the workspace/path dependency declared in pyproject.toml
    # resolves -- gateway-api forwards verified tenant context using this
    # shared type, so it must be importable from day one.
    import naive_first_common  # noqa: F401
