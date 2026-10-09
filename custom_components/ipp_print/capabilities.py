"""Small public capability contract and strict shared option validation."""
from __future__ import annotations

import re

import voluptuous as vol

from .capability_cache import CapabilityCache
from .const import DOMAIN, MAX_UPLOAD_BYTES
from .printer import SIDES, PrinterInfo

UPLOAD_FORMATS = ("application/pdf", "image/jpeg", "image/png")
MAX_COPIES = 99


def validate_copies(value: object) -> int:
    """Never coerce a boolean, float, signed value or whitespace to copies."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,3}", value):
        value = int(value)
    if type(value) is not int or not 1 <= value <= MAX_COPIES:
        raise vol.Invalid("copies must be a decimal integer from 1 to 99")
    return value


def capability_snapshot(cache: CapabilityCache[PrinterInfo], entity_id: str | None) -> dict:
    info = cache.value
    return {
        "schema_version": 1,
        "domain": DOMAIN,
        "entity_id": entity_id,
        **cache.metadata(),
        "identity": {
            "name": (info.info or info.name or "")[:256] or None if info else None,
            "model": (info.make_and_model or "")[:256] or None if info else None,
        },
        "supported": {
            "formats": [fmt for fmt in UPLOAD_FORMATS if info.supports_format(fmt)]
            if info and info.formats else None,
            "sides": [side for side in SIDES if side in info.sides]
            if info and info.sides else None,
            "copies_max": info.copies_max if info else None,
            "auto_sensing": info.auto_sensing if info and info.formats else None,
            "media": list(info.media_supported)[:128] if info and info.media_supported else None,
            "media_sources": info.media_sources[:128] if info and info.media_sources else None,
            "media_ready": info.media_ready[:128] if info and info.media_ready is not None else None,
            "color_modes": list(info.color_modes)[:128] if info and info.color_modes else None,
            "qualities": [q for q in info.qualities if q in (3, 4, 5)] if info and info.qualities else None,
        },
        "defaults": info.defaults if info else {},
        "document_format": info.document_format if info else None,
        "request_options": ["entity_id", "copies", "sides", "media", "color_mode", "quality", "media_source"],
        "limits": {"copies_min": 1, "copies_max": MAX_COPIES,
                   "upload_bytes": MAX_UPLOAD_BYTES, "formats": list(UPLOAD_FORMATS)},
    }
