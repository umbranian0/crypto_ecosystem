"""Application-level symmetric encryption for tenant crawler credentials.

Implements ADR-0004: Fernet (AES-128-CBC + HMAC) with the key held in a single
environment variable, `INGESTION_CREDENTIAL_ENCRYPTION_KEY`. This module is the
only place a credential's plaintext exists in memory on this service's write
path; callers (`INGEST-004`) are responsible for not logging around it, but
this module itself must never emit plaintext or ciphertext via print/logging/
exceptions.

Losing the key makes every previously-stored credential permanently
undecryptable - there is no rotation/recovery tooling. See
`docs/adr/0004-tenant-credential-encryption-at-rest.md`.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

_KEY_ENV_VAR = "INGESTION_CREDENTIAL_ENCRYPTION_KEY"


class CredentialCryptoError(Exception):
    """Raised for any key or credential-crypto failure in this module.

    Never carries the plaintext, ciphertext, or key value in its message -
    only enough context (which env var, which operation) to diagnose without
    leaking a secret into logs/tracebacks.
    """


def generate_key() -> bytes:
    """Generate a new Fernet key.

    Not called anywhere in this service's runtime path - this is the helper a
    future bootstrap script (out of scope for this ticket) would call once to
    print `INGESTION_CREDENTIAL_ENCRYPTION_KEY` for one-time reveal, the same
    way `provision_tenant.py` one-time-reveals an API key.
    """
    return Fernet.generate_key()


def _load_fernet() -> Fernet:
    raw_key = os.environ.get(_KEY_ENV_VAR)
    if not raw_key:
        raise CredentialCryptoError(
            f"{_KEY_ENV_VAR} is not set; cannot encrypt or decrypt credentials."
        )
    try:
        return Fernet(raw_key)
    except (ValueError, TypeError) as exc:
        raise CredentialCryptoError(
            f"{_KEY_ENV_VAR} is not a valid Fernet key."
        ) from exc


def encrypt(plaintext: str) -> bytes:
    """Encrypt `plaintext`, reading the key from the environment at call time.

    Rejects the empty string: a credential value is never legitimately empty,
    so treating it as a valid ciphertext-producing input would only mask a
    caller bug (e.g. reading an unset field) as a "successfully stored" secret.
    """
    if plaintext == "":
        raise CredentialCryptoError("Cannot encrypt an empty credential value.")
    fernet = _load_fernet()
    try:
        return fernet.encrypt(plaintext.encode("utf-8"))
    except Exception as exc:
        raise CredentialCryptoError("Failed to encrypt credential value.") from exc


def decrypt(ciphertext: bytes) -> str:
    """Decrypt `ciphertext`, reading the key from the environment at call time."""
    fernet = _load_fernet()
    try:
        return fernet.decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialCryptoError(
            "Ciphertext could not be decrypted with the configured key."
        ) from exc
    except Exception as exc:
        raise CredentialCryptoError("Failed to decrypt credential value.") from exc
