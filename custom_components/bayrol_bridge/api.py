"""Async API client for Bayrol Pool Access webview."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, cast

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from bs4 import BeautifulSoup, Tag

from .const import (
    BASE_URL,
    CHLOR_METHODS,
    ControlConfig,
    DATA_CHLORINE_DOSING,
    DATA_CONNECTIVITY,
    DATA_PH_DOSING,
    DATA_STATUS,
    DEFAULT_CHLOR_METHOD,
    MEASUREMENT_KEYS,
    PATH_DATA_JSON,
    PATH_DEVICE,
    PATH_GETDATA,
    PATH_INDEX,
    PATH_LOGIN_MOBILE,
    PATH_LOGIN_PORTAL,
    PATH_LOGIN_POST,
    PATH_PLANTS,
    get_controls,
)

_LOGGER = logging.getLogger(__name__)

_RELEVANT_CLASS_PARTS = (
    "tab_box",
    "item",
    "i_active",
    "i_inactive",
    "dosing",
    "box",
    "tab_data",
)
_MAX_DEBUG_ELEMENTS = 150
_MAX_DEBUG_CHARS = 8000
_MAX_DEBUG_TEXT_LEN = 80

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
_HEX_TOKEN_RE = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_LONG_DIGITS_RE = re.compile(r"\b\d{8,}\b")
_SESSION_RE = re.compile(r"PHPSESSID[=:]\s*\S+", re.IGNORECASE)

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) "
        "Gecko/20100101 Firefox/131.0"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.7",
    "Connection": "keep-alive",
}

LOGIN_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.bayrol-poolaccess.de",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}

DATA_HEADERS = {
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

JSON_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/json; charset=utf-8",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


class BayrolAuthError(Exception):
    """Authentication failed."""


class BayrolConnectionError(Exception):
    """Connection or transport error."""


class BayrolApiClient:
    """Bayrol Pool Access HTTP client with session resilience."""

    def __init__(
        self,
        session: ClientSession,
        timeout: int = 30,
        chlor_method: str = DEFAULT_CHLOR_METHOD,
        *,
        controls: dict[str, ControlConfig] | None = None,
        access_code: str | None = None,
    ) -> None:
        """Initialize client."""
        self._session = session
        self._timeout = ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()
        self._phpsessid: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._access_code = access_code
        self._logged_in = False
        self._chlor_method = chlor_method
        self._controls = controls or get_controls(chlor_method)

    def _url(self, path: str) -> str:
        return f"{BASE_URL}/{path.lstrip('/')}"

    def _headers(
        self, extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        headers = BASE_HEADERS.copy()
        if self._phpsessid:
            headers["Cookie"] = f"PHPSESSID={self._phpsessid}"
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _extract_phpsessid(response: aiohttp.ClientResponse) -> str | None:
        for cookie in response.cookies.values():
            if cookie.key == "PHPSESSID":
                return cookie.value
        set_cookie = response.headers.get("Set-Cookie", "")
        match = re.search(r"PHPSESSID=([^;]+)", set_cookie)
        return match.group(1) if match else None

    @staticmethod
    def _parse_login_form(html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", {"id": "form_login"}) or soup.find("form")
        if not form:
            return {}
        form_data: dict[str, str] = {}
        for field in form.find_all("input"):
            name = field.get("name")
            if name:
                form_data[name] = field.get("value", "")
        return form_data

    @staticmethod
    def _classify_login_response(html: str) -> str:
        """Return 'ok', 'auth' (bad credentials) or 'timeout' (captcha/session)."""
        low = html.lower()
        if "passwort falsch" in low or "benutzername oder passwort" in low:
            return "auth"
        if "zeit abgelaufen" in low:
            return "timeout"
        soup = BeautifulSoup(html, "html.parser")
        if soup.find("div", class_="error_text"):
            return "auth"
        return "ok"

    async def _refresh_login_form(
        self, username: str, password: str
    ) -> dict[str, str]:
        """Reload portal login form (refresh PHPSESSID / captcha timing)."""
        async with self._session.get(
            self._url(PATH_LOGIN_POST),
            headers=self._headers(),
            timeout=self._timeout,
            allow_redirects=True,
        ) as response:
            phpsessid = self._extract_phpsessid(response)
            if phpsessid:
                self._phpsessid = phpsessid
            html = await response.text()

        form_data = self._parse_login_form(html)
        if not form_data:
            raise BayrolConnectionError("Login form fields missing")
        form_data["username"] = username
        form_data["password"] = password
        form_data.setdefault("login", "Anmelden")
        return form_data

    async def _submit_login(
        self, form_data: dict[str, str], login_url: str
    ) -> str:
        """POST login credentials; return response body."""
        headers = self._headers(LOGIN_HEADERS)
        headers["Referer"] = self._url(PATH_LOGIN_POST)
        async with self._session.post(
            login_url,
            headers=headers,
            data=form_data,
            timeout=self._timeout,
            allow_redirects=True,
        ) as response:
            return await response.text()

    async def _login_locked(self, username: str, password: str) -> None:
        """Authenticate (caller must hold ``_lock``)."""
        self._username = username
        self._password = password
        self._session.cookie_jar.clear()
        self._phpsessid = None
        self._logged_in = False

        init_paths = (PATH_LOGIN_POST, PATH_INDEX, PATH_LOGIN_PORTAL)
        form_html: str | None = None

        for path in init_paths:
            try:
                async with self._session.get(
                    self._url(path),
                    headers=self._headers(),
                    timeout=self._timeout,
                    allow_redirects=True,
                ) as response:
                    phpsessid = self._extract_phpsessid(response)
                    if phpsessid:
                        self._phpsessid = phpsessid
                    html = await response.text()
                    if self._parse_login_form(html):
                        form_html = html
                        break
            except aiohttp.ClientError as err:
                _LOGGER.debug("Init path %s failed: %s", path, err)

        if not self._phpsessid:
            raise BayrolConnectionError("No PHPSESSID received")

        if not form_html:
            raise BayrolConnectionError("Login form not found")

        form_data = self._parse_login_form(form_html)
        if not form_data:
            raise BayrolConnectionError("Login form fields missing")

        form_data["username"] = username
        form_data["password"] = password
        form_data.setdefault("login", "Anmelden")

        post_urls = (
            self._url(PATH_LOGIN_POST),
            self._url(PATH_LOGIN_PORTAL),
        )
        timeout_retried = False
        last_error: Exception | None = None
        for login_url in post_urls:
            try:
                content = await self._submit_login(form_data, login_url)
                result = self._classify_login_response(content)

                if result == "timeout" and not timeout_retried:
                    timeout_retried = True
                    form_data = await self._refresh_login_form(username, password)
                    content = await self._submit_login(
                        form_data, self._url(PATH_LOGIN_POST)
                    )
                    result = self._classify_login_response(content)

                if result == "auth":
                    soup = BeautifulSoup(content, "html.parser")
                    error = soup.find("div", class_="error_text")
                    if error:
                        _LOGGER.error(
                            "Login error: %s", error.get_text(strip=True)
                        )
                    raise BayrolAuthError("Invalid credentials")
                if result == "ok":
                    self._logged_in = True
                    return
                if result == "timeout":
                    raise BayrolConnectionError("Login captcha/timeout")
            except BayrolAuthError:
                raise
            except BayrolConnectionError:
                raise
            except aiohttp.ClientError as err:
                last_error = err

        if last_error:
            raise BayrolConnectionError(str(last_error)) from last_error
        raise BayrolAuthError("Login failed")

    async def login(self, username: str, password: str) -> None:
        """Authenticate (acquires the lock)."""
        async with self._lock:
            await self._login_locked(username, password)

    async def _ensure_logged_in(self) -> None:
        if self._logged_in and self._phpsessid:
            return
        if not self._username or not self._password:
            raise BayrolAuthError("Not authenticated")
        await self._login_locked(self._username, self._password)

    async def _request_text_with_retry(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> tuple[int, str]:
        """Perform HTTP request with one auto re-login retry."""
        await self._ensure_logged_in()
        url = self._url(path)

        for attempt in range(2):
            try:
                async with self._session.request(
                    method,
                    url,
                    headers=self._headers(headers),
                    timeout=self._timeout,
                    **kwargs,
                ) as response:
                    body = await response.text()
                    if response.status in (401, 403) and attempt == 0:
                        self._logged_in = False
                        await self._login_locked(self._username, self._password)  # type: ignore[arg-type]
                        continue
                    return response.status, body
            except aiohttp.ClientError as err:
                if attempt == 0:
                    self._logged_in = False
                    await self._login_locked(self._username, self._password)  # type: ignore[arg-type]
                    continue
                raise BayrolConnectionError(str(err)) from err

        raise BayrolConnectionError("Request failed after retry")

    @property
    def chlor_method(self) -> str:
        """Configured chlorine dosing method."""
        return self._chlor_method

    async def async_detect_chlor_method(self, cid: str) -> str | None:
        """Detect chlorine control item from device page HTML."""
        try:
            html = await self._fetch_device_html(cid)
        except BayrolConnectionError:
            return None

        if "item5_40" in html:
            return "salt"
        if "item5_154" in html:
            return "redox"
        return None

    async def async_get_device_html_debug(
        self, cid: str
    ) -> list[dict[str, Any]] | dict[str, str]:
        """Return a sanitized excerpt of the device page for troubleshooting."""
        try:
            html = await self._fetch_device_html(cid)
        except BayrolConnectionError as err:
            return {"error": str(err)}
        return _sanitize_device_html(html, cid=cid)

    async def async_get_raw_getdata(self, cid: str) -> str:
        """Return the raw getdata.php body (read-only) for diagnostics."""
        headers = DATA_HEADERS.copy()
        headers["Referer"] = self._url(PATH_PLANTS)
        try:
            status, body = await self._request_text_with_retry(
                "GET", f"{PATH_GETDATA}?cid={cid}", headers=headers
            )
        except BayrolConnectionError as err:
            return f"<error: {err}>"
        return body if status == 200 else f"<status {status}>"

    async def async_probe_data_json(self, cid: str) -> list[dict[str, Any]]:
        """Try read-only data_json.php variants; never switch. Returns attempts."""
        headers = JSON_HEADERS.copy()
        headers["Referer"] = self._url(f"{PATH_DEVICE}?c={cid}")

        candidate_payloads: list[dict[str, Any] | None] = [
            {"device": cid, "action": "getItems"},
            {"device": cid, "action": "getItems", "data": {"items": []}},
            {"device": cid, "action": "getAll"},
            {"device": cid, "action": "get"},
            None,
        ]

        attempts: list[dict[str, Any]] = []
        for payload in candidate_payloads:
            try:
                if payload is None:
                    status, body = await self._request_text_with_retry(
                        "GET", f"{PATH_DATA_JSON}?device={cid}", headers=headers
                    )
                    sent = "GET ?device=<cid>"
                else:
                    status, body = await self._request_text_with_retry(
                        "POST", PATH_DATA_JSON, headers=headers, json=payload
                    )
                    sent = {k: v for k, v in payload.items() if k != "device"}
            except BayrolConnectionError as err:
                attempts.append({"sent": str(payload), "error": str(err)})
                continue
            attempts.append(
                {
                    "sent": sent,
                    "status": status,
                    "body_excerpt": body[:2000],
                }
            )
        return attempts

    async def async_probe_get_items(self, cid: str) -> dict[str, Any]:
        """Read-only getItems probe with the real topics (diagnostics)."""
        headers = JSON_HEADERS.copy()
        headers["Referer"] = self._url(f"{PATH_DEVICE}?c={cid}")

        topics = ["5.42", "5.154", "5.40", "4.2", "4.82", "4.91"]
        payload = {
            "device": cid,
            "action": "getItems",
            "data": {"items": [{"topic": t} for t in topics]},
        }

        try:
            status, body = await self._request_text_with_retry(
                "POST", PATH_DATA_JSON, headers=headers, json=payload
            )
        except BayrolConnectionError as err:
            return {"sent_topics": topics, "error": str(err)}

        return {
            "sent_topics": topics,
            "status": status,
            "body_excerpt": body[:4000],
        }

    async def async_probe_access(self, cid: str, code: str) -> list[dict[str, Any]]:
        """Try read-only unlock/access variants for the access code. Never switches."""
        headers = JSON_HEADERS.copy()
        headers["Referer"] = self._url(f"{PATH_DEVICE}?c={cid}")

        candidates: list[dict[str, Any]] = [
            {"device": cid, "action": "getAccess"},
            {"device": cid, "action": "getAccess", "data": {"code": code}},
            {"device": cid, "action": "setCode", "data": {"code": code}},
            {"device": cid, "action": "setAccess", "data": {"code": code}},
            {"device": cid, "action": "access", "data": {"code": code}},
            {"device": cid, "action": "login", "data": {"code": code}},
        ]

        attempts: list[dict[str, Any]] = []
        for payload in candidates:
            try:
                status, body = await self._request_text_with_retry(
                    "POST", PATH_DATA_JSON, headers=headers, json=payload
                )
            except BayrolConnectionError as err:
                attempts.append({"action": payload["action"], "error": str(err)})
                continue
            attempts.append(
                {
                    "action": payload["action"],
                    "had_code": "code" in payload.get("data", {}),
                    "status": status,
                    "body_excerpt": body[:1500],
                }
            )
        return attempts

    async def async_list_device_items(self, cid: str) -> list[dict[str, Any]]:
        """Return all item codes present on the device page.

        Each entry: {"item": "5.154", "css": "item5_154",
                     "state": "active"|"inactive"|None,
                     "classes": [...]}.
        Best-effort, read-only; returns [] if the page can't be fetched/parsed.
        """
        try:
            html = await self._fetch_device_html(cid)
        except BayrolConnectionError:
            return []
        return _parse_device_items(html)

    async def get_controllers(self) -> list[dict[str, str]]:
        """Return available pool controllers."""
        async with self._lock:
            status, html = await self._request_text_with_retry(
                "GET", PATH_PLANTS, headers=LOGIN_HEADERS
            )
            if status != 200:
                raise BayrolConnectionError(f"Plants page returned {status}")

        return _parse_controllers(html)

    async def fetch_pool_data(self, cid: str) -> dict[str, Any]:
        """Fetch measurements and control state for a controller."""
        async with self._lock:
            data: dict[str, Any] = {
                DATA_STATUS: "unknown",
                DATA_CONNECTIVITY: False,
            }
            headers = DATA_HEADERS.copy()
            headers["Referer"] = self._url(PATH_PLANTS)
            status, html = await self._request_text_with_retry(
                "GET",
                f"{PATH_GETDATA}?cid={cid}",
                headers=headers,
            )
            if status != 200:
                raise BayrolConnectionError(f"getdata returned {status}")
            data.update(_parse_pool_data(html))

            if data.get(DATA_STATUS) != "offline":
                try:
                    device_html = await self._fetch_device_html(cid)
                    data.update(_parse_control_states(device_html, self._controls))
                except BayrolConnectionError:
                    _LOGGER.debug(
                        "Could not parse control states for controller %s",
                        cid,
                    )

            data[DATA_CONNECTIVITY] = data.get(DATA_STATUS) == "online"
            return data

    async def _fetch_device_html(self, cid: str) -> str:
        headers = self._headers()
        headers["Referer"] = self._url(PATH_PLANTS)
        status, html = await self._request_text_with_retry(
            "GET",
            f"{PATH_DEVICE}?c={cid}",
            headers=headers,
        )
        if status != 200:
            raise BayrolConnectionError(f"device page returned {status}")
        return html

    async def set_control(self, cid: str, control_key: str, enabled: bool) -> None:
        """Enable or disable a dosing control."""
        controls = self._controls
        if control_key not in controls:
            raise ValueError(f"Unknown control: {control_key}")

        control = controls[control_key]
        value = control["value_on"] if enabled else control["value_off"]
        payload = {
            "device": cid,
            "action": "setItems",
            "data": {
                "items": [
                    {
                        "topic": control["item"],
                        "name": control["name"],
                        "value": value,
                        "valid": 1,
                        "cmd": 1,
                    }
                ]
            },
        }

        async with self._lock:
            headers = JSON_HEADERS.copy()
            headers["Referer"] = self._url(f"{PATH_DEVICE}?c={cid}")
            status, body = await self._request_text_with_retry(
                "POST",
                control["set_path"],
                headers=headers,
                json=payload,
            )
            if status != 200:
                raise BayrolConnectionError(f"setItems returned {status}")
            # Success schema and item/value codes (5.154/5.40/5.42, 19.17/19.18)
            # should be verified against a real device via data_json.php in DevTools.
            try:
                result = json.loads(body)
            except (ValueError, TypeError) as err:
                _LOGGER.debug("Unerwartete setItems-Antwort: %s", body[:200])
                raise BayrolConnectionError("setItems: ungültige Antwort") from err
            if result.get("error"):
                raise BayrolConnectionError(
                    f"setItems abgelehnt: {result.get('error')}"
                )


def _mask_sensitive(text: str, cid: str | None = None) -> str:
    """Mask emails, tokens, CID, and session-like values in diagnostic text."""
    if not text:
        return text
    result = _SESSION_RE.sub("PHPSESSID=<redacted>", text)
    result = _EMAIL_RE.sub("<email>", result)
    if cid:
        result = result.replace(cid, "<cid>")
    result = _HEX_TOKEN_RE.sub("<token>", result)
    result = _LONG_DIGITS_RE.sub("<digits>", result)
    return result


def _class_list_relevant(classes: object) -> bool:
    if not classes:
        return False
    if isinstance(classes, str):
        classes = [classes]
    return any(
        part in cls for cls in cast(list[str], classes) for part in _RELEVANT_CLASS_PARTS
    )


def _collect_relevant_nodes(soup: BeautifulSoup) -> list[Tag]:
    """Collect measurement/dosing nodes and their direct parent containers."""
    collected: dict[int, Tag] = {}
    for element in soup.find_all(True):
        if not _class_list_relevant(element.get("class")):
            continue
        for node in (element, element.parent):
            if not isinstance(node, Tag) or not node.name:
                continue
            collected[id(node)] = node
    return [el for el in soup.find_all(True) if id(el) in collected]


def _sanitize_device_html(
    html: str, *, cid: str | None = None
) -> list[dict[str, Any]]:
    """Extract a compact, redacted structure from device page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "svg"]):
        tag.decompose()

    nodes = _collect_relevant_nodes(soup)
    result: list[dict[str, Any]] = []
    total_chars = 0
    truncated = False

    for element in nodes:
        if len(result) >= _MAX_DEBUG_ELEMENTS:
            truncated = True
            break

        classes = element.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        class_list = [_mask_sensitive(c, cid) for c in classes]

        elem_id = element.get("id")
        if elem_id:
            elem_id = _mask_sensitive(str(elem_id), cid)
        else:
            elem_id = None

        text = _mask_sensitive(element.get_text(separator=" ", strip=True), cid)
        if len(text) > _MAX_DEBUG_TEXT_LEN:
            text = text[: _MAX_DEBUG_TEXT_LEN - 3] + "..."

        entry: dict[str, Any] = {
            "tag": element.name,
            "class": class_list,
            "id": elem_id,
            "text": text,
        }
        entry_json = json.dumps(entry, ensure_ascii=False)
        if total_chars + len(entry_json) > _MAX_DEBUG_CHARS and result:
            truncated = True
            break
        result.append(entry)
        total_chars += len(entry_json)

    if truncated:
        result.append(
            {
                "tag": "truncated",
                "class": [],
                "id": None,
                "text": "...truncated",
            }
        )
    return result


def _parse_device_items(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict[str, Any]] = {}
    for div in soup.find_all("div", class_=re.compile(r"item\d+_\d+")):
        classes = div.get("class", [])
        for cls in classes:
            m = re.fullmatch(r"item(\d+)_(\d+)", cls)
            if not m:
                continue
            item = f"{m.group(1)}.{m.group(2)}"
            state = None
            if "i_active" in classes:
                state = "active"
            elif "i_inactive" in classes:
                state = "inactive"
            if item not in found:
                found[item] = {
                    "item": item,
                    "css": cls,
                    "state": state,
                    "classes": classes,
                }
            elif state and found[item]["state"] is None:
                found[item]["state"] = state
    return sorted(
        found.values(),
        key=lambda e: tuple(int(p) for p in e["item"].split(".")),
    )


def _parse_controllers(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    controllers: list[dict[str, str]] = []

    for tab_row in soup.find_all("div", class_="tab_row"):
        tab_1 = tab_row.find("div", class_="tab_1")
        tab_2 = tab_row.find("div", class_="tab_2")
        if not tab_1 or not tab_2:
            continue

        cid: str | None = None
        tab_id = tab_2.get("id", "")
        match = re.search(r"tab_data(\d+)", tab_id)
        if match:
            cid = match.group(1)

        if not cid:
            onclick_div = tab_1.find(
                "div", onclick=re.compile(r"plant_settings\.php\?c=\d+")
            )
            if onclick_div:
                onclick = onclick_div.get("onclick", "")
                cid_match = re.search(r"c=(\d+)", onclick)
                if cid_match:
                    cid = cid_match.group(1)

        if not cid:
            continue

        name = "Pool Controller"
        p_tag = tab_1.find("p")
        if p_tag:
            name = p_tag.get_text(strip=True)

        controllers.append({"cid": cid, "name": name})

    return controllers


def _parse_pool_data(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    offline = soup.find("div", class_="tab_error")
    if offline and "No connection to the controller" in offline.get_text():
        return {DATA_STATUS: "offline"}

    measurement_map = {
        "pH": "pH",
        "Redox": "mV",
        "mV": "mV",
        "Temp.": "T",
        "Cl": "Cl",
        "Salz": "Salt",
        "T": "T",
        "T1": "T",
    }

    data: dict[str, Any] = {}
    for box in soup.find_all("div", class_="tab_box"):
        span = box.find("span")
        h1 = box.find("h1")
        if not span or not h1:
            continue
        label_text = span.get_text(strip=True)
        label_match = re.match(r"^([^[]+)", label_text)
        if not label_match:
            continue
        raw_label = label_match.group(1).replace("\xa0", " ").strip()
        label = measurement_map.get(raw_label)
        if not label or label not in MEASUREMENT_KEYS:
            continue
        try:
            data[label] = float(h1.get_text(strip=True))
            classes = box.get("class", [])
            # stat_warning is the normal tile colour on some devices (e.g. pH 7.1,
            # Temp 17) and is not an alarm; only stat_alarm signals a real problem.
            data[f"{label}_alarm"] = "stat_alarm" in classes
        except ValueError:
            continue

    if data:
        data[DATA_STATUS] = "online"
    return data


_CONTROL_STATE_KEYS = {
    "chlorine": DATA_CHLORINE_DOSING,
    "ph": DATA_PH_DOSING,
}


def _parse_control_states(
    html: str,
    controls: dict[str, ControlConfig] | str | None = None,
    *,
    chlor_method: str = DEFAULT_CHLOR_METHOD,
) -> dict[str, bool | None]:
    """Parse dosing switch states from device page HTML."""
    states: dict[str, bool | None] = {
        DATA_CHLORINE_DOSING: None,
        DATA_PH_DOSING: None,
    }

    if isinstance(controls, str):
        chlor_method = controls
        controls = None

    effective = controls or get_controls(chlor_method)
    item_map = {
        control["item"]: _CONTROL_STATE_KEYS[key]
        for key, control in effective.items()
    }

    soup = BeautifulSoup(html, "html.parser")
    for item_id, data_key in item_map.items():
        css_class = f"item{item_id.replace('.', '_')}"
        item_div = soup.find(
            "div", class_=lambda c: c and css_class in c  # type: ignore[misc]
        )
        if not item_div:
            continue
        active = "i_active" in item_div.get("class", [])
        inactive = "i_inactive" in item_div.get("class", [])
        if active:
            states[data_key] = True
        elif inactive:
            states[data_key] = False

    return {k: v for k, v in states.items() if v is not None}
