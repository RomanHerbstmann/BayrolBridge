"""Bayrol Bridge custom integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BayrolApiClient
from .const import (
    CONF_ACCESS_CODE,
    CONF_CID,
    CONF_DEVICE_NAME,
    DOMAIN,
    get_chlor_method,
    resolve_controls,
    resolve_mqtt_items,
)
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
    chlor_method = get_chlor_method(entry)
    controls = resolve_controls(entry.data, entry.options)
    merged = {**entry.data, **entry.options}
    access_code = merged.get(CONF_ACCESS_CODE)
    if isinstance(access_code, str):
        access_code = access_code.strip() or None
    else:
        access_code = None

    if not access_code:
        _LOGGER.error("App-Link-Code erforderlich für MQTT-Betrieb")
        raise ConfigEntryAuthFailed("App-Link-Code erforderlich")

    client = BayrolApiClient(
        session,
        chlor_method=chlor_method,
        controls=controls,
        access_code=access_code,
    )
    client.set_credentials(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])

    mqtt_items = resolve_mqtt_items(entry.data, entry.options)
    coordinator = BayrolBridgeCoordinator(
        hass,
        client,
        mqtt_items,
        access_code,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
        "mqtt": coordinator.mqtt,
        "device_name": entry.data.get(CONF_DEVICE_NAME, entry.title),
        "cid": entry.data[CONF_CID],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime is not None:
        await runtime["coordinator"].async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
