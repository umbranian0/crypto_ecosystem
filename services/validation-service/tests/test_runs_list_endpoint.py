"""VS-022: `GET /runs` tenant-scoped, paginated list endpoint tests.

Own file (mirrors `test_splits_endpoint.py`'s precedent of keeping each
route's tests in a dedicated module) even though `GET /runs` is added to the
same `runs.py`/`test_runs_endpoint.py` pair VS-006/VS-007 already own -- no
other ticket in this sprint touches either file, so there is no collision
risk either way; a separate file just keeps this ticket's tests easy to find.

Runs are seeded directly via `SQLiteValidationRunRepository.create_run`
(same `VALIDATION_SERVICE_DB_PATH`-backed file the `TestClient`'s app uses),
not through `POST /runs`'s full `run_validation_protocol` execution -- that
keeps the pagination/ordering/cross-tenant tests fast and focused on the list
endpoint itself, matching `test_sqlite_repository.py`'s own precedent for
seeding fixture data directly through the repository.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

SPLIT_CONFIG = {"train_window": 100, "test_window": 20, "step": 10}


def _fixed_utcnow_datetime(fixed_now: datetime) -> type:
    """Builds a `datetime` subclass whose `utcnow()` always returns
    `fixed_now`, for monkeypatching `sqlite_repository`'s module-level
    `datetime` name (VS-034 -- reproduces a `created_at` collision
    deterministically instead of relying on real-clock timing).
    """

    class _FixedDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return fixed_now

    return _FixedDatetime


def _increasing_utcnow_datetime(start: datetime) -> type:
    """Builds a `datetime` subclass whose `utcnow()` returns a strictly
    increasing timestamp on each successive call (start + an incrementing
    seconds counter), for monkeypatching `sqlite_repository`'s module-level
    `datetime` name (VS-034 -- guarantees `created_at` strictly increases in
    seed order by construction, instead of relying on real-clock timing
    across rapid sequential `create_run` calls).
    """
    counter = {"n": 0}

    class _IncreasingDatetime(datetime):
        @classmethod
        def utcnow(cls):
            value = start + timedelta(seconds=counter["n"])
            counter["n"] += 1
            return value

    return _IncreasingDatetime


def _client_and_repo(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app
    from app.repositories.sqlite_repository import SQLiteValidationRunRepository

    return TestClient(app), SQLiteValidationRunRepository(db_path)


def _seed_run(repo, tenant_id: str, dataset_id: str) -> str:
    return repo.create_run(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        horizon=1,
        purge_gap_hours=0,
        split_config=SPLIT_CONFIG,
    ).id


def test_tenant_with_three_runs_sees_exactly_its_own_in_created_at_desc_order(tmp_path, monkeypatch):
    client, repo = _client_and_repo(tmp_path, monkeypatch)

    run_ids = [_seed_run(repo, "tenant-1", f"dataset-{i}") for i in range(3)]

    response = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 20
    assert body["offset"] == 0
    returned_ids = [item["id"] for item in body["items"]]
    # created_at strictly increases with each sequential create_run call, so
    # the correct descending order is the reverse of seed order.
    assert returned_ids == list(reversed(run_ids))


def test_tied_created_at_breaks_ties_by_id_descending_deterministically(tmp_path, monkeypatch):
    """VS-034 regression test: reproduces the tie-break scenario without
    relying on real-clock timing -- `datetime.utcnow` is monkeypatched to
    return a single fixed value for every `create_run` call, so all three
    seeded runs get an identical `created_at`. Pre-fix (`order_by` on
    `created_at` alone), SQLite has no defined order for these tied rows;
    post-fix, `id` descending is the only remaining sort key, so the order
    is fully determined and must be reproduced identically across repeated
    `GET /runs` calls.
    """
    client, repo = _client_and_repo(tmp_path, monkeypatch)

    fixed_now = datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(
        "app.repositories.sqlite_repository.datetime",
        _fixed_utcnow_datetime(fixed_now),
    )

    run_ids = [_seed_run(repo, "tenant-1", f"dataset-{i}") for i in range(3)]
    expected_order = sorted(run_ids, reverse=True)

    first_response = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"})
    second_response = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"})

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text

    first_ids = [item["id"] for item in first_response.json()["items"]]
    second_ids = [item["id"] for item in second_response.json()["items"]]

    assert first_ids == expected_order
    assert second_ids == expected_order


def test_second_tenants_runs_never_appear_in_first_tenants_results(tmp_path, monkeypatch):
    """Non-tautological cross-tenant test (ticket's own flagged highest-risk
    case): asserts by run id, not merely by count, in both directions.
    """
    client, repo = _client_and_repo(tmp_path, monkeypatch)

    tenant_a_ids = [_seed_run(repo, "tenant-a", f"dataset-a-{i}") for i in range(2)]
    tenant_b_ids = [_seed_run(repo, "tenant-b", f"dataset-b-{i}") for i in range(2)]

    response_a = client.get("/runs", headers={"X-Tenant-Id": "tenant-a"})
    response_b = client.get("/runs", headers={"X-Tenant-Id": "tenant-b"})

    assert response_a.status_code == 200, response_a.text
    assert response_b.status_code == 200, response_b.text

    ids_seen_by_a = {item["id"] for item in response_a.json()["items"]}
    ids_seen_by_b = {item["id"] for item in response_b.json()["items"]}

    assert ids_seen_by_a == set(tenant_a_ids)
    assert ids_seen_by_b == set(tenant_b_ids)
    assert ids_seen_by_a.isdisjoint(set(tenant_b_ids))
    assert ids_seen_by_b.isdisjoint(set(tenant_a_ids))
    for run_id in tenant_b_ids:
        assert run_id not in response_a.text
    for run_id in tenant_a_ids:
        assert run_id not in response_b.text


def test_limit_and_offset_paginate_correctly_across_a_seeded_set_larger_than_one_page(tmp_path, monkeypatch):
    client, repo = _client_and_repo(tmp_path, monkeypatch)

    monkeypatch.setattr(
        "app.repositories.sqlite_repository.datetime",
        _increasing_utcnow_datetime(datetime(2026, 1, 1, 12, 0, 0)),
    )

    run_ids = [_seed_run(repo, "tenant-1", f"dataset-{i}") for i in range(25)]
    expected_desc_order = list(reversed(run_ids))

    first_page = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"}, params={"limit": 10, "offset": 0})
    second_page = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"}, params={"limit": 10, "offset": 10})
    third_page = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"}, params={"limit": 10, "offset": 20})

    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    assert third_page.status_code == 200, third_page.text

    first_ids = [item["id"] for item in first_page.json()["items"]]
    second_ids = [item["id"] for item in second_page.json()["items"]]
    third_ids = [item["id"] for item in third_page.json()["items"]]

    assert first_ids == expected_desc_order[0:10]
    assert second_ids == expected_desc_order[10:20]
    assert third_ids == expected_desc_order[20:25]

    for page in (first_page, second_page, third_page):
        assert page.json()["total"] == 25


def test_limit_zero_returns_422(tmp_path, monkeypatch):
    client, _ = _client_and_repo(tmp_path, monkeypatch)

    response = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"}, params={"limit": 0})

    assert response.status_code == 422


def test_limit_over_100_returns_422(tmp_path, monkeypatch):
    client, _ = _client_and_repo(tmp_path, monkeypatch)

    response = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"}, params={"limit": 101})

    assert response.status_code == 422


def test_negative_offset_returns_422(tmp_path, monkeypatch):
    client, _ = _client_and_repo(tmp_path, monkeypatch)

    response = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"}, params={"offset": -1})

    assert response.status_code == 422


def test_empty_tenant_returns_200_with_empty_items(tmp_path, monkeypatch):
    client, repo = _client_and_repo(tmp_path, monkeypatch)

    # Seed a run for a different tenant so the empty result is because of
    # tenant scoping, not because the table is globally empty.
    _seed_run(repo, "tenant-other", "dataset-1")

    response = client.get("/runs", headers={"X-Tenant-Id": "tenant-empty"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_missing_tenant_header_returns_401_before_repository_touched(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.dependencies.repositories import get_validation_run_repository
    from app.main import app

    class _FailingRepo:
        def list_runs(self, *args, **kwargs):
            raise AssertionError("list_runs must not be reached when tenant context resolution fails")

        def count_runs(self, *args, **kwargs):
            raise AssertionError("count_runs must not be reached when tenant context resolution fails")

    app.dependency_overrides[get_validation_run_repository] = lambda: _FailingRepo()
    try:
        client = TestClient(app)
        response = client.get("/runs")  # no X-Tenant-Id header
    finally:
        app.dependency_overrides.pop(get_validation_run_repository, None)

    assert response.status_code == 401


def test_response_items_have_summary_fields_only(tmp_path, monkeypatch):
    client, repo = _client_and_repo(tmp_path, monkeypatch)
    _seed_run(repo, "tenant-1", "dataset-1")

    response = client.get("/runs", headers={"X-Tenant-Id": "tenant-1"})

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert set(item.keys()) == {
        "id",
        "dataset_id",
        "horizon",
        "status",
        "created_at",
        "completed_at",
        "label",
    }
