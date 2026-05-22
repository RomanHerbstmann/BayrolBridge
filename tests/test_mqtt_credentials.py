"""Tests for MQTT credential fetch via /api/."""

from __future__ import annotations

import json

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.bayrol_bridge.api import (
    BayrolApiClient,
    BayrolAuthError,
    BayrolConnectionError,
)
from custom_components.bayrol_bridge.const import API_CODE_PATH, MQTT_HOST

pytestmark = pytest.mark.asyncio

_CREDENTIALS_URL = f"https://{MQTT_HOST}{API_CODE_PATH}?code=APP123"


async def test_async_fetch_mqtt_credentials_success() -> None:
    """Valid JSON returns access token and device serial."""
    with aioresponses() as mocked:
        mocked.get(
            _CREDENTIALS_URL,
            body=json.dumps(
                {
                    "accessToken": "a" * 32,
                    "deviceSerial": "POOL-001",
                }
            ),
        )
        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            token, serial = await client.async_fetch_mqtt_credentials("APP123")

    assert token == "a" * 32
    assert serial == "POOL-001"


async def test_async_fetch_mqtt_credentials_incomplete_json() -> None:
    """Missing token or serial raises BayrolAuthError."""
    with aioresponses() as mocked:
        mocked.get(
            _CREDENTIALS_URL,
            body=json.dumps({"accessToken": "only-token"}),
        )
        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            with pytest.raises(BayrolAuthError, match="incomplete"):
                await client.async_fetch_mqtt_credentials("APP123")


async def test_async_fetch_mqtt_credentials_http_error() -> None:
    """Non-200 response raises BayrolAuthError."""
    with aioresponses() as mocked:
        mocked.get(_CREDENTIALS_URL, status=404, body="not found")
        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            with pytest.raises(BayrolAuthError, match="404"):
                await client.async_fetch_mqtt_credentials("APP123")


async def test_async_fetch_mqtt_credentials_invalid_json() -> None:
    """Non-JSON body raises BayrolConnectionError."""
    with aioresponses() as mocked:
        mocked.get(_CREDENTIALS_URL, body="not-json")
        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            with pytest.raises(BayrolConnectionError, match="JSON"):
                await client.async_fetch_mqtt_credentials("APP123")
