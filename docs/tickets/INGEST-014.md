# INGEST-014 — Per-`(tenant_id, source)` in-process crawl registry

## Analysis

Source: this sprint's follow-up (post Sprint 18 QA sweep), not `docs/sprints/sprint-18.md` itself.
QA reproduced two real bugs against the live stack in
`services/ingestion-service/src/app/routers/connectors.py`'s `POST /connectors/{source}/run`:

1. A full crawl (Binance's now-deep `2017-08-17` backfill floor, INGEST-013) runs synchronously
   inside the HTTP request (~70s, 79,127 rows) — `gateway-api`'s downstream timeout was band-aided
   to 240s (`infra/docker-compose.yml`, already committed by the QA sweep, not to be touched here),
   which is a number tuned to today's volume, not a fix.
2. A client retry after that timeout races the still-in-flight original crawl: both independently
   resolve the same `since` watermark and attempt to insert the same rows — reproduced as an
   unhandled `500` (Postgres `UniqueViolation` on `price_ohlcv`'s primary key).

This ticket builds the **synchronization primitive** the real fix (`INGEST-015`) needs: a
per-`(tenant_id, source)` mutual-exclusion registry, so only one crawl can be in flight for a given
tenant+source at a time, and a second concurrent attempt gets a clean, structural rejection instead
of racing. This ticket does **not** touch the router — it is a standalone module with its own unit
tests, so `INGEST-015` (router wiring, background execution, the real HTTP-level race reproduction)
can build on a primitive already proven correct in isolation.

Constraint from the requester's design direction (binding, not re-litigated): no message queue
exists yet in this single-process service, and none should be introduced for this. FastAPI's sync
`def` route handlers here run in a real thread pool (`anyio.to_thread`), so the primitive must be
thread-safe (`threading.Lock`), not `asyncio.Lock` (which only protects against interleaving on one
event loop, not concurrent OS threads).

## Design

No pattern from `implementation-plan.md` section 7's table is forced here — this is a
synchronization primitive, not a Strategy/Repository/Adapter/Factory/Observer/Template-Method
instance. It is exposed via the existing **Dependency Injection** convention (FastAPI `Depends()`),
matching `app/dependencies/repositories.py`'s own `functools.lru_cache`-memoized-singleton shape for
`_get_engine` — same "one shared instance for the life of the process, injected via `Depends()`"
idea, applied to a lock registry instead of a `Engine`.

**File touched** (one, scoped to this module only): `services/ingestion-service/src/app/crawl_registry.py`
(new) + `services/ingestion-service/tests/test_crawl_registry.py` (new). No existing file is edited by
this ticket — confirmed via a DRY-check grep below.

**DRY check**: grepped `services/ingestion-service/src/app/` for any existing lock/mutex/registry
concept — none exists (`crawl_runs`/`ConnectorRecordRepository.record_crawl_run` tracks *history* of
past attempts, not *whether one is currently in flight*; `app/dependencies/repositories.py`'s
`_get_engine` is the only existing "process-lifetime singleton via `functools.lru_cache`" precedent,
reused here as the shape to imitate, not a lock implementation to duplicate). Nothing to reuse beyond
that shape.

**Shape**:

```python
class CrawlRegistry:
    def try_acquire(self, tenant_id: str, source: str) -> bool: ...
    def release(self, tenant_id: str, source: str) -> None: ...
```

- `try_acquire` is atomic (single `threading.Lock`-guarded check-and-insert into a `set[tuple[str, str]]`)
  — returns `True` and marks `(tenant_id, source)` in-flight iff it was not already in-flight, `False`
  otherwise. Never raises.
- `release` is idempotent — safe to call even if the key was never acquired or already released
  (`set.discard`, not `.remove`), since the caller's `finally` block (`INGEST-015`) must be able to
  call it unconditionally without a second try/except.
- One module-level singleton instance + a `get_crawl_registry()` provider function + a
  `CrawlRegistryDep = Annotated[CrawlRegistry, Depends(get_crawl_registry)]` alias, mirroring
  `app/dependencies/repositories.py`'s `HealthCheckEngineDep`/`ConnectorRecordRepositoryDep` naming
  convention exactly (same file location: `app/dependencies/repositories.py` gets a new
  `get_crawl_registry`/`CrawlRegistryDep` pair rather than a second DI module, since this is one more
  process-lifetime singleton alongside the existing `Engine` one — not enough new surface to justify a
  new `dependencies/` file).

## Implementation acceptance criteria

- [ ] `CrawlRegistry` class in `src/app/crawl_registry.py`: `try_acquire(tenant_id, source) -> bool`,
      `release(tenant_id, source) -> None`, backed by a single `threading.Lock` + `set[tuple[str, str]]`.
      Two different `source` values for the same `tenant_id` (or vice versa) must not block each other
      — the key is the full `(tenant_id, source)` pair, never `source` alone (a shared `source` string
      across tenants, e.g. `binance_price_btcusdt_1h`, must not serialize unrelated tenants' crawls).
- [ ] `get_crawl_registry()` / `CrawlRegistryDep` added to `src/app/dependencies/repositories.py`,
      module-level singleton (not constructed fresh per request — this must be the *same* instance
      across concurrent requests to actually serialize them).
- [ ] No change to any other existing file in this ticket (`git status` scoped to
      `services/ingestion-service/` after this ticket shows only the two new files).

## Test acceptance criteria

- [ ] Unit tests, no FastAPI/HTTP involved: `try_acquire` returns `True` once and `False` on a second
      call for the same key while still held; `release` then a fresh `try_acquire` for the same key
      returns `True` again.
- [ ] Different `source` for the same `tenant_id`, and the same `source` for a different `tenant_id`,
      can both be acquired simultaneously (proves the key is the pair, not either half alone).
- [ ] `release` on a key that was never acquired, and a second `release` on an already-released key,
      are both no-ops (no exception).
- [ ] **Real concurrency proof, not merely structural**: spawn N (>=8) real `threading.Thread`s, all
      racing to `try_acquire` the *same* key at roughly the same time (synchronized via
      `threading.Barrier(N)` so they actually overlap, not just called in a tight sequential loop),
      assert **exactly one** returns `True` and the rest `False` — this is what proves the lock is
      actually atomic under real thread contention, not just correct in a single-threaded call
      sequence (which a plain, unsynchronized `if key not in set: set.add(key)` would also pass
      trivially in a non-concurrent test).

## Review acceptance criteria (Tech Lead verifies personally)

- [ ] Read `crawl_registry.py` directly: confirm the check-and-insert in `try_acquire` happens inside
      one `with self._lock:` block (not check-then-separately-insert with the lock released in
      between, which would reopen the exact race this ticket exists to close).
- [ ] Confirm `get_crawl_registry()` returns the same object identity across two calls (module-level
      singleton, not `functools.lru_cache`-per-argument or a fresh instance).
- [ ] Re-run the barrier-based concurrency test personally (not just trust the dev agent's report) —
      confirm it fails if `try_acquire`'s check-and-insert is deliberately de-atomized (e.g. temporarily
      split into two statements with a `time.sleep(0)` between them) as a non-tautology check, then
      confirm it passes again once reverted.
- [ ] `git status` scoped to `services/ingestion-service/` shows only the two new files.

## Documentation acceptance criteria

- [ ] `services/ingestion-service/README.md`: new short paragraph under the existing
      `POST /connectors/{source}/run` section (ahead of `INGEST-015` filling in the behavioral
      change) noting that a per-`(tenant_id, source)` in-process lock (`app/crawl_registry.py`) now
      exists, disclosing plainly that it is process-local (not shared across multiple
      `ingestion-service` replicas/processes — a known limitation if this service is ever scaled
      horizontally, matching this repo's existing disclosed-limitation convention, e.g. the
      encryption-key-rotation gap already documented in the same README).
