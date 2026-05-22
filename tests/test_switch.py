"""Tests for switch platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.bayrol_bridge.const import (
    CHLOR_METHODS,
    CONF_CHLOR_ITEM,
    CONF_CHLOR_METHOD,
    CONF_PH_ITEM,
    DATA_CONNECTIVITY,
    DOMAIN,
    DOSING_OFF,
    DOSING_ON,
    PH_ITEM,
    resolve_controls,
)
from custom_components.bayrol_bridge.switch import BayrolBridgeSwitch, async_setup_entry


def _make_switch(
    coordinator: MagicMock,
    *,
    item: str = PH_ITEM,
    value_on: str = DOSING_ON,
    value_off: str = DOSING_OFF,
) -> BayrolBridgeSwitch:
    return BayrolBridgeSwitch(
        coordinator,
        "entry1",
        "Pool",
        "99",
        "ph",
        item,
        value_on,
        value_off,
    )


def test_switch_is_on_from_mqtt_items() -> None:
    """is_on reflects coordinator items[item] vs value_on/value_off."""
    coordinator = MagicMock()
    coordinator.data = {
        "items": {PH_ITEM: DOSING_ON},
    }
    switch = _make_switch(coordinator)
    assert switch.is_on is True

    coordinator.data = {"items": {PH_ITEM: DOSING_OFF}}
    assert switch.is_on is False

    coordinator.data = {"items": {}}
    assert switch.is_on is None

    coordinator.data = {"items": {PH_ITEM: "99.99"}}
    assert switch.is_on is None


@pytest.mark.asyncio
async def test_switch_async_set_mqtt() -> None:
    """_async_set publishes via mqtt.async_set with on/off values."""
    coordinator = MagicMock()
    coordinator.mqtt = AsyncMock()
    switch = _make_switch(coordinator)

    await switch._async_set(True)
    coordinator.mqtt.async_set.assert_awaited_with(PH_ITEM, DOSING_ON)

    await switch._async_set(False)
    coordinator.mqtt.async_set.assert_awaited_with(PH_ITEM, DOSING_OFF)


@pytest.mark.asyncio
async def test_switch_async_set_no_mqtt_raises() -> None:
    """_async_set raises when MQTT client is not connected."""
    coordinator = MagicMock()
    coordinator.mqtt = None
    switch = _make_switch(coordinator)

    with pytest.raises(HomeAssistantError, match="MQTT not connected"):
        await switch._async_set(True)


@pytest.mark.asyncio
async def test_switch_turn_on_off_no_set_control() -> None:
    """Turn on/off use MQTT only; client.set_control is never called."""
    coordinator = MagicMock()
    coordinator.mqtt = AsyncMock()
    coordinator.client = AsyncMock()
    switch = _make_switch(coordinator)

    await switch.async_turn_on()
    coordinator.mqtt.async_set.assert_awaited_with(PH_ITEM, DOSING_ON)
    coordinator.client.set_control.assert_not_called()

    await switch.async_turn_off()
    coordinator.mqtt.async_set.assert_awaited_with(PH_ITEM, DOSING_OFF)
    coordinator.client.set_control.assert_not_called()


def test_switch_available_offline() -> None:
    """Switch unavailable when coordinator failed or device offline."""
    coordinator = MagicMock()
    coordinator.last_update_success = False
    coordinator.data = {DATA_CONNECTIVITY: False}

    switch = _make_switch(coordinator)
    assert switch.available is False

    coordinator.last_update_success = True
    coordinator.data = {DATA_CONNECTIVITY: False}
    assert switch.available is False

    coordinator.data = {DATA_CONNECTIVITY: True}
    assert switch.available is True


@pytest.mark.asyncio
async def test_setup_entry_none_skips_chlorine_switch(hass) -> None:
    """No chlorine switch when method is none."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {}
    entry.data = {CONF_CHLOR_METHOD: "none"}

    coordinator = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}}

    entities: list[BayrolBridgeSwitch] = []

    def _add(new_entities: list[BayrolBridgeSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    control_keys = {entity._control_key for entity in entities}
    assert control_keys == {"ph"}
    assert all(
        entity._attr_unique_id == f"42_{entity._control_key}_dosing"
        for entity in entities
    )


@pytest.mark.asyncio
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

    entities: list[BayrolBridgeSwitch] = []

    def _add(new_entities: list[BayrolBridgeSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    chlor = next(e for e in entities if e._control_key == "chlorine")
    assert CHLOR_METHODS["salt"]["item"] == "5.40"
    assert chlor._item == "5.40"
    assert chlor._attr_unique_id == "42_chlorine_dosing"


@pytest.mark.asyncio
async def test_setup_entry_redox_uses_item_5154(hass) -> None:
    """Redox method uses item 5.154 for chlorine control."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {}
    entry.data = {CONF_CHLOR_METHOD: "redox"}

    coordinator = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}}

    entities: list[BayrolBridgeSwitch] = []

    def _add(new_entities: list[BayrolBridgeSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    assert {e._control_key for e in entities} == {"ph", "chlorine"}
    chlor = next(e for e in entities if e._control_key == "chlorine")
    assert CHLOR_METHODS["redox"]["item"] == "5.154"
    assert chlor._item == "5.154"
    assert chlor._attr_unique_id == "42_chlorine_dosing"


@pytest.mark.asyncio
async def test_setup_entry_chlor_item_override_with_none_method(hass) -> None:
    """Chlor item override enables chlorine switch when method is none."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {CONF_CHLOR_METHOD: "none", CONF_CHLOR_ITEM: "5.40"}
    entry.data = {}

    coordinator = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}}

    entities: list[BayrolBridgeSwitch] = []

    def _add(new_entities: list[BayrolBridgeSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    assert {e._control_key for e in entities} == {"ph", "chlorine"}
    assert resolve_controls(entry.data, entry.options)["chlorine"]["item"] == "5.40"
    assert all(
        e._attr_unique_id == f"42_{e._control_key}_dosing" for e in entities
    )


@pytest.mark.asyncio
async def test_setup_entry_ph_item_override(hass) -> None:
    """Options ph_item is used for control resolution."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {CONF_PH_ITEM: "5.77"}
    entry.data = {CONF_CHLOR_METHOD: "none"}

    coordinator = MagicMock()
    hass.data = {DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}}

    entities: list[BayrolBridgeSwitch] = []

    def _add(new_entities: list[BayrolBridgeSwitch]) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    assert resolve_controls(entry.data, entry.options)["ph"]["item"] == "5.77"
    assert entities[0]._item == "5.77"
    assert entities[0]._attr_unique_id == "42_ph_dosing"
