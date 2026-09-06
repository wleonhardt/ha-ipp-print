"""HTTP endpoint tests for /api/ipp_print/{print,cancel}."""
from unittest.mock import AsyncMock, patch

import aiohttp
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.ipp_print as integration
from custom_components.ipp_print.const import DOMAIN
from custom_components.ipp_print.coordinator import JobCoordinator
from custom_components.ipp_print.printer import IppHttpError, JobSubmissionResult

PDF = b"%PDF-1.7 fake body"
OK_RESULT = JobSubmissionResult(
    ipp_status=0, job_id=42, job_state=3, job_state_name="pending", raw=b""
)


async def _setup(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="127.0.0.1:443"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _form(payload: bytes, field: str = "file", filename: str = "doc.pdf"):
    form = aiohttp.FormData()
    form.add_field(
        field, payload, filename=filename, content_type="application/pdf"
    )
    return form


async def test_print_happy_path(hass, hass_client):
    await _setup(hass)
    with patch.object(
        integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)
    ), patch.object(JobCoordinator, "_ensure_poll_loop"):
        client = await hass_client()
        resp = await client.post("/api/ipp_print/print", data=_form(PDF))
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["job_id"] == 42
        assert body["bytes"] == len(PDF)
        assert body["filename"] == "doc.pdf"


def test_safe_pdf_filename():
    # Direct unit tests — aiohttp's test client percent-encodes filenames,
    # so exotic names can't reach the view verbatim from here (browsers send
    # raw UTF-8).
    f = integration._safe_pdf_filename
    assert f(None) == "upload.pdf"
    assert f("") == "upload.pdf"
    assert f("my döc!.pdf") == "my-d-c-.pdf"
    assert f("../../etc/passwd") == "passwd.pdf"
    assert f("no-extension") == "no-extension.pdf"
    assert f("UPPER.PDF") == "UPPER.PDF"
    assert f("a" * 300 + ".pdf").startswith("a")
    assert len(f("a" * 300 + ".pdf")) <= 120


async def test_print_missing_file_field(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    resp = await client.post("/api/ipp_print/print", data=_form(PDF, field="nope"))
    assert resp.status == 400


async def test_print_rejects_non_pdf(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    resp = await client.post("/api/ipp_print/print", data=_form(b"GIF89a not a pdf"))
    assert resp.status == 415


async def test_print_accepts_magic_within_first_kib(hass, hass_client):
    await _setup(hass)
    payload = b"\x00" * 100 + PDF  # preamble junk before %PDF- is legal
    with patch.object(
        integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)
    ), patch.object(JobCoordinator, "_ensure_poll_loop"):
        client = await hass_client()
        resp = await client.post("/api/ipp_print/print", data=_form(payload))
        assert resp.status == 200


async def test_print_too_large(hass, hass_client, monkeypatch):
    await _setup(hass)
    monkeypatch.setattr(integration, "MAX_UPLOAD_BYTES", 10)
    client = await hass_client()
    resp = await client.post("/api/ipp_print/print", data=_form(PDF))
    assert resp.status == 413


async def test_print_maps_auth_failure(hass, hass_client):
    await _setup(hass)
    with patch.object(
        integration.PrinterClient,
        "print_job",
        new=AsyncMock(side_effect=IppHttpError(401)),
    ):
        client = await hass_client()
        resp = await client.post("/api/ipp_print/print", data=_form(PDF))
        assert resp.status == 502
        assert "authentication failed" in (await resp.json())["message"]


async def test_print_after_unload_returns_503(hass, hass_client):
    entry = await _setup(hass)
    client = await hass_client()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    resp = await client.post("/api/ipp_print/print", data=_form(PDF))
    assert resp.status == 503


async def test_cancel_unknown_job_is_404(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    resp = await client.post("/api/ipp_print/cancel", json={"job_id": 12345})
    assert resp.status == 404


async def test_cancel_requires_int_job_id(hass, hass_client):
    await _setup(hass)
    client = await hass_client()
    resp = await client.post("/api/ipp_print/cancel", json={"job_id": "7"})
    assert resp.status == 400


async def test_cancel_tracked_job(hass, hass_client):
    entry = await _setup(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    with patch.object(JobCoordinator, "_ensure_poll_loop"):
        coordinator.track(job_id=7, filename="x.pdf", bytes_sent=1)
    with patch.object(
        integration.PrinterClient, "cancel_job", new=AsyncMock(return_value=0)
    ):
        client = await hass_client()
        resp = await client.post("/api/ipp_print/cancel", json={"job_id": 7})
        assert resp.status == 200
        assert (await resp.json())["ok"] is True


async def test_print_unconfigured_refuses_before_reading_body(hass, hass_client):
    entry = await _setup(hass)
    client = await hass_client()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    # A body that would otherwise be a 400 (not multipart) must still get
    # 503: the configured check runs before any of the body is consumed.
    resp = await client.post(
        "/api/ipp_print/print", data=b"not multipart",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status == 503
