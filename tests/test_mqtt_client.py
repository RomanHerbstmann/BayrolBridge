"""Tests for BayrolMqttClient (mocked paho, no live broker)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from paho.mqtt.client import MQTTMessage

from custom_components.bayrol_bridge.const import MQTT_PASSWORD, TOPIC_PREFIX
from custom_components.bayrol_bridge.mqtt_client import BayrolMqttClient

pytestmark = pytest.mark.asyncio

_SERIAL = "DEV999"
_TOKEN = "b" * 32


def _make_message(topic: str, payload: dict | str) -> MQTTMessage:
    msg = MQTTMessage()
    msg._topic = topic.encode("utf-8")
    if isinstance(payload, dict):
        msg.payload = json.dumps(payload).encode("utf-8")
    else:
        msg.payload = str(payload).encode("utf-8")
    return msg


@pytest.fixture
async def hass_loop(hass):
    """Use the pytest-homeassistant event loop."""
    return hass


async def test_on_message_full_payload(hass_loop) -> None:
    """Payload with t/createdAt/v: item from topic, value from v key."""
    received: list[tuple[str, str]] = []

    with patch("custom_components.bayrol_bridge.mqtt_client.Client") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        client = BayrolMqttClient(
            hass_loop,
            _TOKEN,
            _SERIAL,
            lambda item, value: received.append((item, value)),
        )
        paho_client = client._make_client()

    msg = _make_message(
        f"{TOPIC_PREFIX}/{_SERIAL}/v/5.42",
        {"t": "5.42", "createdAt": "2024-01-01", "v": "19.18"},
    )
    paho_client.on_message(paho_client, None, msg)
    await asyncio.sleep(0)

    assert received == [("5.42", "19.18")]


async def test_on_message_minimal_payload(hass_loop) -> None:
    """Payload with only v: item still derived from topic."""
    received: list[tuple[str, str]] = []

    with patch("custom_components.bayrol_bridge.mqtt_client.Client") as mock_client_cls:
        mock_client_cls.return_value = MagicMock()
        client = BayrolMqttClient(
            hass_loop,
            _TOKEN,
            _SERIAL,
            lambda item, value: received.append((item, value)),
        )
        paho_client = client._make_client()

    msg = _make_message(f"{TOPIC_PREFIX}/{_SERIAL}/v/1", {"v": "17.2"})
    paho_client.on_message(paho_client, None, msg)
    await asyncio.sleep(0)

    assert received == [("1", "17.2")]


async def test_on_connect_subscribes_v_wildcard(hass_loop) -> None:
    """CONNACK subscribes to d02/<serial>/v/#."""
    with patch("custom_components.bayrol_bridge.mqtt_client.Client") as mock_client_cls:
        mock_paho = MagicMock()
        mock_client_cls.return_value = mock_paho
        client = BayrolMqttClient(hass_loop, _TOKEN, _SERIAL, lambda _i, _v: None)
        paho_client = client._make_client()

    paho_client.on_connect(paho_client, None, {}, 0, None)

    paho_client.subscribe.assert_called_once_with(f"{TOPIC_PREFIX}/{_SERIAL}/v/#")
    assert client.connected is True


async def test_on_connection_change_connect_and_disconnect(hass_loop) -> None:
    """on_connection_change is invoked on successful connect and disconnect."""
    states: list[bool] = []

    with patch("custom_components.bayrol_bridge.mqtt_client.Client") as mock_client_cls:
        mock_paho = MagicMock()
        mock_client_cls.return_value = mock_paho
        client = BayrolMqttClient(
            hass_loop,
            _TOKEN,
            _SERIAL,
            lambda _i, _v: None,
            on_connection_change=states.append,
        )
        paho_client = client._make_client()

    paho_client.on_connect(paho_client, None, {}, 0, None)
    await asyncio.sleep(0)
    assert states == [True]

    paho_client.on_disconnect(paho_client, None, {}, 0, None)
    await asyncio.sleep(0)
    assert states == [True, False]


async def test_async_set_payload(hass_loop) -> None:
    """async_set publishes JSON {\"t\": item, \"v\": value}."""
    published: list[tuple[str, bytes]] = []

    def capture_publish(topic: str, payload: bytes = b"", **kwargs: object) -> None:
        published.append((topic, payload))

    with patch("custom_components.bayrol_bridge.mqtt_client.Client") as mock_client_cls:
        mock_paho = MagicMock()
        mock_paho.publish.side_effect = capture_publish
        mock_client_cls.return_value = mock_paho
        client = BayrolMqttClient(hass_loop, _TOKEN, _SERIAL, lambda _i, _v: None)
        client._client = mock_paho
        client._connected = True
        await client.async_set("5.42", "19.17")

    assert len(published) == 1
    topic, body = published[0]
    assert topic == f"{TOPIC_PREFIX}/{_SERIAL}/s/5.42"
    assert json.loads(body.decode()) == {"t": "5.42", "v": "19.17"}


async def test_make_client_uses_token_and_password(hass_loop) -> None:
    """Client is configured with access token username and '*' password."""
    with patch("custom_components.bayrol_bridge.mqtt_client.Client") as mock_client_cls:
        mock_paho = MagicMock()
        mock_client_cls.return_value = mock_paho
        client = BayrolMqttClient(hass_loop, _TOKEN, _SERIAL, lambda _i, _v: None)
        client._make_client()

    mock_client_cls.assert_called_once()
    mock_paho.username_pw_set.assert_called_once_with(_TOKEN, MQTT_PASSWORD)
    mock_paho.tls_set.assert_called_once()
    mock_paho.ws_set_options.assert_called_once_with(path="/")
