"""Base entity for Bayrol Pool."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BayrolPoolCoordinator


class BayrolPoolEntity(CoordinatorEntity[BayrolPoolCoordinator]):
    """Base Bayrol Pool entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BayrolPoolCoordinator,
        entry_id: str,
        device_name: str,
        cid: str,
    ) -> None:
        """Initialize entity."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._cid = cid
        self._device_name = device_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, cid)},
            name=device_name,
            manufacturer="Bayrol",
            model=device_name,
        )

    @property
    def available(self) -> bool:
        """Return availability based on connectivity."""
        if not super().available or self.coordinator.data is None:
            return False
        return self.coordinator.data.get("connectivity", False)
