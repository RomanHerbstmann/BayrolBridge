"""Tests for binary_sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.bayrol_bridge.binary_sensor import (
    BayrolBridgeConnectivityBinary,
    async_setup_entry,
)
from custom_components.bayrol_bridge.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_entry_only_connectivity(hass) -> None:
    """Only connectivity binary sensor is created (alarms removed)."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {}
    entry.data = {}

    coordinator = MagicMock()
    hass.data = {
        DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}
    }

    entities: list = []

    def _add(new_entities: list) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    assert len(entities) == 1
    assert isinstance(entities[0], BayrolBridgeConnectivityBinary)
    assert entities[0]._attr_translation_key == "connectivity"


def test_alarm_binary_class_removed() -> None:
    """BayrolBridgeAlarmBinary must not exist after MQTT migration."""
    import custom_components.bayrol_bridge.binary_sensor as mod

    assert not hasattr(mod, "BayrolBridgeAlarmBinary")


@pytest.mark.asyncio
async def test_connectivity_binary_unchanged(hass) -> None:
    """Connectivity binary sensor reflects coordinator connectivity."""
    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {}
    entry.data = {}

    coordinator = MagicMock()
    coordinator.data = {"connectivity": True}
    coordinator.last_update_success = True
    hass.data = {
        DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}
    }

    entities: list = []

    def _add(new_entities: list) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    conn = entities[0]
    assert conn.is_on is True
