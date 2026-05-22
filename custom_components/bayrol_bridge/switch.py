"""Switch platform for Bayrol Bridge."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CHLOR_METHOD,
    DATA_CONNECTIVITY,
    DEFAULT_CHLOR_METHOD,
    DOMAIN,
    resolve_controls,
)
from .entity import BayrolBridgeEntity

_LOGGER = logging.getLogger(__name__)


def _get_chlor_method(entry: ConfigEntry) -> str:
    return entry.options.get(
        CONF_CHLOR_METHOD,
        entry.data.get(CONF_CHLOR_METHOD, DEFAULT_CHLOR_METHOD),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bayrol Bridge switches."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    device_name = runtime["device_name"]
    cid = runtime["cid"]
    entities: list[BayrolBridgeSwitch] = []
    for control_key, control in resolve_controls(entry.data, entry.options).items():
        entities.append(
            BayrolBridgeSwitch(
                coordinator,
                entry.entry_id,
                device_name,
                cid,
                control_key,
                control["item"],
                control["value_on"],
                control["value_off"],
            )
        )

    async_add_entities(entities)


class BayrolBridgeSwitch(BayrolBridgeEntity, SwitchEntity):
    """Bayrol dosing switch (MQTT set + v/- readback)."""

    def __init__(
        self,
        coordinator,
        entry_id: str,
        device_name: str,
        cid: str,
        control_key: str,
        item: str,
        value_on: str,
        value_off: str,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator, entry_id, device_name, cid)
        self._control_key = control_key
        self._item = item
        self._value_on = value_on
        self._value_off = value_off
        self._attr_unique_id = f"{cid}_{control_key}_dosing"
        self._attr_translation_key = f"{control_key}_dosing"

    @property
    def is_on(self) -> bool | None:
        """Return dosing state from MQTT v/- readback."""
        data = self.coordinator.data or {}
        raw = data.get("items", {}).get(self._item)
        if raw is None:
            return None
        if raw == self._value_on:
            return True
        if raw == self._value_off:
            return False
        return None

    @property
    def available(self) -> bool:
        """Unavailable when offline; avoids misleading 'off' while disconnected."""
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data or {}
        return bool(data.get(DATA_CONNECTIVITY))

    async def async_turn_on(self, **kwargs) -> None:
        """Turn dosing on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn dosing off."""
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        mqtt = self.coordinator.mqtt
        if mqtt is None:
            raise HomeAssistantError("MQTT not connected")
        value = self._value_on if enabled else self._value_off
        await mqtt.async_set(self._item, value)
