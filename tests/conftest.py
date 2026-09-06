"""Shared fixtures."""
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ipp_print.printer import PrinterInfo

DEFAULT_PRINTER_INFO = PrinterInfo(
    name="TestPrinter",
    info="Test Printer",
    location=None,
    make_and_model="Acme LaserJet 1000",
    uuid="urn:uuid:12345678-1234-1234-1234-123456789abc",
    formats=["application/pdf", "image/jpeg", "image/png"],
    sides=["one-sided", "two-sided-long-edge"],
    copies_max=99,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow loading custom_components/ipp_print in tests."""
    return


@pytest.fixture(autouse=True)
def no_lovelace_sync():
    """The real sync busy-waits up to 60s for lovelace data; never in tests."""
    with patch(
        "custom_components.ipp_print._sync_lovelace_resource", new=AsyncMock()
    ):
        yield


@pytest.fixture(autouse=True)
def printer_attrs():
    """Setup probes the printer; answer with a canned PrinterInfo."""
    with patch(
        "custom_components.ipp_print.printer.PrinterClient.get_printer_attrs",
        new=AsyncMock(return_value=DEFAULT_PRINTER_INFO),
    ) as mock:
        yield mock
