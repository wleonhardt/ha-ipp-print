"""IPP Print — direct document submission to a network printer with per-job state."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
import re
import stat
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_extract_config_entry_ids
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
from .capability_cache import CapabilityCache
from .capabilities import capability_snapshot, validate_copies
from .connection import DeviceConnection
from .coordinator import JobCoordinator
from .printer import SIDES, IppError, IppHttpError, PrinterClient, media_dimensions

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]

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
        vol.Optional(ATTR_COPIES): validate_copies,
        vol.Optional(ATTR_SIDES): vol.In(SIDES),
        vol.Optional("media"): vol.All(str, vol.Length(min=1, max=255)),
        vol.Optional("color_mode"): vol.All(str, vol.Length(min=1, max=64)),
        vol.Optional("quality"): vol.All(validate_copies, vol.In([3, 4, 5])),
        vol.Optional("media_source"): vol.All(str, vol.Length(min=1, max=255)),
    }
).extend(cv.TARGET_SERVICE_FIELDS)


def _safe_filename(filename: str | None, fmt: str = "application/pdf") -> str:
    """Strip path components and unsafe characters; ensure an extension
    matching the document format."""
    ext = FORMAT_EXTENSIONS.get(fmt, "")
    fallback = f"upload{ext or '.bin'}"
    if not filename:
        return fallback
    name = Path(filename.replace("\\", "/")).name
    name = _UNSAFE.sub("-", name).strip("-._") or fallback
    if ext and not name.lower().endswith(tuple({ext, ".jpeg"} if ext == ".jpg" else {ext})):
        name = f"{name}{ext}"
    suffix = Path(name).suffix if ext else ""
    return name[:-len(suffix)][:120 - len(suffix)] + suffix if suffix else name[:120]


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
    coordinator = JobCoordinator(hass, client, entry.entry_id)
    connection = DeviceConnection(hass, client.get_connection_status, DOMAIN)
    capability_cache = CapabilityCache(lambda: client.get_printer_attrs())
    platform_setup_started = False

    try:
        # Setup remains usable while the printer is asleep/offline.
        printer_info = await capability_cache.async_get()
        if printer_info is None:
            _LOGGER.warning("Printer capabilities unavailable; will retry on demand")

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "client": client,
            "coordinator": coordinator,
            "connection": connection,
            "printer_info": printer_info,
            "capability_cache": capability_cache,
        }

        # Views look up the live coordinator/client from hass.data on every
        # request so options-flow reloads (which build a new coordinator) take
        # effect without re-registering the URLs.
        if not hass.data[DOMAIN].get("_views_registered"):
            hass.http.register_view(PrintView(hass))
            hass.http.register_view(CancelView(hass))
            hass.http.register_view(CapabilitiesView(hass))
            hass.data[DOMAIN]["_views_registered"] = True
        _LOGGER.info(
            "%s: endpoints ready at /api/%s/{print,cancel} (printer=%s)",
            DOMAIN, DOMAIN, data[CONF_HOST],
        )

        # Serve the upload card with a content-hash URL so browsers re-fetch
        # on every edit. Track which URLs we've already registered so reloads
        # (options change → async_reload) don't re-call register_static_paths
        # on the same URL — aiohttp rejects duplicate GET routes with
        # "Added route will never be executed". Old hash URLs stay registered
        # as orphans for the rest of the HA process lifetime; that's fine
        # since content-hash URLs are designed to be cache-invalidation keys.
        card_url = await hass.async_add_executor_job(_card_url_sync)
        registered = hass.data[DOMAIN].setdefault("_card_urls_registered", set())
        async with hass.data[DOMAIN].setdefault("_card_registration_lock", asyncio.Lock()):
            if card_url not in registered:
                # cache_headers=True: the URL embeds a content hash, so the browser
                # may cache forever — a changed card gets a brand-new URL.
                await hass.http.async_register_static_paths(
                    [StaticPathConfig(card_url, str(_CARD_FILE), True)]
                )
                registered.add(card_url)
        hass.data[DOMAIN][entry.entry_id]["card_url"] = card_url
        platform_setup_started = True
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        hass.async_create_background_task(
            _sync_lovelace_resource(hass, card_url), name="ipp_print resource sync"
        )

        async def _stop(_event) -> None:
            await connection.async_close()
            await capability_cache.async_close()
            await coordinator.async_shutdown()
            await client.async_close()

        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop))

        # Reload entry when options change.
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        connection.start()
        return True

    except BaseException:
        if platform_setup_started:
            try:
                await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
            except Exception:
                _LOGGER.exception("failed to clean up platforms after setup failure")
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        await connection.async_close()
        await capability_cache.async_close()
        await coordinator.async_shutdown()
        await client.async_close()
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id, None)
        if data:
            # Stop the poll task and release pooled printer connections so a
            # reload can't leave the old coordinator polling the old config.
            if connection := data.get("connection"):
                await connection.async_close()
            await data["capability_cache"].async_close()
            for cache in list(data.get("format_caches", {}).values()):
                await cache.async_close()
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
    async with hass.data[DOMAIN].setdefault("_resource_sync_lock", asyncio.Lock()):
        try:
            if not getattr(coll, "loaded", True):
                await coll.async_load()
                coll.loaded = True
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


def _live_entries(hass: HomeAssistant) -> dict[str, dict]:
    """entry_id → client/coordinator dict for every loaded printer.

    hass.data[DOMAIN] also holds underscore-prefixed bookkeeping keys.
    """
    return {
        key: entry_data
        for key, entry_data in hass.data.get(DOMAIN, {}).items()
        if not key.startswith("_") and "coordinator" in entry_data
    }


class SubmitError(Exception):
    """A submission was refused; carries an HTTP-ish status for the views."""

    def __init__(self, message: str, status: int, *, job_may_exist: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.job_may_exist = job_may_exist


def _pick_entry(hass: HomeAssistant, entry_ids: set[str] | None) -> dict | None:
    """Choose the printer to act on.

    `entry_ids` is the set the caller targeted (None = no target given).
    With no target, the single configured printer is used; with several
    configured a target is required. Returns None when nothing is loaded.
    """
    live = _live_entries(hass)
    if not live:
        return None
    if entry_ids is None:
        if len(live) == 1:
            return next(iter(live.values()))
        raise SubmitError(
            "several printers are configured; pass entity_id to pick one", 400
        )
    hits = [live[eid] for eid in entry_ids if eid in live]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SubmitError("target is not a loaded IPP Print printer", 404)
    raise SubmitError("target matches more than one printer", 400)


def _entry_for_entity(hass: HomeAssistant, entity_id: str | None) -> dict | None:
    """Resolve an optional job-sensor entity_id (views) to its printer."""
    if not entity_id:
        return _pick_entry(hass, None)
    reg_entry = er.async_get(hass).async_get(entity_id)
    if reg_entry is None or reg_entry.platform != DOMAIN:
        raise SubmitError(f"{entity_id} is not an IPP Print entity", 404)
    return _pick_entry(hass, {reg_entry.config_entry_id})


async def _format_cache(live: dict, document_format: str) -> CapabilityCache:
    caches = live.setdefault("format_caches", {})
    old = None
    if document_format not in caches:
        if len(caches) >= 8:
            old = caches.pop(next(iter(caches)))
        caches[document_format] = CapabilityCache(
            lambda: live["client"].get_printer_attrs(document_format, fresh=True))
    cache = caches[document_format]
    if old is not None:
        await old.async_close()
    return cache


async def _submit(
    live: dict,
    *,
    filename: str,
    document: bytes | bytearray,
    document_format: str,
    copies: int | None = None,
    sides: str | None = None,
    media: str | None = None,
    color_mode: str | None = None,
    quality: int | None = None,
    media_source: str | None = None,
) -> dict[str, Any]:
    """Shared submit path for the HTTP view and the service.

    Checks the format/sides against the printer's advertised capabilities
    when known, sends Print-Job, and starts tracking the returned job-id.
    """
    client: PrinterClient = live["client"]
    coordinator: JobCoordinator = live["coordinator"]

    # Validate here as well as at HTTP/service boundaries: every caller shares
    # the same strict options contract before a device probe or submission.
    if copies is not None:
        try:
            copies = validate_copies(copies)
        except vol.Invalid as exc:
            raise SubmitError(str(exc), 400) from exc
    if sides is not None and sides not in SIDES:
        raise SubmitError("invalid sides", 400)
    cache = live["capability_cache"]
    info = live["printer_info"] = await cache.async_get()
    if cache.closed:
        raise SubmitError("printer integration unloaded; no job submitted", 503)
    explicit = copies is not None or sides is not None or media or media_source or color_mode or quality is not None
    if explicit:
        format_cache = await _format_cache(live, document_format)
        info = live["printer_info"] = await format_cache.async_get(fresh=True)
        if format_cache.metadata()["status"] != "fresh" or format_cache.closed:
            raise SubmitError(
                "cannot read the printer's current format and paper settings; "
                "check its connection. No print job was submitted", 502,
            )
    if cache.closed:
        raise SubmitError("printer integration unloaded; no job submitted", 503)
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
    if copies is not None and info is not None and info.copies_max is not None:
        if copies > info.copies_max:
            raise SubmitError(f"printer supports at most {info.copies_max} copies", 400)
    if media is not None and (not isinstance(media, str) or not info
                              or media not in info.media_supported):
        raise SubmitError("selected paper size is not advertised by this printer", 400)
    if color_mode is not None and (not isinstance(color_mode, str) or not info
                                   or color_mode not in info.color_modes):
        raise SubmitError("selected color mode is not advertised by this printer", 400)
    if quality is not None and (type(quality) is not int or not info or quality not in info.qualities):
        raise SubmitError("selected print quality is not advertised by this printer", 400)
    if media_source is not None and (not isinstance(media_source, str) or not info
                                    or media_source not in info.media_sources):
        raise SubmitError("selected tray is not advertised by this printer", 400)
    if media_source and info and info.media_col_members and "media-source" not in info.media_col_members:
        raise SubmitError("this printer does not support selecting a tray with media-col", 400)
    effective_media = media if media is not None else (
        info.media_default if (sides or media_source) and info is not None else None)
    if (media_source and effective_media and media_dimensions(effective_media) is None
            and info and info.media_col_members and "media-size-name" not in info.media_col_members):
        raise SubmitError("this paper name cannot be combined with a tray; use the default tray", 400)
    options = dict(copies=copies, sides=sides, media=effective_media)
    if media_source is not None:
        options["media_source"] = media_source
    if color_mode is not None:
        options["color_mode"] = color_mode
    if quality is not None:
        options["quality"] = quality
    validation_warning = None
    if explicit:
        try:
            validation_warning = await client.validate_job(document_format=document_format, **options)
        except Exception as exc:
            raise SubmitError(f"{exc}. No print job was submitted", 400) from exc

    try:
        result = await client.print_job(
            job_name=filename,
            document_format=document_format,
            document=document,
            # Some HP firmware rejects duplex when media is implicit even
            # though media-default is loaded and sides-supported lists it.
            **options,
        )
    except IppError as exc:
        _LOGGER.warning("IPP submission failed: %s", exc)
        detail = str(exc)
        if not isinstance(exc, IppHttpError):
            detail += "; the printer may have accepted the job; check its queue before retrying"
        raise SubmitError(detail, 502, job_may_exist=True) from exc
    except Exception as exc:
        _LOGGER.exception("IPP submission failed")
        raise SubmitError(
            f"IPP submission failed: {type(exc).__name__}: {str(exc)[:120]}; "
            "the printer may have accepted the job; check its queue before retrying",
            502, job_may_exist=True,
        ) from exc

    if result.ipp_status not in (0x0000, 0x0001, 0x0002):
        if result.ipp_status == 0x040B:
            raise SubmitError(
                "printer refused the requested print settings; check copies, "
                "sides and the printer's default paper size "
                "(ipp_status=0x040b)", 502,
            )
        raise SubmitError(
            f"printer refused job (ipp_status=0x{result.ipp_status:04x})", 502
        )
    if result.job_id is None:
        raise SubmitError(
            "printer did not return a job-id; the job may have printed; "
            "check its queue before retrying", 502, job_may_exist=True
        )

    try:
        tracked = coordinator.track(
            job_id=result.job_id, filename=filename, bytes_sent=len(document),
            warning=result.warning or validation_warning,
            requested_settings={key: value for key, value in options.items() if value is not None},
        )
    except RuntimeError as exc:
        raise SubmitError(
            "printer unloaded during submission; the job may have printed", 503, job_may_exist=True
        ) from exc
    return {
        "ok": True,
        "filename": filename,
        "bytes": len(document),
        "job_id": result.job_id,
        "submitted_at": tracked.submitted_at.isoformat(),
        "state": result.job_state_name,
        "warning": result.warning or validation_warning,
        "unsupported_attributes": list(result.unsupported_attributes),
    }


def _read_file_capped(path: str) -> bytes:
    """Executor helper: read a file, refusing anything over the upload cap."""
    p = Path(path)
    file_stat = p.stat()
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError(f"{path} is not a regular file")
    if file_stat.st_size > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"{path} exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB limit"
        )
    with p.open("rb") as handle:
        document = handle.read(MAX_UPLOAD_BYTES + 1)
    if len(document) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{path} exceeds the upload limit")
    return document


def _make_print_file_handler(hass: HomeAssistant):
    async def _handle(call: ServiceCall) -> ServiceResponse:
        targeted = any(k in call.data for k in cv.TARGET_SERVICE_FIELDS)
        try:
            live = _pick_entry(
                hass,
                await async_extract_config_entry_ids(call) if targeted else None,
            )
        except SubmitError as exc:
            raise ServiceValidationError(str(exc)) from exc
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
                media=call.data.get("media"), color_mode=call.data.get("color_mode"),
                quality=call.data.get("quality"), media_source=call.data.get("media_source"),
            )
        except SubmitError as exc:
            raise HomeAssistantError(str(exc)) from exc
        return job if call.return_response else None

    return _handle


class PrintView(HomeAssistantView):
    """POST /api/ipp_print/print

    Multipart/form-data with field 'file' = PDF / JPEG / PNG and, when more
    than one printer is configured, 'entity_id' = that printer's job sensor.
    Identifies the format from content, submits via IPP Print-Job, returns
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
        if not _live_entries(self._hass):
            return self.json_message("integration not configured", status_code=503)

        try:
            reader = await request.multipart()
        except Exception as exc:
            _LOGGER.warning("bad multipart body: %s", exc)
            return self.json_message("invalid multipart body", status_code=400)

        filename_raw: str | None = None
        entity_id: str | None = None
        copies: int | None = None
        sides: str | None = None
        options: dict = {}
        seen: set[str] = set()
        buf = bytearray()
        try:
            while (part := await reader.next()) is not None:
                if part.name not in ("entity_id", "file", "copies", "sides", "media", "color_mode", "quality", "media_source"):
                    raise SubmitError("unexpected multipart field", 400)
                if part.name in seen:
                    raise SubmitError(f"duplicate '{part.name}' field", 400)
                seen.add(part.name)
                if part.name == "file":
                    filename_raw = part.filename
                    target = buf
                    limit = MAX_UPLOAD_BYTES
                else:
                    target = bytearray()
                    limit = 512
                while chunk := await part.read_chunk(64 * 1024):
                    if len(target) + len(chunk) > limit:
                        raise SubmitError("too large", 413)
                    target.extend(chunk)
                if part.name == "entity_id":
                    entity_id = target.decode("utf-8").strip() or None
                elif part.name == "copies":
                    try:
                        copies = validate_copies(target.decode("utf-8"))
                    except vol.Invalid as exc:
                        raise SubmitError(str(exc), 400) from exc
                elif part.name == "sides":
                    sides = target.decode("utf-8")
                    if sides not in SIDES:
                        raise SubmitError("invalid sides", 400)
                elif part.name in ("media", "color_mode", "quality", "media_source"):
                    value = target.decode("utf-8")
                    if part.name == "quality":
                        if value not in ("3", "4", "5"):
                            raise SubmitError("quality must be 3, 4 or 5", 400)
                        value = int(value)
                    options[part.name] = value
        except SubmitError as exc:
            return self.json_message(str(exc), status_code=exc.status)
        except Exception as exc:
            _LOGGER.warning("bad multipart body: %s", exc)
            return self.json_message("invalid multipart body", status_code=400)
        if "file" not in seen:
            return self.json_message("missing 'file' field", status_code=400)

        try:
            live = _entry_for_entity(self._hass, entity_id)
        except SubmitError as exc:
            return self.json_message(str(exc), status_code=exc.status)
        if live is None:
            return self.json_message("integration not configured", status_code=503)

        fmt = sniff_format(buf)
        if fmt is None:
            return self.json_message(
                "unsupported file type (PDF, JPEG, or PNG)", status_code=415
            )
        filename = _safe_filename(filename_raw, fmt)

        try:
            job = await _submit(
                live, filename=filename, document=buf, document_format=fmt,
                copies=copies, sides=sides, **options,
            )
        except SubmitError as exc:
            return self.json({"message": str(exc), "job_may_exist": exc.job_may_exist},
                             status_code=exc.status)
        return self.json(job)


class CapabilitiesView(HomeAssistantView):
    """Authenticated, entity-scoped options for dashboard users; no job required."""

    url = "/api/ipp_print/capabilities"
    name = "api:ipp_print:capabilities"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request) -> web.Response:
        if (set(request.query) - {"entity_id", "document_format"}
                or any(len(request.query.getall(key, [])) > 1
                       for key in ("entity_id", "document_format"))):
            return self.json_message("invalid capability query", status_code=400)
        fmt = request.query.get("document_format")
        if fmt is not None and fmt not in ("application/pdf", "image/jpeg", "image/png"):
            return self.json_message("unsupported capability document format", status_code=400)
        entity_id = request.query.get("entity_id")
        if entity_id is not None and not entity_id.startswith("sensor."):
            return self.json_message("target is not an IPP Print sensor", status_code=404)
        try:
            live = _entry_for_entity(self._hass, entity_id)
        except SubmitError as exc:
            return self.json_message(str(exc), status_code=exc.status)
        if live is None:
            return self.json_message("integration not configured", status_code=503)
        cache = live["capability_cache"]
        if cache.closed:
            return self.json_message("integration unloaded", status_code=503)
        if fmt:
            cache = await _format_cache(live, fmt)
        live["printer_info"] = await cache.async_get()
        if cache.closed:
            return self.json_message("integration unloaded", status_code=503)
        if not entity_id:
            entry_id = next(key for key, data in _live_entries(self._hass).items() if data is live)
            entity_id = next((entry.entity_id for entry in er.async_entries_for_config_entry(
                er.async_get(self._hass), entry_id
            ) if entry.domain == "sensor"), None)
        return self.json(capability_snapshot(cache, entity_id))


class CancelView(HomeAssistantView):
    """POST /api/ipp_print/cancel  body: {"job_id": int, "entity_id"?: str}

    entity_id (the printer's job sensor) is required once more than one
    printer is configured — job ids are only unique per printer.
    """

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
        if type(job_id) is not int or not 1 <= job_id <= 2**31 - 1:
            return self.json_message(
                "missing or invalid 'job_id'", status_code=400
            )
        submitted_at = data.get("submitted_at")
        if submitted_at is not None and (not isinstance(submitted_at, str) or not 1 <= len(submitted_at) <= 64):
            return self.json_message("invalid submitted_at", status_code=400)
        entity_id = data.get("entity_id")
        if entity_id is not None and not isinstance(entity_id, str):
            return self.json_message("invalid 'entity_id'", status_code=400)
        try:
            live = _entry_for_entity(self._hass, entity_id)
        except SubmitError as exc:
            return self.json_message(str(exc), status_code=exc.status)
        if live is None:
            return self.json_message("integration not configured", status_code=503)
        coordinator = live["coordinator"]
        # Only jobs this integration submitted may be cancelled through HA —
        # not arbitrary printer-side job ids.
        if not coordinator.knows(job_id):
            return self.json_message("unknown job_id", status_code=404)
        ok = await coordinator.async_cancel(job_id, submitted_at=submitted_at) if submitted_at is not None else await coordinator.async_cancel(job_id)
        if not ok:
            return self.json_message("printer refused cancel", status_code=502)
        return self.json({"ok": True, "job_id": job_id})
