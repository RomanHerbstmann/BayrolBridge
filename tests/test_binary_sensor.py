"""Tests for binary_sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.bayrol_bridge.binary_sensor import (
    BayrolBridgeAlarmBinary,
    BayrolBridgeConnectivityBinary,
    async_setup_entry,
)
from custom_components.bayrol_bridge.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_entry_no_dosing_active_entities(hass) -> None:
    """Dosing-active binary sensors are no longer created."""
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

    translation_keys = {e._attr_translation_key for e in entities}
    assert "chlorine_dosing_active" not in translation_keys
    assert "ph_dosing_active" not in translation_keys
    assert "connectivity" in translation_keys
    assert "ph_alarm" in translation_keys


def test_alarm_binary_reflects_stat_alarm_only() -> None:
    """Alarm sensor reads coordinator data; stat_warning must not trigger alarm."""
    coordinator = MagicMock()
    coordinator.data = {"pH": 7.1, "pH_alarm": False}

    alarm = BayrolBridgeAlarmBinary(
        coordinator, "entry1", "Pool", "42", "pH", "ph_alarm"
    )
    assert alarm.is_on is False

    coordinator.data["pH_alarm"] = True
    assert alarm.is_on is True


def test_dosing_binary_class_removed() -> None:
    """BayrolBridgeDosingBinary must not exist after cleanup."""
    import custom_components.bayrol_bridge.binary_sensor as mod

    assert not hasattr(mod, "BayrolBridgeDosingBinary")


@pytest.mark.asyncio
async def test_connectivity_binary_unchanged(hass) -> None:
    """Connectivity binary sensor is still set up."""
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

    conn = next(
        e for e in entities if isinstance(e, BayrolBridgeConnectivityBinary)
    )
    assert conn.is_on is True
