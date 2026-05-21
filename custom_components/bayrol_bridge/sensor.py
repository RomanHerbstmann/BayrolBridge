"""Sensor platform for Bayrol Pool."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricPotential, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_PH, DATA_REDOX, DATA_TEMPERATURE, DOMAIN
from .entity import BayrolPoolEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bayrol Pool sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    device_name = runtime["device_name"]
    cid = runtime["cid"]
    entry_id = entry.entry_id

    sensors: list[BayrolPoolSensor] = [
        BayrolPoolSensor(
            coordinator,
            entry_id,
            device_name,
            cid,
            DATA_PH,
            "ph",
            None,
            SensorStateClass.MEASUREMENT,
            None,
            "mdi:ph",
        ),
        BayrolPoolSensor(
            coordinator,
            entry_id,
            device_name,
            cid,
            DATA_REDOX,
            "redox",
            UnitOfElectricPotential.MILLIVOLT,
            SensorStateClass.MEASUREMENT,
            None,
            "mdi:flash",
        ),
        BayrolPoolSensor(
            coordinator,
            entry_id,
            device_name,
            cid,
            DATA_TEMPERATURE,
            "temperature",
            UnitOfTemperature.CELSIUS,
            SensorStateClass.MEASUREMENT,
            SensorDeviceClass.TEMPERATURE,
            None,
        ),
    ]

    async_add_entities(sensors)


class BayrolPoolSensor(BayrolPoolEntity, SensorEntity):
    """Measurement sensor."""

    def __init__(
        self,
        coordinator,
        entry_id: str,
        device_name: str,
        cid: str,
        data_key: str,
        translation_key: str,
        unit: str | None,
        state_class: SensorStateClass | None,
        device_class: SensorDeviceClass | None,
        icon: str | None,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry_id, device_name, cid)
        self._data_key = data_key
        self._attr_unique_id = f"{cid}_{translation_key}"
        self._attr_translation_key = translation_key
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        if icon:
            self._attr_icon = icon

    @property
    def native_value(self) -> float | str | None:
        """Return sensor value."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)

