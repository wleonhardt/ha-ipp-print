"""Per-job IPP progress tracker.

Polls Get-Job-Attributes every 1.5 s for each active job. Only runs while
at least one job is non-terminal, then shuts itself off.

Three observable surfaces:
* `JobCoordinator.current` is the most-recently-active job, mirrored to
  `sensor.printer_current_job`.
* `ipp_print_job_state_changed` events fire on every observed state change.
* `ipp_print_job_completed` events fire once per terminal transition.

Jobs whose printer stops answering are given up after MAX_POLL_FAILURES
consecutive failures and reported as `aborted` with state_reasons
`printer-unreachable`, so the sensor can never stick on `processing`.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Callable

from homeassistant.core import HomeAssistant

from .printer import (
    JobAttributes,
    JobGoneError,
    PrinterClient,
    TERMINAL_JOB_STATES,
)

_LOGGER = logging.getLogger(__name__)

POLL_INTERVAL = 1.5  # seconds between Get-Job-Attributes sweeps
MAX_POLL_INTERVAL = 12.0  # backoff ceiling while the printer is unreachable
TERMINAL_HOLD_SECONDS = 8.0  # how long to keep a finished job in `current`
MAX_POLL_FAILURES = 10  # consecutive failed polls before a job is given up
# A parse-ok-but-attrs-missing response usually means buggy firmware purged
# the job; require two in a row before treating it as gone so a one-off
# glitch can't end tracking early.
GONE_DEBOUNCE = 2

EVENT_JOB_STATE_CHANGED = "ipp_print_job_state_changed"
EVENT_JOB_COMPLETED = "ipp_print_job_completed"


@dataclass
class TrackedJob:
    job_id: int
    filename: str
    bytes_sent: int
    submitted_at: datetime
    state: str = "pending"
    state_reasons: str | None = None
    pages_done: int | None = None
    pages_total: int | None = None
    finished_at: datetime | None = None
    last_seen: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    cancel_requested: bool = False
    fail_count: int = 0  # consecutive poll failures
    gone_count: int = 0  # consecutive attrs-missing responses

    def is_terminal(self) -> bool:
        return self.finished_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "bytes": self.bytes_sent,
            "state": self.state,
            "state_reasons": self.state_reasons,
            "pages_done": self.pages_done,
            "pages_total": self.pages_total,
            "submitted_at": self.submitted_at.isoformat(),
            "finished_at": (
                self.finished_at.isoformat() if self.finished_at else None
            ),
        }


class JobCoordinator:
    """Background poller mirroring printer-side job state into HA."""

    def __init__(self, hass: HomeAssistant, client: PrinterClient) -> None:
        self._hass = hass
        self._client = client
        self._jobs: dict[int, TrackedJob] = {}
        self._current: TrackedJob | None = None
        self._poll_task: asyncio.Task | None = None
        self._update_listeners: list[Callable[[], None]] = []

    @property
    def current(self) -> TrackedJob | None:
        return self._current

    def register_update_listener(
        self, callback: Callable[[], None]
    ) -> Callable[[], None]:
        self._update_listeners.append(callback)

        def _unsub() -> None:
            try:
                self._update_listeners.remove(callback)
            except ValueError:
                pass

        return _unsub

    def _notify(self) -> None:
        for cb in list(self._update_listeners):
            try:
                cb()
            except Exception:
                _LOGGER.exception("update listener raised")

    def track(self, *, job_id: int, filename: str, bytes_sent: int) -> TrackedJob:
        job = TrackedJob(
            job_id=job_id,
            filename=filename,
            bytes_sent=bytes_sent,
            submitted_at=datetime.now(timezone.utc),
        )
        self._jobs[job_id] = job
        self._current = job
        self._notify()
        self._ensure_poll_loop()
        _LOGGER.info("tracking new job %s (%s)", job_id, filename)
        return job

    def _ensure_poll_loop(self) -> None:
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = self._hass.async_create_background_task(
                self._poll_loop(), name="ipp_print job poll"
            )

    async def async_shutdown(self) -> None:
        """Stop polling. Called on entry unload/reload."""
        task = self._poll_task
        self._poll_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _poll_loop(self) -> None:
        _LOGGER.debug("poll loop starting; %d job(s) tracked", len(self._jobs))
        try:
            while True:
                active = [j for j in self._jobs.values() if not j.is_terminal()]
                # Prune finished jobs so the map doesn't grow forever;
                # `current` stays readable via its own reference.
                if len(self._jobs) > len(active):
                    self._jobs = {j.job_id: j for j in active}
                if not active:
                    if self._current and self._current.is_terminal():
                        age = (
                            datetime.now(timezone.utc) - self._current.finished_at
                        ).total_seconds()
                        if age > TERMINAL_HOLD_SECONDS:
                            self._current = None
                            self._notify()
                            break
                        await asyncio.sleep(POLL_INTERVAL)
                        continue
                    break
                for job in active:
                    await self._poll_one(job)
                # Back off while every active job is failing to answer, so an
                # unplugged printer doesn't get hammered every 1.5 s.
                min_fails = min(j.fail_count for j in active)
                interval = min(
                    POLL_INTERVAL * (2 ** min(min_fails, 4)), MAX_POLL_INTERVAL
                )
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("poll loop crashed")
        finally:
            _LOGGER.debug("poll loop exited")

    async def _poll_one(self, job: TrackedJob) -> None:
        try:
            attrs = await self._client.get_job_attrs(job.job_id)
        except JobGoneError:
            # Printer purged the job. Report what actually happened: a purge
            # right after a cancel request is a cancel, not a completion.
            self._mark_terminal(
                job,
                "canceled" if job.cancel_requested else "completed",
                None,
            )
            return
        except Exception as exc:
            job.fail_count += 1
            _LOGGER.warning(
                "Get-Job-Attributes failed for %s (%d/%d): %s",
                job.job_id, job.fail_count, MAX_POLL_FAILURES, exc,
            )
            if job.fail_count >= MAX_POLL_FAILURES:
                self._mark_terminal(job, "aborted", "printer-unreachable")
            return
        if attrs is None:
            job.gone_count += 1
            if job.gone_count >= GONE_DEBOUNCE:
                self._mark_terminal(
                    job,
                    "canceled" if job.cancel_requested else "completed",
                    None,
                )
            return
        job.fail_count = 0
        job.gone_count = 0
        self._apply_attrs(job, attrs)

    def _apply_attrs(self, job: TrackedJob, attrs: JobAttributes) -> None:
        prior_state = job.state
        job.state = attrs.job_state_name
        job.state_reasons = attrs.job_state_reasons
        job.pages_done = attrs.media_sheets_completed or attrs.impressions_completed
        job.pages_total = attrs.impressions_total
        job.last_seen = datetime.now(timezone.utc)

        if attrs.job_state in TERMINAL_JOB_STATES:
            self._mark_terminal(job, attrs.job_state_name, attrs.job_state_reasons)
            return

        if prior_state != job.state:
            _LOGGER.debug(
                "job %s state %s → %s", job.job_id, prior_state, job.state
            )
            self._fire(EVENT_JOB_STATE_CHANGED, job)
        self._notify()

    def _mark_terminal(
        self, job: TrackedJob, state: str, reasons: str | None
    ) -> None:
        if job.is_terminal():
            return
        job.state = state
        job.state_reasons = reasons
        job.finished_at = datetime.now(timezone.utc)
        _LOGGER.info(
            "job %s reached terminal state %s (%s)",
            job.job_id, state, reasons or "no reason",
        )
        self._fire(EVENT_JOB_STATE_CHANGED, job)
        self._fire(EVENT_JOB_COMPLETED, job)
        self._notify()

    def _fire(self, event: str, job: TrackedJob) -> None:
        self._hass.bus.async_fire(event, job.to_dict())

    def knows(self, job_id: int) -> bool:
        """True if this coordinator submitted/tracks the given job."""
        return job_id in self._jobs or (
            self._current is not None and self._current.job_id == job_id
        )

    async def async_cancel(self, job_id: int) -> bool:
        # Record intent first: if the printer purges the job before our next
        # poll, _poll_one reports "canceled" instead of "completed".
        job = self._jobs.get(job_id)
        if job is not None:
            job.cancel_requested = True
        try:
            status = await self._client.cancel_job(job_id)
        except Exception as exc:
            _LOGGER.warning("Cancel-Job failed for %s: %s", job_id, exc)
            return False
        _LOGGER.info("Cancel-Job %s returned IPP status 0x%04x", job_id, status)
        return status in (0x0000, 0x0001, 0x0002)
