"""JobCoordinator state-machine tests with a scripted fake client."""
import asyncio

import pytest
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.ipp_print import coordinator as coord_mod
from custom_components.ipp_print.coordinator import JobCoordinator
from custom_components.ipp_print.printer import (
    JOB_STATE_NAMES,
    JobAttributes,
    JobGoneError,
)


def _attrs(state: int, job_id: int = 7, done=None, total=None, reasons=None):
    return JobAttributes(
        job_id=job_id,
        job_state=state,
        job_state_name=JOB_STATE_NAMES.get(state, f"unknown-{state}"),
        job_state_reasons=reasons,
        impressions_completed=done,
        media_sheets_completed=None,
        impressions_total=total,
        job_name="x.pdf",
    )


class FakeClient:
    """Replays a script of responses; repeats the final item forever.

    Items: JobAttributes, None (attrs missing), or an Exception to raise.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
        self.cancel_status = 0x0000
        self.cancelled = []

    async def get_job_attrs(self, job_id):
        self.calls += 1
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, Exception):
            raise item
        return item

    async def cancel_job(self, job_id):
        self.cancelled.append(job_id)
        return self.cancel_status


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(coord_mod, "POLL_INTERVAL", 0.01)
    monkeypatch.setattr(coord_mod, "MAX_POLL_INTERVAL", 0.02)
    monkeypatch.setattr(coord_mod, "TERMINAL_HOLD_SECONDS", 0.05)


async def _wait_for(predicate, timeout=5.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition timeout"
        await asyncio.sleep(0.01)


async def test_full_lifecycle_to_completed(hass):
    client = FakeClient([_attrs(3), _attrs(5, done=1, total=2), _attrs(9, done=2)])
    coord = JobCoordinator(hass, client)
    completed = async_capture_events(hass, coord_mod.EVENT_JOB_COMPLETED)
    changed = async_capture_events(hass, coord_mod.EVENT_JOB_STATE_CHANGED)

    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    await _wait_for(lambda: coord.current is None)

    assert len(completed) == 1
    assert completed[0].data["state"] == "completed"
    assert completed[0].data["pages_done"] == 2
    states = [e.data["state"] for e in changed]
    assert "processing" in states and states[-1] == "completed"
    # Terminal jobs are pruned from the tracking map.
    assert not coord._jobs


async def test_unreachable_printer_gives_up_as_aborted(hass, monkeypatch):
    monkeypatch.setattr(coord_mod, "MAX_POLL_FAILURES", 3)
    client = FakeClient([OSError("no route to host")])
    coord = JobCoordinator(hass, client)
    completed = async_capture_events(hass, coord_mod.EVENT_JOB_COMPLETED)

    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    await _wait_for(lambda: len(completed) == 1)

    assert completed[0].data["state"] == "aborted"
    assert completed[0].data["state_reasons"] == "printer-unreachable"
    # Poll loop must terminate rather than spin forever.
    await _wait_for(lambda: coord._poll_task.done())
    assert client.calls == 3


async def test_purged_job_after_cancel_reports_canceled(hass):
    client = FakeClient([_attrs(3), JobGoneError("gone")])
    coord = JobCoordinator(hass, client)
    completed = async_capture_events(hass, coord_mod.EVENT_JOB_COMPLETED)

    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    assert await coord.async_cancel(7)
    await _wait_for(lambda: len(completed) == 1)

    assert client.cancelled == [7]
    assert completed[0].data["state"] == "canceled"


async def test_purged_job_without_cancel_reports_completed(hass):
    client = FakeClient([_attrs(5), JobGoneError("gone")])
    coord = JobCoordinator(hass, client)
    completed = async_capture_events(hass, coord_mod.EVENT_JOB_COMPLETED)

    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    await _wait_for(lambda: len(completed) == 1)
    assert completed[0].data["state"] == "completed"


async def test_attrs_missing_is_debounced(hass):
    # One glitchy attrs-missing response must not end tracking...
    client = FakeClient([None, _attrs(5), _attrs(9)])
    coord = JobCoordinator(hass, client)
    completed = async_capture_events(hass, coord_mod.EVENT_JOB_COMPLETED)
    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    await _wait_for(lambda: len(completed) == 1)
    assert completed[0].data["state"] == "completed"
    assert client.calls >= 3


async def test_attrs_missing_twice_marks_completed(hass):
    # ...but two in a row means the printer really purged the job.
    client = FakeClient([None])
    coord = JobCoordinator(hass, client)
    completed = async_capture_events(hass, coord_mod.EVENT_JOB_COMPLETED)
    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    await _wait_for(lambda: len(completed) == 1)
    assert completed[0].data["state"] == "completed"
    assert client.calls == coord_mod.GONE_DEBOUNCE


async def test_shutdown_cancels_poll_task(hass):
    client = FakeClient([_attrs(5)])  # never terminal on its own
    coord = JobCoordinator(hass, client)
    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    await asyncio.sleep(0.05)
    task = coord._poll_task
    assert task is not None and not task.done()
    await coord.async_shutdown()
    assert task.done()
    assert coord._poll_task is None


async def test_knows_only_tracked_jobs(hass):
    client = FakeClient([_attrs(5)])
    coord = JobCoordinator(hass, client)
    coord.track(job_id=7, filename="x.pdf", bytes_sent=10)
    assert coord.knows(7)
    assert not coord.knows(999)
    await coord.async_shutdown()
