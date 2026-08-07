"""Smoke test baseline (VS-001): confirms the app package imports and the
FastAPI app is constructible, without depending on any endpoint/repository
work from later VS tickets. Mirrors naive_first_engine's NFE-001 approach:
`uv run pytest` with zero real tests would exit non-zero (pytest exit code 5
for "no tests collected"), so a minimal import smoke test is the faithful
"passing baseline" instead of a literal empty suite.
"""

from __future__ import annotations


def test_app_module_imports() -> None:
    from app.main import app

    assert app.title == "validation-service"


def test_naive_first_engine_importable_as_path_dependency() -> None:
    # Confirms the workspace/path dependency declared in pyproject.toml
    # resolves -- validation-service wraps this library, so it must be
    # importable from day one even before VS-006 wires up an actual call.
    import naive_first_engine  # noqa: F401
