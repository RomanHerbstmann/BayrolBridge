# Bayrol Bridge – Home-Assistant-Custom-Integration

**Sprache:** [Deutsch](README.de.md) · [English](README.md)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![hassfest](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml/badge.svg)](https://github.com/RomanHerbstmann/BayrolBridge/actions/workflows/validate.yml)

Inoffizielle Home-Assistant-Integration für [Bayrol Pool Access](https://www.bayrol-poolaccess.de/webview).

## Funktionen

- **Sensoren:** pH, Redox (mV), Temperatur (°C)
- **Schalter:** Chlordosierung (Redox/ACL), pH-Dosierung
- **Binärsensoren:** Dosierung aktiv je Steuerung, Messwert-Alarme, Cloud-Verbindung
- Config Flow mit Steuerungs-Erkennung
- Sitzungsstabilität mit automatischem Re-Login

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

### Optionen (konfigurierbare Item-Codes)

Die Item-Codes für Dosierung und die Ein-/Aus-Werte unterscheiden sich je nach
Bayrol-Gerätegeneration. Da sie nicht zuverlässig erkannt werden können, sind sie
ohne Codeänderung editierbar:

**Einstellungen → Geräte & Dienste → Bayrol Bridge → Konfigurieren**

| Option | Standard | Hinweise |
|--------|----------|----------|
| Chlor-/Desinfektionsmethode | `redox` | Bequeme Voreinstellung für das Chlor-Item |
| Chlor-Item-Override | _(leer)_ | Nur setzen, wenn die Methode nicht passt; überschreibt die Methode, wenn ausgefüllt |
| pH-Item | `5.42` | pH-Dosierungs-Item |
| Wert für EIN | `19.17` | Ein-Wert, der an `data_json.php` gesendet wird |
| Wert für AUS | `19.18` | Aus-Wert, der an `data_json.php` gesendet wird |

#### Bekannte Standard-Item-Codes

Das sind die Werte, mit denen die Integration ausgeliefert wird. Sie stammen aus
Community-Projekten und sind **Ausgangspunkte, keine garantierte oder vollständige
Liste** — Item-Codes variieren je nach Gerätetyp (Automatic Cl-pH, SALT/ASE,
PoolManager, PoolRelax) und Firmware. Nutze den Diagnose-Export (unten), um die
Codes zu sehen, die dein konkretes Gerät tatsächlich bereitstellt.

| Zweck | Code | Hinweise |
|-------|------|----------|
| pH-Dosierungs-Item | `5.42` | Bisher bei den unterstützten Familien gleich |
| Chlor / Redox-Item | `5.154` | Gemessenes Chlor / Redox (ACL usw.) |
| Salzelektrolyse-Item | `5.40` | Salzsysteme (ASE / SALT) |
| Wert für EIN | `19.17` | Wird als Ein-Wert gesendet |
| Wert für AUS | `19.18` | Wird als Aus-Wert gesendet |

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

In der heruntergeladenen JSON-Datei listet der Abschnitt `device_items` jeden auf
der Geräteseite gefundenen `item`-Code inklusive des aktuellen Zustands aktiv oder
inaktiv. Den passenden Code in den Optionen eintragen (Chlor-Item / pH-Item), dann
einmal umschalten und im Bayrol-Portal prüfen.

Bleibt `device_items` bei deinem Gerät leer, aktiviere unter den Integrationsoptionen
die **HTML-Diagnose (nur zur Fehlersuche)**, lade die Diagnose erneut herunter und
deaktiviere den Schalter danach wieder.

## Entitäten

| Entität | Beschreibung |
|---------|--------------|
| `sensor.*_ph` | pH-Wert |
| `sensor.*_redox` | Redoxpotential (mV) |
| `sensor.*_temperature` | Wassertemperatur (°C) |
| `switch.*_chlorine_dosing` | Chlor / Redox-Dosierung ein/aus |
| `switch.*_ph_dosing` | pH-Dosierung ein/aus |
| `binary_sensor.*_chlorine_dosing_active` | Chlordosierung läuft |
| `binary_sensor.*_ph_dosing_active` | pH-Dosierung läuft |
| `binary_sensor.*_connectivity` | Cloud-Verbindung |
| `binary_sensor.*_*_alarm` | Messwert-Alarme |

## API-Quellen

Diese Integration nutzt die Bayrol-Webview-HTTP-API, dokumentiert bzw. reverse-engineered
durch Community-Projekte:

- [razem-io/ha-bayrol-cloud](https://github.com/razem-io/ha-bayrol-cloud) – Login, `getdata.php`, `data_json.php` / `setItems`
- [tdenolle/bayrol-poolaccess-mqtt](https://github.com/tdenolle/bayrol-poolaccess-mqtt) – MQTT-Item-IDs für Dosierungssteuerungen (`5.42`, `5.154`, `5.40`)

## Haftungsausschluss

Dies ist ein **inoffizielles** Community-Projekt. Es steht in keiner Verbindung zu
Bayrol und wird von Bayrol nicht unterstützt. Nutzung auf eigenes Risiko.

## Entwicklung

```bash
pip install -r requirements-test.txt
pytest
```

## Lizenz

MIT – siehe [LICENSE](LICENSE).
