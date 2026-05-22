"""MQTT-over-WebSocket client for Bayrol Pool Access."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion, Client, MQTTMessage
from paho.mqtt.enums import MQTTProtocolVersion

from .api import BayrolConnectionError
from .const import (
    MQTT_HOST,
    MQTT_KEEPALIVE,
    MQTT_PASSWORD,
    MQTT_PORT,
    MQTT_WS_PATH,
    TOPIC_PREFIX,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 15.0


def _random_client_suffix() -> str:
    return f"{random.randint(0, 0xFFFFFF):06x}"


def _item_from_topic(topic: str, serial: str) -> str | None:
    prefix = f"{TOPIC_PREFIX}/{serial}/v/"
    if not topic.startswith(prefix):
        return None
    return topic[len(prefix) :]


def _parse_value_payload(payload: bytes) -> str | None:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    v = data.get("v")
    return str(v) if v is not None else None


class BayrolMqttClient:
    """Bayrol MQTT-over-WebSocket client (paho, sync I/O in executor)."""

    def __init__(
        self,
        hass: HomeAssistant,
        access_token: str,
        serial: str,
        on_value: Callable[[str, str], None],
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        """Initialize client; ``on_value`` receives (item, value) from v/-topics."""
        self._hass = hass
        self._access_token = access_token
        self._serial = serial
        self._on_value = on_value
        self._on_connection_change = on_connection_change
        self._client: Client | None = None
        self._connected = False
        self._ready = asyncio.Event()

    @property
    def connected(self) -> bool:
        """Whether the last CONNACK succeeded."""
        return self._connected

    def _make_client(self) -> Client:
        client_id = f"user_{_random_client_suffix()}"
        client = Client(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=MQTTProtocolVersion.MQTTv311,
            transport="websockets",
        )
        client.username_pw_set(self._access_token, MQTT_PASSWORD)
        client.tls_set()
        client.ws_set_options(path=MQTT_WS_PATH)
        client.reconnect_delay_set(min_delay=1, max_delay=30)

        def on_connect(
            mqtt_client: Client,
            _userdata: Any,
            _flags: mqtt.ConnectFlags,
            reason_code: mqtt.ReasonCode,
            _properties: mqtt.Properties | None,
        ) -> None:
            if reason_code != 0 and getattr(reason_code, "value", reason_code) != 0:
                self._connected = False
                _LOGGER.warning("MQTT connect failed: %s", reason_code)
                self._notify_connection_change(False)
                return
            self._connected = True
            sub_topic = f"{TOPIC_PREFIX}/{self._serial}/v/#"
            mqtt_client.subscribe(sub_topic)
            self._notify_connection_change(True)
            self._hass.loop.call_soon_threadsafe(self._ready.set)

        def on_disconnect(
            _mqtt_client: Client,
            _userdata: Any,
            _disconnect_flags: mqtt.DisconnectFlags,
            _reason_code: mqtt.ReasonCode,
            _properties: mqtt.Properties | None,
        ) -> None:
            self._connected = False
            self._notify_connection_change(False)

        def on_message(
            _mqtt_client: Client, _userdata: Any, msg: MQTTMessage
        ) -> None:
            item = _item_from_topic(msg.topic, self._serial)
            if item is None:
                return
            value = _parse_value_payload(msg.payload)
            if value is None:
                return
            self._hass.loop.call_soon_threadsafe(self._dispatch_value, item, value)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        return client

    def _dispatch_value(self, item: str, value: str) -> None:
        self._on_value(item, value)

    def _notify_connection_change(self, connected: bool) -> None:
        if self._on_connection_change is None:
            return
        self._hass.loop.call_soon_threadsafe(self._on_connection_change, connected)

    async def async_connect(self) -> None:
        """Connect via WebSocket and subscribe to v/#."""
        self._ready.clear()
        self._client = self._make_client()

        def _connect_sync() -> None:
            assert self._client is not None
            self._client.connect(MQTT_HOST, MQTT_PORT, keepalive=MQTT_KEEPALIVE)
            self._client.loop_start()

        await self._hass.loop.run_in_executor(None, _connect_sync)
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=_CONNECT_TIMEOUT)
        except TimeoutError as err:
            await self.async_disconnect()
            raise BayrolConnectionError("MQTT connection timeout") from err

    async def async_request(self, item: str) -> None:
        """Publish g/<item> with empty payload to request a value."""
        topic = f"{TOPIC_PREFIX}/{self._serial}/g/{item}"
        await self._publish(topic, b"")

    async def async_set(self, item: str, value: str) -> None:
        """Publish s/<item> with {\"t\": item, \"v\": value}."""
        topic = f"{TOPIC_PREFIX}/{self._serial}/s/{item}"
        body = json.dumps({"t": item, "v": value}, separators=(",", ":"))
        await self._publish(topic, body.encode("utf-8"))

    async def _publish(self, topic: str, payload: bytes) -> None:
        if self._client is None or not self._connected:
            raise BayrolConnectionError("MQTT not connected")

        def _pub() -> None:
            assert self._client is not None
            self._client.publish(topic, payload=payload, qos=0)

        await self._hass.loop.run_in_executor(None, _pub)

    async def async_disconnect(self) -> None:
        """Stop the network loop and disconnect."""
        client = self._client
        if client is None:
            return

        def _disconnect_sync() -> None:
            client.loop_stop()
            client.disconnect()

        await self._hass.loop.run_in_executor(None, _disconnect_sync)
        self._client = None
        self._connected = False
        self._ready.clear()
