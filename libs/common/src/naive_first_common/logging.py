"""OPS-006: structured logging + request/tenant-correlation id.

Single responsibility: give every FastAPI service the same JSON logging
convention and the same correlation-id-per-request mechanism, so a request
proxied from `gateway-api` into `validation-service` can be joined across
both services' log output by one shared id (implementation-plan.md section
9 -- cross-service duplication of this shape belongs in `libs/common`, not
copy-pasted into each service).

Deliberately stdlib-only (`logging` + a small JSON `Formatter` subclass, no
`structlog`/`python-json-logger`) -- see this ticket's Design section: this
is a Could-priority story that must not add new dependency surface.

`configure_structured_logging()` sets up the JSON formatter *and* attaches
`_CorrelationIdFilter` to the root logger's handler, so every logger created
anywhere in the process (via plain `logging.getLogger(__name__)`, e.g.
`validation-service`'s `events.py`) picks up both the JSON shape and the
current request's correlation id with no per-call-site change required.
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-Id"

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


class _CorrelationIdFilter(logging.Filter):
    """Injects the current request's correlation id into every log record.

    Reads `correlation_id_var` at emit time, not at record-creation-site
    time, so a plain `logger.info(...)` call anywhere in the process (no
    `extra=` needed) still carries the right id. Empty string (never the
    literal `"None"`) when no request is in flight -- mirrors
    `RedisStreamsEventPublisher`'s existing `None -> ""` field convention in
    `events.py`.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    """Renders one JSON object per log record: `timestamp`, `level`,
    `logger`, `message`, `correlation_id`.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", ""),
        }
        return json.dumps(payload)


def configure_structured_logging(level: int = logging.INFO) -> None:
    """Configures the root logger with one stream handler carrying the JSON
    formatter and the correlation-id filter.

    Idempotent: clears any previously attached handlers first, so calling
    this more than once (e.g. import-time in a service's `app.main` plus a
    test importing the same module) never duplicates log lines.
    """

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for existing_handler in list(root_logger.handlers):
        root_logger.removeHandler(existing_handler)

    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler.addFilter(_CorrelationIdFilter())
    root_logger.addHandler(handler)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reads `X-Correlation-Id` from the inbound request if present
    (non-empty), otherwise generates `uuid4().hex`; sets `correlation_id_var`
    for the duration of the request, resetting it via a `contextvars.Token`
    in a `finally` block so a reused worker's next request can never see a
    stale id. Also sets `X-Correlation-Id` on the response.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound = request.headers.get(CORRELATION_ID_HEADER)
        correlation_id = inbound if inbound else uuid.uuid4().hex

        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)

        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
