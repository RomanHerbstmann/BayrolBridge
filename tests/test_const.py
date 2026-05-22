"""Tests for control resolution helpers."""

from __future__ import annotations

from custom_components.bayrol_bridge.const import (
    CONF_CHLOR_ITEM,
    CONF_CHLOR_METHOD,
    CONF_DOSING_OFF,
    CONF_DOSING_ON,
    CONF_PH_ITEM,
    DOSING_OFF,
    DOSING_ON,
    MEASUREMENT_MQTT_ITEMS,
    PH_ITEM,
    get_controls,
    resolve_controls,
    resolve_mqtt_items,
)


def test_get_controls_applies_overrides() -> None:
    """ph_item and dosing values override defaults."""
    controls = get_controls(
        "redox",
        ph_item="5.99",
        dosing_on="1.1",
        dosing_off="2.2",
    )
    assert controls["ph"]["item"] == "5.99"
    assert controls["ph"]["value_on"] == "1.1"
    assert controls["ph"]["value_off"] == "2.2"
    assert controls["chlorine"]["item"] == "5.154"


def test_get_controls_empty_chlor_item_uses_method() -> None:
    """Empty chlor_item falls back to method item."""
    controls = get_controls("salt", chlor_item="")
    assert controls["chlorine"]["item"] == "5.40"


def test_get_controls_chlor_item_overrides_none_method() -> None:
    """Set chlor_item creates chlorine control even when method is none."""
    controls = get_controls("none", chlor_item="5.154")
    assert "chlorine" in controls
    assert controls["chlorine"]["item"] == "5.154"


def test_get_controls_chlor_item_overrides_method() -> None:
    """Explicit chlor_item overrides method mapping."""
    controls = get_controls("redox", chlor_item="5.40")
    assert controls["chlorine"]["item"] == "5.40"


def test_resolve_controls_options_take_precedence() -> None:
    """Options override data for effective control values."""
    controls = resolve_controls(
        {
            CONF_CHLOR_METHOD: "redox",
            CONF_PH_ITEM: "5.42",
            CONF_DOSING_ON: DOSING_ON,
        },
        {
            CONF_PH_ITEM: "5.77",
            CONF_DOSING_ON: "9.9",
        },
    )
    assert controls["ph"]["item"] == "5.77"
    assert controls["ph"]["value_on"] == "9.9"
    assert controls["ph"]["value_off"] == DOSING_OFF


def test_resolve_mqtt_items_includes_controls_and_measurements() -> None:
    """MQTT items list contains dosing controls and measurement topics."""
    items = resolve_mqtt_items({CONF_CHLOR_METHOD: "redox"}, {})
    assert set(MEASUREMENT_MQTT_ITEMS).issubset(items)
    assert "5.42" in items
    assert "5.154" in items
