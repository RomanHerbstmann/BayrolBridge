"""Diagnostics for Bayrol Bridge."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEBUG_HTML, DOMAIN, resolve_controls

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

    merged = {**entry.data, **entry.options}
    debug_html = None
    if merged.get(CONF_DEBUG_HTML):
        debug_html = await client.async_get_device_html_debug(cid)

    return {
        "options": async_redact_data(
            merged,
            TO_REDACT,
        ),
        "effective_controls": effective,
        "device_items": device_items,
        "device_html_debug": debug_html,
        "coordinator_data": coordinator.data,
    }
