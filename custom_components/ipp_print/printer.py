"""Minimal IPP/2.0 client.

Self-contained binary-wire-format builder + parser. Only the surface we need
is implemented:
    * Print-Job              (0x0002) — submit a document, returns job-id
    * Get-Job-Attributes     (0x0009) — read state/progress of one job
    * Cancel-Job             (0x0008) — cancel by job-id
    * Get-Printer-Attributes (0x000B) — identity + capabilities probe

We don't depend on `pyipp` because its public API is read-only (printer
attributes) and Print-Job requires the document body inline after the
attribute groups — handcrafted bytes are simpler than monkey-patching.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import partial
import logging
import ssl

import aiohttp

from .ipp_codec import LocalizedText, decode_response

_LOGGER = logging.getLogger(__name__)

# IPP status: client-error-not-found — the printer no longer knows the job.
STATUS_NOT_FOUND = 0x0406

# Print-Job needs to cover the whole document upload on slow links/printers;
# status polls should fail fast.
PRINT_TIMEOUT = 300.0
POLL_TIMEOUT = 10.0
MAX_RESPONSE_BYTES = 1024 * 1024
DOCUMENT_CHUNK_BYTES = 64 * 1024


class _IppDocumentPayload(aiohttp.payload.Payload):
    """Sized IPP header + document, without copying the whole document."""

    def __init__(self, header: bytes, document: bytes | bytearray) -> None:
        super().__init__(document, content_type="application/ipp")
        self._header = header
        self._document = memoryview(document)
        self._size = len(header) + len(document)

    def decode(self, encoding: str = "utf-8", errors: str = "strict") -> str:
        raise TypeError("IPP document payload is binary")

    async def write(self, writer) -> None:
        await writer.write(self._header)
        for offset in range(0, len(self._document), DOCUMENT_CHUNK_BYTES):
            await writer.write(self._document[offset:offset + DOCUMENT_CHUNK_BYTES])


class IppError(Exception):
    """Base for printer communication errors."""


class IppHttpError(IppError):
    """Printer answered with a non-200 HTTP status."""

    def __init__(self, status: int) -> None:
        self.status = status
        detail = (
            "authentication failed (check user/password)"
            if status in (401, 403)
            else f"HTTP {status}"
        )
        super().__init__(f"printer rejected request: {detail}")


class JobGoneError(IppError):
    """Get-Job-Attributes: printer reports the job no longer exists."""

# IPP value tags we read/write. Full list in RFC 8011 §5.5.
TAG_END_ATTRS = 0x03
TAG_OPERATION_ATTRS = 0x01
TAG_JOB_ATTRS = 0x02
TAG_INTEGER = 0x21
TAG_BOOLEAN = 0x22
TAG_ENUM = 0x23
TAG_RANGE_OF_INTEGER = 0x33
TAG_NAME_WITHOUT_LANG = 0x42
TAG_KEYWORD = 0x44
TAG_URI = 0x45
TAG_CHARSET = 0x47
TAG_NATURAL_LANGUAGE = 0x48
TAG_MIME_MEDIA_TYPE = 0x49

# Operations.
OP_PRINT_JOB = 0x0002
OP_VALIDATE_JOB = 0x0004
OP_CANCEL_JOB = 0x0008
OP_GET_JOB_ATTRS = 0x0009
OP_GET_PRINTER_ATTRS = 0x000B

DEFAULT_PATH = "/ipp/print"

# Values for the `sides` job-template attribute (RFC 8011 §5.2.8).
SIDES = ("one-sided", "two-sided-long-edge", "two-sided-short-edge")

# What we ask the printer for in the probe. Kept small: some firmware
# chokes on large requested-attributes lists.
PRINTER_ATTRS_REQUESTED = (
    b"printer-name",
    b"printer-info",
    b"printer-location",
    b"printer-make-and-model",
    b"printer-uuid",
    b"document-format-supported",
    b"sides-supported",
    b"copies-supported",
    b"media-default",
    b"operations-supported",
    b"ipp-versions-supported",
)
OPTION_ATTRS_REQUESTED = (
    # Never request media-col-database during routine reads. Real HP firmware
    # expands it into ~938 KiB of combinations; even a small name list can
    # exhaust a response/time budget. Source keywords + Validate-Job suffice.
    b"media-supported", b"media-ready", b"media-col-default", b"media-source-supported",
    b"media-col-supported",
    b"print-color-mode-supported", b"print-quality-supported",
    b"print-color-mode-default", b"print-quality-default", b"sides-default", b"copies-default",
)

# IPP job-state enum values (RFC 8011 §5.3.7).
JOB_STATE_NAMES = {
    3: "pending",
    4: "pending-held",
    5: "processing",
    6: "processing-stopped",
    7: "canceled",
    8: "aborted",
    9: "completed",
}
TERMINAL_JOB_STATES = {7, 8, 9}


@dataclass
class JobSubmissionResult:
    """Outcome of a Print-Job request."""

    ipp_status: int  # 0x0000 = successful-ok
    job_id: int | None
    job_state: int | None
    job_state_name: str | None
    raw: bytes  # full response for diagnostics
    warning: str | None = None
    unsupported_attributes: tuple[str, ...] = ()


@dataclass
class PrinterInfo:
    """Identity + capabilities from Get-Printer-Attributes."""

    name: str | None
    info: str | None
    location: str | None
    make_and_model: str | None
    uuid: str | None  # "urn:uuid:..." as the printer reports it
    formats: list[str]  # document-format-supported
    sides: list[str]  # sides-supported
    copies_max: int | None  # upper bound of copies-supported
    media_default: str | None = None  # explicit default for duplex firmware compatibility
    media_supported: list[str] = field(default_factory=list)
    media_ready: list[str] | None = None
    media_sources: list[str] = field(default_factory=list)
    media_col_members: list[str] = field(default_factory=list)
    color_modes: list[str] = field(default_factory=list)
    qualities: list[int] = field(default_factory=list)
    operations: list[int] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    document_format: str | None = None
    defaults: dict = field(default_factory=dict)
    media_collections: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "info": self.info,
            "location": self.location,
            "make_and_model": self.make_and_model,
            "uuid": self.uuid,
            "formats": list(self.formats),
            "sides": list(self.sides),
            "copies_max": self.copies_max,
            "media_default": self.media_default,
            "auto_sensing": self.auto_sensing,
            "media_supported": self.media_supported,
            "media_ready": self.media_ready,
            "media_sources": self.media_sources,
            "media_col_members": self.media_col_members,
            "color_modes": self.color_modes,
            "qualities": self.qualities,
            "operations": self.operations,
            "versions": self.versions,
            "document_format": self.document_format,
            "defaults": self.defaults,
        }

    def supports_format(self, fmt: str) -> bool:
        """Only an explicit advertised MIME type establishes support."""
        return fmt in self.formats

    @property
    def auto_sensing(self) -> bool:
        return "application/octet-stream" in self.formats


@dataclass
class JobAttributes:
    """Subset of attributes returned by Get-Job-Attributes."""

    job_id: int
    job_state: int
    job_state_name: str
    job_state_reasons: str | None
    impressions_completed: int | None
    media_sheets_completed: int | None
    impressions_total: int | None  # often unknown until print starts
    job_name: str | None


def _attr(tag: int, name: bytes, value: bytes) -> bytes:
    return (
        tag.to_bytes(1, "big")
        + len(name).to_bytes(2, "big")
        + name
        + len(value).to_bytes(2, "big")
        + value
    )


def _int_value(n: int) -> bytes:
    return n.to_bytes(4, "big", signed=True)


def _header(op: int, request_id: int = 1) -> bytes:
    # version 2.0, operation, request-id
    return b"\x02\x00" + op.to_bytes(2, "big") + request_id.to_bytes(4, "big")


def _operation_group(
    *, printer_uri: str, user: str, extra: bytes = b""
) -> bytes:
    return (
        TAG_OPERATION_ATTRS.to_bytes(1, "big")
        + _attr(TAG_CHARSET, b"attributes-charset", b"utf-8")
        + _attr(TAG_NATURAL_LANGUAGE, b"attributes-natural-language", b"en")
        + _attr(TAG_URI, b"printer-uri", printer_uri.encode())
        + _attr(TAG_NAME_WITHOUT_LANG, b"requesting-user-name", user.encode())
        + extra
    )


def media_dimensions(media: str | None) -> tuple[int, int] | None:
    """PWG self-describing media keyword to hundredths of a millimeter."""
    match = re.search(r"_([0-9]+(?:\.[0-9]+)?)x([0-9]+(?:\.[0-9]+)?)(in|mm)$", media or "")
    if match is None:
        return None
    factor = 2540 if match[3] == "in" else 100
    dimensions = tuple(int(Decimal(value) * factor) for value in match.group(1, 2))
    return dimensions if all(1 <= value <= 2**31 - 1 for value in dimensions) else None


def build_print_job(
    *,
    printer_uri: str,
    user: str,
    job_name: str,
    document_format: str,
    document: bytes | bytearray,
    copies: int | None = None,
    sides: str | None = None,
    media: str | None = None,
    color_mode: str | None = None,
    media_source: str | None = None,
    quality: int | None = None,
) -> bytes:
    # Truncate at a codepoint boundary — a raw byte-slice can split UTF-8.
    job_name_bytes = job_name.encode()[:255].decode("utf-8", "ignore").encode()
    op_attrs = _operation_group(
        printer_uri=printer_uri,
        user=user,
        extra=(
            _attr(TAG_NAME_WITHOUT_LANG, b"job-name", job_name_bytes)
            + _attr(
                TAG_MIME_MEDIA_TYPE, b"document-format", document_format.encode()
            )
            # Explicit settings must not silently fall back to simplex or
            # another copy count. Without fidelity, IPP permits substitution.
            + (_attr(TAG_BOOLEAN, b"ipp-attribute-fidelity", b"\x01")
               if copies is not None or sides or media or color_mode or media_source or quality else b"")
        ),
    )
    # Job-template attributes live in their own group (RFC 8011 §4.2.1).
    job_attrs = b""
    if copies is not None:
        job_attrs += _attr(TAG_INTEGER, b"copies", _int_value(copies))
    if sides:
        job_attrs += _attr(TAG_KEYWORD, b"sides", sides.encode())
    if media_source:
        # RFC 8011/PWG media-col: a source and optional size name belong in
        # the same collection. Do not send conflicting media and media-col.
        members = _attr(0x4A, b"", b"media-source") + _attr(TAG_KEYWORD, b"", media_source.encode())
        if dimensions := media_dimensions(media):
            # media-size is broadly supported; HP rejects media-size-name
            # even for an advertised paper keyword (live Validate-Job evidence).
            members += _attr(0x4A, b"", b"media-size") + _attr(0x34, b"", b"")
            for name, value in zip((b"x-dimension", b"y-dimension"), dimensions):
                members += _attr(0x4A, b"", name) + _attr(TAG_INTEGER, b"", _int_value(value))
            members += _attr(0x37, b"", b"")
        elif media:
            members += _attr(0x4A, b"", b"media-size-name") + _attr(TAG_KEYWORD, b"", media.encode())
        job_attrs += _attr(0x34, b"media-col", b"") + members + _attr(0x37, b"", b"")
    elif media:
        job_attrs += _attr(TAG_KEYWORD, b"media", media.encode())
    if color_mode:
        job_attrs += _attr(TAG_KEYWORD, b"print-color-mode", color_mode.encode())
    if quality is not None:
        job_attrs += _attr(TAG_ENUM, b"print-quality", _int_value(quality))
    if job_attrs:
        job_attrs = bytes([TAG_JOB_ATTRS]) + job_attrs
    return (
        _header(OP_PRINT_JOB) + op_attrs + job_attrs
        + bytes([TAG_END_ATTRS]) + document
    )


def build_get_printer_attrs(
    *, printer_uri: str, user: str, requested: tuple[bytes, ...] = PRINTER_ATTRS_REQUESTED,
    document_format: str | None = None,
) -> bytes:
    # 1setOf keyword: first value carries the name, the rest have an empty
    # name and inherit it.
    extra = b"".join(
        _attr(TAG_KEYWORD, b"requested-attributes" if i == 0 else b"", kw)
        for i, kw in enumerate(requested)
    )
    if document_format:
        extra += _attr(TAG_MIME_MEDIA_TYPE, b"document-format", document_format.encode())
    op_attrs = _operation_group(printer_uri=printer_uri, user=user, extra=extra)
    return _header(OP_GET_PRINTER_ATTRS) + op_attrs + bytes([TAG_END_ATTRS])


def build_get_job_attrs(
    *, printer_uri: str, user: str, job_id: int
) -> bytes:
    extra = _attr(TAG_INTEGER, b"job-id", _int_value(job_id))
    op_attrs = _operation_group(printer_uri=printer_uri, user=user, extra=extra)
    return _header(OP_GET_JOB_ATTRS) + op_attrs + bytes([TAG_END_ATTRS])


def build_cancel_job(
    *, printer_uri: str, user: str, job_id: int
) -> bytes:
    extra = _attr(TAG_INTEGER, b"job-id", _int_value(job_id))
    op_attrs = _operation_group(printer_uri=printer_uri, user=user, extra=extra)
    return _header(OP_CANCEL_JOB) + op_attrs + bytes([TAG_END_ATTRS])


def parse_response(data: bytes) -> tuple[int, dict[str, list]]:
    """Compatibility accessor; typed groups remain available in decode_response."""
    response = decode_response(data)
    return response.status, response.attributes()


def parse_print_job_response(data: bytes) -> JobSubmissionResult:
    response = decode_response(data)
    status, attrs = response.status, response.attributes((1, 2))
    unsupported = tuple(response.attributes((5,)))[:32]
    warning = {
        1: "The printer accepted the job but ignored or changed some settings.",
        2: "The printer accepted the job after resolving conflicting settings.",
    }.get(status)
    job_id = attrs.get("job-id", [None])[0]
    job_state = attrs.get("job-state", [None])[0]
    return JobSubmissionResult(
        ipp_status=status,
        job_id=job_id if type(job_id) is int and job_id > 0 else None,
        job_state=int(job_state) if isinstance(job_state, int) else None,
        job_state_name=(
            JOB_STATE_NAMES.get(int(job_state))
            if isinstance(job_state, int)
            else None
        ),
        raw=data,
        warning=warning,
        unsupported_attributes=unsupported,
    )


def parse_job_attrs_response(data: bytes) -> JobAttributes | None:
    """Parse a Get-Job-Attributes response.

    Raises JobGoneError when the printer explicitly reports the job as
    unknown (purged after completion/cancel). Returns None when the response
    parsed but lacks usable job attributes — callers should treat that as a
    transient glitch, not a terminal state.
    """
    status, attrs = parse_response(data)
    if status == STATUS_NOT_FOUND:
        raise JobGoneError(f"job not found (ipp_status=0x{status:04x})")
    if status not in (0x0000, 0x0001, 0x0002):
        raise IppError(f"Get-Job-Attributes failed (ipp_status=0x{status:04x})")
    job_id = attrs.get("job-id", [None])[0]
    job_state = attrs.get("job-state", [None])[0]
    if type(job_id) is not int or type(job_state) is not int:
        return None
    if job_id <= 0 or job_state not in JOB_STATE_NAMES:
        raise IppError("invalid job-id or job-state in IPP response")
    reasons = _all_str(attrs, "job-state-reasons")
    return JobAttributes(
        job_id=int(job_id),
        job_state=int(job_state),
        job_state_name=JOB_STATE_NAMES.get(int(job_state), f"unknown-{job_state}"),
        job_state_reasons=",".join(reasons) if reasons else None,
        impressions_completed=_first_int(attrs, "job-impressions-completed"),
        media_sheets_completed=_first_int(attrs, "job-media-sheets-completed"),
        impressions_total=_first_int(attrs, "job-impressions"),
        job_name=_first_str(attrs, "job-name"),
    )


def parse_printer_attrs_response(data: bytes) -> PrinterInfo:
    """Parse a Get-Printer-Attributes response. Raises IppError when the
    printer rejects the operation."""
    response = decode_response(data)
    status, attrs = response.status, response.attributes((1, 4))
    if status not in (0x0000, 0x0001, 0x0002):
        raise IppError(f"Get-Printer-Attributes failed (ipp_status=0x{status:04x})")
    return _printer_info_from_attributes(attrs)


def _printer_info_from_attributes(attrs: dict[str, list]) -> PrinterInfo:
    copies = attrs.get("copies-supported") or []
    copies_max: int | None = None
    for v in copies:
        if isinstance(v, tuple) and len(v) == 2 and 1 <= v[0] <= v[1] <= 2**31 - 1:
            copies_max = max(copies_max or 0, v[1])
        elif type(v) is int and 1 <= v <= 2**31 - 1:
            copies_max = max(copies_max or 0, v)
    return PrinterInfo(
        name=_first_str(attrs, "printer-name"),
        info=_first_str(attrs, "printer-info"),
        location=_first_str(attrs, "printer-location"),
        make_and_model=_first_str(attrs, "printer-make-and-model"),
        uuid=_first_str(attrs, "printer-uuid"),
        formats=_all_str(attrs, "document-format-supported"),
        sides=_all_str(attrs, "sides-supported"),
        copies_max=copies_max,
        media_default=_first_str(attrs, "media-default"),
        media_supported=_all_str(attrs, "media-supported"),
        media_ready=_all_str(attrs, "media-ready") if "media-ready" in attrs else None,
        media_sources=_all_str(attrs, "media-source-supported"),
        media_col_members=_all_str(attrs, "media-col-supported"),
        color_modes=_all_str(attrs, "print-color-mode-supported"),
        qualities=[v for v in attrs.get("print-quality-supported", []) if type(v) is int],
        operations=[v for v in attrs.get("operations-supported", []) if type(v) is int],
        versions=_all_str(attrs, "ipp-versions-supported"),
        defaults={key: attrs[key][0] for key in (
            "media-default", "sides-default", "copies-default", "print-color-mode-default",
            "print-quality-default",
        ) if attrs.get(key) and type(attrs[key][0]) in (str, int)},
        media_collections={key: [v for v in attrs.get(key, []) if isinstance(v, dict)]
                           for key in ("media-col-default", "media-col-ready", "media-col-database")},
    )


def _all_str(attrs: dict, key: str) -> list[str]:
    return [v for v in (attrs.get(key) or []) if isinstance(v, str)]


def _first_int(attrs: dict, key: str) -> int | None:
    for v in attrs.get(key) or []:
        if type(v) is int:
            return v
    return None


def _first_str(attrs: dict, key: str) -> str | None:
    for v in attrs.get(key) or []:
        if isinstance(v, LocalizedText):
            return v.text
        if isinstance(v, str):
            return v
    return None


def _ssl_context(*, verify: bool, relaxed_ciphers: bool) -> ssl.SSLContext:
    """Build an SSL context for talking to a printer.

    `verify`: validate the printer's certificate. Most consumer/SMB printers
        ship a self-signed cert, so this typically wants to be False.
    `relaxed_ciphers`: allow legacy (non-PFS) cipher suites. Required for
        printers that don't offer ECDHE — e.g. several HP LaserJets only
        present AES256-GCM-SHA384, which Python's default SECLEVEL=2
        cipher list rejects. SECLEVEL=1 admits those without also
        admitting the export/NULL-grade suites SECLEVEL=0 allows. Turn this on if you see SSLV3_ALERT_HANDSHAKE
        _FAILURE in the logs.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if verify:
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_default_certs()
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if relaxed_ciphers:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


class PrinterClient:
    """IPP client bound to a single printer host."""

    def __init__(
        self,
        *,
        host: str,
        port: int = 443,
        use_tls: bool = True,
        user: str = "anonymous",
        password: str = "",
        verify_tls: bool = False,
        relaxed_ciphers: bool = False,
        path: str = DEFAULT_PATH,
        timeout: float = 60.0,
    ) -> None:
        self._host = host
        self._port = port
        self._path = "/" + (path or DEFAULT_PATH).strip("/")
        self._use_tls = use_tls
        self._user = user
        self._password = password
        self._verify_tls = verify_tls
        self._relaxed_ciphers = relaxed_ciphers
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self._closed = False
        self._version = b"\x02\x00"
        self._format_cache: dict[str, tuple[float, PrinterInfo]] = {}
        self._format_lock = asyncio.Lock()
        self._validate_supported: bool | None = None
        scheme = "https" if use_tls else "http"
        # Keep the configured port explicit: HTTP(S) and IPP(S) do not
        # necessarily have the same default port. Bracket IPv6 literals.
        authority_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
        authority = f"{authority_host}:{port}"
        self._url = f"{scheme}://{authority}{self._path}"
        # IPP URIs are always `ipp://` or `ipps://`, never http/https.
        ipp_scheme = "ipps" if use_tls else "ipp"
        self._uri = f"{ipp_scheme}://{authority}{self._path}"

    @property
    def host(self) -> str:
        return self._host

    @property
    def printer_uri(self) -> str:
        return self._uri

    @property
    def web_url(self) -> str:
        """Best-guess URL of the printer's embedded web UI."""
        scheme = "https" if self._use_tls else "http"
        authority_host = (
            f"[{self._host}]" if ":" in self._host and not self._host.startswith("[")
            else self._host
        )
        port_suffix = "" if self._port == (443 if self._use_tls else 80) else f":{self._port}"
        return f"{scheme}://{authority_host}{port_suffix}/"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazily create the shared session (keep-alive connections).

        The SSL context does blocking work (cipher setup, CA loading), so it
        is built in an executor exactly once — never on the event loop.
        """
        if self._closed:
            raise IppError("printer connection has been unloaded")
        if self._session is not None and not self._session.closed:
            return self._session
        async with self._session_lock:
            if self._closed:
                raise IppError("printer connection has been unloaded")
            if self._session is not None and not self._session.closed:
                return self._session
            if self._use_tls:
                ctx = await asyncio.get_running_loop().run_in_executor(
                    None,
                    partial(
                        _ssl_context,
                        verify=self._verify_tls,
                        relaxed_ciphers=self._relaxed_ciphers,
                    ),
                )
                connector = aiohttp.TCPConnector(ssl=ctx)
            else:
                connector = aiohttp.TCPConnector()
            self._session = aiohttp.ClientSession(
                connector=connector, timeout=self._timeout
            )
            return self._session

    async def async_close(self) -> None:
        """Release the pooled session/connections."""
        async with self._session_lock:
            self._closed = True
            if self._session is not None:
                await self._session.close()
                self._session = None

    async def _post_ipp(
        self, body: bytes | aiohttp.payload.Payload, *, timeout: float | None = None
    ) -> bytes:
        auth = (
            aiohttp.BasicAuth(self._user, self._password)
            if self._password
            else None
        )
        session = await self._get_session()
        client_timeout = (
            aiohttp.ClientTimeout(total=timeout) if timeout else self._timeout
        )
        async with session.post(
            self._url,
            data=body,
            headers={"Content-Type": "application/ipp"},
            auth=auth,
            timeout=client_timeout,
            allow_redirects=False,
        ) as resp:
            if resp.status != 200:
                _LOGGER.warning("Printer returned HTTP %s for IPP request", resp.status)
                raise IppHttpError(resp.status)
            content = bytearray()
            async for chunk in resp.content.iter_chunked(DOCUMENT_CHUNK_BYTES):
                if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise IppError("printer response exceeds the 1 MiB limit")
                content.extend(chunk)
            return bytes(content)

    async def print_job(
        self,
        *,
        job_name: str,
        document_format: str,
        document: bytes | bytearray,
        copies: int | None = None,
        sides: str | None = None,
        media: str | None = None,
        color_mode: str | None = None,
        media_source: str | None = None,
        quality: int | None = None,
    ) -> JobSubmissionResult:
        req = build_print_job(
            printer_uri=self._uri,
            user=self._user,
            job_name=job_name,
            document_format=document_format,
            document=b"",
            copies=copies,
            sides=sides,
            media=media,
            color_mode=color_mode, quality=quality, media_source=media_source,
        )
        req = self._version + req[2:]
        return parse_print_job_response(
            await self._post_ipp(_IppDocumentPayload(req, document), timeout=PRINT_TIMEOUT)
        )

    async def get_job_attrs(self, job_id: int) -> JobAttributes | None:
        req = build_get_job_attrs(
            printer_uri=self._uri, user=self._user, job_id=job_id
        )
        return parse_job_attrs_response(
            await self._post_ipp(self._version + req[2:], timeout=POLL_TIMEOUT)
        )

    async def _probe(self, req: bytes) -> bytes:
        """Only explicit version rejection permits a read-only retry."""
        raw = await self._post_ipp(self._version + req[2:], timeout=POLL_TIMEOUT)
        response = decode_response(raw)
        if response.status == 0x0503 and self._version != b"\x01\x01":
            raw = await self._post_ipp(b"\x01\x01" + req[2:], timeout=POLL_TIMEOUT)
            if decode_response(raw).status in (0, 1, 2):
                self._version = b"\x01\x01"
        return raw

    async def get_printer_attrs(
        self, document_format: str | None = None, *, fresh: bool = False,
    ) -> PrinterInfo:
        if document_format is None:
            req = build_get_printer_attrs(printer_uri=self._uri, user=self._user)
            return parse_printer_attrs_response(await self._probe(req))
        if not isinstance(document_format, str) or len(document_format) > 127 or not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", document_format):
            raise ValueError("unsupported capability document format")
        async with self._format_lock:
            now = asyncio.get_running_loop().time()
            cached = self._format_cache.get(document_format)
            if not fresh and cached and cached[0] > now:
                return cached[1]
            response = None
            # Small batches avoid long requested-attributes lists on older firmware.
            requested = PRINTER_ATTRS_REQUESTED + OPTION_ATTRS_REQUESTED
            for offset in range(0, len(requested), 8):
                req = build_get_printer_attrs(
                    printer_uri=self._uri, user=self._user, document_format=document_format,
                    requested=requested[offset:offset + 8],
                )
                raw = await self._probe(req)
                parsed = decode_response(raw)
                if parsed.status not in (0, 1, 2):
                    raise IppError(f"format capability probe failed (ipp_status=0x{parsed.status:04x})")
                if response is None:
                    response = parsed
                else:
                    response.groups.extend(parsed.groups)
            # Reuse the normalizer without serializing typed collections again.
            info = _printer_info_from_attributes(response.attributes((1, 4)))
            info.document_format = document_format
            if len(self._format_cache) >= 8:
                self._format_cache.pop(next(iter(self._format_cache)))
            self._format_cache[document_format] = (now + 900, info)
            return info

    async def validate_job(self, *, document_format: str, **options) -> str | None:
        if self._validate_supported is False:
            return "Printer does not support preflight validation; settings are sent with fidelity."
        req = build_print_job(printer_uri=self._uri, user=self._user, job_name="Validate settings",
                              document_format=document_format, document=b"", **options)
        req = self._version + OP_VALIDATE_JOB.to_bytes(2, "big") + req[4:]
        response = decode_response(await self._probe(req))
        if response.status == 0x0501:
            self._validate_supported = False
            return "Printer does not support preflight validation; settings are sent with fidelity."
        self._validate_supported = True
        if response.status != 0:
            fields = ", ".join(response.attributes((5,)))[:240]
            raise IppError("printer refused the selected settings during validation"
                           + (f": {fields}" if fields else "")
                           + f" (ipp_status=0x{response.status:04x})")
        return None

    async def cancel_job(self, job_id: int) -> int:
        req = build_cancel_job(
            printer_uri=self._uri, user=self._user, job_id=job_id
        )
        status, _ = parse_response(await self._post_ipp(self._version + req[2:], timeout=POLL_TIMEOUT))
        return status
