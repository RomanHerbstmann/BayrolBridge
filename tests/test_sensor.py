"""Tests for sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.bayrol_bridge.const import DOMAIN
from custom_components.bayrol_bridge.sensor import BayrolBridgeSensor


def _sensor(item: str, scale: float) -> BayrolBridgeSensor:
    coordinator = MagicMock()
    coordinator.data = {"connectivity": True, "items": {}}
    coordinator.last_update_success = True
    return BayrolBridgeSensor(
        coordinator,
        "entry1",
        "Pool",
        "42",
        item,
        scale,
        "ph",
        None,
        None,
        None,
        None,
    )


def test_read_scaled_ph() -> None:
    """pH raw 72 scales to 7.2."""
    sensor = _sensor("4.2", 0.1)
    sensor.coordinator.data["items"]["4.2"] = "72"
    assert sensor._read_scaled() == 7.2


def test_read_scaled_redox() -> None:
    """Redox raw 775 stays 775.0."""
    sensor = _sensor("4.82", 1.0)
    sensor.coordinator.data["items"]["4.82"] = 775
    assert sensor._read_scaled() == 775.0


def test_read_scaled_temperature() -> None:
    """Temperature raw 17.2 stays 17.2."""
    sensor = _sensor("1", 1.0)
    sensor.coordinator.data["items"]["1"] = "17.2"
    assert sensor._read_scaled() == 17.2


def test_read_scaled_missing_or_invalid() -> None:
    """Missing or invalid item values return None."""
    sensor = _sensor("4.2", 0.1)
    assert sensor._read_scaled() is None
    sensor.coordinator.data["items"]["4.2"] = "n/a"
    assert sensor._read_scaled() is None


def test_sensor_available_false_when_offline() -> None:
    """Sensor unavailable when connectivity is false."""
    sensor = _sensor("1", 1.0)
    sensor.coordinator.data["connectivity"] = False
    assert sensor.available is False


def test_sensor_available_true_when_connected() -> None:
    """Sensor available when MQTT is connected."""
    sensor = _sensor("1", 1.0)
    assert sensor.available is True


@pytest.mark.asyncio
async def test_setup_entry_uses_meas_items(hass) -> None:
    """Sensors bind to configured measurement items."""
    from custom_components.bayrol_bridge.sensor import async_setup_entry

    entry = MagicMock()
    entry.entry_id = "entry1"
    entry.options = {"ph_meas_item": "9.9", "redox_meas_item": "8.8"}
    entry.data = {}

    coordinator = MagicMock()
    hass.data = {
        DOMAIN: {"entry1": {"coordinator": coordinator, "device_name": "Pool", "cid": "42"}}
    }

    entities: list = []

    def _add(new_entities: list) -> None:
        entities.extend(new_entities)

    await async_setup_entry(hass, entry, _add)

    items = {e._item for e in entities}
    assert "1" in items
    assert "9.9" in items
    assert "8.8" in items
