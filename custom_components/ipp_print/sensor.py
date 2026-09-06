"""sensor.printer_current_job — mirrors the active IPP job state."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JobCoordinator

_LOGGER = logging.getLogger(__name__)

# Order matches IPP-defined progression so HA can render as enum.
JOB_STATES = [
    "idle",
    "pending",
    "pending-held",
    "processing",
    "processing-stopped",
    "canceled",
    "aborted",
    "completed",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PrinterJobSensor(entry, data)])


def _device_info(entry: ConfigEntry, data: dict) -> DeviceInfo:
    """One device per configured printer, populated from
    Get-Printer-Attributes when the probe succeeded."""
    info = data.get("printer_info")
    client = data["client"]
    name = None
    manufacturer = None
    model = None
    if info is not None:
        name = (info.info or info.name or "").strip() or None
        model = (info.make_and_model or "").strip() or None
        if model:
            manufacturer = model.split(" ", 1)[0]
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=name or entry.title or f"IPP printer at {client.host}",
        manufacturer=manufacturer,
        model=model,
        configuration_url=client.web_url,
    )


class PrinterJobSensor(SensorEntity):
    """Mirrors JobCoordinator.current as a sensor entity."""

    _attr_has_entity_name = True
    _attr_name = "Current job"
    _attr_icon = "mdi:printer-pos"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = JOB_STATES
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, data: dict) -> None:
        self._coord: JobCoordinator = data["coordinator"]
        self._attr_unique_id = f"{entry.entry_id}_current_job"
        self._attr_device_info = _device_info(entry, data)
        # Stable entity_id so the card can find it without renames.
        self.entity_id = "sensor.printer_current_job"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self._coord.register_update_listener(self._handle_update)
        # Without this the entity stays "unavailable" until first job submit.
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        job = self._coord.current
        return "idle" if job is None else job.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        job = self._coord.current
        return {"job_id": None} if job is None else job.to_dict()
