"""SETUP-021: in-process ring-buffer of recent WARNING+ log records.

Single responsibility: a `logging.Handler` observer (one additional observer
of the standard `logging` module's event stream, alongside -- not replacing
-- OPS-006's existing JSON-formatter/correlation-id observer) that keeps a
bounded, in-memory record of the last 50 WARNING-and-above log records, so
each service can expose a `/diagnostics/recent-errors` endpoint without
standing up a log-aggregation backend (still OPS-007's declined scope).

Deliberately no I/O, no FastAPI dependency, no third-party import -- pure
`logging` + `collections`, per libs/common's own no-I/O constraint.
"""

from __future__ import annotations

import logging
from collections import deque


class RecentErrorsHandler(logging.Handler):
    """Bounded ring buffer of the last `maxlen` WARNING+ log records.

    Level filtering is done via the standard library's own `setLevel`
    mechanism (the logging module never calls `emit()` for a record below
    the handler's level) -- not a manual level check duplicated here.

    `emit()` never records `record.exc_info`/`record.exc_text` (a raw
    traceback), request body, or any secret value -- only the already-
    formatted `message` string (`record.getMessage()`) and the four plain
    fields below. This is a deliberate, reviewed boundary (SETUP-021 Review
    acceptance criteria), not an oversight.
    """

    def __init__(self, maxlen: int = 50) -> None:
        super().__init__(level=logging.WARNING)
        self._buffer: deque[dict[str, str]] = deque(maxlen=maxlen)

    def emit(self, record: logging.LogRecord) -> None:
        self._buffer.append(
            {
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "correlation_id": getattr(record, "correlation_id", ""),
            }
        )

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return logging.Formatter().formatTime(record, datefmt)

    def snapshot(self) -> list[dict[str, str]]:
        """Most-recent-first plain list copy (never a live deque reference)."""

        return list(reversed(self._buffer))

    def clear(self) -> None:
        """Empties the buffer -- test-isolation helper for callers holding a
        module-level singleton instance across tests (e.g. dashboard-web's
        `recent_errors_handler`), not used by any production code path.
        """

        self._buffer.clear()
