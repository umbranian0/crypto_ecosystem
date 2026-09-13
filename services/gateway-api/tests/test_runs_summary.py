"""SETUP-022: `GET /system/runs-summary`.

Wires the real `SQLiteTenantRepository` (same `_wire_sqlite` pattern
`test_tenants_router.py` established) for `TenantRepositoryDep`, and fakes
`validation-service`'s `GET /runs` via `httpx.MockTransport` (same pattern
`test_system_health.py` uses for its own downstream fakes).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_api_key_repository, get_tenant_repository
from app.main import app
from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository

OPERATOR_TOKEN = "the-real-operator-token"


def _wire_sqlite(tmp_path):
    db_path = str(tmp_path / "gateway.db")
    tenant_repo = SQLiteTenantRepository(db_path)
    key_repo = SQLiteApiKeyRepository(db_path)
    app.dependency_overrides[get_tenant_repository] = lambda: tenant_repo
    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    return tenant_repo, key_repo


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://internal-service.example"
    )


def _clear_overrides():
    app.dependency_overrides.pop(get_tenant_repository, None)
    app.dependency_overrides.pop(get_api_key_repository, None)
    app.dependency_overrides.pop(get_validation_service_client, None)


def _op_headers():
    return {"X-Operator-Token": OPERATOR_TOKEN}


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_requires_operator_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _wire_sqlite(tmp_path)
    app.dependency_overrides[get_validation_service_client] = lambda: _mock_client(
        lambda request: httpx.Response(200, json={"items": [], "limit": 100, "offset": 0, "total": 0})
    )
    try:
        response = TestClient(app).get("/system/runs-summary")
        assert response.status_code == 401
    finally:
        _clear_overrides()


def test_wrong_kind_of_credential_returns_403(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    app.dependency_overrides[get_validation_service_client] = lambda: _mock_client(
        lambda request: httpx.Response(200, json={"items": [], "limit": 100, "offset": 0, "total": 0})
    )
    try:
        import hashlib

        tenant = tenant_repo.create_tenant("Acme Corp")
        raw_key = "tenant-a-real-raw-key"
        key_repo.create_key(tenant.id, hashlib.sha256(raw_key.encode()).hexdigest())

        response = TestClient(app).get(
            "/system/runs-summary", headers={"X-Operator-Token": raw_key}
        )
        assert response.status_code == 403
    finally:
        _clear_overrides()


def test_zero_runs_in_window_renders_all_zero_percentages(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _ = _wire_sqlite(tmp_path)
    tenant_repo.create_tenant("Acme Corp")
    app.dependency_overrides[get_validation_service_client] = lambda: _mock_client(
        lambda request: httpx.Response(200, json={"items": [], "limit": 100, "offset": 0, "total": 0})
    )
    try:
        response = TestClient(app).get("/system/runs-summary", headers=_op_headers())
        assert response.status_code == 200
        assert response.json() == {
            "total": 0,
            "completed_pct": 0.0,
            "failed_pct": 0.0,
            "running_pct": 0.0,
        }
    finally:
        _clear_overrides()


def test_correct_percentage_math_across_two_tenants_and_all_statuses(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _ = _wire_sqlite(tmp_path)
    tenant_a = tenant_repo.create_tenant("Tenant A")
    tenant_b = tenant_repo.create_tenant("Tenant B")

    now = datetime.now(timezone.utc)

    def _run(status: str, run_id: str) -> dict:
        return {
            "id": run_id,
            "status": status,
            "created_at": _iso(now - timedelta(minutes=5)),
            "completed_at": None,
        }

    def handler(request: httpx.Request) -> httpx.Response:
        tenant_id = request.headers.get("x-tenant-id")
        if tenant_id == tenant_a.id:
            items = [_run("completed", "a1"), _run("completed", "a2"), _run("failed", "a3")]
        elif tenant_id == tenant_b.id:
            items = [_run("pending", "b1")]
        else:
            items = []
        return httpx.Response(
            200, json={"items": items, "limit": 100, "offset": 0, "total": len(items)}
        )

    app.dependency_overrides[get_validation_service_client] = lambda: _mock_client(handler)
    try:
        response = TestClient(app).get("/system/runs-summary", headers=_op_headers())
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 4
        assert body["completed_pct"] == 50.0
        assert body["failed_pct"] == 25.0
        assert body["running_pct"] == 25.0
    finally:
        _clear_overrides()


def test_run_outside_24h_window_is_excluded(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _ = _wire_sqlite(tmp_path)
    tenant = tenant_repo.create_tenant("Acme Corp")

    now = datetime.now(timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        items = [
            {
                "id": "recent",
                "status": "completed",
                "created_at": _iso(now - timedelta(hours=1)),
                "completed_at": None,
            },
            {
                "id": "stale",
                "status": "failed",
                "created_at": _iso(now - timedelta(hours=48)),
                "completed_at": None,
            },
        ]
        return httpx.Response(
            200, json={"items": items, "limit": 100, "offset": 0, "total": len(items)}
        )

    app.dependency_overrides[get_validation_service_client] = lambda: _mock_client(handler)
    try:
        response = TestClient(app).get("/system/runs-summary", headers=_op_headers())
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["completed_pct"] == 100.0
        assert body["failed_pct"] == 0.0
    finally:
        _clear_overrides()


def test_one_unreachable_tenant_does_not_fail_the_whole_aggregate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _ = _wire_sqlite(tmp_path)
    tenant_a = tenant_repo.create_tenant("Tenant A")
    tenant_repo.create_tenant("Tenant B")

    now = datetime.now(timezone.utc)

    def handler(request: httpx.Request) -> httpx.Response:
        tenant_id = request.headers.get("x-tenant-id")
        if tenant_id == tenant_a.id:
            items = [
                {
                    "id": "a1",
                    "status": "completed",
                    "created_at": _iso(now - timedelta(minutes=5)),
                    "completed_at": None,
                }
            ]
            return httpx.Response(
                200, json={"items": items, "limit": 100, "offset": 0, "total": len(items)}
            )
        raise httpx.ConnectError("connection refused", request=request)

    app.dependency_overrides[get_validation_service_client] = lambda: _mock_client(handler)
    try:
        response = TestClient(app).get("/system/runs-summary", headers=_op_headers())
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["completed_pct"] == 100.0
    finally:
        _clear_overrides()
