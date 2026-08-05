"""Smoke test: the package and its five modules are importable.

Serves as the passing test-runner baseline for NFE-001 (pytest's default exit
code for zero collected tests is non-zero, so a real assertion is used
instead of an empty test suite).
"""

import naive_first_engine
from naive_first_engine import baselines, dm_test, metrics, report_schema, splitting


def test_package_importable():
    assert naive_first_engine is not None


def test_all_five_modules_importable():
    for module in (splitting, baselines, metrics, dm_test, report_schema):
        assert module.__doc__, f"{module.__name__} is missing its single-responsibility docstring"
