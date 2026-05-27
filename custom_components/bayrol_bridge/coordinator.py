"""Data update coordinator for Bayrol Bridge (MQTT push)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import BayrolApiClient, BayrolAuthError, BayrolConnectionError
from .const import DATA_CONNECTIVITY
from .mqtt_client import BayrolMqttClient

_LOGGER = logging.getLogger(__name__)


class BayrolBridgeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Maintain Bayrol pool state from MQTT v/-topic push updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: BayrolApiClient,
        items: list[str],
        cid: str,
        username: str,
        password: str,
    ) -> None:
        """Initialize coordinator."""
        self.client = client
        self._items = items
        self._cid = cid
        self._username = username
        self._password = password
        self._mqtt: BayrolMqttClient | None = None
        self._state: dict[str, Any] = {
            DATA_CONNECTIVITY: False,
            "items": {},
        }
        super().__init__(
            hass,
            _LOGGER,
            name="bayrol_bridge",
            update_interval=None,
        )

    @property
    def mqtt(self) -> BayrolMqttClient | None:
        """Connected MQTT client, if any."""
        return self._mqtt

    def _snapshot(self) -> dict[str, Any]:
        return {
            DATA_CONNECTIVITY: self._state[DATA_CONNECTIVITY],
            "items": dict(self._state["items"]),
        }

    def handle_value(self, item: str, value: str) -> None:
        """Apply an incoming v/<item> value and notify listeners."""
        self._state["items"][item] = value
        self._state[DATA_CONNECTIVITY] = True
        self.async_set_updated_data(self._snapshot())

    def handle_connection_change(self, connected: bool) -> None:
        """Update MQTT connectivity and notify listeners."""
        self._state[DATA_CONNECTIVITY] = connected
        self.async_set_updated_data(self._snapshot())

    async def _provide_token(self) -> tuple[str, str]:
        """Refresh HTTP session and fetch new MQTT credentials."""
        await self.client.login(self._username, self._password)
        return await self.client.async_fetch_mqtt_credentials_auto(self._cid)

    async def async_start(self) -> None:
        """Log in, fetch MQTT credentials, connect, and request initial values."""
        try:
            await self.client.login(self._username, self._password)
        except BayrolAuthError as err:
            raise ConfigEntryAuthFailed("Authentication failed") from err
        except BayrolConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from err

        try:
            token, serial = await self.client.async_fetch_mqtt_credentials_auto(
                self._cid
            )
        except BayrolAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BayrolConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from err

        self._mqtt = BayrolMqttClient(
            self.hass,
            token,
            serial,
            on_value=self.handle_value,
            on_connection_change=self.handle_connection_change,
            request_items=self._items,
            token_provider=self._provide_token,
        )
        try:
            await self._mqtt.async_connect()
        except BayrolConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from err

        self.handle_connection_change(True)

    async def async_stop(self) -> None:
        """Disconnect MQTT and mark the integration offline."""
        if self._mqtt is not None:
            await self._mqtt.async_stop()
            self._mqtt = None
        self.handle_connection_change(False)
