#!/usr/bin/env python3
"""Stufe 1: MQTT-over-WebSocket Machbarkeits-PoC (standalone, nicht in der Integration).

Verwendung (aus ha-bayrol-pool/):
  python3 tools/mqtt_poc.py --code <APP_LINK_CODE> read
  python3 tools/mqtt_poc.py --code <APP_LINK_CODE> discover
  python3 tools/mqtt_poc.py --code <APP_LINK_CODE> discover --seconds 90

Einmalig Abhängigkeiten (Homebrew-python3 erlaubt kein globales pip):
  python3 -m venv .venv
  .venv/bin/pip install -r requirements-dev.txt

Das Skript wechselt automatisch auf .venv/bin/python, falls vorhanden.

Umgebungsvariable: BAYROL_APP_LINK_CODE (Fallback für --code)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import threading
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin


def _reexec_with_venv_if_needed() -> None:
    """Nutze Projekt-.venv, wenn System-python3 paho/requests nicht hat."""
    try:
        import paho.mqtt.client  # noqa: F401
        import requests  # noqa: F401
        return
    except ImportError:
        pass

    repo_root = Path(__file__).resolve().parent.parent
    venv_dir = repo_root / ".venv"
    in_project_venv = Path(sys.prefix).resolve() == venv_dir.resolve()

    for name in ("python3", "python"):
        venv_python = venv_dir / "bin" / name
        if venv_python.is_file() and not in_project_venv:
            os.execv(venv_python, [str(venv_python), *sys.argv])

    print(
        "Fehlende Python-Pakete (paho-mqtt, requests).\n\n"
        "Im Verzeichnis ha-bayrol-pool ausführen:\n"
        "  python3 -m venv .venv\n"
        "  .venv/bin/pip install -r requirements-dev.txt\n"
        "  python3 tools/mqtt_poc.py --help\n",
        file=sys.stderr,
    )
    raise SystemExit(1)


_reexec_with_venv_if_needed()

import paho.mqtt.client as mqtt
import requests

API_BASE = "https://www.bayrol-poolaccess.de"
CREDENTIALS_URL = f"{API_BASE}/api/"
WEBVIEW_BASE = f"{API_BASE}/webview"
MQTT_HOST = "www.bayrol-poolaccess.de"
MQTT_PORT = 8083
MQTT_WS_PATH = "/"
# Bayrol-App / tdenolle/bayrol-poolaccess-mqtt: Passwort ist "*", nicht leer
MQTT_PASSWORD = "*"
TOPIC_PREFIX = "d02"

DEFAULT_READ_ITEMS = ("1", "5.42", "5.154")
LISTEN_SECONDS = 10
DISCOVER_SECONDS_DEFAULT = 60
DISCOVER_GET_BATCH_SIZE = 50
DISCOVER_GET_BATCH_SLEEP = 0.2
DISCOVER_ITEMS: tuple[str, ...] = tuple(
    [str(i) for i in range(1, 21)]
    + [f"4.{n}" for n in range(1, 130)]
    + [f"5.{n}" for n in range(1, 200)]
)

LOG = logging.getLogger("mqtt_poc")


class _LoginFormParser(HTMLParser):
    """Extract input fields from the portal login form."""

    def __init__(self) -> None:
        super().__init__()
        self._in_form = False
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "form" and (
            attr.get("id") == "form_login" or not self._in_form
        ):
            self._in_form = True
        if self._in_form and tag == "input":
            name = attr.get("name")
            if name:
                self.fields[name] = attr.get("value") or ""


def mask_token(token: str) -> str:
    """Return a safe log representation (first 4 chars only)."""
    if len(token) <= 4:
        return "****"
    return f"{token[:4]}…"


def _random_client_suffix() -> str:
    """Wie Bayrol-App: user_<8 hex-Zeichen>."""
    return format(random.getrandbits(32), "08x")[:8]


def _parse_login_form(html: str) -> dict[str, str]:
    parser = _LoginFormParser()
    parser.feed(html)
    return parser.fields


def _classify_login_response(html: str) -> str:
    low = html.lower()
    if "passwort falsch" in low or "benutzername oder passwort" in low:
        return "auth"
    if "zeit abgelaufen" in low:
        return "timeout"
    if 'class="error_text"' in low or "class='error_text'" in low:
        return "auth"
    return "ok"


def portal_login(session: requests.Session, username: str, password: str) -> None:
    """Establish a Bayrol Pool Access webview session (PHPSESSID cookie)."""
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) "
                "Gecko/20100101 Firefox/131.0"
            ),
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
        }
    )

    init_paths = (
        "p/login.php?r=reg",
        "index.php",
        "p/login.php",
    )
    form_html: str | None = None
    for path in init_paths:
        url = urljoin(WEBVIEW_BASE + "/", path)
        try:
            resp = session.get(url, timeout=30, allow_redirects=True)
            resp.raise_for_status()
        except requests.RequestException as err:
            LOG.debug("Init path %s failed: %s", path, err)
            continue
        if _parse_login_form(resp.text):
            form_html = resp.text
            break

    if not session.cookies.get("PHPSESSID"):
        raise RuntimeError("Login fehlgeschlagen: kein PHPSESSID erhalten")

    if not form_html:
        raise RuntimeError("Login fehlgeschlagen: Anmeldeformular nicht gefunden")

    form_data = _parse_login_form(form_html)
    if not form_data:
        raise RuntimeError("Login fehlgeschlagen: Formularfelder fehlen")

    form_data["username"] = username
    form_data["password"] = password
    form_data.setdefault("login", "Anmelden")

    post_urls = (
        urljoin(WEBVIEW_BASE + "/", "p/login.php?r=reg"),
        urljoin(WEBVIEW_BASE + "/", "p/login.php"),
    )
    login_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": API_BASE,
        "Referer": urljoin(WEBVIEW_BASE + "/", "p/login.php?r=reg"),
    }

    timeout_retried = False
    last_error: Exception | None = None
    for login_url in post_urls:
        try:
            resp = session.post(
                login_url,
                data=form_data,
                headers=login_headers,
                timeout=30,
                allow_redirects=True,
            )
            result = _classify_login_response(resp.text)
            if result == "timeout" and not timeout_retried:
                timeout_retried = True
                refresh = session.get(
                    urljoin(WEBVIEW_BASE + "/", "p/login.php?r=reg"),
                    timeout=30,
                    allow_redirects=True,
                )
                refresh.raise_for_status()
                form_data = _parse_login_form(refresh.text)
                form_data["username"] = username
                form_data["password"] = password
                form_data.setdefault("login", "Anmelden")
                resp = session.post(
                    urljoin(WEBVIEW_BASE + "/", "p/login.php?r=reg"),
                    data=form_data,
                    headers=login_headers,
                    timeout=30,
                    allow_redirects=True,
                )
                result = _classify_login_response(resp.text)
            if result == "auth":
                raise RuntimeError("Login fehlgeschlagen: ungültige Zugangsdaten")
            if result == "ok":
                return
            if result == "timeout":
                raise RuntimeError(
                    "Login fehlgeschlagen: Captcha/Zeit abgelaufen — erneut versuchen"
                )
        except RuntimeError:
            raise
        except requests.RequestException as err:
            last_error = err

    if last_error:
        raise RuntimeError(f"Login fehlgeschlagen: {last_error}") from last_error
    raise RuntimeError("Login fehlgeschlagen")


def fetch_credentials(
    code: str,
    *,
    session: requests.Session | None = None,
) -> tuple[str, str]:
    """GET /api/?code=… → (accessToken, deviceSerial)."""
    http = session or requests.Session()
    try:
        resp = http.get(
            CREDENTIALS_URL,
            params={"code": code},
            timeout=30,
            headers={"Accept": "application/json"},
        )
    except requests.RequestException as err:
        raise RuntimeError(f"Credentials-Anfrage fehlgeschlagen: {err}") from err

    if resp.status_code != 200:
        excerpt = (resp.text or "")[:200]
        raise RuntimeError(
            f"Credentials-Anfrage HTTP {resp.status_code}"
            + (f": {excerpt}" if excerpt else "")
        )

    try:
        data = resp.json()
    except json.JSONDecodeError as err:
        raise RuntimeError("Credentials-Antwort ist kein gültiges JSON") from err

    token = data.get("accessToken")
    serial = data.get("deviceSerial")
    if not token or not serial:
        raise RuntimeError(
            "Credentials-Antwort unvollständig "
            f"(Keys: {', '.join(sorted(data.keys()))})"
        )
    return str(token), str(serial)


def _make_mqtt_client(client_id: str) -> mqtt.Client:
    """paho-mqtt 1.x und 2.x (Callback API v2 wie Integration)."""
    kwargs: dict[str, Any] = {
        "client_id": client_id,
        "protocol": mqtt.MQTTv311,
        "transport": "websockets",
        "clean_session": False,
    }
    if hasattr(mqtt, "CallbackAPIVersion"):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, **kwargs)
    return mqtt.Client(**kwargs)


def _connect_reason_ok(reason: Any) -> bool:
    if hasattr(reason, "is_failure"):
        return not reason.is_failure
    return int(reason) == mqtt.MQTT_ERR_SUCCESS


def connect(access_token: str, *, mqtt_password: str = MQTT_PASSWORD) -> mqtt.Client:
    """MQTT-over-WebSocket: username=accessToken, password='*' (Bayrol-Standard)."""
    client_id = f"user_{_random_client_suffix()}"
    client = _make_mqtt_client(client_id)
    client.username_pw_set(access_token, mqtt_password)
    client.tls_set()
    client.ws_set_options(path=MQTT_WS_PATH)

    connected = threading.Event()
    connect_rc: list[int] = []

    def on_connect(
        _client: mqtt.Client,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any = None,
    ) -> None:
        connect_rc.append(reason_code)
        reason = (
            mqtt.connack_string(reason_code)
            if hasattr(mqtt, "connack_string")
            else str(reason_code)
        )
        LOG.info("MQTT on_connect reason=%s (%s)", reason_code, reason)
        connected.set()

    client.on_connect = on_connect
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    if not connected.wait(timeout=15):
        client.loop_stop()
        raise RuntimeError("MQTT-Verbindung: Timeout beim Warten auf CONNACK")

    if not connect_rc or not _connect_reason_ok(connect_rc[-1]):
        rc = connect_rc[-1] if connect_rc else -1
        client.loop_stop()
        reason = mqtt.connack_string(rc) if hasattr(mqtt, "connack_string") else str(rc)
        raise RuntimeError(f"MQTT-Verbindung fehlgeschlagen: reason={rc} ({reason})")

    return client


def _topic_v_prefix(serial: str) -> str:
    return f"{TOPIC_PREFIX}/{serial}/v/"


def _item_from_v_topic(topic: str, serial: str) -> str | None:
    prefix = _topic_v_prefix(serial)
    if not topic.startswith(prefix):
        return None
    return topic[len(prefix) :]


def read_mode(
    client: mqtt.Client,
    serial: str,
    items: tuple[str, ...],
) -> dict[str, str]:
    """Subscribe v/#, sendet g/<item>, sammelt 10 s Werte."""
    values: dict[str, str] = {}
    lock = threading.Lock()

    def on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")
        LOG.info("RAW %s → %s", msg.topic, payload)
        item = _item_from_v_topic(msg.topic, serial)
        if item is None:
            return
        with lock:
            values[item] = payload

    client.on_message = on_message
    sub_topic = f"{TOPIC_PREFIX}/{serial}/v/#"
    client.subscribe(sub_topic, qos=0)
    LOG.info("Subscribed: %s", sub_topic)

    time.sleep(0.5)
    for item in items:
        get_topic = f"{TOPIC_PREFIX}/{serial}/g/{item}"
        client.publish(get_topic, payload=b"", qos=0)
        LOG.info("Published GET: %s", get_topic)

    LOG.info("Lausche %s s auf v/-Topics …", LISTEN_SECONDS)
    time.sleep(LISTEN_SECONDS)

    with lock:
        return dict(values)


def _extract_v_from_payload(payload: str) -> tuple[str, str | None]:
    """JSON-Key ``v`` extrahieren; bei Fehler (Anzeige, None) = nur roh."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload, None
    if isinstance(data, dict) and "v" in data:
        return str(data["v"]), payload
    return payload, None


def discover_mode(
    client: mqtt.Client,
    serial: str,
    *,
    seconds: int = DISCOVER_SECONDS_DEFAULT,
) -> dict[str, str]:
    """Subscribe v/#, GET-Sturm auf Kandidaten, alle v/-Items sammeln."""
    values: dict[str, str] = {}
    lock = threading.Lock()

    def on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")
        LOG.info("RAW %s → %s", msg.topic, payload)
        item = _item_from_v_topic(msg.topic, serial)
        if item is None:
            return
        with lock:
            values[item] = payload

    client.on_message = on_message
    sub_topic = f"{TOPIC_PREFIX}/{serial}/v/#"
    client.subscribe(sub_topic, qos=0)
    LOG.info("Subscribed: %s", sub_topic)

    time.sleep(0.5)
    items = DISCOVER_ITEMS
    LOG.info(
        "Discover: sende g/ für %s Kandidaten (%s pro %.1f s) …",
        len(items),
        DISCOVER_GET_BATCH_SIZE,
        DISCOVER_GET_BATCH_SLEEP,
    )
    for batch_start in range(0, len(items), DISCOVER_GET_BATCH_SIZE):
        batch = items[batch_start : batch_start + DISCOVER_GET_BATCH_SIZE]
        for item in batch:
            get_topic = f"{TOPIC_PREFIX}/{serial}/g/{item}"
            client.publish(get_topic, payload=b"", qos=0)
        if batch_start + DISCOVER_GET_BATCH_SIZE < len(items):
            time.sleep(DISCOVER_GET_BATCH_SLEEP)

    LOG.info("Lausche %s s auf alle v/-Topics …", seconds)
    time.sleep(seconds)

    with lock:
        return dict(values)


def set_mode(
    client: mqtt.Client,
    serial: str,
    item: str,
    value: str,
) -> bool:
    """Publish s/<item>, wartet auf Bestätigung v/<item>."""
    confirmed = threading.Event()
    confirmed_value: list[str] = []
    expected_topic = f"{TOPIC_PREFIX}/{serial}/v/{item}"

    def on_message(_client: mqtt.Client, _userdata: Any, msg: mqtt.MQTTMessage) -> None:
        payload = msg.payload.decode("utf-8", errors="replace")
        LOG.info("RAW %s → %s", msg.topic, payload)
        if msg.topic == expected_topic:
            confirmed_value.append(payload)
            confirmed.set()

    client.on_message = on_message
    client.subscribe(expected_topic, qos=0)
    LOG.info("Subscribed (Bestätigung): %s", expected_topic)

    set_topic = f"{TOPIC_PREFIX}/{serial}/s/{item}"
    body = json.dumps({"t": item, "v": value}, separators=(",", ":"))
    client.publish(set_topic, payload=body.encode("utf-8"), qos=0)
    LOG.info("Published SET: %s → %s", set_topic, body)

    if not confirmed.wait(timeout=LISTEN_SECONDS):
        LOG.warning("Keine Bestätigung auf %s innerhalb von %s s", expected_topic, LISTEN_SECONDS)
        return False

    received = confirmed_value[-1] if confirmed_value else ""
    match = _value_matches(received, item, value)
    LOG.info(
        "Bestätigung: erwartet v=%r, empfangen=%r → %s",
        value,
        received,
        "OK" if match else "ABWEICHUNG",
    )
    return match


def _value_matches(payload: str, item: str, expected: str) -> bool:
    """Prüft ob die Bestätigung den gesendeten Wert enthält."""
    if payload.strip() == expected:
        return True
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return expected in payload
    if isinstance(data, dict):
        if str(data.get("v")) == expected:
            return True
        if str(data.get("value")) == expected:
            return True
        if data.get("t") == item and str(data.get("v")) == expected:
            return True
    return expected in payload


def _parse_set_arg(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"--set erwartet ITEM=VALUE, erhalten: {raw!r}"
        )
    item, _, value = raw.partition("=")
    item, value = item.strip(), value.strip()
    if not item or not value:
        raise argparse.ArgumentTypeError(
            f"--set erwartet ITEM=VALUE, erhalten: {raw!r}"
        )
    return item, value


def _print_results_table(values: dict[str, str]) -> None:
    if not values:
        print("  (keine v/-Nachrichten empfangen)")
        return
    width = max(len(k) for k in values)
    print(f"  {'Item':<{width}}  Wert (roh)")
    print(f"  {'-' * width}  {'-' * 20}")
    for item in sorted(values):
        print(f"  {item:<{width}}  {values[item]}")


def _print_discover_table(values: dict[str, str]) -> None:
    if not values:
        print("  (keine v/-Nachrichten empfangen)")
        return
    width = max(len(k) for k in values)
    print(f"  {'Item':<{width}}  v")
    print(f"  {'-' * width}  {'-' * 16}")
    for item in sorted(values, key=_discover_sort_key):
        display, _parsed = _extract_v_from_payload(values[item])
        print(f"  {item:<{width}}  {display}")


def _discover_sort_key(item: str) -> tuple[int, int, str]:
    """Numerisch sortieren: 1, 4.2, 5.42 (nicht lexikographisch)."""
    parts = item.split(".")
    try:
        return (len(parts), int(parts[0]), int(parts[1]) if len(parts) > 1 else 0, item)
    except ValueError:
        return (99, 0, 0, item)


def build_parser() -> argparse.ArgumentParser:
    epilog = """
Beispiele:
  %(prog)s --code <CODE> read
  %(prog)s --code <CODE> read --items 1,5.42,5.154
  %(prog)s --code <CODE> discover
  %(prog)s --code <CODE> discover --seconds 90
  %(prog)s --code <CODE> set --set 5.42=19.17

Hinweis discover: Nur GET (g/) + Lauschen — schaltet nichts. Breiter
Kandidaten-Sturm, um alle v/-Items sichtbar zu machen (pH/Redox/Temp zuordnen).

Hinweis set: Schaltet die Dosierung (pH-Item 5.42). Den ursprünglichen Wert
danach wiederherstellen (z. B. --set 5.42=19.18 für Aus).
"""
    parser = argparse.ArgumentParser(
        description="Bayrol MQTT-over-WebSocket PoC (Stufe 1)",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--code",
        default=os.environ.get("BAYROL_APP_LINK_CODE"),
        help="App-Link-Code (oder Env BAYROL_APP_LINK_CODE)",
    )
    parser.add_argument(
        "--with-login",
        nargs=2,
        metavar=("USER", "PASS"),
        help="Optional: vorher Portal-Login für /api/?code=…",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug-Logging",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    read_p = sub.add_parser("read", help="Werte lesen (nur GET, kein Schalten)")
    read_p.add_argument(
        "--items",
        default=",".join(DEFAULT_READ_ITEMS),
        help=f"Komma-getrennte Item-IDs (Standard: {','.join(DEFAULT_READ_ITEMS)})",
    )

    set_p = sub.add_parser(
        "set",
        help="Einen Wert setzen (SICHERHEIT: nur mit explizitem --set)",
    )
    set_p.add_argument(
        "--set",
        required=True,
        type=_parse_set_arg,
        metavar="ITEM=VALUE",
        help="Zu schaltendes Item, z. B. 5.42=19.17 (pH Dosierung ein)",
    )

    discover_p = sub.add_parser(
        "discover",
        help="Alle v/-Items sammeln (GET-Sturm + langes Lauschen, nur lesend)",
    )
    discover_p.add_argument(
        "--seconds",
        type=int,
        default=DISCOVER_SECONDS_DEFAULT,
        metavar="SEC",
        help=f"Lauschzeit nach GET-Sturm (Standard: {DISCOVER_SECONDS_DEFAULT})",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if not args.code:
        parser.error("--code oder BAYROL_APP_LINK_CODE erforderlich")

    cred_ok = False
    mqtt_ok = False
    access_token = ""
    serial = ""

    http = requests.Session()
    if args.with_login:
        user, password = args.with_login
        LOG.info("Portal-Login für %s …", user)
        try:
            portal_login(http, user, password)
            LOG.info("Portal-Login erfolgreich")
        except RuntimeError as err:
            print(f"❌ Portal-Login: {err}")
            return 1

    try:
        access_token, serial = fetch_credentials(args.code, session=http)
        cred_ok = True
        print(
            f"✅ Credentials: Serial={serial}, "
            f"Token={mask_token(access_token)}"
        )
    except RuntimeError as err:
        print(f"❌ Credentials: {err}")
        if not args.with_login:
            print(
                "   Tipp: Erneut mit --with-login USER PASS versuchen, "
                "falls der Code eine Session braucht."
            )
        return 1

    client: mqtt.Client | None = None
    try:
        client = connect(access_token)
        mqtt_ok = True
        print("✅ MQTT verbunden")
    except RuntimeError as err:
        print(f"❌ MQTT: {err}")
        return 1

    exit_code = 0
    try:
        if args.command == "read":
            items = tuple(i.strip() for i in args.items.split(",") if i.strip())
            if not items:
                print("❌ read: --items ist leer")
                return 1
            print(f"\nRead-Modus: Items={', '.join(items)}, lausche {LISTEN_SECONDS}s …\n")
            values = read_mode(client, serial, items)
            print("\nEmpfangene v/-Items:")
            _print_results_table(values)
            if not values:
                print("❌ Read: keine Werte empfangen")
                exit_code = 1
            else:
                print(f"✅ Read: {len(values)} Item(s) mit Wert")

        elif args.command == "discover":
            if args.seconds < 1:
                print("❌ discover: --seconds muss >= 1 sein")
                return 1
            print(
                f"\nDiscover-Modus: {len(DISCOVER_ITEMS)} GET-Kandidaten, "
                f"lausche {args.seconds}s …\n"
            )
            values = discover_mode(client, serial, seconds=args.seconds)
            print("\nEntdeckte v/-Items (v = JSON-Key, roh nur bei Parse-Fehler):")
            _print_discover_table(values)
            if not values:
                print("❌ Discover: keine Werte empfangen")
                exit_code = 1
            else:
                print(f"✅ Discover: {len(values)} Item(s) mit Wert")

        elif args.command == "set":
            item, value = args.set
            print(
                f"\nSet-Modus: schalte Item {item} → {value} "
                f"(Bestätigung max. {LISTEN_SECONDS}s) …\n"
            )
            ok = set_mode(client, serial, item, value)
            if ok:
                print(f"✅ Set: Bestätigung für {item} entspricht {value!r}")
            else:
                print(f"❌ Set: Bestätigung für {item} fehlt oder weicht ab")
                exit_code = 1
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()

    if not cred_ok:
        print("❌ Credentials (intern)")
        exit_code = 1
    if not mqtt_ok:
        print("❌ MQTT (intern)")
        exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
