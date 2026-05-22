"""Binary sensor platform for Bayrol Bridge."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_CONNECTIVITY, DOMAIN
from .entity import BayrolBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bayrol Bridge binary sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    device_name = runtime["device_name"]
    cid = runtime["cid"]
    entry_id = entry.entry_id

    async_add_entities(
        [
            BayrolBridgeConnectivityBinary(
                coordinator, entry_id, device_name, cid
            ),
        ]
    )


class BayrolBridgeConnectivityBinary(BayrolBridgeEntity, BinarySensorEntity):
    """Cloud connectivity binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator,
        entry_id: str,
        device_name: str,
        cid: str,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator, entry_id, device_name, cid)
        self._attr_unique_id = f"{cid}_connectivity_binary"
        self._attr_translation_key = "connectivity"

    @property
    def is_on(self) -> bool | None:
        """Return true when connected."""
        if self.coordinator.data is None:
            return None
        return bool(self.coordinator.data.get(DATA_CONNECTIVITY))

    @property
    def available(self) -> bool:
        """Stay available while coordinator is running."""
        return self.coordinator.last_update_success
