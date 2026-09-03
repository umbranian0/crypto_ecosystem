"""Unit tests for `src/app/crawl_registry.py` (INGEST-014).

`ingestion-service` is installed editable (`uv pip install -e .`) -- `app.crawl_registry`
imports directly, no `sys.path` insert needed, same convention as `tests/test_health.py`.

No FastAPI/HTTP involved here (`app.dependencies.repositories.get_crawl_registry`/
`CrawlRegistryDep` is exercised only indirectly, via the identity check below, since
wiring it into a live route is `INGEST-015`'s job, not this ticket's).
"""

from __future__ import annotations

import threading

from app.crawl_registry import CrawlRegistry
from app.dependencies.repositories import get_crawl_registry


def test_try_acquire_then_blocks_second_call_for_same_key():
    registry = CrawlRegistry()

    assert registry.try_acquire("tenant-a", "binance_price_btcusdt_1h") is True
    assert registry.try_acquire("tenant-a", "binance_price_btcusdt_1h") is False


def test_release_then_try_acquire_succeeds_again():
    registry = CrawlRegistry()
    registry.try_acquire("tenant-a", "binance_price_btcusdt_1h")

    registry.release("tenant-a", "binance_price_btcusdt_1h")

    assert registry.try_acquire("tenant-a", "binance_price_btcusdt_1h") is True


def test_key_is_the_full_pair_not_either_half_alone():
    registry = CrawlRegistry()

    assert registry.try_acquire("tenant-a", "binance_price_btcusdt_1h") is True
    # Different source, same tenant -- must not be blocked by the above.
    assert registry.try_acquire("tenant-a", "reddit_vader_sentiment") is True
    # Same source, different tenant -- must not be blocked by either above.
    assert registry.try_acquire("tenant-b", "binance_price_btcusdt_1h") is True


def test_release_on_never_acquired_key_is_a_noop():
    registry = CrawlRegistry()

    registry.release("tenant-a", "binance_price_btcusdt_1h")  # must not raise


def test_release_twice_on_same_key_is_a_noop():
    registry = CrawlRegistry()
    registry.try_acquire("tenant-a", "binance_price_btcusdt_1h")
    registry.release("tenant-a", "binance_price_btcusdt_1h")

    registry.release("tenant-a", "binance_price_btcusdt_1h")  # must not raise


def test_concurrent_try_acquire_on_same_key_only_one_thread_wins():
    registry = CrawlRegistry()
    thread_count = 16
    barrier = threading.Barrier(thread_count)
    results: list[bool] = [False] * thread_count

    def worker(index: int) -> None:
        barrier.wait()
        results[index] = registry.try_acquire("tenant-a", "binance_price_btcusdt_1h")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 1
    assert results.count(False) == thread_count - 1


def test_get_crawl_registry_returns_same_instance_across_calls():
    assert get_crawl_registry() is get_crawl_registry()
