"""Binary sensor platform for Bayrol Bridge."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DATA_CHLORINE_DOSING,
    DATA_CONNECTIVITY,
    DATA_PH,
    DATA_PH_DOSING,
    DATA_REDOX,
    DATA_TEMPERATURE,
    DOMAIN,
    resolve_controls,
)
from .entity import BayrolBridgeEntity

DOSING_KEYS = {
    "chlorine": DATA_CHLORINE_DOSING,
    "ph": DATA_PH_DOSING,
}

ALARM_KEYS = {
    DATA_PH: "ph_alarm",
    DATA_REDOX: "redox_alarm",
    DATA_TEMPERATURE: "temperature_alarm",
}


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
    entities: list[BayrolBridgeEntity] = [
        BayrolBridgeConnectivityBinary(
            coordinator, entry_id, device_name, cid
        ),
    ]

    for control_key in resolve_controls(entry.data, entry.options):
        entities.append(
            BayrolBridgeDosingBinary(
                coordinator,
                entry_id,
                device_name,
                cid,
                control_key,
            )
        )

    for data_key, translation_key in (
        (DATA_PH, "ph_alarm"),
        (DATA_REDOX, "redox_alarm"),
        (DATA_TEMPERATURE, "temperature_alarm"),
    ):
        entities.append(
            BayrolBridgeAlarmBinary(
                coordinator,
                entry_id,
                device_name,
                cid,
                data_key,
                translation_key,
            )
        )

    async_add_entities(entities)


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


class BayrolBridgeDosingBinary(BayrolBridgeEntity, BinarySensorEntity):
    """Active dosing status per control."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(
        self,
        coordinator,
        entry_id: str,
        device_name: str,
        cid: str,
        control_key: str,
    ) -> None:
        """Initialize dosing binary sensor."""
        super().__init__(coordinator, entry_id, device_name, cid)
        self._state_key = DOSING_KEYS[control_key]
        self._attr_unique_id = f"{cid}_{control_key}_dosing_active"
        self._attr_translation_key = f"{control_key}_dosing_active"

    @property
    def is_on(self) -> bool | None:
        """Return true when dosing is active."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._state_key)
        if value is None:
            return None
        return bool(value)


class BayrolBridgeAlarmBinary(BayrolBridgeEntity, BinarySensorEntity):
    """Measurement alarm binary sensor."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator,
        entry_id: str,
        device_name: str,
        cid: str,
        data_key: str,
        translation_key: str,
    ) -> None:
        """Initialize alarm binary sensor."""
        super().__init__(coordinator, entry_id, device_name, cid)
        self._alarm_key = f"{data_key}_alarm"
        self._attr_unique_id = f"{cid}_{translation_key}"
        self._attr_translation_key = translation_key
        self._attr_icon = "mdi:alarm-light"

    @property
    def is_on(self) -> bool | None:
        """Return true when alarm is active."""
        if self.coordinator.data is None:
            return None
        if self._alarm_key not in self.coordinator.data:
            return None
        return bool(self.coordinator.data.get(self._alarm_key))
