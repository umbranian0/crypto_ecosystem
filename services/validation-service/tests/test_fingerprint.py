"""TRUST-003: `app.fingerprint` unit tests.

Covers `compute_config_fingerprint`'s determinism/sensitivity and
`get_engine_version`'s real-value (not hardcoded-literal) behavior.
"""

from __future__ import annotations

from importlib.metadata import version

from app.fingerprint import compute_config_fingerprint, get_engine_version


def test_compute_config_fingerprint_is_deterministic_across_key_order() -> None:
    # Two dicts with identical key/value pairs but different insertion
    # order -- proves canonicalization (sort_keys=True), not just "the same
    # object hashes the same as itself".
    a = {"train_window": 100, "test_window": 20, "step": 10}
    b = {"step": 10, "test_window": 20, "train_window": 100}

    assert list(a.keys()) != list(b.keys())
    assert compute_config_fingerprint(a) == compute_config_fingerprint(b)


def test_compute_config_fingerprint_is_sensitive_to_a_single_differing_value() -> None:
    a = {"train_window": 100, "test_window": 20, "step": 10}
    b = {"train_window": 101, "test_window": 20, "step": 10}

    assert compute_config_fingerprint(a) != compute_config_fingerprint(b)


def test_get_engine_version_returns_real_installed_version() -> None:
    result = get_engine_version()

    assert isinstance(result, str)
    assert result
    # Not a hardcoded "0.1.0" literal -- matches the real installed
    # distribution version, which would silently go stale on a real bump.
    assert result == version("naive_first_engine")
