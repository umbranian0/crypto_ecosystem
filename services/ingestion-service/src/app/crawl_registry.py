"""Per-`(tenant_id, source)` in-process mutual-exclusion registry (INGEST-014).

Synchronization primitive only -- built for `INGEST-015` (router wiring,
background execution) to serialize concurrent `POST /connectors/{source}/run`
attempts for the same tenant+source, closing the race QA reproduced
(`docs/tickets/INGEST-014.md`'s Analysis section). No message queue exists in
this single-process service; FastAPI's sync `def` route handlers run in a real
thread pool (`anyio.to_thread`), so this uses `threading.Lock`, not
`asyncio.Lock` (which only guards interleaving on one event loop, not
concurrent OS threads).
"""

from __future__ import annotations

import threading


class CrawlRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight: set[tuple[str, str]] = set()

    def try_acquire(self, tenant_id: str, source: str) -> bool:
        key = (tenant_id, source)
        with self._lock:
            if key in self._in_flight:
                return False
            self._in_flight.add(key)
            return True

    def release(self, tenant_id: str, source: str) -> None:
        key = (tenant_id, source)
        with self._lock:
            self._in_flight.discard(key)
