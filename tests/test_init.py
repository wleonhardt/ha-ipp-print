"""Entry lifecycle, lovelace resource sync, sensor entity."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.ipp_print as integration
from custom_components.ipp_print.const import DOMAIN
from custom_components.ipp_print.coordinator import JobCoordinator


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="127.0.0.1:443"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_unload_stops_poller_and_closes_session(hass):
    entry = await _setup(hass)
    data = hass.data[DOMAIN][entry.entry_id]
    with patch.object(data["coordinator"], "async_shutdown", new=AsyncMock()) as sd, \
            patch.object(data["client"], "async_close", new=AsyncMock()) as cl:
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    sd.assert_awaited_once()
    cl.assert_awaited_once()
    assert entry.entry_id not in hass.data[DOMAIN]
    # Bookkeeping survives so a re-setup doesn't re-register routes.
    assert hass.data[DOMAIN]["_views_registered"] is True


async def test_setup_survives_printer_offline(hass, printer_attrs):
    printer_attrs.side_effect = OSError("no route")
    entry = await _setup(hass)
    data = hass.data[DOMAIN][entry.entry_id]
    assert data["printer_info"] is None
    # Sensor still exists with a host-derived device name.
    state = hass.states.get("sensor.printer_current_job")
    assert state is not None and state.state == "idle"


async def test_sensor_mirrors_coordinator(hass):
    entry = await _setup(hass)
    coord: JobCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    assert hass.states.get("sensor.printer_current_job").state == "idle"
    with patch.object(JobCoordinator, "_ensure_poll_loop"):
        coord.track(job_id=3, filename="x.pdf", bytes_sent=5)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.printer_current_job")
    assert state.state == "pending"
    assert state.attributes["job_id"] == 3
    assert state.attributes["filename"] == "x.pdf"


class FakeCollection:
    """Minimal stand-in for lovelace's ResourceStorageCollection."""

    def __init__(self, items):
        self.items = list(items)
        self.created = []
        self.deleted = []

    def async_items(self):
        return list(self.items)

    async def async_create_item(self, data):
        self.created.append(data)

    async def async_delete_item(self, item_id):
        self.deleted.append(item_id)


# conftest replaces `_sync_lovelace_resource` with an AsyncMock for every
# test; grab the real coroutine at import time so these can exercise it.
_REAL_SYNC = integration.__dict__["_sync_lovelace_resource"]


async def test_lovelace_sync_creates_and_reaps_stale(hass):
    hass.data[DOMAIN] = {}
    coll = FakeCollection([
        {"id": "old", "url": "/ipp_print/card-deadbeef0000.js"},
        {"id": "other", "url": "/hacsfiles/other-card.js"},
    ])
    hass.data["lovelace_resources"] = coll
    with patch("custom_components.ipp_print.add_extra_js_url") as extra:
        await _REAL_SYNC(hass, "/ipp_print/card-abc.js")
    assert coll.deleted == ["old"]
    assert coll.created == [{"res_type": "module", "url": "/ipp_print/card-abc.js"}]
    extra.assert_not_called()


async def test_lovelace_sync_noop_when_current(hass):
    hass.data[DOMAIN] = {}
    coll = FakeCollection([{"id": "cur", "url": "/ipp_print/card-abc.js"}])
    hass.data["lovelace_resources"] = coll
    await _REAL_SYNC(hass, "/ipp_print/card-abc.js")
    assert coll.created == [] and coll.deleted == []


async def test_lovelace_sync_yaml_mode_falls_back_to_extra_js(hass):
    hass.data[DOMAIN] = {}
    # YAML-mode collection has no create/delete API.
    hass.data["lovelace_resources"] = SimpleNamespace(async_items=lambda: [])
    with patch("custom_components.ipp_print.add_extra_js_url") as extra:
        await _REAL_SYNC(hass, "/ipp_print/card-abc.js")
        await _REAL_SYNC(hass, "/ipp_print/card-abc.js")  # idempotent
    extra.assert_called_once_with(hass, "/ipp_print/card-abc.js")
