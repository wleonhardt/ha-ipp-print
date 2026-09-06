"""Diagnostics: redacted entry config, printer capabilities, current job."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, DOMAIN

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    info = data.get("printer_info")
    coordinator = data.get("coordinator")
    client = data.get("client")
    current = coordinator.current if coordinator is not None else None
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "printer_uri": client.printer_uri if client is not None else None,
        "printer": info.to_dict() if info is not None else None,
        "current_job": current.to_dict() if current is not None else None,
        "card_url": data.get("card_url"),
    }
