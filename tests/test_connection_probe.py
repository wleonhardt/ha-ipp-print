"""The connection check requests small status attributes, without changing jobs."""
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ipp_print.printer import IppError, PrinterClient


def _resp(status):
    return b"\x02\x00" + status.to_bytes(2, "big") + b"\x00\x00\x00\x01\x03"


@pytest.fixture
def printer_status():
    """Use the real status method in this focused test module."""
    yield


async def test_connection_probe_requests_status_only():
    client = PrinterClient(host="printer")
    with patch.object(client, "_probe", AsyncMock(return_value=_resp(0))) as probe:
        await client.get_connection_status()
    request = probe.call_args.args[0]
    assert b"printer-state" in request
    assert b"printer-is-accepting-jobs" in request
    assert b"media-col" not in request and b"document-format" not in request
    assert request[2:4] == b"\x00\x0b"  # Get-Printer-Attributes


@pytest.mark.parametrize("reply", [_resp(0x0403), b"<html>login</html>"])
async def test_connection_probe_rejects_errors_or_non_protocol_reply(reply):
    client = PrinterClient(host="printer")
    with patch.object(client, "_probe", AsyncMock(return_value=reply)):
        with pytest.raises((IppError, ValueError)):
            await client.get_connection_status()
