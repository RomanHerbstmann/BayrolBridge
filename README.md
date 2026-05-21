# Bayrol Bridge – Home Assistant Custom Integration

**Language:** [English](README.md) · [Deutsch](README.de.md)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![hassfest](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml/badge.svg)](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml)

Unofficial Home Assistant integration for [Bayrol Pool Access](https://www.bayrol-poolaccess.de/webview).

## Features

- **Sensors:** pH, redox (mV), temperature (°C)
- **Switches:** chlorine dosing (Redox/ACL), pH dosing
- **Binary sensors:** dosing active per control, measurement alarms, cloud connectivity
- Config flow with controller discovery
- Session resilience with automatic re-login

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
| Chlorine / disinfection method | `redox` | Convenient preset for the chlorine item |
| Chlorine item override | _(empty)_ | Set only if the method does not yield the right item; overrides the method when filled |
| pH item | `5.42` | pH dosing item |
| Value for ON | `19.17` | Switch-on value sent to `data_json.php` |
| Value for OFF | `19.18` | Switch-off value sent to `data_json.php` |

#### Known default item codes

These are the values the integration ships with. They come from community
projects and are **starting points, not a guaranteed or exhaustive list** —
item codes vary by device type (Automatic Cl-pH, SALT/ASE, PoolManager,
PoolRelax) and firmware. Use the diagnostics export (below) to see the codes
your specific device actually exposes.

| Purpose | Code | Notes |
|---------|------|-------|
| pH dosing item | `5.42` | Same across the supported families so far |
| Chlorine / redox item | `5.154` | Measured chlorine / redox (ACL etc.) |
| Salt electrolysis item | `5.40` | Salt systems (ASE / SALT) |
| Value for ON | `19.17` | Sent as the on value |
| Value for OFF | `19.18` | Sent as the off value |

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

In the downloaded JSON, the `device_items` section lists every `item` code found
on the device page, including whether it currently reads as active or inactive.
Pick the relevant code and enter it in the options (chlorine item / pH item),
then verify by toggling once and checking the Bayrol portal.

If `device_items` stays empty on your device, enable **HTML diagnostics (troubleshooting
only)** under the integration options, download diagnostics again, then disable the
switch after analysis. The debug export also includes `raw_getdata` (raw `getdata.php`
response) and `data_json_probes` (read-only attempts against `data_json.php`) to help
derive the correct item codes when `device_html_debug` is empty on some devices.

## Entities

| Entity | Description |
|--------|-------------|
| `sensor.*_ph` | pH value |
| `sensor.*_redox` | Redox potential (mV) |
| `sensor.*_temperature` | Water temperature (°C) |
| `switch.*_chlorine_dosing` | Chlorine / Redox dosing on/off |
| `switch.*_ph_dosing` | pH dosing on/off |
| `binary_sensor.*_chlorine_dosing_active` | Chlorine dosing running |
| `binary_sensor.*_ph_dosing_active` | pH dosing running |
| `binary_sensor.*_connectivity` | Cloud connection |
| `binary_sensor.*_*_alarm` | Measurement alarms |

## API sources

This integration uses the Bayrol webview HTTP API documented/reverse-engineered by community projects:

- [razem-io/ha-bayrol-cloud](https://github.com/razem-io/ha-bayrol-cloud) – login, `getdata.php`, `data_json.php` / `setItems`
- [tdenolle/bayrol-poolaccess-mqtt](https://github.com/tdenolle/bayrol-poolaccess-mqtt) – MQTT item IDs for dosing controls (`5.42`, `5.154`, `5.40`)

## Disclaimer

This is an **unofficial** community project. It is not affiliated with or endorsed by Bayrol. Use at your own risk.

## Development

```bash
pip install -r requirements-test.txt
pytest
```

## License

MIT – see [LICENSE](LICENSE).
