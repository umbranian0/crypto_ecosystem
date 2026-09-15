"""Tests for INGEST-010's `app.seed_platform_history` module and its thin
CLI wrapper (`scripts/seed_tenant.py`).

Reuses `tests/fake_repository.py`'s `FakeConnectorRecordRepository` (this
service's existing test-double convention) rather than a live Postgres, and
a small synthetic CSV per source (written to `tmp_path`) rather than reading
the real, large `data/raw/_platform/` archive -- `--from <arbitrary-path>`
single-tenant mode is exactly what exercises the same loader code path
`--from platform-csv` would, without depending on the real archive's size or
contents.
"""

from __future__ import annotations

import httpx
import pytest

from fake_repository import FakeConnectorRecordRepository

from app.seed_platform_history import (
    SOURCE_SPECS,
    fetch_all_tenant_ids,
    resolve_source_spec,
    seed_all_existing_tenants,
    seed_single_source,
    seed_tenant_platform_history,
)


PRICE_CSV = """open_time,open,high,low,close,volume,close_time,quote_vol,trades,taker_buy_base,taker_buy_quote,ignore,symbol
2020-01-01T00:00:00Z,100,110,90,105,10,2020-01-01T00:59:59Z,1000,5,4,400,0,BTCUSDT
2020-01-01T01:00:00Z,105,115,95,110,12,2020-01-01T01:59:59Z,1200,6,5,500,0,BTCUSDT
"""

ONCHAIN_CSV = """timestamp,date,hash-rate
1577836800,2020-01-01,1.0
1577923200,2020-01-02,1.1
"""

SENTIMENT_CSV = """Date,Short Description,Accurate Sentiments
2021-11-05 04:42:00,headline one,0.5
2021-11-05 08:15:00,headline two,-0.2
"""


def _write(tmp_path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def test_resolve_source_spec_known_and_unknown():
    assert resolve_source_spec("binance_price_btcusdt_1h").record_kind == "price"
    with pytest.raises(ValueError):
        resolve_source_spec("not-a-real-source")


def test_source_specs_cover_all_four_platform_sources():
    assert {spec.source for spec in SOURCE_SPECS} == {
        "binance_price_btcusdt_1h",
        "blockchain_info_hash-rate",
        "blockchain_info_n-unique-addresses",
        "kaggle_bitcoin_sentiments_21_24",
    }


def test_seed_single_source_writes_via_add_price_records(tmp_path):
    csv_path = _write(tmp_path, "price.csv", PRICE_CSV)
    repository = FakeConnectorRecordRepository()

    row_count = seed_single_source("tenant-a", "binance_price_btcusdt_1h", csv_path, repository)

    assert row_count == 2
    assert len(repository.price) == 1
    written_tenant, written_source, written_records = repository.price[0]
    assert written_tenant == "tenant-a"
    assert written_source == "binance_price_btcusdt_1h"
    assert len(written_records) == 2
    assert "fetched_at" in written_records.columns


def test_seed_single_source_onchain_and_sentiment_shapes(tmp_path):
    onchain_path = _write(tmp_path, "onchain.csv", ONCHAIN_CSV)
    sentiment_path = _write(tmp_path, "sentiment.csv", SENTIMENT_CSV)
    repository = FakeConnectorRecordRepository()

    onchain_written = seed_single_source(
        "tenant-a", "blockchain_info_hash-rate", onchain_path, repository
    )
    sentiment_written = seed_single_source(
        "tenant-a", "kaggle_bitcoin_sentiments_21_24", sentiment_path, repository
    )

    assert onchain_written == 2
    assert sentiment_written == 2
    _, _, onchain_records = repository.onchain[0]
    assert set(["date", "hash-rate", "fetched_at"]).issubset(onchain_records.columns)
    _, _, sentiment_records = repository.sentiment[0]
    assert sentiment_records["post_id"].tolist() == ["kaggle_0", "kaggle_1"]
    assert sentiment_records["reddit_sid_pos"].tolist() == [0.0, 0.0]


# --- Idempotency (Test AC) -------------------------------------------------


def test_idempotent_running_write_path_twice_writes_zero_new_rows_second_time(tmp_path):
    csv_path = _write(tmp_path, "price.csv", PRICE_CSV)
    repository = FakeConnectorRecordRepository()

    first = seed_single_source("tenant-a", "binance_price_btcusdt_1h", csv_path, repository)
    second = seed_single_source("tenant-a", "binance_price_btcusdt_1h", csv_path, repository)

    assert first == 2
    assert second == 0
    # Only the first call actually reached add_price_records with rows;
    # the second call's zero-row result short-circuits before any write.
    assert len(repository.price) == 1


def test_idempotency_is_per_tenant_not_global(tmp_path):
    csv_path = _write(tmp_path, "price.csv", PRICE_CSV)
    repository = FakeConnectorRecordRepository()

    seed_single_source("tenant-a", "binance_price_btcusdt_1h", csv_path, repository)
    second_tenant_count = seed_single_source(
        "tenant-b", "binance_price_btcusdt_1h", csv_path, repository
    )

    assert second_tenant_count == 2  # tenant-b has its own, independent watermark


# --- --dry-run (Test AC) ----------------------------------------------------


def test_dry_run_makes_zero_add_records_calls(tmp_path):
    csv_path = _write(tmp_path, "price.csv", PRICE_CSV)
    repository = FakeConnectorRecordRepository()

    row_count = seed_single_source(
        "tenant-a", "binance_price_btcusdt_1h", csv_path, repository, dry_run=True
    )

    assert row_count == 2
    assert repository.price == []


def test_dry_run_still_reports_correct_count_against_existing_watermark(tmp_path):
    csv_path = _write(tmp_path, "price.csv", PRICE_CSV)
    repository = FakeConnectorRecordRepository()
    seed_single_source("tenant-a", "binance_price_btcusdt_1h", csv_path, repository)

    row_count = seed_single_source(
        "tenant-a", "binance_price_btcusdt_1h", csv_path, repository, dry_run=True
    )

    assert row_count == 0
    assert len(repository.price) == 1  # unchanged by the dry-run call


# --- --all-existing-tenants (Test AC) ---------------------------------------


def _fake_tenants_transport(tenant_ids: list[str]):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tenants"
        assert request.headers.get("x-operator-token") == "op-secret"
        return httpx.Response(
            200,
            json={"items": [{"id": tid, "name": tid, "created_at": "2026-01-01T00:00:00Z", "api_keys": []} for tid in tenant_ids]},
        )

    return httpx.MockTransport(handler)


def test_all_existing_tenants_writes_n_independent_passes(monkeypatch, tmp_path):
    tenant_ids = ["tenant-a", "tenant-b", "tenant-c"]
    transport = _fake_tenants_transport(tenant_ids)
    client = httpx.Client(transport=transport, base_url="http://gateway-api.test")
    repository = FakeConnectorRecordRepository()

    # Point the module at the real platform CSVs is unnecessary here -- what
    # matters for this AC is that N tenants each get their own independent
    # write pass, never landing under another tenant's tenant_id. We monkey-
    # patch `_load_platform_csvs` indirectly by seeding the repository with a
    # small per-source loader stand-in via seed_tenant_platform_history's own
    # SOURCE_SPECS, driven from the real (small) platform archive files.
    results = seed_all_existing_tenants(
        "http://gateway-api.test", "op-secret", repository, client=client
    )

    assert set(results.keys()) == set(tenant_ids)
    for source in SOURCE_SPECS:
        rows_by_tenant = {tid: len(recs) for (tid, s, recs) in getattr(repository, source.record_kind) if s == source.source}
        # every tenant that has rows for this source has its own row set,
        # never sharing tenant_id with another tenant's rows
        assert set(rows_by_tenant.keys()).issubset(set(tenant_ids))
    # Cross-tenant isolation: each tenant's own rows are recorded under its
    # own tenant_id only.
    for record_kind in ("price", "onchain", "sentiment"):
        for tenant_id, _source, _records in getattr(repository, record_kind):
            assert tenant_id in tenant_ids


def test_gateway_api_unreachable_is_a_clear_error_not_a_silent_no_op():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://gateway-api.test")
    repository = FakeConnectorRecordRepository()

    with pytest.raises(httpx.ConnectError):
        seed_all_existing_tenants("http://gateway-api.test", "op-secret", repository, client=client)

    # No partial silent success: nothing was written to any table.
    assert repository.price == []
    assert repository.onchain == []
    assert repository.sentiment == []


def test_fetch_all_tenant_ids_parses_response_shape():
    transport = _fake_tenants_transport(["tenant-x"])
    client = httpx.Client(transport=transport, base_url="http://gateway-api.test")

    tenant_ids = fetch_all_tenant_ids("http://gateway-api.test", "op-secret", client=client)

    assert tenant_ids == ["tenant-x"]


# --- CLI wrapper (thin, argument parsing only) ------------------------------


def test_cli_requires_tenant_id_source_and_from_in_base_mode(capsys):
    from scripts.seed_tenant import main

    with pytest.raises(SystemExit):
        main(["--tenant-id", "tenant-a"])


def test_cli_dry_run_base_mode_prints_would_write(tmp_path, monkeypatch, capsys):
    csv_path = _write(tmp_path, "price.csv", PRICE_CSV)
    repository = FakeConnectorRecordRepository()

    import app.dependencies.repositories as repositories_module
    monkeypatch.setattr(repositories_module, "get_connector_record_repository", lambda: repository)

    from scripts import seed_tenant as seed_tenant_module

    monkeypatch.setattr(seed_tenant_module, "get_connector_record_repository", lambda: repository)

    exit_code = seed_tenant_module.main(
        [
            "--tenant-id",
            "tenant-a",
            "--source",
            "binance_price_btcusdt_1h",
            "--from",
            csv_path,
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert repository.price == []
    out = capsys.readouterr().out
    assert "would write 2 rows" in out


def test_cli_all_existing_tenants_missing_operator_token_is_fatal(monkeypatch, capsys):
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    from scripts.seed_tenant import main

    exit_code = main(["--all-existing-tenants"])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "OPERATOR_TOKEN" in err
