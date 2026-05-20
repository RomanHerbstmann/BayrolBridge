# Bayrol Pool – Home Assistant Custom Integration

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
2. Install **Bayrol Pool** via HACS.
3. Restart Home Assistant.
4. Add the integration via **Settings → Devices & services → Add integration**.

### Manual

Copy `custom_components/bayrol_pool` into your Home Assistant `config/custom_components/` directory and restart.

## Configuration

Use the config flow with your Bayrol Pool Access email and password. If you have multiple controllers, select the desired one.

Optional: set the polling interval (minimum 30 seconds, default 60).

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
- [tdenolle/bayrol-poolaccess-mqtt](https://github.com/tdenolle/bayrol-poolaccess-mqtt) – MQTT item IDs for dosing controls (`5.42`, `5.154`)

## Disclaimer

This is an **unofficial** community project. It is not affiliated with or endorsed by Bayrol. Use at your own risk.

## Development

```bash
pip install -r requirements-test.txt
pytest
```

## License

MIT – see [LICENSE](LICENSE).
