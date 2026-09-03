# INGEST-023 — `CrawlRegistry` gains a per-crawl cancellation flag

Sprint: docs/sprints/sprint-23.md. Backlog: docs/product/backlog-crawl-lifecycle-control.md.
Status: **done**
Depends on: INGEST-022 (done first).

## Analysis

Covers the backlog's INGEST-023 story. `services/ingestion-service/src/app/crawl_registry.py`
(`INGEST-014`) already holds a `threading.Lock` + `set[tuple[str, str]]` mutual-exclusion primitive for
`(tenant_id, source)`, wired into `run_connector`/`_execute_crawl` (`INGEST-015`). This ticket extends
that same registry with a second flag set, rather than introducing a second coordination mechanism (the
backlog explicitly names this "don't reinvent" constraint).

## Design

**File touched**: `services/ingestion-service/src/app/crawl_registry.py` only (no router/connector
change here — this ticket is the registry primitive; wiring it into `_execute_crawl`'s `should_cancel`
argument is this same ticket's own AC below, a one-line addition to `connectors.py`).

**DRY check**: reuses the existing single `self._lock` (`threading.Lock`) for the new flag set too — no
second lock, no `asyncio.Lock` (this service's sync `def` handlers run in FastAPI's real thread pool,
same reasoning `crawl_registry.py`'s own docstring already states for the existing lock).

```python
class CrawlRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight: set[tuple[str, str]] = set()
        self._cancel_requested: set[tuple[str, str]] = set()

    def try_acquire(self, tenant_id, source) -> bool: ...  # unchanged

    def release(self, tenant_id, source) -> None:
        key = (tenant_id, source)
        with self._lock:
            self._in_flight.discard(key)
            self._cancel_requested.discard(key)  # clears any pending cancel flag

    def request_cancel(self, tenant_id, source) -> bool:
        key = (tenant_id, source)
        with self._lock:
            if key not in self._in_flight:
                return False
            self._cancel_requested.add(key)
            return True

    def should_cancel(self, tenant_id, source) -> bool:
        with self._lock:
            return (tenant_id, source) in self._cancel_requested
```

`release`'s existing `self._in_flight.discard(key)` line gets one more line added
(`self._cancel_requested.discard(key)`) — this is what prevents a stale flag from a prior crawl of the
same `(tenant_id, source)` from pre-cancelling a fresh one, per the story's own AC.

## Implementation acceptance criteria

- [x] `CrawlRegistry.request_cancel(tenant_id, source) -> bool` added: returns `True` only if a matching
      in-flight entry exists.
- [x] `CrawlRegistry.should_cancel(tenant_id, source) -> bool` added.
- [x] `release(tenant_id, source)` clears any pending cancellation flag for that key too.
- [x] No second synchronization primitive introduced — both new methods guarded by the existing
      `self._lock`.
- [x] `_execute_crawl` passes `should_cancel=lambda: registry.should_cancel(tenant_id, connector.name)`
      at its `connector.fetch(...)` call site.

## Test acceptance criteria

- [x] `tests/test_crawl_registry.py::test_request_cancel_then_should_cancel_scoped_to_exact_key_and_cleared_on_release`
      proves the full sequence including exact-key scoping and clearing on release.
- [x] `tests/test_crawl_registry.py::test_request_cancel_on_key_with_no_in_flight_entry_is_a_noop` proves
      the no-op case.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual diff: confirmed only one `threading.Lock` exists, both new methods acquire it.
- [x] Confirmed `_execute_crawl`'s `should_cancel` lambda captures the exact same `tenant_id`/
      `connector.name` values `try_acquire`/`release` already use — read the actual closure directly.
- [x] Full `services/ingestion-service` test suite re-run by the Tech Lead: `126 passed, 1 skipped`
      (pre-existing unrelated skip), zero regressions.

## Documentation acceptance criteria

- [ ] `services/ingestion-service/README.md`'s existing "Crawl mutual-exclusion primitive (`INGEST-014`)"
      paragraph gets one additional sentence naming `request_cancel`/`should_cancel` as the same
      registry's cancellation-flag extension (`INGEST-023`), pointing forward to `INGEST-024` for the
      endpoint that calls `request_cancel`.
