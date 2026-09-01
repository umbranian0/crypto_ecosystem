"""Tests for `src/app/credential_crypto.py` (INGEST-011).

Placed under this service's plain-pytest `tests/` convention (no
pyproject.toml/pytest config exists yet for `src/app/` - see the README's
"Testing" note). Imports `src/app` directly via a `sys.path` insert since
there is no installable package yet, mirroring `tests/` `conftest.py`'s
existing approach for `connectors/`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from app import credential_crypto as cc


@pytest.fixture
def valid_key(monkeypatch):
    key = cc.generate_key()
    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", key.decode("utf-8"))
    return key


def test_round_trip_representative_values(valid_key):
    for value in ["client-id-123", "s3cr3t!with spaces and $ymbols", "a" * 500]:
        ciphertext = cc.encrypt(value)
        assert cc.decrypt(ciphertext) == value


def test_encrypt_rejects_empty_string(valid_key):
    with pytest.raises(cc.CredentialCryptoError):
        cc.encrypt("")


def test_encrypt_output_is_not_plaintext_bytes(valid_key):
    plaintext = "reddit-client-secret-abc123"
    ciphertext = cc.encrypt(plaintext)
    assert ciphertext != plaintext.encode("utf-8")
    assert plaintext.encode("utf-8") not in ciphertext


def test_missing_key_env_var_raises_typed_error(monkeypatch):
    monkeypatch.delenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(cc.CredentialCryptoError):
        cc.encrypt("some-value")
    with pytest.raises(cc.CredentialCryptoError):
        cc.decrypt(b"irrelevant-ciphertext")


def test_malformed_key_env_var_raises_typed_error(monkeypatch):
    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    with pytest.raises(cc.CredentialCryptoError):
        cc.encrypt("some-value")


def test_decrypt_with_wrong_key_raises_typed_error(monkeypatch):
    key_a = cc.generate_key()
    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", key_a.decode("utf-8"))
    ciphertext = cc.encrypt("some-value")

    key_b = cc.generate_key()
    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", key_b.decode("utf-8"))
    with pytest.raises(cc.CredentialCryptoError):
        cc.decrypt(ciphertext)


def test_generate_key_produces_usable_fernet_key(monkeypatch):
    key = cc.generate_key()
    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", key.decode("utf-8"))
    assert cc.decrypt(cc.encrypt("round-trips")) == "round-trips"
