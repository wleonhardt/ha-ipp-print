"""IPP Print — direct document submission to a network printer with per-job state."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import re
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_COPIES,
    ATTR_DOCUMENT_FORMAT,
    ATTR_JOB_NAME,
    ATTR_PATH,
    ATTR_SIDES,
    CARD_FILENAME,
    CARD_URL_PREFIX,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PATH,
    CONF_PORT,
    CONF_RELAXED_CIPHERS,
    CONF_USER,
    CONF_USE_TLS,
    CONF_VERIFY_TLS,
    DEFAULT_PATH,
    DEFAULT_PORT,
    DEFAULT_USER,
    DOMAIN,
    FORMAT_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    SERVICE_PRINT_FILE,
    sniff_format,
)
from .coordinator import JobCoordinator
from .printer import SIDES, IppError, PrinterClient, PrinterInfo

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

_CARD_FILE = Path(__file__).parent / "static" / CARD_FILENAME

# The integration has no YAML configuration — everything is set up via the
# config flow — but hassfest still requires a schema declaration when
# async_setup is defined.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Filename sanitiser for incoming uploads.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

PRINT_FILE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PATH): cv.string,
        vol.Optional(ATTR_DOCUMENT_FORMAT): cv.string,
        vol.Optional(ATTR_JOB_NAME): cv.string,
        vol.Optional(ATTR_COPIES): vol.All(vol.Coerce(int), vol.Range(min=1, max=99)),
        vol.Optional(ATTR_SIDES): vol.In(SIDES),
    }
)


def _safe_filename(filename: str | None, fmt: str = "application/pdf") -> str:
    """Strip path components and unsafe characters; ensure an extension
    matching the document format."""
    ext = FORMAT_EXTENSIONS.get(fmt, "")
    fallback = f"upload{ext or '.bin'}"
    if not filename:
        return fallback
    name = Path(filename).name
    name = _UNSAFE.sub("-", name).strip("-._") or fallback
    if ext and not name.lower().endswith(tuple({ext, ".jpeg"} if ext == ".jpg" else {ext})):
        name = f"{name}{ext}"
    return name[:120]


def _card_url_sync() -> str:
    """Compute the content-hashed card URL. Reads card.js from disk;
    must be called from an executor, not the event loop."""
    digest = hashlib.sha256(_CARD_FILE.read_bytes()).hexdigest()[:12]
    return f"{CARD_URL_PREFIX}{digest}.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_FILE,
        _make_print_file_handler(hass),
        schema=PRINT_FILE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    client = PrinterClient(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        path=data.get(CONF_PATH, DEFAULT_PATH),
        use_tls=data.get(CONF_USE_TLS, True),
        user=data.get(CONF_USER) or DEFAULT_USER,
        password=data.get(CONF_PASSWORD, ""),
        verify_tls=data.get(CONF_VERIFY_TLS, False),
        relaxed_ciphers=data.get(CONF_RELAXED_CIPHERS, False),
    )
    coordinator = JobCoordinator(hass, client)

    # Identity + capabilities. A printer that is off right now must not
    # block setup (endpoints/service still work once it wakes), so failure
    # here only degrades device info and format checks until next reload.
    printer_info: PrinterInfo | None = None
    try:
        printer_info = await client.get_printer_attrs()
    except Exception as exc:
        _LOGGER.warning(
            "%s: Get-Printer-Attributes failed (%s); device details and "
            "format checks unavailable until the entry is reloaded",
            data[CONF_HOST], exc,
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "printer_info": printer_info,
    }

    # Views look up the live coordinator/client from hass.data on every
    # request so options-flow reloads (which build a new coordinator) take
    # effect without re-registering the URLs.
    if not hass.data[DOMAIN].get("_views_registered"):
        hass.http.register_view(PrintView(hass))
        hass.http.register_view(CancelView(hass))
        hass.data[DOMAIN]["_views_registered"] = True
    _LOGGER.info(
        "%s: endpoints ready at /api/%s/{print,cancel} (printer=%s)",
        DOMAIN, DOMAIN, data[CONF_HOST],
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Serve the upload card with a content-hash URL so browsers re-fetch
    # on every edit. Track which URLs we've already registered so reloads
    # (options change → async_reload) don't re-call register_static_paths
    # on the same URL — aiohttp rejects duplicate GET routes with
    # "Added route will never be executed". Old hash URLs stay registered
    # as orphans for the rest of the HA process lifetime; that's fine
    # since content-hash URLs are designed to be cache-invalidation keys.
    card_url = await hass.async_add_executor_job(_card_url_sync)
    registered = hass.data[DOMAIN].setdefault("_card_urls_registered", set())
    if card_url not in registered:
        # cache_headers=True: the URL embeds a content hash, so the browser
        # may cache forever — a changed card gets a brand-new URL.
        await hass.http.async_register_static_paths(
            [StaticPathConfig(card_url, str(_CARD_FILE), True)]
        )
        registered.add(card_url)
    hass.data[DOMAIN][entry.entry_id]["card_url"] = card_url
    hass.async_create_task(_sync_lovelace_resource(hass, card_url))

    # Reload entry when options change.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data:
            # Stop the poll task and release pooled printer connections so a
            # reload can't leave the old coordinator polling the old config.
            await data["coordinator"].async_shutdown()
            await data["client"].async_close()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _add_extra_js_once(hass: HomeAssistant, card_url: str) -> None:
    """Fallback card injection for setups without a writable resource store."""
    added = hass.data[DOMAIN].setdefault("_extra_js_urls", set())
    if card_url not in added:
        add_extra_js_url(hass, card_url)
        added.add(card_url)
        _LOGGER.info("card injected via extra_js_url: %s", card_url)


async def _sync_lovelace_resource(hass: HomeAssistant, card_url: str) -> None:
    """Make the global lovelace resource collection match `card_url`.

    Drops any stale entries pointing at older card hashes so the OLD class
    can't register first and beat the new one's customElements.define race.

    In YAML-resource mode (or if the storage collection is unavailable) the
    collection can't be edited; fall back to add_extra_js_url so the card
    still loads — on the next full page load.
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
        _LOGGER.warning(
            "lovelace resources collection never appeared; "
            "falling back to extra_js_url"
        )
        _add_extra_js_once(hass, card_url)
        return
    if not hasattr(coll, "async_create_item"):
        # YAML-mode dashboards: resources are read-only.
        _LOGGER.debug("lovelace resources read-only (YAML mode); using extra_js_url")
        _add_extra_js_once(hass, card_url)
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
        _LOGGER.exception(
            "failed to sync lovelace resources; falling back to extra_js_url"
        )
        _add_extra_js_once(hass, card_url)


def _live_entry(hass: HomeAssistant) -> dict | None:
    """Return the configured entry's client/coordinator dict, or None.

    The integration declares single_config_entry, so at most one real entry
    exists alongside the underscore-prefixed bookkeeping keys.
    """
    entries = hass.data.get(DOMAIN, {})
    for key, entry_data in entries.items():
        if key.startswith("_"):
            continue
        if "coordinator" in entry_data and "client" in entry_data:
            return entry_data
    return None


class SubmitError(Exception):
    """A submission was refused; carries an HTTP-ish status for the views."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


async def _submit(
    live: dict,
    *,
    filename: str,
    document: bytes | bytearray,
    document_format: str,
    copies: int | None = None,
    sides: str | None = None,
) -> dict[str, Any]:
    """Shared submit path for the HTTP view and the service.

    Checks the format/sides against the printer's advertised capabilities
    when known, sends Print-Job, and starts tracking the returned job-id.
    """
    client: PrinterClient = live["client"]
    coordinator: JobCoordinator = live["coordinator"]

    info: PrinterInfo | None = live.get("printer_info")
    if info is None:
        # Printer was off at setup; try once more now that someone wants it.
        try:
            info = live["printer_info"] = await client.get_printer_attrs()
        except Exception as exc:
            _LOGGER.debug("Get-Printer-Attributes still failing: %s", exc)
    if info is not None and info.formats and not info.supports_format(document_format):
        raise SubmitError(
            f"printer does not accept {document_format} "
            f"(supported: {', '.join(info.formats)})",
            415,
        )
    if sides and info is not None and info.sides and sides not in info.sides:
        raise SubmitError(
            f"printer does not support sides={sides} "
            f"(supported: {', '.join(info.sides)})",
            400,
        )

    try:
        result = await client.print_job(
            job_name=filename,
            document_format=document_format,
            document=document,
            copies=copies,
            sides=sides,
        )
    except IppError as exc:
        _LOGGER.warning("IPP submission failed: %s", exc)
        raise SubmitError(str(exc), 502) from exc
    except Exception as exc:
        _LOGGER.exception("IPP submission failed")
        raise SubmitError(
            f"IPP submission failed: {type(exc).__name__}: {str(exc)[:120]}",
            502,
        ) from exc

    if result.ipp_status not in (0x0000, 0x0001, 0x0002):
        raise SubmitError(
            f"printer refused job (ipp_status=0x{result.ipp_status:04x})", 502
        )
    if result.job_id is None:
        raise SubmitError("printer did not return a job-id", 502)

    coordinator.track(
        job_id=result.job_id, filename=filename, bytes_sent=len(document)
    )
    return {
        "ok": True,
        "filename": filename,
        "bytes": len(document),
        "job_id": result.job_id,
        "state": result.job_state_name,
    }


def _read_file_capped(path: str) -> bytes:
    """Executor helper: read a file, refusing anything over the upload cap."""
    p = Path(path)
    if p.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"{path} exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit"
        )
    return p.read_bytes()


def _make_print_file_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> ServiceResponse:
        live = _live_entry(hass)
        if live is None:
            raise ServiceValidationError("IPP Print is not configured")

        path = call.data[ATTR_PATH]
        if not await hass.async_add_executor_job(hass.config.is_allowed_path, path):
            raise ServiceValidationError(
                f"path is not allowed: {path} — place the file under "
                "www/ or a media dir, or add its directory to "
                "allowlist_external_dirs"
            )
        try:
            document = await hass.async_add_executor_job(_read_file_capped, path)
        except FileNotFoundError as exc:
            raise ServiceValidationError(f"file not found: {path}") from exc
        except (OSError, ValueError) as exc:
            raise ServiceValidationError(f"cannot read {path}: {exc}") from exc

        fmt = call.data.get(ATTR_DOCUMENT_FORMAT) or sniff_format(document)
        if not fmt:
            raise ServiceValidationError(
                f"cannot identify the document type of {path}; pass "
                f"{ATTR_DOCUMENT_FORMAT} explicitly (e.g. application/octet-stream)"
            )
        filename = _safe_filename(call.data.get(ATTR_JOB_NAME) or Path(path).name, fmt)

        try:
            job = await _submit(
                live,
                filename=filename,
                document=document,
                document_format=fmt,
                copies=call.data.get(ATTR_COPIES),
                sides=call.data.get(ATTR_SIDES),
            )
        except SubmitError as exc:
            raise HomeAssistantError(str(exc)) from exc
        return job if call.return_response else None

    return _handle


class PrintView(HomeAssistantView):
    """POST /api/ipp_print/print

    Multipart/form-data with field 'file' = PDF / JPEG / PNG. Identifies the
    format from content, submits via IPP Print-Job, returns
    {ok, filename, bytes, job_id, state}.
    """

    url = "/api/ipp_print/print"
    name = "api:ipp_print:print"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def post(self, request: web.Request) -> web.Response:
        # Refuse before touching the body so an unconfigured install doesn't
        # buffer a 50 MiB upload just to answer 503.
        live = _live_entry(self._hass)
        if live is None:
            return self.json_message("integration not configured", status_code=503)

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

        buf = bytearray()
        while True:
            chunk = await field.read_chunk(64 * 1024)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > MAX_UPLOAD_BYTES:
                return self.json_message("too large", status_code=413)

        fmt = sniff_format(buf)
        if fmt is None:
            return self.json_message(
                "unsupported file type (PDF, JPEG, or PNG)", status_code=415
            )
        filename = _safe_filename(field.filename, fmt)

        try:
            job = await _submit(
                live, filename=filename, document=buf, document_format=fmt
            )
        except SubmitError as exc:
            return self.json_message(str(exc), status_code=exc.status)
        return self.json(job)


class CancelView(HomeAssistantView):
    """POST /api/ipp_print/cancel  body: {"job_id": int}"""

    url = "/api/ipp_print/cancel"
    name = "api:ipp_print:cancel"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

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
        live = _live_entry(self._hass)
        if live is None:
            return self.json_message("integration not configured", status_code=503)
        coordinator = live["coordinator"]
        # Only jobs this integration submitted may be cancelled through HA —
        # not arbitrary printer-side job ids.
        if not coordinator.knows(job_id):
            return self.json_message("unknown job_id", status_code=404)
        ok = await coordinator.async_cancel(job_id)
        if not ok:
            return self.json_message("printer refused cancel", status_code=502)
        return self.json({"ok": True, "job_id": job_id})
