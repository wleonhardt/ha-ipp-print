"""Capability API and multipart options share routing and validation."""
import asyncio
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
import voluptuous as vol

import custom_components.ipp_print as integration
from custom_components.ipp_print.capabilities import validate_copies
from custom_components.ipp_print.coordinator import JobCoordinator

from test_views import OK_RESULT, PDF, _setup, _setup_two


def form(fields):
    result = aiohttp.FormData()
    for name, value in fields:
        if name == "file":
            result.add_field(name, value, filename="phase2.pdf", content_type="application/pdf")
        else:
            result.add_field(name, value)
    return result


async def test_read_only_user_can_read_capabilities(hass, hass_client, hass_read_only_access_token):
    await _setup(hass)
    http = await hass_client(hass_read_only_access_token)
    assert (await http.get("/api/ipp_print/capabilities")).status == 200


async def test_idle_capabilities_are_cached_scoped_and_private(hass, hass_client, printer_attrs):
    await _setup_two(hass)
    http = await hass_client()
    assert (await http.get("/api/ipp_print/capabilities")).status == 400
    responses = await asyncio.gather(*(http.get(
        "/api/ipp_print/capabilities?entity_id=sensor.test_printer_current_job_2"
    ) for _ in range(5)))
    for response in responses:
        assert response.status == 200
        body = await response.json()
        assert body["schema_version"] == 1 and body["status"] == "fresh"
        assert body["entity_id"] == "sensor.test_printer_current_job_2"
        assert body["supported"]["copies_max"] == 99
        assert body["supported"]["sides"] == ["one-sided", "two-sided-long-edge"]
        assert body["request_options"] == ["entity_id", "copies", "sides", "media", "color_mode", "quality", "media_source"]
        assert "127.0.0." not in str(body)
    assert printer_attrs.await_count == 2  # only the two setup probes
    for query in ("entity_id=sensor.other", "entity_id=button.other"):
        assert (await http.get("/api/ipp_print/capabilities?" + query)).status == 404
    for query in ("refresh=true", "entity_id=a&entity_id=b"):
        assert (await http.get("/api/ipp_print/capabilities?" + query)).status == 400


async def test_capabilities_require_auth(hass, hass_client_no_auth):
    await _setup(hass)
    http = await hass_client_no_auth()
    assert (await http.get("/api/ipp_print/capabilities")).status == 401


async def test_unknown_capabilities_do_not_claim_unsupported(hass, hass_client, printer_attrs):
    printer_attrs.side_effect = OSError("offline with secret")
    entry = await _setup(hass)
    http = await hass_client()
    body = await (await http.get("/api/ipp_print/capabilities")).json()
    assert body["status"] == "unknown"
    assert all(value is None for value in body["supported"].values())
    assert body["fetched_at"] is None and body["error"] == "refresh_failed"
    assert "secret" not in str(body)
    assert printer_attrs.await_count == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert (await http.get("/api/ipp_print/capabilities")).status == 503


@pytest.mark.parametrize("sides", ["one-sided", "two-sided-long-edge", "two-sided-short-edge"])
async def test_upload_options_route_after_file_and_use_fresh_media(
    hass, hass_client, printer_attrs, sides,
):
    a, b = await _setup_two(hass)
    printer_attrs.return_value.sides.append("two-sided-short-edge")
    printer_attrs.return_value.media_default = "iso_a4_210x297mm"
    with patch.object(integration.PrinterClient, "print_job",
                      new=AsyncMock(return_value=OK_RESULT)) as submit, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        http = await hass_client()
        response = await http.post("/api/ipp_print/print", data=form([
            ("file", PDF), ("copies", "2"), ("sides", sides),
            ("entity_id", "sensor.test_printer_current_job_2"),
        ]))
    assert response.status == 200
    submit.assert_awaited_once()
    assert submit.call_args.kwargs["copies"] == 2
    assert submit.call_args.kwargs["sides"] == sides
    assert submit.call_args.kwargs["media"] == "iso_a4_210x297mm"
    assert printer_attrs.await_count == 3
    assert hass.data["ipp_print"][b.entry_id]["coordinator"].knows(42)
    assert not hass.data["ipp_print"][a.entry_id]["coordinator"].knows(42)


@pytest.mark.parametrize("fields,status", [
    ([("copies", "0")], 400), ([("copies", "100")], 400),
    ([("copies", "-2")], 400), ([("copies", "+2")], 400),
    ([("copies", "1.5")], 400), ([("copies", "true")], 400),
    ([("copies", " 2")], 400), ([("copies", "")], 400),
    ([("copies", "٢")], 400), ([("copies", "2e1")], 400),
    ([("copies", "1"), ("copies", "2")], 400),
    ([("sides", "one-sided"), ("sides", "one-sided")], 400),
    ([("sides", "duplex")], 400), ([("sides", "")], 400),
    ([("sides", "x" * 513)], 413), ([("copies", "1" * 513)], 413),
    ([("quality", "normal")], 400),
])
async def test_invalid_options_submit_nothing(hass, hass_client, fields, status):
    await _setup(hass)
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock()) as submit:
        http = await hass_client()
        response = await http.post("/api/ipp_print/print", data=form([("file", PDF)] + fields))
    assert response.status == status
    submit.assert_not_called()


@pytest.mark.parametrize("value", [True, False, 1.0, 1.9, None, [], {}, "1.0", " 1", "-1"])
def test_service_schema_never_coerces_invalid_copies(value):
    with pytest.raises(vol.Invalid):
        integration.PRINT_FILE_SCHEMA({"path": "/tmp/file.pdf", "copies": value})


def test_strict_copies_accepts_integer_and_decimal_strings():
    assert validate_copies(2) == validate_copies("2") == validate_copies("002") == 2


async def test_advertised_copy_limit_and_failed_sides_probe_block_upload(
    hass, hass_client, printer_attrs,
):
    await _setup(hass)
    printer_attrs.return_value.copies_max = 1
    http = await hass_client()
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock()) as submit:
        response = await http.post("/api/ipp_print/print", data=form([
            ("copies", "2"), ("file", PDF),
        ]))
        assert response.status == 400
        printer_attrs.side_effect = OSError("offline")
        for _ in range(2):
            response = await http.post("/api/ipp_print/print", data=form([
                ("sides", "one-sided"), ("file", PDF),
            ]))
            assert response.status == 502
            assert "No print job was submitted" in (await response.json())["message"]
    submit.assert_not_called()
    assert printer_attrs.await_count == 3  # setup, format-specific copies, failed paper read


@pytest.mark.parametrize("options", [[], [("copies", "1"), ("sides", "one-sided")]])
async def test_png_named_jpeg_reports_unsupported_format_before_failed_profile_probe(
    hass, hass_client, printer_attrs, validation_result, options,
):
    printer_attrs.return_value.formats = ["application/pdf", "image/jpeg", "application/octet-stream"]
    await _setup(hass)
    # This HP rejects a PNG-scoped query. It must never be reached when the
    # fresh generic response already excludes PNG, even with card defaults.
    printer_attrs.side_effect = OSError("format probe failed")
    payload = aiohttp.FormData()
    for key, value in options:
        payload.add_field(key, value)
    payload.add_field("file", b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
                      filename="photo.jpg", content_type="image/jpeg")
    http = await hass_client()
    with patch.object(integration.PrinterClient, "print_job", new=AsyncMock()) as submit:
        response = await http.post("/api/ipp_print/print", data=payload)
    body = await response.json()
    assert response.status == 415
    assert body["job_may_exist"] is False
    assert "contains PNG data" in body["message"]
    assert "PDF or JPEG" in body["message"]
    assert "Renaming" in body["message"]
    assert "No print job was submitted" in body["message"]
    assert "connection" not in body["message"]
    assert printer_attrs.await_count == 1
    validation_result.assert_not_called()
    submit.assert_not_called()


async def test_stale_generic_format_list_does_not_veto_fresh_format_support(
    hass, hass_client, printer_attrs,
):
    from copy import deepcopy

    entry = await _setup(hass)
    live = hass.data["ipp_print"][entry.entry_id]
    fresh = deepcopy(printer_attrs.return_value)
    live["capability_cache"].value.formats = ["image/jpeg"]
    live["capability_cache"]._expires_at = 0
    printer_attrs.side_effect = [OSError("temporary generic probe failure"), fresh]
    http = await hass_client()
    with patch.object(integration.PrinterClient, "print_job",
                      new=AsyncMock(return_value=OK_RESULT)) as submit, \
            patch.object(JobCoordinator, "_ensure_poll_loop"):
        response = await http.post("/api/ipp_print/print", data=form([
            ("copies", "1"), ("file", PDF),
        ]))
    assert response.status == 200
    submit.assert_awaited_once()
    assert submit.call_args.kwargs["document_format"] == "application/pdf"
    assert printer_attrs.await_count == 3
