"""Constants for the Bayrol Bridge integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, TypedDict

DOMAIN: Final = "bayrol_bridge"

BASE_URL: Final = "https://www.bayrol-poolaccess.de/webview"

# Session / login (razem-io/ha-bayrol-cloud; fallback paths per portal spec)
PATH_INDEX: Final = "index.php"
PATH_LOGIN_MOBILE: Final = "m/login.php"
PATH_LOGIN_PORTAL: Final = "p/login.php"
PATH_LOGIN_POST: Final = "p/login.php?r=reg"
PATH_PLANTS: Final = "m/plants.php"
PATH_DEVICE: Final = "p/device.php"
PATH_GETDATA: Final = "getdata.php"
PATH_DATA_JSON: Final = "data_json.php"

CONF_CID: Final = "cid"
CONF_DEVICE_NAME: Final = "device_name"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_CHLOR_METHOD: Final = "chlor_method"
CONF_PH_ITEM: Final = "ph_item"
CONF_CHLOR_ITEM: Final = "chlor_item"
CONF_DOSING_ON: Final = "dosing_on"
CONF_DOSING_OFF: Final = "dosing_off"

DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 30

# MQTT topic codes (tdenolle/bayrol-poolaccess-mqtt entities.json)
DOSING_ON: Final = "19.17"
DOSING_OFF: Final = "19.18"

PH_ITEM: Final = "5.42"

CHLOR_METHODS: Final[dict[str, dict[str, str | None]]] = {
    "redox": {"item": "5.154"},
    "salt": {"item": "5.40"},
    "none": {"item": None},
}
DEFAULT_CHLOR_METHOD: Final = "redox"


class ControlConfig(TypedDict):
    """Configuration for a dosing control."""

    set_path: str
    item: str
    value_on: str
    value_off: str
    name: str


def get_controls(
    chlor_method: str,
    *,
    ph_item: str | None = None,
    chlor_item: str | None = None,
    dosing_on: str | None = None,
    dosing_off: str | None = None,
) -> dict[str, ControlConfig]:
    """Return dosing controls for the configured chlorine method."""
    on = dosing_on or DOSING_ON
    off = dosing_off or DOSING_OFF
    eff_ph = ph_item or PH_ITEM

    controls: dict[str, ControlConfig] = {
        "ph": {
            "set_path": PATH_DATA_JSON,
            "item": eff_ph,
            "value_on": on,
            "value_off": off,
            "name": "ph_on_off",
        },
    }

    eff_chlor = (chlor_item or "").strip() or CHLOR_METHODS.get(
        chlor_method, CHLOR_METHODS[DEFAULT_CHLOR_METHOD]
    )["item"]

    if eff_chlor:
        controls["chlorine"] = {
            "set_path": PATH_DATA_JSON,
            "item": eff_chlor,
            "value_on": on,
            "value_off": off,
            "name": "mv_on_off",
        }
    return controls


def resolve_controls(
    data: Mapping[str, object], options: Mapping[str, object]
) -> dict[str, ControlConfig]:
    """Merge config entry data/options and return effective dosing controls."""
    merged = {**data, **options}
    return get_controls(
        str(merged.get(CONF_CHLOR_METHOD, DEFAULT_CHLOR_METHOD)),
        ph_item=_opt_str(merged.get(CONF_PH_ITEM)),
        chlor_item=_opt_str(merged.get(CONF_CHLOR_ITEM)),
        dosing_on=_opt_str(merged.get(CONF_DOSING_ON)),
        dosing_off=_opt_str(merged.get(CONF_DOSING_OFF)),
    )


def _opt_str(value: object) -> str | None:
    """Return stripped string or None for non-string/empty values."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


# Keys in coordinator data
DATA_STATUS: Final = "status"
DATA_CONNECTIVITY: Final = "connectivity"
DATA_PH: Final = "pH"
DATA_REDOX: Final = "mV"
DATA_TEMPERATURE: Final = "T"
DATA_CHLORINE_DOSING: Final = "chlorine_dosing"
DATA_PH_DOSING: Final = "ph_dosing"

MEASUREMENT_KEYS: Final = (DATA_PH, DATA_REDOX, DATA_TEMPERATURE)
