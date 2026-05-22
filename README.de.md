# Bayrol Bridge – Home-Assistant-Custom-Integration

**Sprache:** [Deutsch](README.de.md) · [English](README.md)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![hassfest](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml/badge.svg)](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml)

Inoffizielle Home-Assistant-Integration für [Bayrol Pool Access](https://www.bayrol-poolaccess.de/webview).

## Funktionen

- **Sensoren:** pH, Redox (mV), Temperatur (°C) — Live-Werte per MQTT
- **Schalter:** Chlordosierung (Redox/ACL oder Salz), pH-Dosierung — Steuerung und echtes Readback per MQTT
- **Binärsensor:** Cloud-Verbindung (MQTT)
- Config Flow mit Steuerungs-Erkennung
- Sitzungsstabilität mit automatischem Re-Login (HTTP-Portal-Session)
- **Dauerbetrieb:** MQTT-Reconnect mit automatischer Token-Erneuerung bei Auth-Fehler; Initialwerte nach jedem erfolgreichen Connect erneut angefordert

## Architektur

| Pfad | Rolle |
|------|--------|
| **MQTT-over-WebSocket** (`wss://www.bayrol-poolaccess.de:8083`) | Live-Messwerte, Dosierung ein/aus (`s/`-Topics), Zustands-Readback (`v/`-Topics), Initialwerte (`g/`-Topics) |
| **HTTP** (`/api/?code=`) | **App-Link**-Code gegen MQTT-Token und Geräte-Seriennummer tauschen |
| **HTTP** (Bayrol-Webview-Login) | Portal-Session (`PHPSESSID`) für Steuerungsauswahl und optionale Diagnose |

Es gibt **keine lokale LAN-API** — die Integration nutzt ausschließlich Bayrol Pool Access in der Cloud.

### App-Link-Code (erforderlich)

MQTT-Zugangsdaten werden mit dem **App-Link**-Code aus dem Bayrol-Portal bezogen
(**App Link** / App-Link-URL). In den Integrationsoptionen als **Geräte-/App-Link-Code**
eintragen. Ohne gültigen Code sind Steuerung und Live-MQTT-Daten nicht verfügbar.

## Installation

### HACS (empfohlen)

1. Dieses Repository als [Custom Repository](https://hacs.xyz/docs/faq/custom_repositories/) hinzufügen (Kategorie: Integration).
2. **Bayrol Bridge** über HACS installieren.
3. Home Assistant neu starten.
4. Integration über **Einstellungen → Geräte & Dienste → Integration hinzufügen** einrichten.

### Manuell

`custom_components/bayrol_bridge` in das Verzeichnis `config/custom_components/` von Home Assistant kopieren und neu starten.

## Konfiguration

### Ersteinrichtung

Nutze den Config Flow mit E-Mail und Passwort von Bayrol Pool Access. Bei mehreren
Steuerungen die gewünschte auswählen, dann die Chlor-/Desinfektionsmethode wählen:

- **redox** – gemessenes Chlor / Redox (ACL, viele PoolManager / PoolRelax), Item `5.154`
- **salt** – Salzelektrolyse (ASE / SALT), Item `5.40`
- **none** – keinen Chlor-Schalter anlegen

Die Methode wird per Best-Effort-Autoerkennung vorausgewählt; du kannst sie überschreiben.

Optional: Abfrageintervall setzen (Minimum 30 Sekunden, Standard 60).

Danach unter **Konfigurieren** den **App-Link-Code** eintragen (für MQTT erforderlich).

### Optionen (konfigurierbare Item-Codes)

Die Item-Codes für Dosierung und die Ein-/Aus-Werte unterscheiden sich je nach
Bayrol-Gerätegeneration. Da sie nicht zuverlässig erkannt werden können, sind sie
ohne Codeänderung editierbar:

**Einstellungen → Geräte & Dienste → Bayrol Bridge → Konfigurieren**

| Option | Standard | Hinweise |
|--------|----------|----------|
| Geräte-/App-Link-Code | _(erforderlich)_ | Im Bayrol-Portal unter **App Link**; schaltet MQTT-Token frei |
| Chlor-/Desinfektionsmethode | `redox` | Bequeme Voreinstellung für das Chlor-Item |
| Chlor-Item-Override | _(leer)_ | Nur setzen, wenn die Methode nicht passt; überschreibt die Methode, wenn ausgefüllt |
| pH-Item | `5.42` | pH-Dosierungs-Item |
| pH-Messwert-Item | `4.2` | MQTT-Item für pH-Messwert (Rohwert ÷ 10) |
| Redox-Messwert-Item | `4.82` | MQTT-Item für Redox (mV) |
| Wert für EIN | `19.17` | MQTT-Wert beim Einschalten der Dosierung |
| Wert für AUS | `19.18` | MQTT-Wert beim Ausschalten der Dosierung |
| Debug-Diagnose | aus | Roh-/HTML-/Probe-Daten in der Diagnose nur bei Aktivierung |

#### Bekannte Standard-Item-Codes

Das sind die Werte, mit denen die Integration ausgeliefert wird. Sie stammen aus
Community-Projekten und sind **Ausgangspunkte, keine garantierte oder vollständige
Liste** — Item-Codes variieren je nach Gerätetyp (Automatic Cl-pH, SALT/ASE,
PoolManager, PoolRelax) und Firmware. Nutze den Diagnose-Export (unten), um die
Codes zu sehen, die dein konkretes Gerät tatsächlich bereitstellt.

| Zweck | Code | Hinweise |
|-------|------|----------|
| pH-Dosierungs-Item | `5.42` | Bisher bei den unterstützten Familien gleich |
| pH-Messwert-Item | `4.2` | Automatic Cl-pH (discover-verifiziert) |
| Redox-Messwert-Item | `4.82` | Automatic Cl-pH (discover-verifiziert) |
| Temperatur-Messwert-Item | `1` | Geräteübergreifend stabil (fest) |
| Chlor / Redox-Item | `5.154` | Gemessenes Chlor / Redox (ACL usw.) |
| Salzelektrolyse-Item | `5.40` | Salzsysteme (ASE / SALT) |
| Wert für EIN | `19.17` | Wird als Ein-Wert gesendet |
| Wert für AUS | `19.18` | Wird als Aus-Wert gesendet |

**Gerätespezifisch:** die Codes oben sind für **Automatic Cl-pH** verifiziert; andere Modelle
(PoolManager, PoolRelax, SALT/ASE) können abweichen — per Optionen oder Diagnose anpassen.

Ein leeres Feld stellt den Standardwert wieder her. Beim Speichern wird die
Integration automatisch neu geladen, sodass die Schalter die neuen Werte sofort nutzen.

#### Codes am echten Gerät verifizieren

Die Item-Codes und Ein-/Aus-Werte stammen aus Community-Quellen und passen nicht
auf jedes Gerät. Zur Verifikation den Request im Bayrol-Webportal mitschneiden:
Portal öffnen, **F12 → Netzwerk**, Chlordosierung und pH-Dosierung jeweils einmal
manuell umschalten und die `data_json.php`-Requests auf die tatsächlichen
Item-Topics und Werte prüfen. Abweichende Werte in den Optionen oben eintragen —
ohne Codeänderung.

### Echte Item-Codes deines Geräts finden (Diagnose)

Statt zu raten, kann die Integration die Item-Codes auflisten, die dein Gerät
tatsächlich bereitstellt:

**Einstellungen → Geräte & Dienste → Bayrol Bridge → (dein Eintrag) → ⋮ → Diagnose herunterladen**

Bei manchen Geräten (z. B. Automatic Cl-pH, FW v2.30) ist kein HTTP-Readback der
Dosier-Zustände möglich: `getItems` liefert leere Items, `device_items` bleibt leer.
Live-Messwerte (pH, Redox, Temperatur) und Dosier-Schalter kommen über MQTT;
`getdata.php` bleibt nur für Diagnose verfügbar. Tatsächliche Dosierung im
Bayrol-Portal oder per MQTT prüfen.

Wo die Geräteseite Item-Divs bereitstellt, listet `device_items` in der Diagnose
jeden `item`-Code mit aktiv/inaktiv. Passenden Code in den Optionen eintragen
(Chlor-Item / pH-Item), dann im Portal verifizieren.

Bleibt `device_items` leer, **Debug-Diagnose (Rohdaten, nur zur Fehlersuche)** aktivieren,
Diagnose erneut laden und die Option danach deaktivieren. Zusätzlich enthalten:
`raw_getdata` und `data_json_probes`, falls `device_html_debug` leer bleibt.

## Entitäten

| Entität | Beschreibung |
|---------|--------------|
| `sensor.*_ph` | pH-Wert (MQTT) |
| `sensor.*_redox` | Redoxpotential in mV (MQTT) |
| `sensor.*_temperature` | Wassertemperatur in °C (MQTT) |
| `switch.*_chlorine_dosing` | Chlor / Redox-Dosierung ein/aus (MQTT set + Readback) |
| `switch.*_ph_dosing` | pH-Dosierung ein/aus (MQTT set + Readback) |
| `binary_sensor.*_connectivity` | MQTT-Verbindung |

Alarm-Sensoren werden **noch nicht** bereitgestellt (bekannte Einschränkung, bis die Alarm-Quelle über MQTT geklärt ist).

Die Dosier-Schalter lesen den Zustand per MQTT (`v/`-Topics) und sind bei
Verbindungsverlust nicht verfügbar (kein veralteter Wert). Nach einem Reconnect
fordert die Integration alle konfigurierten Items per `g/`-Topics erneut an.

## Sicherheit

Die Integration steuert **echte chemische Dosierung** über die Bayrol-Cloud.
Die Regelung liegt im Poolgerät; Home Assistant sendet nur Ein-/Aus-Befehle.

- Automatisierungen mit Hysterese, maximaler Laufzeit und Watchdog absichern.
- Änderungen zuerst manuell prüfen, bevor unbeaufsichtigte Automatisierungen laufen.
- Portal-Zugangsdaten und App-Link-Code geheim halten.

## Änderungen

Siehe [CHANGELOG.md](CHANGELOG.md).

## API-Quellen

Diese Integration nutzt die Bayrol-Webview-HTTP-API, dokumentiert bzw. reverse-engineered
durch Community-Projekte:

- [razem-io/ha-bayrol-cloud](https://github.com/razem-io/ha-bayrol-cloud) – Login, `getdata.php`, Diagnose
- [tdenolle/bayrol-poolaccess-mqtt](https://github.com/tdenolle/bayrol-poolaccess-mqtt) – MQTT-Item-IDs für Dosierungssteuerungen (`5.42`, `5.154`, `5.40`)

## Haftungsausschluss

Dies ist ein **inoffizielles** Community-Projekt. Es steht in keiner Verbindung zu
Bayrol und wird von Bayrol nicht unterstützt. Der Zugriff erfolgt **nur über die Cloud**
(keine lokale API). Nutzung auf eigenes Risiko.

## Entwicklung

```bash
pip install -r requirements-test.txt
pytest
```

## Lizenz

MIT – siehe [LICENSE](LICENSE).
