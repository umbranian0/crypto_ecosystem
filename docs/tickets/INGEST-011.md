# INGEST-011 — Tenant credential encryption primitive (Fernet)

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: done (pending Tech Lead pyproject.toml dependency merge). **Priority**: Must.
**Depends on**: none (parallel with `INGEST-002`/`LC-010`). **Blocks**: `INGEST-004`.

## Analysis

New ticket, not in the original backlog — added because `docs/solution-design.md` section 8.5 and
`docs/adr/0004-tenant-credential-encryption-at-rest.md` revised `INGEST-004`'s originally-disclosed
plaintext-at-rest posture to Fernet encryption after the backlog was written. This ticket is the
primitive only (encrypt/decrypt functions); `INGEST-004` is the repository/connector wiring that uses
it. Splitting them keeps `INGEST-004`'s diff focused on the credential *lifecycle*, not also
introducing a new crypto dependency in the same diff.

Constraint (ADR-0004, binding): application-level symmetric encryption via `cryptography`'s `Fernet`
only — explicitly not a full secrets-manager integration (Vault/AWS Secrets Manager). Key lives in a
single env var, `INGESTION_CREDENTIAL_ENCRYPTION_KEY`, generated once via `Fernet.generate_key()`.

## Design

No `implementation-plan.md` section 7 pattern applies (this is a small crypto utility, not a
service-boundary concern) — per ADR-0004 itself: "start as a private module inside `ingestion-service`
... move it into `libs/common` the moment a second service needs the same primitive" (YAGNI, extract on
second duplication, not preemptively). File touched (new): `services/ingestion-service/src/app/
credential_crypto.py`.

**DRY check (grep first)**: `grep -rn "Fernet\|cryptography" services/ libs/` — confirmed zero existing
usage anywhere in this platform; this is genuinely new capability, not a duplicate of anything.

## Implementation acceptance criteria

- [x] `encrypt(plaintext: str) -> bytes` and `decrypt(ciphertext: bytes) -> str`, both reading the key
  from `INGESTION_CREDENTIAL_ENCRYPTION_KEY` (env var) at call time (not memoized on import — so a test
  can set the env var per-test without import-order flakiness), raising a clear, typed exception
  (e.g. `CredentialCryptoError`) if the env var is unset or malformed (never a bare `KeyError`/silent
  `None`-key crash).
- [x] No endpoint, log line, CLI print statement, or exception message anywhere in this module ever
  includes a decrypted plaintext value or a raw ciphertext value — this ticket's own `encrypt`/`decrypt`
  functions are the only place plaintext briefly exists in memory; callers (`INGEST-004`) are
  responsible for not logging around them, but this ticket's own code must not add a violation itself
  (e.g. no `print(plaintext)` debug line left in).
- [x] `Fernet.generate_key()` exposed as a small `generate_key() -> bytes` helper (or documented as a
  one-liner in the README) so `infra/bootstrap.ps1`/`.sh` can print it the same way `SETUP-002`'s API
  key is one-time-revealed — this ticket does not wire the bootstrap script itself (that's `infra`'s
  scope, not scheduled this sprint), it only makes the key-generation call available/documented.

## Test acceptance criteria

- [x] Round-trip test: `decrypt(encrypt(x)) == x` for representative values (empty string rejected or
  handled explicitly — decide and test one behavior, not left undefined).
- [x] Missing/malformed `INGESTION_CREDENTIAL_ENCRYPTION_KEY` raises `CredentialCryptoError`, not an
  unhandled `cryptography` library exception leaking to a caller.
- [x] A test asserts `encrypt(x)` output is never byte-identical to `x`'s UTF-8 encoding (a real,
  non-tautological "it actually encrypted something" check, not just "the function ran without error").

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms the key is read from the environment at call time, not hardcoded, cached at import time, or
  derived from anything else (e.g. no `hashlib`-derived key from a weaker secret).
- Confirms zero `print`/`logging` calls in the module that could carry plaintext or ciphertext.
- **File-collision avoidance (binding, since `INGEST-002` runs in the same parallel batch)**: this
  ticket's dev agent must NOT create or edit `services/ingestion-service/pyproject.toml` — that file is
  `INGEST-002`'s to create. Instead, state in your own completion report that `cryptography>=42` needs
  to be added to `services/ingestion-service/pyproject.toml`'s dependencies once it exists; the Tech
  Lead merges this dependency in personally after both tickets land, and confirms it's present before
  marking either ticket done.

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md` gains a short "Credential encryption" note: mechanism
  (Fernet), key env var name, and the disclosed limitation from ADR-0004 (losing the key makes stored
  credentials permanently undecryptable, no rotation/recovery tooling built yet) — linking to ADR-0004
  rather than restating its full reasoning.

## Dev agent completion note (2026-08-25)

Implemented `services/ingestion-service/src/app/credential_crypto.py` and
`services/ingestion-service/tests/test_credential_crypto.py` (7 tests, all passing — run via a
throwaway venv with `pip install cryptography pytest`, since this service has no `pyproject.toml`/test
harness of its own yet). Did **not** create or edit `services/ingestion-service/pyproject.toml` per the
file-collision rule — `cryptography>=42` still needs to be added to that file's dependencies once
`INGEST-002` lands it, per the Review acceptance criteria above.
