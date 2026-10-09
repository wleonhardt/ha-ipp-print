"""Cache backoff and bounded per-job recovery, stale data and unload safety."""
import asyncio
import ssl
from unittest.mock import AsyncMock

import aiohttp
import pytest

from custom_components.ipp_print import capability_cache as module
from custom_components.ipp_print.printer import IppHttpError, IppStatusError


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
    assert cache.diagnostic_snapshot()["last_failure"]["category"] == "timeout"


async def test_cancellation_does_not_invent_failure_evidence():
    fetch = AsyncMock(side_effect=[TimeoutError("private"), asyncio.CancelledError()])
    cache = module.CapabilityCache(fetch)
    await cache.async_get()
    previous = cache.diagnostic_snapshot()["last_failure"]
    cache._retry_at = 0
    with pytest.raises(asyncio.CancelledError):
        await cache.async_get(fresh=True)
    assert cache.diagnostic_snapshot()["last_failure"] == previous


@pytest.mark.parametrize("error", [
    TimeoutError(), aiohttp.ServerDisconnectedError(),
    IppHttpError(502), IppHttpError(503), IppHttpError(504),
])
async def test_deliberate_retry_recovers_without_shortening_ordinary_backoff(clock, error):
    fetch = AsyncMock(side_effect=[error, "recovered"])
    cache = module.CapabilityCache(fetch)
    assert await cache.async_get(fresh=True) is None
    failure = cache.diagnostic_snapshot()["last_failure"]
    assert cache.metadata()["refresh_after_seconds"] == 300
    assert cache.retry_after_seconds(fresh=True) == 30
    clock[0] += 29
    assert await cache.async_get(fresh=True) is None
    assert cache.retry_after_seconds(fresh=True) == 1
    clock[0] += 1
    assert await cache.async_get() is None  # Dashboard reads cannot trigger it.
    fetch.assert_awaited_once()
    assert await cache.async_get(fresh=True) == "recovered"
    assert fetch.await_count == 2
    assert cache.metadata()["status"] == "fresh"
    assert cache.retry_after_seconds(fresh=True) == 0
    assert cache.diagnostic_snapshot()["last_failure"] == failure


async def test_only_one_early_retry_before_full_backoff(clock):
    fetch = AsyncMock(side_effect=TimeoutError())
    cache = module.CapabilityCache(fetch)
    await cache.async_get(fresh=True)
    clock[0] += 30
    await asyncio.gather(*(cache.async_get(fresh=True) for _ in range(12)))
    assert fetch.await_count == 2
    assert cache.retry_after_seconds(fresh=True) == 300
    clock[0] += 30
    await cache.async_get(fresh=True)
    assert fetch.await_count == 2
    clock[0] += module.RETRY_SECONDS - 30
    await cache.async_get(fresh=True)
    assert fetch.await_count == 3


@pytest.mark.parametrize("error", [
    ssl.SSLError(), IppHttpError(401), IppHttpError(403), IppHttpError(429),
    IppStatusError("unsupported format", 0x040A), ValueError(), aiohttp.ClientPayloadError(),
])
async def test_nontransient_failure_keeps_full_backoff(clock, error):
    fetch = AsyncMock(side_effect=error)
    cache = module.CapabilityCache(fetch)
    await cache.async_get(fresh=True)
    clock[0] += 30
    await cache.async_get(fresh=True)
    fetch.assert_awaited_once()
    assert cache.retry_after_seconds(fresh=True) == 270


async def test_canceled_early_retry_consumes_opportunity_without_rewriting_failure(clock):
    fetch = AsyncMock(side_effect=[TimeoutError(), asyncio.CancelledError(), "recovered"])
    cache = module.CapabilityCache(fetch)
    await cache.async_get(fresh=True)
    failure = cache.diagnostic_snapshot()["last_failure"]
    clock[0] += 30
    with pytest.raises(asyncio.CancelledError):
        await cache.async_get(fresh=True)
    assert cache.diagnostic_snapshot()["last_failure"] == failure
    await cache.async_get(fresh=True)
    assert fetch.await_count == 2
    clock[0] += module.RETRY_SECONDS - 30
    assert await cache.async_get(fresh=True) == "recovered"


async def test_early_retry_keeps_stale_data_until_success(clock):
    fetch = AsyncMock(side_effect=["old", TimeoutError(), "new", TimeoutError(), "latest"])
    cache = module.CapabilityCache(fetch)
    assert await cache.async_get() == "old"
    assert await cache.async_get(fresh=True) == "old"
    assert cache.metadata()["status"] == "stale"
    clock[0] += 30
    assert await cache.async_get(fresh=True) == "new"
    # A successful recovery resets the budget for a later, independent outage.
    assert await cache.async_get(fresh=True) == "new"
    clock[0] += 30
    assert await cache.async_get(fresh=True) == "latest"
