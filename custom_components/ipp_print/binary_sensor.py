"""Protocol connectivity; job idle state does not imply reachability."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import callback

from .const import DOMAIN
from .sensor import _device_info


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ConnectionSensor(entry, data)])


class ConnectionSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_should_poll = False

    def __init__(self, entry, data):
        self._connection = data["connection"]
        self._attr_unique_id = f"{entry.entry_id}_connection"
        self._attr_device_info = _device_info(entry, data)

    async def async_added_to_hass(self):
        self.async_on_remove(self._connection.register_update_listener(self._handle_update))

    @callback
    def _handle_update(self):
        self.async_write_ha_state()

    @property
    def is_on(self):
        state = self._connection.state
        return None if state == "unknown" else state == "reachable"

    @property
    def extra_state_attributes(self):
        return self._connection.snapshot()
