"""Tests for `app.repositories.interfaces.CredentialRepository` (INGEST-004,
ADR-0004), exercised against `FakeCredentialRepository` -- an in-memory
double storing ciphertext exactly like `PostgresCredentialRepository`'s real
`connector_credentials` columns (see `tests/fake_repository.py`), so these
tests can assert "the raw stored value is not the plaintext" without a live
Postgres instance. A real-Postgres round-trip is a documented nice-to-have,
not required by the ticket's own test acceptance criteria -- skipped here
since no `timescaledb` container is currently running in this environment.
"""

from __future__ import annotations

import logging

import pytest

from app import credential_crypto as cc
from fake_repository import FakeCredentialRepository


@pytest.fixture
def valid_key(monkeypatch):
    key = cc.generate_key()
    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", key.decode("utf-8"))
    return key


def test_round_trip_returns_original_plaintext(valid_key) -> None:
    repository = FakeCredentialRepository()

    repository.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="cid-123", client_secret="s3cret!"
    )
    credentials = repository.get_credentials("tenant-a", "reddit_vader_sentiment")

    assert credentials is not None
    assert credentials.client_id == "cid-123"
    assert credentials.client_secret == "s3cret!"


def test_raw_stored_value_is_not_plaintext(valid_key) -> None:
    repository = FakeCredentialRepository()
    plaintext_id = "cid-123"
    plaintext_secret = "s3cret!"

    repository.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id=plaintext_id, client_secret=plaintext_secret
    )

    raw_row = repository._rows[("tenant-a", "reddit_vader_sentiment")]
    assert raw_row["client_id"] != plaintext_id.encode("utf-8")
    assert raw_row["client_secret"] != plaintext_secret.encode("utf-8")
    assert plaintext_id.encode("utf-8") not in raw_row["client_id"]
    assert plaintext_secret.encode("utf-8") not in raw_row["client_secret"]


def test_cross_tenant_isolation_by_actual_value(valid_key) -> None:
    repository = FakeCredentialRepository()
    repository.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="tenant-a-id", client_secret="tenant-a-secret"
    )
    repository.set_credentials(
        "tenant-b", "reddit_vader_sentiment", client_id="tenant-b-id", client_secret="tenant-b-secret"
    )

    creds_a = repository.get_credentials("tenant-a", "reddit_vader_sentiment")
    creds_b = repository.get_credentials("tenant-b", "reddit_vader_sentiment")

    assert creds_a.client_id == "tenant-a-id"
    assert creds_a.client_secret == "tenant-a-secret"
    assert creds_b.client_id == "tenant-b-id"
    assert creds_b.client_secret == "tenant-b-secret"
    assert creds_a.client_id != creds_b.client_id
    assert creds_a.client_secret != creds_b.client_secret


def test_get_credentials_returns_none_for_unknown_tenant(valid_key) -> None:
    repository = FakeCredentialRepository()
    repository.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="tenant-a-id", client_secret="tenant-a-secret"
    )

    assert repository.get_credentials("tenant-b", "reddit_vader_sentiment") is None


def test_set_and_get_credentials_never_log_plaintext_or_ciphertext(valid_key, caplog, capsys) -> None:
    repository = FakeCredentialRepository()
    plaintext_id = "no-leak-client-id"
    plaintext_secret = "no-leak-client-secret"

    with caplog.at_level(logging.DEBUG):
        repository.set_credentials(
            "tenant-a", "reddit_vader_sentiment", client_id=plaintext_id, client_secret=plaintext_secret
        )
        credentials = repository.get_credentials("tenant-a", "reddit_vader_sentiment")

    ciphertext = repository._rows[("tenant-a", "reddit_vader_sentiment")]["client_id"]
    captured = capsys.readouterr()
    haystacks = [caplog.text, captured.out, captured.err]

    for haystack in haystacks:
        assert plaintext_id not in haystack
        assert plaintext_secret not in haystack
        assert ciphertext.decode("latin-1") not in haystack

    assert credentials.client_id == plaintext_id  # sanity: the value really was stored/decrypted
