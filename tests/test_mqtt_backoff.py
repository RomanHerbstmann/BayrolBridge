"""Tests for MQTT reauth backoff helper."""

from custom_components.bayrol_bridge.mqtt_client import next_backoff


def test_next_backoff() -> None:
    """Backoff starts at 5 s and doubles up to 5 min."""
    assert next_backoff(0) == 5
    assert next_backoff(5) == 10
    assert next_backoff(150) == 300
    assert next_backoff(300) == 300
