"""Tests for Bayrol API client."""

from __future__ import annotations

import asyncio
import re

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.bayrol_pool.api import (
    BayrolApiClient,
    BayrolAuthError,
    BayrolConnectionError,
    _parse_control_states,
    _parse_pool_data,
)
from custom_components.bayrol_pool.const import BASE_URL, PATH_DATA_JSON

def test_parse_pool_data(pool_data_html: str) -> None:
    """Parse measurement values from HTML."""
    data = _parse_pool_data(pool_data_html)
    assert data["pH"] == 7.2
    assert data["mV"] == 650.0
    assert data["T"] == 24.5
    assert data["status"] == "online"


pytestmark = pytest.mark.asyncio


async def test_login_and_fetch(
    login_form_html: str,
    plants_html: str,
    pool_data_html: str,
    device_html: str,
) -> None:
    """Login, list controllers, and fetch pool data."""
    with aioresponses() as mocked:
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            payload=login_form_html,
            headers={"Set-Cookie": "PHPSESSID=testsession; path=/"},
        )
        mocked.post(
            re.compile(rf"{re.escape(BASE_URL)}/m/login\.php.*"),
            body="<html>OK</html>",
        )
        mocked.get(
            f"{BASE_URL}/m/plants.php",
            body=plants_html,
        )
        mocked.get(
            f"{BASE_URL}/getdata.php?cid=42",
            body=pool_data_html,
        )
        mocked.get(
            f"{BASE_URL}/p/device.php?c=42",
            body=device_html,
        )

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user@example.com", "secret")
            controllers = await client.get_controllers()
            assert len(controllers) == 1
            assert controllers[0]["cid"] == "42"

            data = await client.fetch_pool_data("42")
            assert data["pH"] == 7.2
            assert data["connectivity"] is True
            assert data["ph_dosing"] is True
            assert data["chlorine_dosing"] is False


async def test_login_invalid_auth(login_form_html: str) -> None:
    """Reject login when portal returns error."""
    with aioresponses() as mocked:
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body=login_form_html,
            headers={"Set-Cookie": "PHPSESSID=testsession; path=/"},
        )
        mocked.post(
            re.compile(rf"{re.escape(BASE_URL)}/.*login.*"),
            body='<html><div class="error_text">Fehler</div></html>',
        )

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            with pytest.raises(BayrolAuthError):
                await client.login("bad", "credentials")


async def test_relogin_without_deadlock(
    login_form_html: str,
    pool_data_html: str,
    device_html: str,
) -> None:
    """Re-login after 401 must not deadlock on the asyncio lock."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/getdata.php?cid=42", status=401, body="")
        mocked.get(f"{BASE_URL}/getdata.php?cid=42", body=pool_data_html)
        mocked.get(f"{BASE_URL}/p/device.php?c=42", body=device_html)
        _mock_login(mocked, login_form_html)

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            client._username = "user"
            client._password = "pass"
            client._phpsessid = "stale"
            client._logged_in = True

            data = await asyncio.wait_for(client.fetch_pool_data("42"), timeout=2.0)

        login_posts = [
            key
            for key in mocked.requests
            if key[0] == "POST" and "login" in str(key[1])
        ]
        assert len(login_posts) == 1
        assert data["pH"] == 7.2


async def test_set_control() -> None:
    """Set dosing control via data_json.php."""
    with aioresponses() as mocked:
        login_html = '<form id="form_login"><input name="token" value="x"/></form>'
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body=login_html,
            headers={"Set-Cookie": "PHPSESSID=sess; path=/"},
        )
        mocked.post(re.compile(rf"{re.escape(BASE_URL)}/.*login.*"), body="ok")
        mocked.post(
            f"{BASE_URL}/{PATH_DATA_JSON}",
            body='{"error":""}',
        )

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user", "pass")
            await client.set_control("42", "ph", True)

        assert mocked.requests


async def test_set_control_rejects_api_error() -> None:
    """set_control raises when API returns a JSON error field."""
    with aioresponses() as mocked:
        login_html = '<form id="form_login"><input name="token" value="x"/></form>'
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body=login_html,
            headers={"Set-Cookie": "PHPSESSID=sess; path=/"},
        )
        mocked.post(re.compile(rf"{re.escape(BASE_URL)}/.*login.*"), body="ok")
        mocked.post(
            f"{BASE_URL}/{PATH_DATA_JSON}",
            body='{"error":"rejected"}',
        )

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user", "pass")
            with pytest.raises(BayrolConnectionError, match="abgelehnt"):
                await client.set_control("42", "ph", True)


async def test_set_control_invalid_json() -> None:
    """set_control raises on non-JSON responses."""
    with aioresponses() as mocked:
        login_html = '<form id="form_login"><input name="token" value="x"/></form>'
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body=login_html,
            headers={"Set-Cookie": "PHPSESSID=sess; path=/"},
        )
        mocked.post(re.compile(rf"{re.escape(BASE_URL)}/.*login.*"), body="ok")
        mocked.post(f"{BASE_URL}/{PATH_DATA_JSON}", body="not-json")

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user", "pass")
            with pytest.raises(BayrolConnectionError, match="ungültige Antwort"):
                await client.set_control("42", "ph", True)


async def test_detect_chlor_method_redox(login_form_html: str) -> None:
    """Detect redox chlorination from device HTML."""
    device_html = '<html><div class="i_item item5_154 i_inactive"></div></html>'
    with aioresponses() as mocked:
        _mock_login(mocked, login_form_html)
        mocked.get(f"{BASE_URL}/p/device.php?c=42", body=device_html)

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user", "pass")
            assert await client.async_detect_chlor_method("42") == "redox"


async def test_detect_chlor_method_salt(login_form_html: str) -> None:
    """Detect salt chlorination from device HTML."""
    device_html = '<html><div class="i_item item5_40 i_active"></div></html>'
    with aioresponses() as mocked:
        _mock_login(mocked, login_form_html)
        mocked.get(f"{BASE_URL}/p/device.php?c=42", body=device_html)

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user", "pass")
            assert await client.async_detect_chlor_method("42") == "salt"


async def test_detect_chlor_method_none(login_form_html: str) -> None:
    """Return None when no chlor item is present."""
    device_html = "<html><div class='i_item item5_42 i_active'></div></html>"
    with aioresponses() as mocked:
        _mock_login(mocked, login_form_html)
        mocked.get(f"{BASE_URL}/p/device.php?c=42", body=device_html)

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            await client.login("user", "pass")
            assert await client.async_detect_chlor_method("42") is None


def test_parse_control_states_salt() -> None:
    """Parse chlorine dosing for salt item."""
    html = """
    <html><body>
    <div class="i_item item5_40 i_active"></div>
    <div class="i_item item5_42 i_inactive"></div>
    </body></html>
    """
    states = _parse_control_states(html, "salt")
    assert states["chlorine_dosing"] is True
    assert states["ph_dosing"] is False


def test_parse_control_states_none() -> None:
    """Skip chlorine state when method is none."""
    html = """
    <html><body>
    <div class="i_item item5_154 i_active"></div>
    <div class="i_item item5_42 i_inactive"></div>
    </body></html>
    """
    states = _parse_control_states(html, "none")
    assert "chlorine_dosing" not in states
    assert states["ph_dosing"] is False


def _mock_login(mocked: aioresponses, login_form_html: str) -> None:
    mocked.get(
        re.compile(rf"{re.escape(BASE_URL)}/.*"),
        body=login_form_html,
        headers={"Set-Cookie": "PHPSESSID=testsession; path=/"},
    )
    mocked.post(
        re.compile(rf"{re.escape(BASE_URL)}/.*login.*"),
        body="<html>OK</html>",
    )


async def test_cannot_connect_no_cookie() -> None:
    """Fail when no session cookie is returned."""
    with aioresponses() as mocked:
        mocked.get(
            re.compile(rf"{re.escape(BASE_URL)}/.*"),
            body="<html></html>",
        )

        async with aiohttp.ClientSession() as session:
            client = BayrolApiClient(session)
            with pytest.raises(BayrolConnectionError):
                await client.login("user", "pass")
