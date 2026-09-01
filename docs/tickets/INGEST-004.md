# INGEST-004 — Per-tenant connector credentials (encrypted at rest)

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: done. **Priority**: Must.
**Depends on**: `INGEST-003`, `INGEST-011`. **Blocks**: `INGEST-005` (same file — run sequentially, not
in parallel), `INGEST-008`.

## Analysis
Story: backlog `INGEST-004`, **revised** by solution-design.md section 8.5 / ADR-0004: encrypted at
rest via `INGEST-011`'s Fernet primitive, not plaintext (the backlog's original disclosed posture is
superseded, not merely an option anymore). `BinancePriceConnector`/`BlockchainInfoConnector` need no
credential row (unchanged).

## Design
Pattern: Repository, extending `INGEST-003`'s `ConnectorRecordRepository` family (a `CredentialRepository`
sibling, same file/module). Files touched: `services/ingestion-service/src/app/repositories/
interfaces.py` and `postgres_repository.py` (extend, same files `INGEST-003` created — this is why
`INGEST-004` and `INGEST-005` must not run concurrently), `connectors/reddit_sentiment.py` (constructor
already partially accepts explicit credentials — wire the tenant-aware path in). **DRY check**: reuse
`INGEST-011`'s `encrypt`/`decrypt` directly, no second crypto implementation.

## Implementation acceptance criteria
- [x] `CredentialRepository.get_credentials(tenant_id, source) -> Credentials | None` decrypts via
  `INGEST-011.decrypt` before returning (in-process only — this method's return value must never be
  logged by any caller; the ticket's own tests must not print it either).
- [x] `CredentialRepository.set_credentials(tenant_id, source, **fields)` encrypts each field via
  `INGEST-011.encrypt` before writing — no plaintext column anywhere in `connector_credentials`.
- [x] `RedditSentimentConnector`'s tenant-aware call path resolves credentials via this repository
  instead of `os.environ`; the existing `os.environ` path is kept as the standalone/no-tenant CLI
  fallback (demote, don't delete).
- [x] `Binance`/`BlockchainInfo` connectors: no credential row invented — confirmed no new required
  parameter added to either.

## Test acceptance criteria
- [x] Round-trip test: `set_credentials` then `get_credentials` returns the original plaintext values
  (via the repository, not by reading the DB column directly — a test that reads the raw column must
  assert it is NOT the plaintext, proving encryption actually happened). Done against the fake
  repository (`tests/test_credential_repository.py`); a real-Postgres round-trip was not run because
  no `timescaledb` container was up in this environment at implementation time — documented as a
  nice-to-have per the ticket's own instructions, not a required criterion.
- [x] Cross-tenant isolation: tenant A's credentials are never returned/used for tenant B's crawl
  (non-tautological — assert by actual credential value, not just presence/absence).
- [x] A test proves no API response, log line, or exception message anywhere in this ticket's diff
  contains a decrypted or ciphertext credential value (grep-style substring-absence check, same
  discipline as `GW-014`'s audit-logging tests).

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms every credential column in `connector_credentials` is populated via `INGEST-011.encrypt`,
  never written as plaintext (reads the actual INSERT/UPDATE statements).
- Confirms `get_credentials`'s return value never crosses an HTTP response body anywhere in this
  ticket's scope (that's `INGEST-008`'s concern to keep true, but this ticket's own code must not
  introduce a leak either).

## Documentation acceptance criteria
- [x] `services/ingestion-service/README.md` documents the credential-storage design (encrypted, via
  `INGEST-011`, linking ADR-0004), replacing the backlog's original "accepted plaintext" language.
