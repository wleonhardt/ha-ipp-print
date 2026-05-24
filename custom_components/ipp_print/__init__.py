"""IPP Print — direct PDF submission to a network printer with per-job state."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import re

from aiohttp import web

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CARD_FILENAME,
    CARD_URL_PREFIX,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_RELAXED_CIPHERS,
    CONF_USER,
    CONF_USE_TLS,
    CONF_VERIFY_TLS,
    DEFAULT_PORT,
    DEFAULT_USER,
    DOMAIN,
    MAX_UPLOAD_BYTES,
    PDF_MAGIC,
)
from .coordinator import JobCoordinator
from .printer import PrinterClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

_CARD_FILE = Path(__file__).parent / "static" / CARD_FILENAME

# Filename sanitiser for incoming uploads.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_pdf_filename(filename: str | None) -> str:
    if not filename:
        return "upload.pdf"
    name = Path(filename).name
    name = _UNSAFE.sub("-", name).strip("-._") or "upload.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name[:120]


def _card_url() -> str:
    digest = hashlib.sha256(_CARD_FILE.read_bytes()).hexdigest()[:12]
    return f"{CARD_URL_PREFIX}{digest}.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    client = PrinterClient(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        use_tls=data.get(CONF_USE_TLS, True),
        user=data.get(CONF_USER) or DEFAULT_USER,
        password=data.get(CONF_PASSWORD, ""),
        verify_tls=data.get(CONF_VERIFY_TLS, False),
        relaxed_ciphers=data.get(CONF_RELAXED_CIPHERS, False),
    )
    coordinator = JobCoordinator(hass, client)
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    hass.http.register_view(PrintView(client, coordinator))
    hass.http.register_view(CancelView(coordinator))
    _LOGGER.info(
        "%s: endpoints ready at /api/%s/{print,cancel} (printer=%s)",
        DOMAIN, DOMAIN, data[CONF_HOST],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Serve the upload card with a content-hash URL so browsers re-fetch
    # on every edit. Idempotent across reloads — register_static_paths
    # over the same path replaces the prior registration.
    card_url = _card_url()
    await hass.http.async_register_static_paths(
        [StaticPathConfig(card_url, str(_CARD_FILE), False)]
    )
    add_extra_js_url(hass, card_url)
    hass.data[DOMAIN][entry.entry_id]["card_url"] = card_url
    hass.async_create_task(_sync_lovelace_resource(hass, card_url))

    # Reload entry when options change.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _sync_lovelace_resource(hass: HomeAssistant, card_url: str) -> None:
    """Make the global lovelace resource collection match `card_url`.

    Drops any stale entries pointing at older card hashes so the OLD class
    can't register first and beat the new one's customElements.define race.
    """
    import asyncio
    for _ in range(60):
        coll = hass.data.get("lovelace_resources") or (
            hass.data.get("lovelace", {}).get("resources")
            if isinstance(hass.data.get("lovelace"), dict)
            else getattr(hass.data.get("lovelace"), "resources", None)
        )
        if coll is not None:
            break
        await asyncio.sleep(1)
    else:
        _LOGGER.warning("lovelace resources collection never appeared")
        return
    try:
        items = list(coll.async_items())
        current_id = None
        stale_ids: list[str] = []
        for item in items:
            url = item.get("url", "")
            if url == card_url:
                current_id = item.get("id")
            elif url.startswith(CARD_URL_PREFIX):
                stale_ids.append(item.get("id"))
        for sid in stale_ids:
            if sid:
                await coll.async_delete_item(sid)
                _LOGGER.info("reaped stale lovelace resource %s", sid)
        if current_id is None:
            await coll.async_create_item({"res_type": "module", "url": card_url})
            _LOGGER.info("registered %s in lovelace resources", card_url)
    except Exception:
        _LOGGER.exception("failed to sync lovelace resources")


class PrintView(HomeAssistantView):
    """POST /api/ipp_print/print

    Multipart/form-data with field 'file' = PDF. Validates magic bytes,
    submits via IPP Print-Job, returns {ok, filename, bytes, job_id, state}.
    """

    url = "/api/ipp_print/print"
    name = "api:ipp_print:print"
    requires_auth = True

    def __init__(
        self, client: PrinterClient, coordinator: JobCoordinator
    ) -> None:
        self._client = client
        self._coordinator = coordinator

    async def post(self, request: web.Request) -> web.Response:
        try:
            reader = await request.multipart()
        except Exception as exc:
            _LOGGER.warning("bad multipart body: %s", exc)
            return self.json_message("invalid multipart body", status_code=400)

        field = None
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "file":
                field = part
                break
        if field is None:
            return self.json_message("missing 'file' field", status_code=400)

        filename = _safe_pdf_filename(field.filename)

        buf = bytearray()
        while True:
            chunk = await field.read_chunk(64 * 1024)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > MAX_UPLOAD_BYTES:
                return self.json_message("too large", status_code=413)

        if buf[:5] != PDF_MAGIC:
            return self.json_message(
                "not a PDF (magic bytes mismatch)", status_code=415
            )

        body = bytes(buf)
        try:
            result = await self._client.print_job(
                job_name=filename,
                document_format="application/pdf",
                document=body,
            )
        except Exception as exc:
            _LOGGER.exception("IPP submission failed")
            return self.json_message(
                f"IPP submission failed: {exc}", status_code=502
            )

        if result.ipp_status not in (0x0000, 0x0001, 0x0002):
            return self.json_message(
                f"printer refused job (ipp_status=0x{result.ipp_status:04x})",
                status_code=502,
            )
        if result.job_id is None:
            return self.json_message(
                "printer did not return a job-id", status_code=502
            )

        self._coordinator.track(
            job_id=result.job_id,
            filename=filename,
            bytes_sent=len(body),
        )
        return self.json(
            {
                "ok": True,
                "filename": filename,
                "bytes": len(body),
                "job_id": result.job_id,
                "state": result.job_state_name,
            }
        )


class CancelView(HomeAssistantView):
    """POST /api/ipp_print/cancel  body: {"job_id": int}"""

    url = "/api/ipp_print/cancel"
    name = "api:ipp_print:cancel"
    requires_auth = True

    def __init__(self, coordinator: JobCoordinator) -> None:
        self._coordinator = coordinator

    async def post(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return self.json_message("invalid JSON", status_code=400)
        job_id = data.get("job_id") if isinstance(data, dict) else None
        if not isinstance(job_id, int):
            return self.json_message(
                "missing or invalid 'job_id'", status_code=400
            )
        ok = await self._coordinator.async_cancel(job_id)
        if not ok:
            return self.json_message("printer refused cancel", status_code=502)
        return self.json({"ok": True, "job_id": job_id})
