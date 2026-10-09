"""Diagnostics: redacted entry config, printer capabilities, current job."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD, DOMAIN

TO_REDACT = {
    CONF_PASSWORD, "host", "user", "path", "printer_uri", "uuid", "unique_id",
    "name", "info", "location", "filename", "job_name", "error",
}


def _document_format(value: str) -> str:
    """Service callers can supply arbitrary MIME strings; only expose known types."""
    return value if value in (
        "application/pdf", "image/jpeg", "image/png", "application/octet-stream",
    ) else "other"


def record_blocked_format_probe(live: dict, document_format: str, cache) -> None:
    """One snapshot of a pre-upload refusal, retained even if the next try works."""
    live["last_blocked_submission"] = {
        "at": datetime.now(UTC).isoformat(),
        "stage": "format_capabilities",
        "document_format": _document_format(document_format),
        "job_may_exist": False,
        "probe": cache.diagnostic_snapshot(),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    info = data.get("printer_info")
    coordinator = data.get("coordinator")
    client = data.get("client")
    cache = data.get("capability_cache")
    connection = data.get("connection")
    current = coordinator.current if coordinator is not None else None
    return async_redact_data({
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "printer_uri": client.printer_uri if client is not None else None,
        "printer": info.to_dict() if info is not None else None,
        "current_job": current.to_dict() if current is not None else None,
        "card_url": data.get("card_url"),
        "connection": connection.snapshot() if connection else None,
        "capability_queries": {
            "generic": cache.diagnostic_snapshot() if cache else None,
            "formats": [
                {"document_format": _document_format(fmt), **probe.diagnostic_snapshot()}
                for fmt, probe in data.get("format_caches", {}).items()
            ],
        },
        "last_blocked_submission": data.get("last_blocked_submission"),
    }, TO_REDACT)
