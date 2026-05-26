"""Tests for MQTT push coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.bayrol_bridge.api import (
    BayrolApiClient,
    BayrolAuthError,
    BayrolConnectionError,
)
from custom_components.bayrol_bridge.coordinator import BayrolBridgeCoordinator

pytestmark = pytest.mark.asyncio

_ITEMS = ["4.2", "5.42", "5.154"]
_CODE = "APP-LINK-123"
_CID = "cid-99"


def _make_coordinator(
    hass,
    client: BayrolApiClient | None = None,
    *,
    access_code: str | None = _CODE,
) -> BayrolBridgeCoordinator:
    if client is None:
        client = MagicMock(spec=BayrolApiClient)
        client.login = AsyncMock()
        client.async_fetch_mqtt_credentials = AsyncMock(
            return_value=("token123", "SERIAL1")
        )
        client.async_fetch_mqtt_credentials_auto = AsyncMock(
            return_value=("token123", "SERIAL1")
        )
    return BayrolBridgeCoordinator(
        hass,
        client,
        _ITEMS,
        access_code,
        _CID,
        "user",
        "pass",
    )


async def test_handle_value_updates_state_and_notifies(hass) -> None:
    """handle_value stores item value, sets connectivity, and notifies."""
    coordinator = _make_coordinator(hass)
    listener = MagicMock()
    coordinator.async_add_listener(listener)

    coordinator.handle_value("5.42", "19.17")

    assert coordinator.data["items"]["5.42"] == "19.17"
    assert coordinator.data["connectivity"] is True
    listener.assert_called_once()


async def test_handle_connection_change_sets_connectivity_false(hass) -> None:
    """Connection loss marks coordinator offline."""
    coordinator = _make_coordinator(hass)
    coordinator.handle_value("5.42", "19.17")
    listener = MagicMock()
    coordinator.async_add_listener(listener)

    coordinator.handle_connection_change(False)

    assert coordinator.data["connectivity"] is False
    assert coordinator.data["items"]["5.42"] == "19.17"
    listener.assert_called_once()


async def test_async_start_fetches_credentials_connects_and_requests(hass) -> None:
    """async_start logs in, connects MQTT, and requests each item."""
    client = MagicMock(spec=BayrolApiClient)
    client.login = AsyncMock()
    client.async_fetch_mqtt_credentials = AsyncMock(return_value=("tok", "SN"))
    coordinator = _make_coordinator(hass, client)

    mock_mqtt = MagicMock()
    mock_mqtt.async_connect = AsyncMock()

    with patch(
        "custom_components.bayrol_bridge.coordinator.BayrolMqttClient",
        return_value=mock_mqtt,
    ) as mock_cls:
        await coordinator.async_start()

    client.login.assert_awaited_once_with("user", "pass")
    client.async_fetch_mqtt_credentials.assert_awaited_once_with(_CODE)
    mock_cls.assert_called_once()
    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs["request_items"] == _ITEMS
    assert call_kwargs["token_provider"] == coordinator._provide_token
    mock_mqtt.async_connect.assert_awaited_once()
    assert coordinator.data["connectivity"] is True


async def test_async_start_without_code_uses_auto_path(hass) -> None:
    """Missing manual access code uses device.php auto credentials."""
    client = MagicMock(spec=BayrolApiClient)
    client.login = AsyncMock()
    client.async_fetch_mqtt_credentials_auto = AsyncMock(return_value=("tok", "SN"))
    coordinator = _make_coordinator(hass, client, access_code=None)

    mock_mqtt = MagicMock()
    mock_mqtt.async_connect = AsyncMock()

    with patch(
        "custom_components.bayrol_bridge.coordinator.BayrolMqttClient",
        return_value=mock_mqtt,
    ):
        await coordinator.async_start()

    client.login.assert_awaited_once_with("user", "pass")
    client.async_fetch_mqtt_credentials.assert_not_called()
    client.async_fetch_mqtt_credentials_auto.assert_awaited_once_with(_CID)


async def test_provide_token_prefers_manual_code(hass) -> None:
    """Token refresh with manual code skips auto fetch."""
    client = MagicMock(spec=BayrolApiClient)
    client.login = AsyncMock()
    client.async_fetch_mqtt_credentials = AsyncMock(return_value=("tok", "SN"))
    client.async_fetch_mqtt_credentials_auto = AsyncMock()
    coordinator = _make_coordinator(hass, client)

    token, serial = await coordinator._provide_token()

    assert (token, serial) == ("tok", "SN")
    client.async_fetch_mqtt_credentials.assert_awaited_once_with(_CODE)
    client.async_fetch_mqtt_credentials_auto.assert_not_called()


async def test_provide_token_without_code_uses_auto(hass) -> None:
    """Token refresh without manual code uses device.php."""
    client = MagicMock(spec=BayrolApiClient)
    client.login = AsyncMock()
    client.async_fetch_mqtt_credentials = AsyncMock()
    client.async_fetch_mqtt_credentials_auto = AsyncMock(return_value=("tok", "SN"))
    coordinator = _make_coordinator(hass, client, access_code=None)

    token, serial = await coordinator._provide_token()

    assert (token, serial) == ("tok", "SN")
    client.async_fetch_mqtt_credentials_auto.assert_awaited_once_with(_CID)
    client.async_fetch_mqtt_credentials.assert_not_called()


async def test_async_start_auth_error_raises_config_entry_auth_failed(hass) -> None:
    """BayrolAuthError during credential fetch becomes ConfigEntryAuthFailed."""
    client = MagicMock(spec=BayrolApiClient)
    client.login = AsyncMock()
    client.async_fetch_mqtt_credentials = AsyncMock(
        side_effect=BayrolAuthError("bad code")
    )
    coordinator = _make_coordinator(hass, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator.async_start()


async def test_async_start_connection_error_raises_not_ready(hass) -> None:
    """BayrolConnectionError during MQTT connect becomes ConfigEntryNotReady."""
    client = MagicMock(spec=BayrolApiClient)
    client.login = AsyncMock()
    client.async_fetch_mqtt_credentials = AsyncMock(return_value=("tok", "SN"))
    coordinator = _make_coordinator(hass, client)

    mock_mqtt = MagicMock()
    mock_mqtt.async_connect = AsyncMock(
        side_effect=BayrolConnectionError("MQTT connection timeout")
    )

    with patch(
        "custom_components.bayrol_bridge.coordinator.BayrolMqttClient",
        return_value=mock_mqtt,
    ):
        with pytest.raises(ConfigEntryNotReady, match="timeout"):
            await coordinator.async_start()


async def test_async_stop_disconnects_and_marks_offline(hass) -> None:
    """async_stop disconnects MQTT and clears connectivity."""
    coordinator = _make_coordinator(hass)
    mock_mqtt = MagicMock()
    mock_mqtt.async_stop = AsyncMock()
    coordinator._mqtt = mock_mqtt
    coordinator.handle_connection_change(True)

    await coordinator.async_stop()

    mock_mqtt.async_stop.assert_awaited_once()
    assert coordinator.mqtt is None
    assert coordinator.data["connectivity"] is False
