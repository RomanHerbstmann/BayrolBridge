"""Bayrol Bridge custom integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BayrolApiClient
from .const import (
    CONF_CID,
    CONF_DEVICE_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    resolve_controls,
)
from .switch import _get_chlor_method
from .coordinator import BayrolBridgeCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bayrol Bridge from a config entry."""
    session = async_get_clientsession(hass)
    chlor_method = _get_chlor_method(entry)
    controls = resolve_controls(entry.data, entry.options)
    client = BayrolApiClient(session, chlor_method=chlor_method, controls=controls)
    client._username = entry.data[CONF_USERNAME]
    client._password = entry.data[CONF_PASSWORD]

    coordinator = BayrolBridgeCoordinator(
        hass,
        client,
        entry.data[CONF_CID],
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "device_name": entry.data.get(CONF_DEVICE_NAME, entry.title),
        "cid": entry.data[CONF_CID],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
