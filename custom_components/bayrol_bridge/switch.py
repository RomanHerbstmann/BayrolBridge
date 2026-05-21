"""Switch platform for Bayrol Bridge."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
                control["name"],
            )
        )

    async_add_entities(entities)


class BayrolBridgeSwitch(BayrolBridgeEntity, SwitchEntity):
    """Bayrol dosing switch (optimistic state; no HTTP readback on some devices)."""

    def __init__(
        self,
        coordinator,
        entry_id: str,
        device_name: str,
        cid: str,
        control_key: str,
        control_name: str,
    ) -> None:
        """Initialize switch."""
        super().__init__(coordinator, entry_id, device_name, cid)
        self._control_key = control_key
        self._attr_assumed_state = True
        self._optimistic_state: bool | None = None
        self._attr_unique_id = f"{cid}_{control_key}_dosing"
        self._attr_translation_key = f"{control_key}_dosing"

    @property
    def is_on(self) -> bool | None:
        """Return last commanded switch state."""
        return self._optimistic_state

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
        await self.coordinator.client.set_control(
            self._cid, self._control_key, enabled
        )
        self._optimistic_state = enabled
        self.async_write_ha_state()
