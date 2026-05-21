"""Tests for data coordinator."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aioresponses import aioresponses
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.bayrol_bridge.api import (
    BayrolApiClient,
    BayrolAuthError,
    BayrolConnectionError,
)
from custom_components.bayrol_bridge.const import BASE_URL
from custom_components.bayrol_bridge.coordinator import BayrolBridgeCoordinator

pytestmark = pytest.mark.asyncio


async def test_coordinator_update(
    hass,
    login_form_html: str,
    pool_data_html: str,
    device_html: str,
) -> None:
    """Coordinator fetches and exposes pool data."""
    with aioresponses() as mocked:
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body=login_form_html,
            headers={"Set-Cookie": "PHPSESSID=testsession; path=/"},
        )
        mocked.post(
            re.compile(rf"{re.escape(BASE_URL)}/.*login.*"),
            body="<html>OK</html>",
        )
        mocked.get(f"{BASE_URL}/getdata.php?cid=7", body=pool_data_html)
        mocked.get(f"{BASE_URL}/p/device.php?c=7", body=device_html)

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user", "pass")
            coordinator = BayrolBridgeCoordinator(hass, client, "7", 60)
            await coordinator.async_refresh()

        assert coordinator.data is not None
        assert coordinator.data["pH"] == 7.2
        assert coordinator.data["connectivity"] is True


async def test_coordinator_maps_auth_error(hass) -> None:
    """BayrolAuthError becomes ConfigEntryAuthFailed."""
    client = BayrolApiClient(AsyncMock())
    client.fetch_pool_data = AsyncMock(side_effect=BayrolAuthError("bad creds"))
    coordinator = BayrolBridgeCoordinator(hass, client, "7", 60)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_maps_connection_error(hass) -> None:
    """BayrolConnectionError becomes UpdateFailed."""
    client = BayrolApiClient(AsyncMock())
    client.fetch_pool_data = AsyncMock(
        side_effect=BayrolConnectionError("network down")
    )
    coordinator = BayrolBridgeCoordinator(hass, client, "7", 60)

    with pytest.raises(UpdateFailed, match="network down"):
        await coordinator._async_update_data()
