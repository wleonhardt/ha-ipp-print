"""Durable bounded metadata cannot become a reprint or a resumed job."""
from datetime import datetime, timedelta, timezone

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ipp_print import async_remove_entry
from custom_components.ipp_print.activity import MAX_RECORDS, PrintActivity, store_key
from custom_components.ipp_print.coordinator import JobCoordinator, TrackedJob

from test_coordinator import FakeClient, _attrs, _wait_for


def job(job_id=7, age=0, state="completed", **kwargs):
    submitted = datetime.now(timezone.utc) - timedelta(seconds=age)
    return TrackedJob(job_id=job_id, filename="report.pdf", bytes_sent=99,
                      submitted_at=submitted, finished_at=submitted if state != "pending" else None,
                      state=state, **kwargs)


async def test_activity_restores_metadata_only_and_separates_entries(hass):
    first, second = PrintActivity(hass, "office"), PrintActivity(hass, "study")
    first.record(job(pages_done=0, progress_unit="impressions"))
    second.record(job(state="canceled"))
    await first.async_close()
    await second.async_close()
    client = FakeClient([_attrs(9)])
    coord = JobCoordinator(hass, client, "office")
    await coord.activity.async_load()
    record = coord.activity.snapshot()[0]
    assert record["state"] == "completed" and record["pages_done"] == 0
    assert not {"bytes", "requested_settings", "file_url", "path"} & record.keys()
    assert coord.current is None and not coord._jobs and coord._poll_task is None
    assert client.calls == 0 and not client.cancelled
    other = PrintActivity(hass, "study")
    await other.async_load()
    assert other.snapshot()[0]["state"] == "canceled"
    await coord.async_shutdown()


async def test_bound_retention_and_reused_job_ids(hass):
    activity = PrintActivity(hass, "bounded")
    for age in range(20):
        activity.record(job(age=age))
    assert len(activity.snapshot()) == MAX_RECORDS
    assert len({r["submitted_at"] for r in activity.snapshot()}) == MAX_RECORDS
    activity.record(job(job_id=99, age=8 * 24 * 3600))
    assert len(activity.snapshot()) == MAX_RECORDS
    assert all(r["job_id"] == 7 for r in activity.snapshot())
    retained = activity.snapshot()
    await activity.async_close()
    restored = PrintActivity(hass, "bounded")
    await restored.async_load()
    assert restored.snapshot() == retained


async def test_pending_restore_has_unknown_outcome_without_a_finish_time(hass, hass_storage):
    pending = job(state="pending")
    activity = PrintActivity(hass, "pending")
    activity.record(pending)
    assert activity.snapshot() == []
    await activity._store.async_save({"records": activity._records})
    restored = PrintActivity(hass, "pending")
    await restored.async_load()
    assert restored.snapshot()[0]["state"] == "unknown"
    assert restored.snapshot()[0]["finished_at"] is None
    await restored.async_close()


async def test_terminal_transition_updates_pending_record_and_survives_idle(hass, monkeypatch):
    monkeypatch.setattr("custom_components.ipp_print.coordinator.POLL_INTERVAL", 0.01)
    monkeypatch.setattr("custom_components.ipp_print.coordinator.TERMINAL_HOLD_SECONDS", 0.02)
    coord = JobCoordinator(hass, FakeClient([_attrs(9, done=2)]), "tracked")
    coord.track(job_id=7, filename="a.pdf", bytes_sent=99)
    await _wait_for(lambda: coord.current is None)
    assert len(coord.activity.snapshot()) == 1
    assert coord.activity.snapshot()[0]["pages_done"] == 2
    await coord.async_shutdown()
    restored = PrintActivity(hass, "tracked")
    await restored.async_load()
    assert restored.snapshot() == coord.activity.snapshot()


@pytest.mark.parametrize("value", [None, [], {"records": 1}, {"records": [
    {"state": {}, "job_id": 7, "filename": "a.pdf", "submitted_at": "9999-12-31T12:00:00+00:00"}
]}])
async def test_corrupt_storage_does_not_block_printing(hass, hass_storage, value):
    hass_storage[store_key("broken")] = {"version": 1, "data": value}
    activity = PrintActivity(hass, "broken")
    await activity.async_load()
    assert activity.snapshot() == []


async def test_removing_printer_removes_only_its_history(hass, hass_storage):
    for key in ("office", "study"):
        activity = PrintActivity(hass, key)
        activity.record(job())
        await activity.async_close()
    await async_remove_entry(hass, MockConfigEntry(domain="ipp_print", entry_id="office", data={}))
    assert store_key("office") not in hass_storage
    assert store_key("study") in hass_storage
