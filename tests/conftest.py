"""Shared fixtures."""
from unittest.mock import AsyncMock, patch

import pytest


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
