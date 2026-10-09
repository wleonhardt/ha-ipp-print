"""Keep the cause of a failed JPEG settings lookup without retaining private data."""
from copy import deepcopy
import json
import ssl
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

import custom_components.ipp_print as integration
from custom_components.ipp_print import capability_cache as cache_module
from custom_components.ipp_print.capability_cache import CapabilityCache
from custom_components.ipp_print.diagnostics import async_get_config_entry_diagnostics
from custom_components.ipp_print.coordinator import JobCoordinator
from custom_components.ipp_print.printer import IppError, IppHttpError, IppStatusError

from test_views import OK_RESULT, _setup, _setup_two


def jpeg_form():
    form = aiohttp.FormData()
    form.add_field("copies", "1")
    form.add_field("sides", "one-sided")
    form.add_field("file", b"\xff\xd8\xffprivate document contents",
                   filename="private-photo.jpg", content_type="image/jpeg")
    return form


async def test_jpeg_failure_survives_backoff_and_successful_retry(
    hass, hass_client, printer_attrs, validation_result, monkeypatch,
):
    now = [1.0]
    monkeypatch.setattr(cache_module, "monotonic", lambda: now[0])
    entry = await _setup(hass)
    http = await hass_client()
    printer_attrs.side_effect = TimeoutError("secret at https://user:pass@192.0.2.1/private")
    with patch.object(integration.PrinterClient, "print_job",
                      new=AsyncMock(return_value=OK_RESULT)) as submit:
        response = await http.post("/api/ipp_print/print", data=jpeg_form())
        assert response.status == 502
        body = await response.json()
        assert body["job_may_exist"] is False
        assert "Try again in 30 seconds" in body["message"]
        diag = await async_get_config_entry_diagnostics(hass, entry)
        blocked = deepcopy(diag["last_blocked_submission"])
        assert blocked["stage"] == "format_capabilities"
        assert blocked["document_format"] == "image/jpeg"
        assert blocked["job_may_exist"] is False
        failure = blocked["probe"]["last_failure"]
        assert failure["category"] == "timeout"
        assert failure["at"] and failure["duration_ms"] >= 0
        assert blocked["probe"]["status"] == "unknown"
        assert blocked["probe"]["refresh_failed"] is True
        assert blocked["probe"]["submit_retry_after_seconds"] == 30

        # Another attempt during backoff uses the same failure, not another query.
        response = await http.post("/api/ipp_print/print", data=jpeg_form())
        assert response.status == 502
        assert printer_attrs.await_count == 2  # setup + one real failed lookup
        validation_result.assert_not_called()
        submit.assert_not_called()
        diag = await async_get_config_entry_diagnostics(hass, entry)
        blocked = deepcopy(diag["last_blocked_submission"])
        assert blocked["probe"]["last_failure"] == failure

        printer_attrs.side_effect = None
        # The printer has recovered. A deliberate retry after a short cooldown
        # must not stay blocked for the full five-minute background backoff.
        now[0] += 30
        # Read-only dashboard refreshes still observe the original backoff.
        response = await http.get("/api/ipp_print/capabilities?document_format=image%2Fjpeg")
        assert response.status == 200
        assert printer_attrs.await_count == 2
        submit.assert_not_called()
        with patch.object(JobCoordinator, "_ensure_poll_loop"):
            response = await http.post("/api/ipp_print/print", data=jpeg_form())
        assert response.status == 200
        submit.assert_awaited_once()
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["last_blocked_submission"] == blocked
        jpeg = diag["capability_queries"]["formats"][0]
        assert jpeg["document_format"] == "image/jpeg"
        assert jpeg["status"] == "fresh" and not jpeg["refresh_failed"]
        assert jpeg["submit_retry_after_seconds"] == 0
        assert jpeg["last_failure"] == failure
        assert diag["capability_queries"]["generic"]["status"] == "fresh"
        assert diag["connection"]["state"] == "reachable"
        assert printer_attrs.await_count == 3  # diagnostic downloads never probe
        text = json.dumps(diag)
        for private in ("secret", "192.0.2.1", "user:pass", "private-photo", "private document"):
            assert private not in text


@pytest.mark.parametrize("outcome", ["timeout", "unsupported", "invalid_settings"])
async def test_recovery_does_not_bypass_validation_or_resend_print(
    hass, hass_client, printer_attrs, validation_result, monkeypatch, outcome,
):
    now = [1.0]
    monkeypatch.setattr(cache_module, "monotonic", lambda: now[0])
    entry = await _setup(hass)
    http = await hass_client()
    printer_attrs.side_effect = TimeoutError()
    with patch.object(integration.PrinterClient, "print_job",
                      new=AsyncMock(side_effect=TimeoutError())) as submit:
        response = await http.post("/api/ipp_print/print", data=jpeg_form())
        assert response.status == 502
        submit.assert_not_called()
        printer_attrs.side_effect = None
        now[0] += 30
        if outcome == "unsupported":
            printer_attrs.return_value.formats = ["application/pdf"]
        elif outcome == "invalid_settings":
            validation_result.side_effect = IppStatusError("settings rejected", 0x040B)
        response = await http.post("/api/ipp_print/print", data=jpeg_form())
        assert response.status == {"timeout": 502, "unsupported": 415, "invalid_settings": 400}[outcome]
        body = await response.json()
        assert body["job_may_exist"] is (outcome == "timeout")
        if outcome == "timeout":
            assert "check its queue before retrying" in body["message"]
        now[0] += 600
        await hass.async_block_till_done()
        await http.get("/api/ipp_print/capabilities?document_format=image%2Fjpeg")
        await async_get_config_entry_diagnostics(hass, entry)
        assert submit.await_count == (1 if outcome == "timeout" else 0)
        assert validation_result.await_count == (0 if outcome == "unsupported" else 1)


@pytest.mark.parametrize("exception,expected", [
    (TimeoutError("private"), {"category": "timeout"}),
    (aiohttp.ServerTimeoutError("private"), {"category": "timeout"}),
    (ssl.SSLError("private"), {"category": "tls"}),
    (aiohttp.ClientConnectorCertificateError(None, ValueError("private")), {"category": "tls"}),
    (IppHttpError(401), {"category": "authentication", "http_status": 401}),
    (IppHttpError(403), {"category": "authentication", "http_status": 403}),
    (IppHttpError(503), {"category": "http", "http_status": 503}),
    (IppStatusError("private", 0x040A), {"category": "ipp_rejected", "ipp_status": "0x040a"}),
    (ValueError("private"), {"category": "invalid_data"}),
    (aiohttp.ClientPayloadError("private"), {"category": "invalid_response"}),
    (aiohttp.ServerDisconnectedError("private"), {"category": "connection"}),
    (OSError("private"), {"category": "connection"}),
    (IppError("private"), {"category": "protocol"}),
    (RuntimeError("private"), {"category": "unexpected"}),
])
async def test_failure_categories_exclude_raw_errors(exception, expected):
    cache = CapabilityCache(AsyncMock(side_effect=exception))
    await cache.async_get()
    failure = cache.diagnostic_snapshot()["last_failure"]
    assert {k: v for k, v in failure.items() if k not in ("at", "duration_ms")} == expected
    assert "private" not in json.dumps(cache.diagnostic_snapshot())
    # Callers cannot modify the retained evidence through the returned snapshot.
    failure["category"] = "changed"
    assert cache.diagnostic_snapshot()["last_failure"]["category"] == expected["category"]


async def test_diagnostics_are_entry_scoped_bounded_and_do_not_query(hass, printer_attrs):
    a, b = await _setup_two(hass)
    live = hass.data["ipp_print"][a.entry_id]
    printer_attrs.side_effect = OSError("private")
    for n in range(10):
        cache = await integration._format_cache(live, f"application/private-{n}")
        await cache.async_get()
    calls = printer_attrs.await_count
    diag_a = await async_get_config_entry_diagnostics(hass, a)
    diag_b = await async_get_config_entry_diagnostics(hass, b)
    assert len(diag_a["capability_queries"]["formats"]) == 8
    assert all(f["document_format"] == "other" for f in diag_a["capability_queries"]["formats"])
    assert "private" not in json.dumps(diag_a)
    assert diag_a["last_blocked_submission"] is None  # Queries alone submit nothing.
    assert diag_b["capability_queries"]["formats"] == []
    assert diag_b["last_blocked_submission"] is None
    assert printer_attrs.await_count == calls
    # Reload starts an empty diagnostic window, without changing persisted activity.
    printer_attrs.side_effect = None
    assert await hass.config_entries.async_reload(a.entry_id)
    diag_a = await async_get_config_entry_diagnostics(hass, a)
    assert diag_a["capability_queries"]["formats"] == []
    assert diag_a["capability_queries"]["generic"]["last_failure"] is None


async def test_diagnostics_before_setup_are_safe(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(domain="ipp_print", data={"host": "private", "password": "secret"})
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["capability_queries"] == {"generic": None, "formats": []}
    assert diag["last_blocked_submission"] is None
    assert "private" not in json.dumps(diag) and "secret" not in json.dumps(diag)
