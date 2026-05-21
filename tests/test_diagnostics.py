"""Tests for config entry diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.bayrol_bridge.const import (
    CONF_CID,
    CONF_CHLOR_METHOD,
    CONF_DEBUG_HTML,
    DOMAIN,
)
from custom_components.bayrol_bridge.diagnostics import async_get_config_entry_diagnostics

pytestmark = pytest.mark.asyncio


async def test_diagnostics_redacts_credentials_and_includes_device_items(
    hass,
) -> None:
    """Diagnostics redact username/password and include device_items."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_CID: "42",
            CONF_CHLOR_METHOD: "redox",
        },
        options={},
    )
    entry.add_to_hass(hass)

    device_items = [
        {"item": "5.42", "css": "item5_42", "state": "active", "classes": []},
        {"item": "5.154", "css": "item5_154", "state": "inactive", "classes": []},
    ]
    client = MagicMock()
    client.async_list_device_items = AsyncMock(return_value=device_items)
    coordinator = MagicMock()
    coordinator.data = {"pH": 7.2, "status": "online"}

    hass.data[DOMAIN] = {
        entry.entry_id: {
            "client": client,
            "coordinator": coordinator,
            "cid": "42",
        }
    }

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["options"]["username"] == "**REDACTED**"
    assert result["options"]["password"] == "**REDACTED**"
    assert result["device_items"] == device_items
    assert result["device_html_debug"] is None
    assert result["raw_getdata"] is None
    assert result["data_json_probes"] is None
    assert "effective_controls" in result
    assert result["coordinator_data"] == coordinator.data
    client.async_list_device_items.assert_awaited_once_with("42")
    client.async_get_device_html_debug.assert_not_called()
    client.async_get_raw_getdata.assert_not_called()
    client.async_probe_data_json.assert_not_called()


async def test_diagnostics_includes_html_debug_when_enabled(hass) -> None:
    """Diagnostics include sanitized HTML excerpt when debug option is on."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_CID: "42",
            CONF_CHLOR_METHOD: "redox",
        },
        options={CONF_DEBUG_HTML: True},
    )
    entry.add_to_hass(hass)

    html_debug = [
        {"tag": "div", "class": ["tab_box"], "id": None, "text": "pH 7.1"},
    ]
    client = MagicMock()
    client.async_list_device_items = AsyncMock(return_value=[])
    client.async_get_device_html_debug = AsyncMock(return_value=html_debug)
    client.async_get_raw_getdata = AsyncMock(return_value="<getdata/>")
    client.async_probe_data_json = AsyncMock(
        return_value=[{"sent": {"action": "getItems"}, "status": 200, "body_excerpt": "{}"}]
    )
    coordinator = MagicMock()
    coordinator.data = {"pH": 7.2, "status": "online"}

    hass.data[DOMAIN] = {
        entry.entry_id: {
            "client": client,
            "coordinator": coordinator,
            "cid": "42",
        }
    }

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["device_html_debug"] == html_debug
    assert result["raw_getdata"] == "<getdata/>"
    assert len(result["data_json_probes"]) == 1
    assert result["options"]["password"] == "**REDACTED**"
    assert result["options"]["username"] == "**REDACTED**"
    dumped = str(result["device_html_debug"])
    assert "secret" not in dumped
    assert "password" not in dumped
    client.async_get_device_html_debug.assert_awaited_once_with("42")
    client.async_get_raw_getdata.assert_awaited_once_with("42")
    client.async_probe_data_json.assert_awaited_once_with("42")
