"""Tests for app-link code parsing from device.php."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from custom_components.bayrol_bridge.api import (
    BayrolApiClient,
    BayrolConnectionError,
)

pytestmark = pytest.mark.asyncio

_CID = "controller-42"
_IFRAME_HTML = (
    '<iframe src="../../app/index.html?code=A-VeVLGX&direct" name="d"></iframe>'
)
_CREDENTIALS = ("mqtt-token", "SERIAL-1")


async def test_async_fetch_app_code_parses_iframe() -> None:
    """Device HTML with iframe yields the app-link code."""
    async with aiohttp.ClientSession() as session:
        client = BayrolApiClient(session)
        with patch.object(
            client, "_fetch_device_html", AsyncMock(return_value=_IFRAME_HTML)
        ):
            code = await client.async_fetch_app_code(_CID)

    assert code == "A-VeVLGX"


async def test_async_fetch_app_code_missing_raises() -> None:
    """HTML without app-link code raises BayrolConnectionError."""
    async with aiohttp.ClientSession() as session:
        client = BayrolApiClient(session)
        with patch.object(
            client, "_fetch_device_html", AsyncMock(return_value="<html></html>")
        ):
            with pytest.raises(BayrolConnectionError, match="device.php"):
                await client.async_fetch_app_code(_CID)


async def test_async_fetch_mqtt_credentials_auto() -> None:
    """Auto path parses code then fetches MQTT credentials."""
    async with aiohttp.ClientSession() as session:
        client = BayrolApiClient(session)
        with (
            patch.object(
                client, "async_fetch_app_code", AsyncMock(return_value="A-VeVLGX")
            ) as mock_code,
            patch.object(
                client,
                "async_fetch_mqtt_credentials",
                AsyncMock(return_value=_CREDENTIALS),
            ) as mock_creds,
        ):
            result = await client.async_fetch_mqtt_credentials_auto(_CID)

    assert result == _CREDENTIALS
    mock_code.assert_awaited_once_with(_CID)
    mock_creds.assert_awaited_once_with("A-VeVLGX")
