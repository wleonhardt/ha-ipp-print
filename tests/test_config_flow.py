"""Config-flow tests: user, zeroconf, options."""
from ipaddress import ip_address
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ipp_print.config_flow import ZeroconfServiceInfo
from custom_components.ipp_print.const import DOMAIN
from custom_components.ipp_print.printer import PrinterInfo

from conftest import DEFAULT_PRINTER_INFO

USER_INPUT = {
    "host": "192.0.2.10",
    "port": 443,
    "path": "/ipp/print",
    "use_tls": True,
    "user": "anonymous",
    "password": "",
    "verify_tls": False,
    "relaxed_ciphers": False,
}

NAMELESS = PrinterInfo(
    name=None, info=None, location=None, make_and_model=None, uuid=None,
    formats=[], sides=[], copies_max=None,
)


def _zc(type_="_ipps._tcp.local.", port=443, **props):
    return ZeroconfServiceInfo(
        ip_address=ip_address("192.0.2.10"),
        ip_addresses=[ip_address("192.0.2.10")],
        port=port,
        hostname="printer.local.",
        type=type_,
        name=f"Acme Printer.{type_}",
        properties=props,
    )


async def test_user_flow_success(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Title from printer-info; unique id from printer-uuid (urn stripped).
    assert result["title"] == "Test Printer"
    assert result["result"].unique_id == "12345678-1234-1234-1234-123456789abc"
    assert result["data"]["host"] == "192.0.2.10"


async def test_user_flow_falls_back_to_host_title_and_id(hass, printer_attrs):
    printer_attrs.return_value = NAMELESS
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "IPP printer at 192.0.2.10"
    assert result["result"].unique_id == "192.0.2.10:443"


async def test_user_flow_cannot_connect(hass, printer_attrs):
    printer_attrs.side_effect = OSError("no route to host")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert "no route to host" in result["description_placeholders"]["error_detail"]


async def test_second_printer_allowed(hass):
    MockConfigEntry(
        domain=DOMAIN, data={"host": "192.0.2.10"}, unique_id="192.0.2.10:443"
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # A different printer is a second entry; only the same unique_id aborts.
    assert result["type"] is FlowResultType.FORM


async def test_zeroconf_flow(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zc(rp="ipp/print", UUID="12345678-1234-1234-1234-123456789abc",
                 ty="Acme LaserJet 1000", pdl="application/pdf,image/jpeg"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"]["name"] == "Acme LaserJet 1000"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "host": "192.0.2.10", "port": 443, "path": "/ipp/print", "use_tls": True,
        "user": "anonymous", "password": "", "verify_tls": False,
        "relaxed_ciphers": False,
    }
    assert result["result"].unique_id == "12345678-1234-1234-1234-123456789abc"


async def test_zeroconf_plain_ipp_uses_rp_path_and_no_tls(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zc("_ipp._tcp.local.", port=631, rp="printers/office"),
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["use_tls"] is False
    assert result["data"]["port"] == 631
    assert result["data"]["path"] == "/printers/office"
    # Confirmation uses the probed UUID even when discovery omitted it.
    assert result["result"].unique_id == "12345678-1234-1234-1234-123456789abc"


async def test_zeroconf_already_configured_by_host_aborts(hass):
    MockConfigEntry(
        domain=DOMAIN, data={"host": "192.0.2.10"}, unique_id="192.0.2.10:443"
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zc(UUID="ffffffff-0000-0000-0000-000000000000"),
    )
    assert result["type"] is FlowResultType.ABORT


async def test_zeroconf_confirm_cannot_connect(hass, printer_attrs):
    printer_attrs.side_effect = OSError("refused")
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zc(UUID="12345678-1234-1234-1234-123456789abc"),
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow_roundtrip(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data=USER_INPUT, unique_id="192.0.2.10:443"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.ipp_print.async_setup_entry", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**USER_INPUT, "path": "/printers/office"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["path"] == "/printers/office"
    assert DEFAULT_PRINTER_INFO.formats  # fixture sanity


async def test_discovery_confirmation_prevents_duplicate_probed_uuid(hass):
    MockConfigEntry(
        domain=DOMAIN, data={"host": "192.0.2.99"},
        unique_id="12345678-1234-1234-1234-123456789abc",
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zc(),
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_discovery_allows_separate_queues_on_same_host(hass, printer_attrs):
    printer_attrs.return_value = NAMELESS
    MockConfigEntry(
        domain=DOMAIN,
        data={"host": "192.0.2.10", "port": 631, "path": "/printers/lab"},
        unique_id="192.0.2.10:631/printers/lab",
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zc("_ipp._tcp.local.", port=631, rp="printers/office"),
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "192.0.2.10:631/printers/office"


async def test_discovery_detects_endpoint_in_options(hass):
    MockConfigEntry(
        domain=DOMAIN, data={"host": "192.0.2.99"},
        options={"host": "192.0.2.10", "port": 631, "path": "/printers/office"},
        unique_id="old-identity",
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF},
        data=_zc("_ipp._tcp.local.", port=631, rp="printers/office"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_manual_setup_rejects_legacy_endpoint_duplicate(hass):
    MockConfigEntry(
        domain=DOMAIN, data={"host": "192.0.2.10"}, unique_id="192.0.2.10:443",
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_confirmation_rechecks_legacy_endpoint_added_while_waiting(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF}, data=_zc(),
    )
    MockConfigEntry(
        domain=DOMAIN, data={"host": "192.0.2.10"}, unique_id="192.0.2.10:443",
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
