"""Tests for config flow."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
import voluptuous as vol
from aioresponses import aioresponses
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.bayrol_bridge.const import (
    BASE_URL,
    CONF_CHLOR_ITEM,
    CONF_CHLOR_METHOD,
    CONF_CID,
    CONF_DOSING_ON,
    CONF_PH_ITEM,
    CONF_PH_MEAS_ITEM,
    CONF_REDOX_MEAS_ITEM,
    DEFAULT_PH_MEAS_ITEM,
    DEFAULT_REDOX_MEAS_ITEM,
    DOMAIN,
)

pytestmark = pytest.mark.asyncio


def _mock_flow_http(
    mocked: aioresponses,
    login_form_html: str,
    plants_html: str,
    device_html: str,
) -> None:
    mocked.get(
        re.compile(rf"{re.escape(BASE_URL)}/.*"),
        body=login_form_html,
        headers={"Set-Cookie": "PHPSESSID=testsession; path=/"},
    )
    mocked.post(
        re.compile(rf"{re.escape(BASE_URL)}/.*login.*"),
        body="<html>OK</html>",
    )
    mocked.get(f"{BASE_URL}/m/plants.php", body=plants_html)
    mocked.get(f"{BASE_URL}/p/device.php?c=42", body=device_html)


async def test_config_flow_success(
    hass,
    login_form_html: str,
    plants_html: str,
    device_html: str,
) -> None:
    """Config flow happy path with chlorine method selection."""
    with aioresponses() as mocked:
        _mock_flow_http(mocked, login_form_html, plants_html, device_html)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "user@example.com", "password": "secret", "scan_interval": 60},
        )
        assert result["type"] == "form"
        assert result["step_id"] == "chlor_method"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CHLOR_METHOD: "redox"},
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Pool Relax"
        assert result["data"]["cid"] == "42"
        assert result["data"][CONF_CHLOR_METHOD] == "redox"


async def test_config_flow_detects_salt_default(
    hass,
    login_form_html: str,
    plants_html: str,
) -> None:
    """Config flow defaults to detected salt method."""
    device_html = '<html><div class="i_item item5_40 i_active"></div></html>'
    with aioresponses() as mocked:
        _mock_flow_http(mocked, login_form_html, plants_html, device_html)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "user@example.com", "password": "secret"},
        )
        assert result["step_id"] == "chlor_method"
        marker = next(
            key
            for key in result["data_schema"].schema
            if isinstance(key, vol.Required) and key.schema == CONF_CHLOR_METHOD
        )
        default = marker.default() if callable(marker.default) else marker.default
        assert default == "salt"


async def test_config_flow_invalid_auth(hass, login_form_html: str) -> None:
    """Config flow reports invalid credentials."""
    with aioresponses() as mocked:
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body=login_form_html,
            headers={"Set-Cookie": "PHPSESSID=testsession; path=/"},
        )
        mocked.post(
            re.compile(rf"{re.escape(BASE_URL)}/.*login.*"),
            body='<html><div class="error_text">Fehler</div></html>',
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "bad", "password": "wrong"},
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"


async def test_config_flow_cannot_connect(hass, login_form_html: str) -> None:
    """Config flow reports connection failure."""
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
        mocked.get(f"{BASE_URL}/m/plants.php", body="<html></html>")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "user", "password": "pass"},
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect"


async def test_config_flow_connection_error(hass) -> None:
    """Config flow handles transport errors."""
    from custom_components.bayrol_bridge.api import BayrolConnectionError

    with patch(
        "custom_components.bayrol_bridge.config_flow.BayrolApiClient.login",
        side_effect=BayrolConnectionError("network down"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "user", "password": "pass"},
        )
        assert result["errors"]["base"] == "cannot_connect"


async def test_reauth_flow_success(
    hass,
    login_form_html: str,
    plants_html: str,
) -> None:
    """Successful reauth updates stored credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "old@example.com",
            CONF_PASSWORD: "old-secret",
            CONF_CID: "42",
            CONF_CHLOR_METHOD: "redox",
        },
    )
    entry.add_to_hass(hass)

    with aioresponses() as mocked:
        _mock_flow_http(mocked, login_form_html, plants_html, device_html="")

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        )
        assert result["type"] == "form"
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "new@example.com", "password": "new-secret"},
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        assert entry.data[CONF_USERNAME] == "new@example.com"
        assert entry.data[CONF_PASSWORD] == "new-secret"


async def test_reauth_flow_invalid_auth(hass, login_form_html: str) -> None:
    """Reauth reports invalid credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_CID: "42",
            CONF_CHLOR_METHOD: "redox",
        },
    )
    entry.add_to_hass(hass)

    with aioresponses() as mocked:
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body=login_form_html,
            headers={"Set-Cookie": "PHPSESSID=testsession; path=/"},
        )
        mocked.post(
            re.compile(rf"{re.escape(BASE_URL)}/.*login.*"),
            body='<html><div class="error_text">Fehler</div></html>',
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "bad", "password": "wrong"},
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"


async def test_options_flow_saves_overrides_and_strips_empty(hass) -> None:
    """Options flow persists overrides; empty fields are not stored."""
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

    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as mock_reload:
        options_flow = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            options_flow["flow_id"],
            {
                CONF_CHLOR_METHOD: "none",
                CONF_CHLOR_ITEM: "5.40",
                CONF_PH_ITEM: "5.77",
                CONF_DOSING_ON: "1.1",
                "dosing_off": "",
            },
        )
        assert result["type"] == "create_entry"
        assert entry.options[CONF_CHLOR_METHOD] == "none"
        assert entry.options[CONF_CHLOR_ITEM] == "5.40"
        assert entry.options[CONF_PH_ITEM] == "5.77"
        assert entry.options[CONF_DOSING_ON] == "1.1"
        assert "dosing_off" not in entry.options
        mock_reload.assert_awaited_once_with(entry.entry_id)


async def test_options_flow_saves_meas_items_and_empty_uses_default(hass) -> None:
    """Options flow persists pH/redox measurement items; empty fields are omitted."""
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

    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ):
        options_flow = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            options_flow["flow_id"],
            {
                CONF_CHLOR_METHOD: "redox",
                CONF_PH_MEAS_ITEM: "9.9",
                CONF_REDOX_MEAS_ITEM: "8.8",
            },
        )
        assert result["type"] == "create_entry"
        assert entry.options[CONF_PH_MEAS_ITEM] == "9.9"
        assert entry.options[CONF_REDOX_MEAS_ITEM] == "8.8"

        options_flow = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            options_flow["flow_id"],
            {
                CONF_CHLOR_METHOD: "redox",
                CONF_PH_MEAS_ITEM: "   ",
                CONF_REDOX_MEAS_ITEM: "",
            },
        )
        assert result["type"] == "create_entry"
        assert CONF_PH_MEAS_ITEM not in entry.options
        assert CONF_REDOX_MEAS_ITEM not in entry.options

    from custom_components.bayrol_bridge.const import resolve_meas_items

    _, ph, redox = resolve_meas_items(entry.data, entry.options)
    assert ph == DEFAULT_PH_MEAS_ITEM
    assert redox == DEFAULT_REDOX_MEAS_ITEM


async def test_options_flow_changes_method_and_reloads(hass) -> None:
    """Options flow updates chlor method and reloads entry."""
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

    with patch.object(
        hass.config_entries, "async_reload", new_callable=AsyncMock
    ) as mock_reload:
        options_flow = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            options_flow["flow_id"],
            {CONF_CHLOR_METHOD: "none"},
        )
        assert result["type"] == "create_entry"
        assert entry.options[CONF_CHLOR_METHOD] == "none"
        mock_reload.assert_awaited_once_with(entry.entry_id)
