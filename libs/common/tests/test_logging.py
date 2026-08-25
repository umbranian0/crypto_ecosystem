"""OPS-006: naive_first_common.logging tests.

Standalone inside libs/common/tests/ (no import from services/*), same
precedent as test_get_tenant_context_app.py -- proves the middleware/context
var/formatter against real FastAPI wiring, not by calling internals directly
only.
"""

from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from naive_first_common.logging import (
    CorrelationIdMiddleware,
    _JsonFormatter,
    configure_structured_logging,
    correlation_id_var,
)

app = FastAPI()
app.add_middleware(CorrelationIdMiddleware)


@app.get("/probe")
def probe() -> dict[str, str]:
    return {"correlation_id": correlation_id_var.get()}


client = TestClient(app)


def test_middleware_generates_id_when_none_supplied() -> None:
    response = client.get("/probe")

    assert response.status_code == 200
    generated = response.headers["X-Correlation-Id"]
    assert generated
    assert response.json()["correlation_id"] == generated


def test_middleware_reuses_inbound_correlation_id() -> None:
    response = client.get("/probe", headers={"X-Correlation-Id": "inbound-id-123"})

    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"] == "inbound-id-123"
    assert response.json()["correlation_id"] == "inbound-id-123"


def test_two_sequential_requests_without_inbound_header_get_different_ids() -> None:
    """Non-tautological proof: two separate generated ids, not the same
    value asserted against itself.
    """
    first = client.get("/probe").headers["X-Correlation-Id"]
    second = client.get("/probe").headers["X-Correlation-Id"]

    assert first != second


def test_correlation_id_var_resets_to_default_outside_a_request() -> None:
    assert correlation_id_var.get() == ""

    client.get("/probe", headers={"X-Correlation-Id": "should-not-leak"})

    assert correlation_id_var.get() == ""


def test_json_formatter_produces_valid_json_with_expected_keys() -> None:
    record = logging.LogRecord(
        name="some.module",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.correlation_id = "abc-123"

    rendered = _JsonFormatter().format(record)
    parsed = json.loads(rendered)

    assert parsed["message"] == "hello world"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "some.module"
    assert parsed["correlation_id"] == "abc-123"
    assert "timestamp" in parsed


def test_configure_structured_logging_attaches_json_formatter_and_correlation_filter() -> None:
    configure_structured_logging()
    root_logger = logging.getLogger()

    assert len(root_logger.handlers) == 1
    handler = root_logger.handlers[0]
    assert isinstance(handler.formatter, _JsonFormatter)

    stream = io.StringIO()
    handler.stream = stream

    token = correlation_id_var.set("test-correlation-id")
    try:
        logging.getLogger("naive_first_common.tests").info("a log line")
    finally:
        correlation_id_var.reset(token)

    parsed = json.loads(stream.getvalue().strip())
    assert parsed["message"] == "a log line"
    assert parsed["correlation_id"] == "test-correlation-id"


def test_configure_structured_logging_is_idempotent() -> None:
    configure_structured_logging()
    configure_structured_logging()

    assert len(logging.getLogger().handlers) == 1
