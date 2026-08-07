from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from naive_first_common import TenantContext, get_tenant_context
from naive_first_common.tenant_context import _extract_tenant_id


def test_valid_tenant_id_round_trips() -> None:
    context = TenantContext(tenant_id="tenant-123")
    assert context.tenant_id == "tenant-123"


def test_empty_tenant_id_raises() -> None:
    with pytest.raises(ValidationError):
        TenantContext(tenant_id="")


def test_whitespace_only_tenant_id_raises() -> None:
    with pytest.raises(ValidationError):
        TenantContext(tenant_id="   ")


def test_missing_tenant_id_raises() -> None:
    with pytest.raises(ValidationError):
        TenantContext()


def test_extract_tenant_id_passes_through_value() -> None:
    assert _extract_tenant_id("tenant-123") == "tenant-123"


def test_extract_tenant_id_passes_through_none() -> None:
    assert _extract_tenant_id(None) is None


def test_get_tenant_context_valid_header_returns_context() -> None:
    context = get_tenant_context(x_tenant_id="tenant-123")
    assert context == TenantContext(tenant_id="tenant-123")


def test_get_tenant_context_missing_header_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(x_tenant_id=None)
    assert exc_info.value.status_code == 401


def test_get_tenant_context_empty_header_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(x_tenant_id="")
    assert exc_info.value.status_code == 401


def test_get_tenant_context_whitespace_header_raises_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        get_tenant_context(x_tenant_id="   ")
    assert exc_info.value.status_code == 401
