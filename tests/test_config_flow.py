"""Config-flow tests."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ipp_print.const import DOMAIN
from custom_components.ipp_print.printer import JobGoneError

USER_INPUT = {
    "host": "192.0.2.10",
    "port": 443,
    "use_tls": True,
    "user": "anonymous",
    "password": "",
    "verify_tls": False,
    "relaxed_ciphers": False,
}


async def test_user_flow_success_on_job_gone_probe(hass):
    """client-error-not-found for job 1 is a *successful* probe."""
    with patch(
        "custom_components.ipp_print.printer.PrinterClient.get_job_attrs",
        new=AsyncMock(side_effect=JobGoneError("no job 1")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "IPP printer at 192.0.2.10"
    assert result["data"]["host"] == "192.0.2.10"


async def test_user_flow_cannot_connect(hass):
    with patch(
        "custom_components.ipp_print.printer.PrinterClient.get_job_attrs",
        new=AsyncMock(side_effect=OSError("no route to host")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_second_entry_blocked(hass):
    MockConfigEntry(
        domain=DOMAIN, data={"host": "192.0.2.10"}, unique_id="192.0.2.10:443"
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # single_config_entry (or duplicate unique_id) must abort the flow.
    assert result["type"] is FlowResultType.ABORT
