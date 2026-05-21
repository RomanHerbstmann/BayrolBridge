"""Diagnostics for Bayrol Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, resolve_controls

TO_REDACT = {"username", "password"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    client = runtime["client"]
    coordinator = runtime["coordinator"]
    cid = runtime["cid"]

    device_items = await client.async_list_device_items(cid)
    effective = resolve_controls(entry.data, entry.options)

    return {
        "options": async_redact_data(
            {**entry.data, **entry.options},
            TO_REDACT,
        ),
        "effective_controls": effective,
        "device_items": device_items,
        "coordinator_data": coordinator.data,
    }
