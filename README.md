# Bayrol Bridge – Home Assistant Custom Integration

**Language:** [English](README.md) · [Deutsch](README.de.md)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![hassfest](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml/badge.svg)](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml)

Unofficial Home Assistant integration for [Bayrol Pool Access](https://www.bayrol-poolaccess.de/webview).

## Features

- **Sensors:** pH, redox (mV), temperature (°C) — live values via MQTT
- **Switches:** chlorine dosing (Redox/ACL or salt), pH dosing — control and real state readback via MQTT
- **Binary sensor:** cloud connectivity (MQTT)
- Config flow with controller discovery
- Session resilience with automatic re-login (HTTP portal session)
- **Continuous operation:** MQTT reconnect with automatic token refresh on auth failure; initial sensor/switch values re-requested after every successful connect

## Architecture

| Path | Role |
|------|------|
| **MQTT-over-WebSocket** (`wss://www.bayrol-poolaccess.de:8083`) | Live measurements, dosing on/off (`s/` topics), state readback (`v/` topics), initial value requests (`g/` topics) |
| **HTTP** (`/api/?code=`) | Exchange **App Link** code for MQTT access token and device serial |
| **HTTP** (Bayrol webview login) | Portal session (`PHPSESSID`) for controller discovery and optional diagnostics |

There is **no local LAN API** — the integration talks to Bayrol Pool Access in the cloud only.

### App Link code (automatic)

MQTT credentials use a short-lived **App Link** code from the Bayrol portal. The
integration fetches it from the device page (`device.php`) when needed — **email and
password** are enough for setup.

You may optionally set an **App Link code** under integration options as a fallback
(e.g. if the portal HTML layout differs).

## Installation

### HACS (recommended)

1. Add this repository as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/) (category: Integration).
2. Install **Bayrol Bridge** via HACS.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & services → Add integration**.

### Manual

Copy `custom_components/bayrol_bridge` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

### Initial setup

Use the config flow with your Bayrol Pool Access email and password. If you have
multiple controllers, select the desired one, then choose the chlorine /
disinfection method:

- **redox** – measured chlorine / redox (ACL, many PoolManager / PoolRelax units), item `5.154`
- **salt** – salt electrolysis (ASE / SALT), item `5.40`
- **none** – do not create a chlorine switch

The method is pre-selected via best-effort auto-detection; you can override it.

Optional: set the polling interval (minimum 30 seconds, default 60).

### Options (configurable item codes)

The dosing item codes and on/off values differ between Bayrol device generations.
Because they cannot be detected reliably, they are editable without touching code:

**Settings → Devices & services → Bayrol Bridge → Configure**

| Option | Default | Notes |
|--------|---------|-------|
| App-link code | _(empty)_ | Optional fallback; usually obtained automatically from the portal |
| Chlorine / disinfection method | `redox` | Convenient preset for the chlorine item |
| Chlorine item override | _(empty)_ | Set only if the method does not yield the right item; overrides the method when filled |
| pH item | `5.42` | pH dosing item |
| pH measurement item | `4.2` | MQTT item for pH reading (raw ÷ 10) |
| Redox measurement item | `4.82` | MQTT item for redox (mV) |
| Value for ON | `19.17` | MQTT value when dosing is turned on |
| Value for OFF | `19.18` | MQTT value when dosing is turned off |
| Debug diagnostics | off | Raw/HTML/probe data in diagnostics export only when enabled |

#### Known default item codes

These are the values the integration ships with. They come from community
projects and are **starting points, not a guaranteed or exhaustive list** —
item codes vary by device type (Automatic Cl-pH, SALT/ASE, PoolManager,
PoolRelax) and firmware. Use the diagnostics export (below) to see the codes
your specific device actually exposes.

| Purpose | Code | Notes |
|---------|------|-------|
| pH dosing item | `5.42` | Same across the supported families so far |
| pH measurement item | `4.2` | Automatic Cl-pH (discover-verified) |
| Redox measurement item | `4.82` | Automatic Cl-pH (discover-verified) |
| Temperature measurement item | `1` | Stable across devices (fixed) |
| Chlorine / redox item | `5.154` | Measured chlorine / redox (ACL etc.) |
| Salt electrolysis item | `5.40` | Salt systems (ASE / SALT) |
| Value for ON | `19.17` | Sent as the on value |
| Value for OFF | `19.18` | Sent as the off value |

**Device-specific:** codes above are verified for **Automatic Cl-pH**; other models
(PoolManager, PoolRelax, SALT/ASE) may differ — adjust via options or diagnostics.

Leaving a field empty restores its default. Saving reloads the integration
automatically, so the switches use the new values immediately.

#### Verifying the codes against a real device

The item codes and on/off values come from community sources and may not match
every device. To verify, capture the request in the Bayrol web portal: open the
portal, press **F12 → Network**, manually toggle chlorine and pH dosing once each,
and inspect the `data_json.php` requests for the actual item topics and values.
Then enter any differing values in the options above — no code change needed.

### Finding your device's real item codes (diagnostics)

Instead of guessing, you can let the integration list the item codes your device
actually exposes:

**Settings → Devices & services → Bayrol Bridge → (your entry) → ⋮ → Download diagnostics**

On some devices (e.g. Automatic Cl-pH, FW v2.30), HTTP readback of dosing states is
not available: `getItems` returns empty items and `device_items` stays empty. Live
live measurements (pH, redox, temperature) and dosing switches use MQTT;
`getdata.php` remains for diagnostics only. Use the Bayrol portal or MQTT tools
to confirm actual dosing.

Where the device page exposes item divs, the `device_items` section in diagnostics
lists each `item` code with active/inactive state. Pick the relevant code for the
options (chlorine item / pH item), then verify by toggling once in the portal.

If `device_items` stays empty, enable **Debug diagnostics (raw data, troubleshooting only)**,
download diagnostics again, then disable the option after analysis. The debug export
also includes `raw_getdata` and `data_json_probes` to help derive item codes when
`device_html_debug` is empty.

## Entities

| Entity | Description |
|--------|-------------|
| `sensor.*_ph` | pH value (MQTT) |
| `sensor.*_redox` | Redox potential in mV (MQTT) |
| `sensor.*_temperature` | Water temperature in °C (MQTT) |
| `switch.*_chlorine_dosing` | Chlorine / Redox dosing on/off (MQTT set + readback) |
| `switch.*_ph_dosing` | pH dosing on/off (MQTT set + readback) |
| `binary_sensor.*_connectivity` | MQTT connection |

Alarm sensors are **not** provided yet (known limitation until the alarm source over MQTT is identified).

Dosing switches read state from MQTT (`v/` topics) and become unavailable when
the connection is lost (no stale values). After a reconnect, the integration
re-requests all configured items via `g/` topics so entities do not stay unknown.

## Safety

This integration controls **real chemical dosing** through the Bayrol cloud.
The pool controller runs its own regulation; Home Assistant only sends on/off commands.

- Use automations with hysteresis, maximum run times, and watchdogs where appropriate.
- Test changes manually before unattended automations.
- Keep portal credentials and the App Link code private.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## API sources

This integration uses the Bayrol webview HTTP API documented/reverse-engineered by community projects:

- [razem-io/ha-bayrol-cloud](https://github.com/razem-io/ha-bayrol-cloud) – login, `getdata.php`, diagnostics
- [tdenolle/bayrol-poolaccess-mqtt](https://github.com/tdenolle/bayrol-poolaccess-mqtt) – MQTT item IDs for dosing controls (`5.42`, `5.154`, `5.40`)

## Disclaimer

This is an **unofficial** community project. It is not affiliated with or endorsed by Bayrol.
It relies on **cloud-only** access (no local API). Use at your own risk.

## Development

```bash
pip install -r requirements-test.txt
pytest
```

## License

MIT – see [LICENSE](LICENSE).
