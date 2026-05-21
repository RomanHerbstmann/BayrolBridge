"""Tests for read-only raw API diagnostics helpers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.bayrol_bridge.api import (
    BayrolApiClient,
    BayrolConnectionError,
)

pytestmark = pytest.mark.asyncio

_READ_ONLY_FORBIDDEN = frozenset({"setItems", "value", "cmd"})


def _payload_keys(payload: dict | None) -> set[str]:
    if payload is None:
        return set()
    keys: set[str] = set(payload.keys())
    data = payload.get("data")
    if isinstance(data, dict):
        keys.update(data.keys())
        items = data.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if isinstance(item, dict):
                    keys.update(item.keys())
    return keys


def _assert_read_only_payload(payload: dict | None) -> None:
    assert _payload_keys(payload).isdisjoint(_READ_ONLY_FORBIDDEN)


async def test_async_get_raw_getdata_returns_body_on_200() -> None:
    """200 response returns raw body."""
    client = BayrolApiClient(AsyncMock())
    client._logged_in = True
    client._phpsessid = "sess"
    with patch.object(
        client,
        "_request_text_with_retry",
        new=AsyncMock(return_value=(200, "<html>pool</html>")),
    ) as mock_request:
        result = await client.async_get_raw_getdata("42")

    assert result == "<html>pool</html>"
    mock_request.assert_awaited_once()
    call = mock_request.await_args
    assert call.args[0] == "GET"
    assert "getdata.php?cid=42" in call.args[1]


async def test_async_get_raw_getdata_returns_error_marker() -> None:
    """Connection errors are returned as markers, not raised."""
    client = BayrolApiClient(AsyncMock())
    client._logged_in = True
    client._phpsessid = "sess"
    with patch.object(
        client,
        "_request_text_with_retry",
        new=AsyncMock(side_effect=BayrolConnectionError("timeout")),
    ):
        result = await client.async_get_raw_getdata("42")

    assert result == "<error: timeout>"


async def test_async_get_raw_getdata_non_200_status() -> None:
    """Non-200 responses return a status marker."""
    client = BayrolApiClient(AsyncMock())
    client._logged_in = True
    client._phpsessid = "sess"
    with patch.object(
        client,
        "_request_text_with_retry",
        new=AsyncMock(return_value=(503, "unavailable")),
    ):
        result = await client.async_get_raw_getdata("42")

    assert result == "<status 503>"


async def test_async_probe_data_json_tries_all_candidates() -> None:
    """All read-only variants are attempted; failures do not abort the loop."""
    client = BayrolApiClient(AsyncMock())
    client._logged_in = True
    client._phpsessid = "sess"
    responses = [
        (404, "not found"),
        (200, '{"items": []}'),
        BayrolConnectionError("offline"),
        (200, "not-json"),
        (200, '{"ok": true}'),
    ]
    call_count = 0

    async def fake_request(method: str, path: str, **kwargs: object) -> tuple[int, str]:
        nonlocal call_count
        if call_count < len(responses):
            outcome = responses[call_count]
            call_count += 1
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return 500, "done"

    with patch.object(
        client, "_request_text_with_retry", new=AsyncMock(side_effect=fake_request)
    ):
        attempts = await client.async_probe_data_json("42")

    assert len(attempts) == 5
    assert attempts[0]["status"] == 404
    assert attempts[1]["status"] == 200
    assert "error" in attempts[2]
    assert attempts[3]["status"] == 200
    assert attempts[4]["status"] == 200
    assert all("body_excerpt" in a or "error" in a for a in attempts)


async def test_async_probe_data_json_payloads_are_read_only() -> None:
    """Probe payloads never include switching fields."""
    client = BayrolApiClient(AsyncMock())
    client._logged_in = True
    client._phpsessid = "sess"

    captured_json: list[dict | None] = []

    async def fake_request(
        method: str, path: str, **kwargs: object
    ) -> tuple[int, str]:
        captured_json.append(kwargs.get("json"))  # type: ignore[arg-type]
        return 404, "nope"

    with patch.object(
        client, "_request_text_with_retry", new=AsyncMock(side_effect=fake_request)
    ):
        await client.async_probe_data_json("99")

    assert len(captured_json) == 5
    for payload in captured_json:
        _assert_read_only_payload(payload)
        if payload is not None:
            dumped = json.dumps(payload)
            assert "setItems" not in dumped
            assert '"value"' not in dumped
            assert '"cmd"' not in dumped
