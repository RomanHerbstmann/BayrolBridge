# Changelog

## [0.2.0] – 2026-05-22

### Added

- MQTT-over-WebSocket control (`wss://www.bayrol-poolaccess.de:8083`) for dosing switches with real state readback (`v/` topics)
- Live measurements (pH, redox, temperature) via MQTT
- Configurable item codes and on/off values (options flow)
- Automatic MQTT reconnect with token refresh on auth failure (exponential backoff, max 5 min)
- Re-request of initial values (`g/<item>`) after every successful MQTT connect
- Diagnostics export with optional debug probes (HTML, `getdata.php`, `data_json.php` — gated by debug option)

### Changed

- Dosing control exclusively via MQTT (`s/` topics); unused HTTP `set_control` removed
- Switches report actual device state from MQTT instead of assumed state

### Removed

- HTTP-based dosing switch (`set_control` / blocked “access” path)
- Measurement alarm binary sensors until alarm source over MQTT is identified
