"""Switch platform for Bayrol Pool."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CHLOR_METHOD,
    DATA_CHLORINE_DOSING,
    DATA_PH_DOSING,
    DEFAULT_CHLOR_METHOD,
    DOMAIN,
    get_controls,
)
from .entity import BayrolPoolEntity

_LOGGER = logging.getLogger(__name__)

CONTROL_STATE_KEYS = {
    "chlorine": DATA_CHLORINE_DOSING,
    "ph": DATA_PH_DOSING,
}


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
    """Set up Bayrol Pool switches."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    device_name = runtime["device_name"]
    cid = runtime["cid"]
    chlor_method = _get_chlor_method(entry)

    entities: list[BayrolPoolSwitch] = []
    for control_key, control in get_controls(chlor_method).items():
        entities.append(
            BayrolPoolSwitch(
                coordinator,
                entry.entry_id,
                device_name,
                cid,
                control_key,
                control["name"],
            )
        )

    async_add_entities(entities)


class BayrolPoolSwitch(BayrolPoolEntity, SwitchEntity):
    """Bayrol dosing switch."""

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
        self._state_key = CONTROL_STATE_KEYS[control_key]
        self._attr_unique_id = f"{cid}_{control_key}_dosing"
        self._attr_translation_key = f"{control_key}_dosing"

    @property
    def is_on(self) -> bool | None:
        """Return switch state."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._state_key)

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
        if self.coordinator.data is not None:
            self.coordinator.data[self._state_key] = enabled
        await self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
