"""ipp_print.print_file service tests."""
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.ipp_print as integration
from custom_components.ipp_print.const import DOMAIN
from custom_components.ipp_print.coordinator import JobCoordinator
from custom_components.ipp_print.printer import JobSubmissionResult

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


@pytest.fixture
def www(hass, tmp_path):
    """A file under an allowed dir."""
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.7 hello")
    return f


async def test_print_file_submits_and_returns_job(hass, www):
    await _setup(hass)
    with patch.object(
        integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)
    ) as pj, patch.object(JobCoordinator, "_ensure_poll_loop"):
        resp = await hass.services.async_call(
            DOMAIN, "print_file",
            {"path": str(www), "copies": 2, "sides": "two-sided-long-edge"},
            blocking=True, return_response=True,
        )
    assert resp["job_id"] == 42
    assert resp["filename"] == "report.pdf"
    kw = pj.call_args.kwargs
    assert kw["document_format"] == "application/pdf"
    assert kw["copies"] == 2 and kw["sides"] == "two-sided-long-edge"


async def test_print_file_rejects_path_outside_allowlist(hass, tmp_path):
    await _setup(hass)
    f = tmp_path / "x.pdf"
    f.write_bytes(b"%PDF-")
    hass.config.allowlist_external_dirs = set()
    with pytest.raises(ServiceValidationError, match="not allowed"):
        await hass.services.async_call(
            DOMAIN, "print_file", {"path": str(f)}, blocking=True
        )


async def test_print_file_missing_file(hass, tmp_path):
    await _setup(hass)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    with pytest.raises(ServiceValidationError, match="not found"):
        await hass.services.async_call(
            DOMAIN, "print_file", {"path": str(tmp_path / "nope.pdf")}, blocking=True
        )


async def test_print_file_unknown_type_needs_explicit_format(hass, tmp_path):
    await _setup(hass)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    f = tmp_path / "raw.prn"
    f.write_bytes(b"GIF89a")
    with pytest.raises(ServiceValidationError, match="cannot identify"):
        await hass.services.async_call(
            DOMAIN, "print_file", {"path": str(f)}, blocking=True
        )
    # Explicit format with an auto-sensing printer goes through.
    with patch.object(
        integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)
    ) as pj, patch.object(JobCoordinator, "_ensure_poll_loop"):
        live = integration._pick_entry(hass, None)
        live["printer_info"].formats.append("application/octet-stream")
        await hass.services.async_call(
            DOMAIN, "print_file",
            {"path": str(f), "document_format": "application/octet-stream"},
            blocking=True,
        )
    assert pj.call_args.kwargs["document_format"] == "application/octet-stream"


async def test_print_file_sides_unsupported(hass, www):
    await _setup(hass)
    with pytest.raises(HomeAssistantError, match="sides=two-sided-short-edge"):
        await hass.services.async_call(
            DOMAIN, "print_file",
            {"path": str(www), "sides": "two-sided-short-edge"},
            blocking=True,
        )


async def test_print_file_unconfigured(hass, www):
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    with pytest.raises(ServiceValidationError, match="not configured"):
        await hass.services.async_call(
            DOMAIN, "print_file", {"path": str(www)}, blocking=True
        )


async def test_device_and_diagnostics(hass):
    from homeassistant.helpers import device_registry as dr

    from custom_components.ipp_print.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "password": "hunter2"},
        unique_id="127.0.0.1:443",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.name == "Test Printer"
    assert device.manufacturer == "Acme"
    assert device.model == "Acme LaserJet 1000"
    assert device.configuration_url == "https://127.0.0.1/"

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["password"] == "**REDACTED**"
    assert diag["printer"]["make_and_model"] == "Acme LaserJet 1000"
    assert diag["printer_uri"] == "ipps://127.0.0.1:443/ipp/print"
    assert diag["current_job"] is None


async def _setup_two(hass):
    a = MockConfigEntry(
        domain=DOMAIN, data={"host": "127.0.0.1"}, unique_id="127.0.0.1:443",
        title="Office",
    )
    b = MockConfigEntry(
        domain=DOMAIN, data={"host": "127.0.0.2"}, unique_id="127.0.0.2:443",
        title="Lab",
    )
    for e in (a, b):
        e.add_to_hass(hass)
        assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    return a, b


async def test_print_file_two_printers_requires_target(hass, www):
    await _setup_two(hass)
    with pytest.raises(ServiceValidationError, match="several printers"):
        await hass.services.async_call(
            DOMAIN, "print_file", {"path": str(www)}, blocking=True
        )


async def test_print_file_routes_by_entity_target(hass, www):
    a, b = await _setup_two(hass)
    coord_b = hass.data[DOMAIN][b.entry_id]["coordinator"]
    with patch.object(
        integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)
    ) as pj, patch.object(JobCoordinator, "_ensure_poll_loop"):
        await hass.services.async_call(
            DOMAIN, "print_file",
            {"path": str(www), "entity_id": "sensor.test_printer_current_job_2"},
            blocking=True,
        )
    # Both entries share the canned PrinterInfo; the second sensor got "_2".
    pj.assert_awaited_once()
    assert coord_b.knows(42)
    assert not hass.data[DOMAIN][a.entry_id]["coordinator"].knows(42)


async def test_print_file_routes_by_device_target(hass, www):
    from homeassistant.helpers import device_registry as dr

    a, b = await _setup_two(hass)
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, a.entry_id)})
    with patch.object(
        integration.PrinterClient, "print_job", new=AsyncMock(return_value=OK_RESULT)
    ), patch.object(JobCoordinator, "_ensure_poll_loop"):
        await hass.services.async_call(
            DOMAIN, "print_file",
            {"path": str(www), "device_id": device.id},
            blocking=True,
        )
    assert hass.data[DOMAIN][a.entry_id]["coordinator"].knows(42)
    assert not hass.data[DOMAIN][b.entry_id]["coordinator"].knows(42)


async def test_print_file_foreign_entity_target(hass, www):
    await _setup(hass)
    hass.states.async_set("sensor.other", "1")
    with pytest.raises(ServiceValidationError, match="not a loaded IPP Print"):
        await hass.services.async_call(
            DOMAIN, "print_file",
            {"path": str(www), "entity_id": "sensor.other"},
            blocking=True,
        )
