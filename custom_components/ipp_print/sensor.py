"""sensor.printer_current_job — mirrors the active IPP job state."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
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
    coordinator: JobCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([PrinterJobSensor(coordinator, entry.entry_id)])


class PrinterJobSensor(SensorEntity):
    """Mirrors JobCoordinator.current as a sensor entity."""

    _attr_has_entity_name = True
    _attr_name = "Current job"
    _attr_icon = "mdi:printer-pos"
    _attr_device_class = "enum"
    _attr_options = JOB_STATES
    _attr_should_poll = False

    def __init__(self, coordinator: JobCoordinator, entry_id: str) -> None:
        self._coord = coordinator
        self._attr_unique_id = f"{entry_id}_current_job"
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
