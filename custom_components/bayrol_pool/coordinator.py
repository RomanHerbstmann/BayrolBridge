"""Data update coordinator for Bayrol Pool."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BayrolApiClient, BayrolAuthError, BayrolConnectionError

_LOGGER = logging.getLogger(__name__)


class BayrolPoolCoordinator(DataUpdateCoordinator[dict]):
    """Fetch Bayrol pool data periodically."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BayrolApiClient,
        cid: str,
        scan_interval: int,
    ) -> None:
        """Initialize coordinator."""
        self.client = client
        self.cid = cid
        super().__init__(
            hass,
            _LOGGER,
            name="bayrol_pool",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.fetch_pool_data(self.cid)
        except BayrolAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except BayrolConnectionError as err:
            raise UpdateFailed(str(err)) from err
