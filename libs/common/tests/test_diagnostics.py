"""SETUP-021: naive_first_common.diagnostics.RecentErrorsHandler tests.

Standalone against a throwaway logger (does not touch the root logger's
handlers, unlike test_logging.py's configure_structured_logging tests) so
these tests never interact with pytest's own logging capture setup.
"""

from __future__ import annotations

import logging

from naive_first_common.diagnostics import RecentErrorsHandler


def _make_logger(handler: RecentErrorsHandler) -> logging.Logger:
    logger = logging.getLogger(f"test.diagnostics.{id(handler)}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(handler)
    return logger


def test_buffer_caps_at_maxlen_and_drops_oldest_first() -> None:
    handler = RecentErrorsHandler(maxlen=3)
    logger = _make_logger(handler)

    for i in range(5):
        logger.warning("warning %s", i)

    snapshot = handler.snapshot()
    assert len(snapshot) == 3
    assert [entry["message"] for entry in snapshot] == [
        "warning 4",
        "warning 3",
        "warning 2",
    ]


def test_only_warning_and_above_captured() -> None:
    handler = RecentErrorsHandler()
    logger = _make_logger(handler)

    logger.info("info message, never captured")
    logger.warning("warning message, captured")
    logger.error("error message, captured")

    snapshot = handler.snapshot()
    messages = [entry["message"] for entry in snapshot]
    assert "info message, never captured" not in messages
    assert "warning message, captured" in messages
    assert "error message, captured" in messages
    assert len(snapshot) == 2


def test_snapshot_returns_most_recent_first() -> None:
    handler = RecentErrorsHandler()
    logger = _make_logger(handler)

    logger.warning("first")
    logger.warning("second")
    logger.warning("third")

    snapshot = handler.snapshot()
    assert [entry["message"] for entry in snapshot] == ["third", "second", "first"]


def test_snapshot_is_a_copy_not_a_live_reference() -> None:
    handler = RecentErrorsHandler()
    logger = _make_logger(handler)
    logger.warning("one")

    snapshot = handler.snapshot()
    logger.warning("two")

    assert len(snapshot) == 1
    assert handler.snapshot() != snapshot


def test_entry_has_expected_fields() -> None:
    handler = RecentErrorsHandler()
    logger = _make_logger(handler)

    logger.warning("something went wrong")

    entry = handler.snapshot()[0]
    assert set(entry.keys()) == {"timestamp", "level", "logger", "message", "correlation_id"}
    assert entry["level"] == "WARNING"
    assert entry["message"] == "something went wrong"


def test_never_includes_exc_info_or_traceback_even_when_logged_with_exc_info() -> None:
    handler = RecentErrorsHandler()
    logger = _make_logger(handler)

    try:
        raise ValueError("boom")
    except ValueError:
        logger.error("failed to process", exc_info=True)

    entry = handler.snapshot()[0]
    assert "exc_info" not in entry
    assert "traceback" not in entry
    assert "Traceback" not in entry["message"]
    assert "ValueError" not in entry["message"]
    assert entry["message"] == "failed to process"
