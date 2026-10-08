"""Shared cache policy: bounded refresh cost, stale data and unload safety."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from custom_components.ipp_print import capability_cache as module


@pytest.fixture
def clock(monkeypatch):
    now = [1.0]
    monkeypatch.setattr(module, "monotonic", lambda: now[0])
    return now


async def test_concurrent_reads_share_one_probe_until_ttl(clock):
    fetch = AsyncMock(return_value={"model": "test"})
    cache = module.CapabilityCache(fetch)
    values = await asyncio.gather(*(cache.async_get() for _ in range(12)))
    assert all(value == {"model": "test"} for value in values)
    assert fetch.await_count == 1
    assert cache.metadata()["status"] == "fresh"
    assert cache.fetched_at and cache.attempted_at
    clock[0] += module.CACHE_TTL_SECONDS
    await cache.async_get()
    assert fetch.await_count == 2


async def test_failed_refresh_retains_stale_data_and_recovers_after_backoff(clock):
    original = {"model": "old"}
    fetch = AsyncMock(return_value=original)
    cache = module.CapabilityCache(fetch)
    await cache.async_get()
    fetched_at = cache.fetched_at
    # A fresh per-job read can fail before the ordinary TTL expires.
    fetch.side_effect = OSError("credentials and internal address must not leak")
    assert await cache.async_get(fresh=True) is original
    metadata = cache.metadata()
    assert metadata["status"] == "stale"
    assert metadata["error"] == "refresh_failed"
    assert metadata["fetched_at"] == fetched_at
    for _ in range(3):
        assert await cache.async_get(fresh=True) is original
    assert fetch.await_count == 2
    clock[0] += module.RETRY_SECONDS
    fetch.side_effect = None
    fetch.return_value = {"model": "new"}
    assert await cache.async_get() == {"model": "new"}
    assert cache.metadata()["status"] == "fresh"
    assert fetch.await_count == 3


async def test_initial_failure_is_unknown_and_rate_limited(clock):
    fetch = AsyncMock(side_effect=OSError("offline"))
    cache = module.CapabilityCache(fetch)
    assert await cache.async_get() is None
    assert await cache.async_get() is None
    assert cache.metadata()["status"] == "unknown"
    assert cache.fetched_at is None
    fetch.assert_awaited_once()


async def test_expired_success_is_stale_before_refresh(clock):
    cache = module.CapabilityCache(AsyncMock(return_value="known"))
    await cache.async_get()
    clock[0] += module.CACHE_TTL_SECONDS + 1
    assert cache.metadata()["status"] == "stale"


async def test_unload_drains_refresh_without_publishing_or_reopening():
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch():
        entered.set()
        await release.wait()
        return "new"

    cache = module.CapabilityCache(fetch)
    read = asyncio.create_task(cache.async_get())
    await entered.wait()
    close = asyncio.create_task(cache.async_close())
    await asyncio.sleep(0)
    assert cache.closed and not close.done()
    release.set()
    await asyncio.gather(read, close)
    assert cache.value is None
    assert await cache.async_get(fresh=True) is None


async def test_probe_timeout_is_bounded_and_cached(monkeypatch):
    monkeypatch.setattr(module, "FETCH_TIMEOUT_SECONDS", 0.001)
    fetch = AsyncMock(side_effect=lambda: None)

    async def blocked():
        await asyncio.Event().wait()

    fetch.side_effect = blocked
    cache = module.CapabilityCache(fetch)
    assert await cache.async_get() is None
    assert await cache.async_get() is None
    fetch.assert_awaited_once()
    assert cache.failed
