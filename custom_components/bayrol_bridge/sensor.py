"""Sensor platform for Bayrol Bridge."""

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

from .const import (
    DATA_CONNECTIVITY,
    DOMAIN,
    PH_SCALE,
    REDOX_SCALE,
    TEMP_MEAS_ITEM,
    TEMP_SCALE,
    resolve_meas_items,
)
from .entity import BayrolBridgeEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bayrol Bridge sensors."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    device_name = runtime["device_name"]
    cid = runtime["cid"]
    entry_id = entry.entry_id

    _, ph_item, redox_item = resolve_meas_items(entry.data, entry.options)

    sensors: list[BayrolBridgeSensor] = [
        BayrolBridgeSensor(
            coordinator,
            entry_id,
            device_name,
            cid,
            TEMP_MEAS_ITEM,
            TEMP_SCALE,
            "temperature",
            UnitOfTemperature.CELSIUS,
            SensorStateClass.MEASUREMENT,
            SensorDeviceClass.TEMPERATURE,
            None,
        ),
        BayrolBridgeSensor(
            coordinator,
            entry_id,
            device_name,
            cid,
            ph_item,
            PH_SCALE,
            "ph",
            None,
            SensorStateClass.MEASUREMENT,
            None,
            "mdi:ph",
        ),
        BayrolBridgeSensor(
            coordinator,
            entry_id,
            device_name,
            cid,
            redox_item,
            REDOX_SCALE,
            "redox",
            UnitOfElectricPotential.MILLIVOLT,
            SensorStateClass.MEASUREMENT,
            None,
            "mdi:flash",
        ),
    ]

    async_add_entities(sensors)


class BayrolBridgeSensor(BayrolBridgeEntity, SensorEntity):
    """Measurement sensor (MQTT items + scaling)."""

    def __init__(
        self,
        coordinator,
        entry_id: str,
        device_name: str,
        cid: str,
        item: str,
        scale: float,
        translation_key: str,
        unit: str | None,
        state_class: SensorStateClass | None,
        device_class: SensorDeviceClass | None,
        icon: str | None,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator, entry_id, device_name, cid)
        self._item = item
        self._scale = scale
        self._attr_unique_id = f"{cid}_{translation_key}"
        self._attr_translation_key = translation_key
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_class = device_class
        if icon:
            self._attr_icon = icon

    def _read_scaled(self) -> float | None:
        """Read raw MQTT item value and apply scale."""
        data = self.coordinator.data or {}
        raw = data.get("items", {}).get(self._item)
        if raw is None:
            return None
        try:
            return round(float(raw) * self._scale, 2)
        except (TypeError, ValueError):
            return None

    @property
    def native_value(self) -> float | None:
        """Return scaled sensor value."""
        return self._read_scaled()

    @property
    def available(self) -> bool:
        """Unavailable when MQTT is disconnected."""
        if not self.coordinator.last_update_success:
            return False
        data = self.coordinator.data or {}
        return bool(data.get(DATA_CONNECTIVITY))
