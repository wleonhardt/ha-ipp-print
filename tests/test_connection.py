"""Reachability is measured separately from job state, with bounded I/O."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock


from custom_components.ipp_print import connection as module
from custom_components.ipp_print.connection import DeviceConnection


async def test_unknown_success_failure_and_recovery(hass):
    probe = AsyncMock()
    monitor = DeviceConnection(hass, probe, "test")
    assert monitor.snapshot()["state"] == "unknown"
    assert monitor.checked_at is None
    updates = []
    monitor.register_update_listener(lambda: updates.append(monitor.snapshot()))
    await monitor.async_check()
    assert monitor.state == "reachable"
    success = monitor.last_success_at
    probe.side_effect = OSError("private host detail")
    intervals = []
    for _ in range(6):
        monitor._due = 0
        await monitor.async_check()
        intervals.append((datetime.fromisoformat(monitor.next_check_at) - datetime.fromisoformat(monitor.checked_at)).total_seconds())
        assert monitor.state == "unreachable"
        assert monitor.last_success_at == success
        assert "private" not in str(monitor.snapshot())
    assert intervals == [60, 120, 240, 300, 300, 300]
    probe.side_effect = None
    monitor._due = 0
    await monitor.async_check()
    assert monitor.state == "reachable"
    assert monitor.last_success_at != success
    assert len(updates) == 8
    await monitor.async_close()


async def test_parallel_checks_are_coalesced_and_cached(hass):
    gate = asyncio.Event()
    probe = AsyncMock(side_effect=gate.wait)
    monitor = DeviceConnection(hass, probe, "test")
    checks = [asyncio.create_task(monitor.async_check()) for _ in range(5)]
    await asyncio.sleep(0)
    assert probe.await_count == 1
    gate.set()
    await asyncio.gather(*checks)
    await monitor.async_check()
    assert probe.await_count == 1
    await monitor.async_close()


async def test_timeout_is_unreachable_and_unload_cancels_background_io(hass, monkeypatch):
    monkeypatch.setattr(module, "CHECK_TIMEOUT", 0.01)
    gate = asyncio.Event()
    monitor = DeviceConnection(hass, gate.wait, "test")
    await monitor.async_check()
    assert monitor.state == "unreachable"
    monitor._due = 0
    monitor.start()
    task = monitor._task
    monitor.start()
    assert monitor._task is task
    await asyncio.sleep(0)
    snapshot = monitor.snapshot()
    await monitor.async_close()
    assert task.done()
    gate.set()
    await monitor.async_check()
    assert monitor.snapshot() == snapshot


async def test_removed_listener_cannot_write_after_unload(hass):
    monitor = DeviceConnection(hass, AsyncMock(), "test")
    called = []
    unsubscribe = monitor.register_update_listener(lambda: called.append(True))
    unsubscribe()
    await monitor.async_check()
    assert not called
    await monitor.async_close()
