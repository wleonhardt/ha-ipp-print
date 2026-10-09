"""Bounded on-demand capability cache with redacted failure evidence."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import ssl
from time import monotonic

import aiohttp

from .printer import IppError, IppHttpError, IppStatusError

CACHE_TTL_SECONDS = 900.0
RETRY_SECONDS = 300.0
FETCH_TIMEOUT_SECONDS = 15.0


def _failure_details(exc: Exception) -> dict:
    """Allowlisted types/statuses only: never retain exceptions or their text."""
    if isinstance(exc, (IppHttpError, aiohttp.ClientResponseError)):
        return {"category": "authentication" if exc.status in (401, 403) else "http",
                "http_status": exc.status}
    if isinstance(exc, IppStatusError):
        return {"category": "ipp_rejected", "ipp_status": f"0x{exc.status:04x}"}
    if isinstance(exc, (ssl.SSLError, aiohttp.ClientSSLError)):
        return {"category": "tls"}
    if isinstance(exc, TimeoutError):
        return {"category": "timeout"}
    if isinstance(exc, aiohttp.ClientPayloadError):
        return {"category": "invalid_response"}
    if isinstance(exc, ValueError):
        return {"category": "invalid_data"}
    if isinstance(exc, (aiohttp.ClientConnectionError, OSError)):
        return {"category": "connection"}
    return {"category": "protocol" if isinstance(exc, IppError) else "unexpected"}


class CapabilityCache[T]:
    """Serialize refreshes, retain stale data, and never poll in the background."""

    def __init__(self, fetch: Callable[[], Awaitable[T]]) -> None:
        self._fetch = fetch
        self._lock = asyncio.Lock()
        self.closed = False
        self.value: T | None = None
        self.fetched_at: str | None = None
        self.attempted_at: str | None = None
        self._expires_at = 0.0
        self._retry_at = 0.0
        self.failed = False
        self._last_failure: dict | None = None

    async def async_get(self, *, fresh: bool = False) -> T | None:
        """Fresh is for per-job paper reads; even those respect failure backoff."""
        async with self._lock:
            if self.closed:
                return self.value
            now = monotonic()
            if now < self._retry_at or (not fresh and not self.failed and now < self._expires_at):
                return self.value
            self.attempted_at = datetime.now(UTC).isoformat()
            try:
                async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
                    value = await self._fetch()
                if value is None:
                    raise ValueError("empty capability response")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.failed = True
                self._retry_at = monotonic() + RETRY_SECONDS
                self._last_failure = {
                    "at": datetime.now(UTC).isoformat(),
                    "duration_ms": max(0, round((monotonic() - now) * 1000)),
                    **_failure_details(exc),
                }
            else:
                if not self.closed:
                    self.value = value
                    self.fetched_at = datetime.now(UTC).isoformat()
                    self._expires_at = monotonic() + CACHE_TTL_SECONDS
                    self._retry_at = 0.0
                    self.failed = False
            return self.value

    def metadata(self) -> dict:
        now = monotonic()
        status = "unknown" if self.value is None else (
            "stale" if self.failed or now >= self._expires_at else "fresh"
        )
        due = self._retry_at if self.failed else self._expires_at
        return {
            "status": status,
            "fetched_at": self.fetched_at,
            "attempted_at": self.attempted_at,
            "error": "refresh_failed" if self.failed else None,
            "refresh_after_seconds": max(0, int(due - now)),
            "cache_ttl_seconds": int(CACHE_TTL_SECONDS),
        }

    def diagnostic_snapshot(self) -> dict:
        """One failure survives recovery; no network I/O or raw error strings."""
        metadata = self.metadata()
        metadata.pop("error")  # Existing diagnostics redact arbitrary error text.
        return {**metadata, "closed": self.closed, "refresh_failed": self.failed,
                "last_failure": dict(self._last_failure) if self._last_failure else None}

    async def async_close(self) -> None:
        """Drain a bounded in-flight refresh before the client is closed."""
        self.closed = True
        async with self._lock:
            pass
