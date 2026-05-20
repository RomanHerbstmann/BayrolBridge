"""Tests for switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bayrol_pool.const import CHLOR_METHODS, CONF_CHLOR_METHOD, DOMAIN
from custom_components.bayrol_pool.switch import BayrolPoolSwitch, async_setup_entry

pytestmark = pytest.mark.asyncio


async def test_switch_turn_on_off() -> None:
    """Switch toggles call API set_control."""
    coordinator = MagicMock()
    coordinator.client = AsyncMock()
    coordinator.async_request_refresh = AsyncMock()
    coordinator.data = {"ph_dosing": False, "chlorine_dosing": False}

    switch = BayrolPoolSwitch(
        coordinator,
        "entry1",
        "Pool",
        "99",
        "ph",
        "ph_on_off",
    )
    with patch.object(switch, "async_write_ha_state", new_callable=AsyncMock):
        await switch.async_turn_on()
        coordinator.client.set_control.assert_awaited_with("99", "ph", True)
        assert coordinator.data["ph_dosing"] is True

        await switch.async_turn_off()
        coordinator.client.set_control.assert_awaited_with("99", "ph", False)
        assert coordinator.data["ph_dosing"] is False


async def test_setup_entry_none_skips_chlorine_switch(hass) -> None:
    """No chlorine switch when method is none."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {}
    entry.data = {CONF_CHLOR_METHOD: "none"}

    coordinator = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}}

    entities: list[BayrolPoolSwitch] = []

    def _add(new_entities: list[BayrolPoolSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    control_keys = {entity._control_key for entity in entities}
    assert control_keys == {"ph"}
    assert all(
        entity._attr_unique_id == f"42_{entity._control_key}_dosing"
        for entity in entities
    )


async def test_setup_entry_salt_uses_item_540(hass) -> None:
    """Salt method uses item 5.40 for chlorine control."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {}
    entry.data = {CONF_CHLOR_METHOD: "salt"}

    coordinator = MagicMock()
    client = MagicMock()
    client._chlor_method = "salt"
    coordinator.client = client
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}}

    entities: list[BayrolPoolSwitch] = []

    def _add(new_entities: list[BayrolPoolSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    chlor = next(e for e in entities if e._control_key == "chlorine")
    assert CHLOR_METHODS["salt"]["item"] == "5.40"
    assert chlor._attr_unique_id == "42_chlorine_dosing"


async def test_setup_entry_redox_uses_item_5154(hass) -> None:
    """Redox method uses item 5.154 for chlorine control."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {}
    entry.data = {CONF_CHLOR_METHOD: "redox"}

    coordinator = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}}

    entities: list[BayrolPoolSwitch] = []

    def _add(new_entities: list[BayrolPoolSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    assert {e._control_key for e in entities} == {"ph", "chlorine"}
    chlor = next(e for e in entities if e._control_key == "chlorine")
    assert CHLOR_METHODS["redox"]["item"] == "5.154"
    assert chlor._attr_unique_id == "42_chlorine_dosing"
