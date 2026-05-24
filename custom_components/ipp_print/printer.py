"""Minimal IPP/2.0 client.

Self-contained binary-wire-format builder + parser. Only the surface we need
is implemented:
    * Print-Job         (0x0002) — submit a document, returns job-id
    * Get-Job-Attributes (0x0009) — read state/progress of one job
    * Cancel-Job        (0x0008) — cancel by job-id

We don't depend on `pyipp` because its public API is read-only (printer
attributes) and Print-Job requires the document body inline after the
attribute groups — handcrafted bytes are simpler than monkey-patching.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import ssl

import aiohttp

_LOGGER = logging.getLogger(__name__)

# IPP value tags we read/write. Full list in RFC 8011 §5.5.
TAG_END_ATTRS = 0x03
TAG_OPERATION_ATTRS = 0x01
TAG_INTEGER = 0x21
TAG_ENUM = 0x23
TAG_NAME_WITHOUT_LANG = 0x42
TAG_URI = 0x45
TAG_CHARSET = 0x47
TAG_NATURAL_LANGUAGE = 0x48
TAG_MIME_MEDIA_TYPE = 0x49

# Operations.
OP_PRINT_JOB = 0x0002
OP_CANCEL_JOB = 0x0008
OP_GET_JOB_ATTRS = 0x0009

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


def build_print_job(
    *,
    printer_uri: str,
    user: str,
    job_name: str,
    document_format: str,
    document: bytes,
) -> bytes:
    op_attrs = _operation_group(
        printer_uri=printer_uri,
        user=user,
        extra=(
            _attr(TAG_NAME_WITHOUT_LANG, b"job-name", job_name.encode()[:255])
            + _attr(
                TAG_MIME_MEDIA_TYPE, b"document-format", document_format.encode()
            )
        ),
    )
    return _header(OP_PRINT_JOB) + op_attrs + bytes([TAG_END_ATTRS]) + document


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


def _parse_attributes(data: bytes, offset: int) -> tuple[dict[str, list], int]:
    """Walk attribute groups to end-of-attributes (0x03)."""
    attrs: dict[str, list] = {}
    current_name: str | None = None
    i = offset
    n = len(data)
    while i < n:
        tag = data[i]
        i += 1
        if tag == TAG_END_ATTRS:
            return attrs, i
        if tag < 0x10:
            # Begin-attribute-group delimiter; reset name carry.
            current_name = None
            continue
        name_len = int.from_bytes(data[i : i + 2], "big")
        i += 2
        name = (
            data[i : i + name_len].decode("utf-8", "replace") if name_len else None
        )
        i += name_len
        value_len = int.from_bytes(data[i : i + 2], "big")
        i += 2
        raw = data[i : i + value_len]
        i += value_len

        if tag in (TAG_INTEGER, TAG_ENUM):
            value: int | str = int.from_bytes(raw, "big", signed=True)
        else:
            value = raw.decode("utf-8", "replace")

        if name:
            current_name = name
        if current_name is None:
            continue
        attrs.setdefault(current_name, []).append(value)
    return attrs, i


def parse_response(data: bytes) -> tuple[int, dict[str, list]]:
    """Return (ipp-status-code, flattened attributes dict)."""
    if len(data) < 8:
        raise ValueError(f"IPP response too short: {len(data)} bytes")
    status = int.from_bytes(data[2:4], "big")
    attrs, _ = _parse_attributes(data, 8)
    return status, attrs


def parse_print_job_response(data: bytes) -> JobSubmissionResult:
    status, attrs = parse_response(data)
    job_id = attrs.get("job-id", [None])[0]
    job_state = attrs.get("job-state", [None])[0]
    return JobSubmissionResult(
        ipp_status=status,
        job_id=int(job_id) if isinstance(job_id, int) else None,
        job_state=int(job_state) if isinstance(job_state, int) else None,
        job_state_name=(
            JOB_STATE_NAMES.get(int(job_state))
            if isinstance(job_state, int)
            else None
        ),
        raw=data,
    )


def parse_job_attrs_response(data: bytes) -> JobAttributes | None:
    status, attrs = parse_response(data)
    if status not in (0x0000, 0x0001, 0x0002):
        _LOGGER.debug("Get-Job-Attributes returned IPP status 0x%04x", status)
    job_id = attrs.get("job-id", [None])[0]
    job_state = attrs.get("job-state", [None])[0]
    if not isinstance(job_id, int) or not isinstance(job_state, int):
        return None
    reasons = attrs.get("job-state-reasons", [None])[0]
    return JobAttributes(
        job_id=int(job_id),
        job_state=int(job_state),
        job_state_name=JOB_STATE_NAMES.get(int(job_state), f"unknown-{job_state}"),
        job_state_reasons=str(reasons) if reasons else None,
        impressions_completed=_first_int(attrs, "job-impressions-completed"),
        media_sheets_completed=_first_int(attrs, "job-media-sheets-completed"),
        impressions_total=_first_int(attrs, "job-impressions"),
        job_name=_first_str(attrs, "job-name"),
    )


def _first_int(attrs: dict, key: str) -> int | None:
    for v in attrs.get(key) or []:
        if isinstance(v, int):
            return v
    return None


def _first_str(attrs: dict, key: str) -> str | None:
    for v in attrs.get(key) or []:
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
        cipher list rejects. Turn this on if you see SSLV3_ALERT_HANDSHAKE
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
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
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
        timeout: float = 60.0,
    ) -> None:
        self._host = host
        self._port = port
        self._use_tls = use_tls
        self._user = user
        self._password = password
        self._verify_tls = verify_tls
        self._relaxed_ciphers = relaxed_ciphers
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        scheme = "https" if use_tls else "http"
        port_suffix = "" if port in (80, 443) else f":{port}"
        self._url = f"{scheme}://{host}{port_suffix}/ipp/print"
        # IPP URIs are always `ipp://` or `ipps://`, never http/https.
        ipp_scheme = "ipps" if use_tls else "ipp"
        self._uri = f"{ipp_scheme}://{host}{port_suffix}/ipp/print"

    @property
    def host(self) -> str:
        return self._host

    @property
    def printer_uri(self) -> str:
        return self._uri

    async def _post_ipp(self, body: bytes, *, timeout: float | None = None) -> bytes:
        auth = (
            aiohttp.BasicAuth(self._user, self._password)
            if self._password
            else None
        )
        if self._use_tls:
            connector = aiohttp.TCPConnector(
                ssl=_ssl_context(
                    verify=self._verify_tls,
                    relaxed_ciphers=self._relaxed_ciphers,
                )
            )
        else:
            connector = aiohttp.TCPConnector()
        client_timeout = (
            aiohttp.ClientTimeout(total=timeout) if timeout else self._timeout
        )
        async with aiohttp.ClientSession(
            connector=connector, timeout=client_timeout
        ) as session:
            async with session.post(
                self._url,
                data=body,
                headers={"Content-Type": "application/ipp"},
                auth=auth,
            ) as resp:
                content = await resp.read()
                if resp.status != 200:
                    _LOGGER.warning(
                        "Printer returned HTTP %s for IPP request: %s",
                        resp.status,
                        content[:200],
                    )
                return content

    async def print_job(
        self,
        *,
        job_name: str,
        document_format: str,
        document: bytes,
    ) -> JobSubmissionResult:
        req = build_print_job(
            printer_uri=self._uri,
            user=self._user,
            job_name=job_name,
            document_format=document_format,
            document=document,
        )
        return parse_print_job_response(await self._post_ipp(req))

    async def get_job_attrs(self, job_id: int) -> JobAttributes | None:
        req = build_get_job_attrs(
            printer_uri=self._uri, user=self._user, job_id=job_id
        )
        return parse_job_attrs_response(
            await self._post_ipp(req, timeout=10.0)
        )

    async def cancel_job(self, job_id: int) -> int:
        req = build_cancel_job(
            printer_uri=self._uri, user=self._user, job_id=job_id
        )
        status, _ = parse_response(await self._post_ipp(req, timeout=10.0))
        return status
