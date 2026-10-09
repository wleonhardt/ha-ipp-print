"""Bounded read-only protocol reachability, independent of tracked job state."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
import logging

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
CHECK_INTERVAL = 60.0
MAX_BACKOFF = 300.0
CHECK_TIMEOUT = 10.0


class DeviceConnection:
    """One serialized status check per device, with cancellation-safe cleanup."""

    def __init__(self, hass: HomeAssistant, probe: Callable[[], Awaitable], name: str):
        self._hass = hass
        self._probe = probe
        self._name = name
        self._task = None
        self._lock = asyncio.Lock()
        self._listeners = []
        self._due = 0.0
        self._failures = 0
        self.closed = False
        self.state = "unknown"
        self.checked_at = None
        self.last_success_at = None
        self.next_check_at = None

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "checked_at": self.checked_at,
            "last_success_at": self.last_success_at,
            "next_check_at": self.next_check_at,
        }

    def register_update_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(callback)

        def unsubscribe():
            if callback in self._listeners:
                self._listeners.remove(callback)

        return unsubscribe

    def start(self) -> None:
        if not self.closed and self._task is None:
            self._task = self._hass.async_create_background_task(
                self._run(), name=f"{self._name} connection"
            )

    async def async_check(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            if self.closed or loop.time() < self._due:
                return
            try:
                async with asyncio.timeout(CHECK_TIMEOUT):
                    await self._probe()
            except Exception:
                state = "unreachable"
                self._failures = min(self._failures + 1, 4)
                _LOGGER.debug("%s protocol connection check failed", self._name)
            else:
                state = "reachable"
                self._failures = 0
            if self.closed:
                return
            now = datetime.now(UTC)
            self.state = state
            self.checked_at = now.isoformat()
            if state == "reachable":
                self.last_success_at = self.checked_at
            delay = min(CHECK_INTERVAL * 2 ** max(0, self._failures - 1), MAX_BACKOFF)
            self._due = loop.time() + delay
            self.next_check_at = (now + timedelta(seconds=delay)).isoformat()
            for callback in tuple(self._listeners):
                try:
                    callback()
                except Exception:
                    _LOGGER.exception("connection listener raised")

    async def _run(self) -> None:
        while not self.closed:
            await self.async_check()
            await asyncio.sleep(max(0, self._due - asyncio.get_running_loop().time()))

    async def async_close(self) -> None:
        self.closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # Also drain a check started by a caller outside the periodic task.
        async with self._lock:
            self._listeners.clear()
