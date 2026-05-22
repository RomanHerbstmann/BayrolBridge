"""Diagnostics for Bayrol Bridge."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_CODE, CONF_DEBUG_HTML, DOMAIN, resolve_controls

TO_REDACT = {"username", "password", CONF_ACCESS_CODE}

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
_HEX_TOKEN_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_SESSION_RE = re.compile(r"PHPSESSID[=:]\s*\S+", re.IGNORECASE)

_MAX_RAW_GETDATA = 6000
_MAX_PROBE_FIELD = 2000


def _sanitize_text(
    text: str, *, cid: str | None = None, max_len: int = _MAX_RAW_GETDATA
) -> str:
    """Mask sensitive fragments and cap length for diagnostic export."""
    if not text:
        return text
    result = _SESSION_RE.sub("<session>", text)
    result = _EMAIL_RE.sub("<email>", result)
    result = _HEX_TOKEN_RE.sub("<token>", result)
    if cid:
        result = result.replace(cid, "<cid>")
    if len(result) > max_len:
        return result[: max_len - 12] + "...truncated"
    return result


def _sanitize_obj(
    obj: Any, *, cid: str | None = None, max_len: int = _MAX_PROBE_FIELD
) -> Any:
    """Recursively sanitize strings inside diagnostic structures."""
    if isinstance(obj, str):
        return _sanitize_text(obj, cid=cid, max_len=max_len)
    if isinstance(obj, dict):
        return {
            key: _sanitize_obj(value, cid=cid, max_len=max_len)
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_sanitize_obj(item, cid=cid, max_len=max_len) for item in obj]
    return obj


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
    debug = bool(merged.get(CONF_DEBUG_HTML))
    debug_html = None
    raw_getdata = None
    data_json_probes = None
    get_items_probe = None
    access_probe = None
    if debug:
        debug_html = await client.async_get_device_html_debug(cid)
        raw_getdata = _sanitize_text(
            await client.async_get_raw_getdata(cid), cid=cid
        )
        probes = await client.async_probe_data_json(cid)
        data_json_probes = [_sanitize_obj(probe, cid=cid) for probe in probes]
        get_items_probe = _sanitize_obj(await client.async_probe_get_items(cid))
        code = merged.get(CONF_ACCESS_CODE)
        if code:
            access_probe = _sanitize_obj(
                await client.async_probe_access(cid, code)
            )

    return {
        "options": async_redact_data(
            merged,
            TO_REDACT,
        ),
        "effective_controls": effective,
        "device_items": device_items,
        "device_html_debug": debug_html,
        "raw_getdata": raw_getdata,
        "data_json_probes": data_json_probes,
        "get_items_probe": get_items_probe,
        "access_probe": access_probe,
        "coordinator_data": coordinator.data,
    }
