"""GW-029: `GET /openapi.json`'s security schemes must not collapse.

Live-verified root cause (ticket Analysis section): `auth.py`'s
`_authorization_scheme`/`_x_api_key_scheme` and `operator_auth.py`'s
`_operator_token_scheme` are all `fastapi.security.APIKeyHeader` instances
with no explicit `scheme_name=`, so FastAPI's OpenAPI generator named all
three after the shared class name (`"APIKeyHeader"`), collapsing them into
one shared, wrongly-labeled `securityScheme` and making tenant-gated and
operator-gated routes show an identical, indistinguishable security
requirement. Fixed by giving each instance its own `scheme_name=`
(`AuthorizationBearer`/`XApiKey`/`XOperatorToken`) -- no runtime auth logic
changed, this test only proves the published schema shape.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _openapi_schema() -> dict:
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_security_schemes_has_exactly_three_distinctly_named_entries() -> None:
    schema = _openapi_schema()
    schemes = schema["components"]["securitySchemes"]

    assert set(schemes.keys()) == {"AuthorizationBearer", "XApiKey", "XOperatorToken"}

    assert schemes["AuthorizationBearer"]["type"] == "apiKey"
    assert schemes["AuthorizationBearer"]["in"] == "header"
    assert schemes["AuthorizationBearer"]["name"] == "Authorization"

    assert schemes["XApiKey"]["type"] == "apiKey"
    assert schemes["XApiKey"]["in"] == "header"
    assert schemes["XApiKey"]["name"] == "X-Api-Key"

    assert schemes["XOperatorToken"]["type"] == "apiKey"
    assert schemes["XOperatorToken"]["in"] == "header"
    assert schemes["XOperatorToken"]["name"] == "X-Operator-Token"


def test_runs_path_security_references_only_tenant_schemes() -> None:
    schema = _openapi_schema()
    runs_get = schema["paths"]["/runs"]["get"]

    security_scheme_names = {
        scheme_name for requirement in runs_get["security"] for scheme_name in requirement
    }

    assert security_scheme_names == {"AuthorizationBearer", "XApiKey"}


def test_at_least_one_operator_gated_path_references_only_operator_scheme() -> None:
    schema = _openapi_schema()
    tenants_get = schema["paths"]["/tenants"]["get"]

    security_scheme_names = {
        scheme_name for requirement in tenants_get["security"] for scheme_name in requirement
    }

    assert security_scheme_names == {"XOperatorToken"}
