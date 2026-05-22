"""Tests for config entry diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.bayrol_bridge.const import (
    CONF_ACCESS_CODE,
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
    assert result["get_items_probe"] is None
    assert result["access_probe"] is None
    assert "effective_controls" in result
    assert result["coordinator_data"] == coordinator.data
    client.async_list_device_items.assert_awaited_once_with("42")
    client.async_get_device_html_debug.assert_not_called()
    client.async_get_raw_getdata.assert_not_called()
    client.async_probe_data_json.assert_not_called()
    client.async_probe_get_items.assert_not_called()
    client.async_probe_access.assert_not_called()


async def test_diagnostics_access_probe_none_without_code_or_debug(hass) -> None:
    """access_probe stays None without debug or without access code."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_CID: "42",
            CONF_CHLOR_METHOD: "redox",
        },
        options={CONF_ACCESS_CODE: "link-code"},
    )
    entry.add_to_hass(hass)

    client = MagicMock()
    client.async_list_device_items = AsyncMock(return_value=[])
    coordinator = MagicMock()
    coordinator.data = {}

    hass.data[DOMAIN] = {
        entry.entry_id: {
            "client": client,
            "coordinator": coordinator,
            "cid": "42",
        }
    }

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["access_probe"] is None
    assert result["options"]["access_code"] == "**REDACTED**"
    client.async_probe_access.assert_not_called()


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
        options={CONF_DEBUG_HTML: True, CONF_ACCESS_CODE: "device-link-42"},
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
    client.async_probe_get_items = AsyncMock(
        return_value={
            "sent_topics": ["5.42", "5.154"],
            "status": 200,
            "body_excerpt": '{"error":""}',
        }
    )
    client.async_probe_access = AsyncMock(
        return_value=[
            {"action": "getAccess", "had_code": False, "status": 403, "body_excerpt": ""},
        ]
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
    assert result["get_items_probe"]["status"] == 200
    assert result["access_probe"][0]["action"] == "getAccess"
    assert result["options"]["password"] == "**REDACTED**"
    assert result["options"]["username"] == "**REDACTED**"
    assert result["options"]["access_code"] == "**REDACTED**"
    dumped = str(result)
    assert "secret" not in dumped
    assert "device-link-42" not in dumped
    client.async_get_device_html_debug.assert_awaited_once_with("42")
    client.async_get_raw_getdata.assert_awaited_once_with("42")
    client.async_probe_data_json.assert_awaited_once_with("42")
    client.async_probe_get_items.assert_awaited_once_with("42")
    client.async_probe_access.assert_awaited_once_with("42", "device-link-42")


async def test_diagnostics_access_probe_none_when_debug_without_code(hass) -> None:
    """Debug on but no access code: access_probe stays None."""
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

    client = MagicMock()
    client.async_list_device_items = AsyncMock(return_value=[])
    client.async_get_device_html_debug = AsyncMock(return_value=[])
    client.async_get_raw_getdata = AsyncMock(return_value="")
    client.async_probe_data_json = AsyncMock(return_value=[])
    client.async_probe_get_items = AsyncMock(return_value={})
    client.async_probe_access = AsyncMock()
    coordinator = MagicMock()
    coordinator.data = {}

    hass.data[DOMAIN] = {
        entry.entry_id: {
            "client": client,
            "coordinator": coordinator,
            "cid": "42",
        }
    }

    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["access_probe"] is None
    client.async_probe_access.assert_not_called()
