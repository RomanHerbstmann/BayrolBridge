"""Config flow for Bayrol Bridge."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BayrolApiClient, BayrolAuthError, BayrolConnectionError
from .const import (
    CHLOR_METHODS,
    CONF_CHLOR_ITEM,
    CONF_CHLOR_METHOD,
    CONF_CID,
    CONF_DEBUG_HTML,
    CONF_DEVICE_NAME,
    CONF_DOSING_OFF,
    CONF_DOSING_ON,
    CONF_PH_ITEM,
    CONF_SCAN_INTERVAL,
    DEFAULT_CHLOR_METHOD,
    DEFAULT_DEBUG_HTML,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DOSING_OFF,
    DOSING_ON,
    MIN_SCAN_INTERVAL,
    PH_ITEM,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_SCAN_INTERVAL),
        ),
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


def _chlor_method_schema(default: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CHLOR_METHOD, default=default): vol.In(
                ("redox", "salt", "none")
            )
        }
    )


class BayrolBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Bayrol Bridge config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._controllers: list[dict[str, str]] = []
        self._credentials: dict[str, Any] = {}
        self._client: BayrolApiClient | None = None
        self._selected_cid: str | None = None
        self._selected_controller: dict[str, str] | None = None
        self._detected_chlor_method: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_login(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                self._credentials = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                }
                self._controllers = info["controllers"]
                self._client = info["client"]
                if len(self._controllers) == 1:
                    return await self.async_step_controller(
                        {CONF_CID: self._controllers[0]["cid"]}
                    )
                return await self.async_step_controller()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_controller(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select pool controller."""
        errors: dict[str, str] = {}

        if user_input is not None:
            cid = user_input[CONF_CID]
            controller = next(
                (c for c in self._controllers if c["cid"] == cid), None
            )
            if controller is None:
                errors["base"] = "cannot_connect"
            else:
                self._selected_cid = cid
                self._selected_controller = controller
                if self._client is not None:
                    self._detected_chlor_method = (
                        await self._client.async_detect_chlor_method(cid)
                    )
                return await self.async_step_chlor_method()

        return self.async_show_form(
            step_id="controller",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CID): vol.In(
                        {
                            c["cid"]: f"{c['name']} ({c['cid']})"
                            for c in self._controllers
                        }
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_chlor_method(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select chlorine dosing method."""
        default_method = self._detected_chlor_method or DEFAULT_CHLOR_METHOD

        if user_input is not None:
            chlor_method = user_input[CONF_CHLOR_METHOD]
            if chlor_method not in CHLOR_METHODS:
                return self.async_show_form(
                    step_id="chlor_method",
                    data_schema=_chlor_method_schema(default_method),
                    errors={"base": "cannot_connect"},
                )

            cid = self._selected_cid
            controller = getattr(self, "_selected_controller", None)
            if not cid or controller is None:
                return self.async_abort(reason="cannot_connect")

            await self.async_set_unique_id(cid)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=controller["name"],
                data={
                    **self._credentials,
                    CONF_CID: cid,
                    CONF_DEVICE_NAME: controller["name"],
                    CONF_CHLOR_METHOD: chlor_method,
                },
            )

        return self.async_show_form(
            step_id="chlor_method",
            data_schema=_chlor_method_schema(default_method),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> FlowResult:
        """Handle re-authentication after ConfigEntryAuthFailed."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm re-authentication with updated credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                await _validate_login(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                REAUTH_SCHEMA,
                {
                    CONF_USERNAME: reauth_entry.data.get(CONF_USERNAME, ""),
                    CONF_PASSWORD: "",
                },
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> BayrolBridgeOptionsFlowHandler:
        """Get options flow."""
        return BayrolBridgeOptionsFlowHandler()


class BayrolBridgeOptionsFlowHandler(OptionsFlowWithReload):
    """Handle Bayrol Bridge options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        data = self.config_entry.data
        options = self.config_entry.options

        def cur(key: str, fallback: str) -> str:
            return options.get(key, data.get(key, fallback))

        def cur_bool(key: str, fallback: bool) -> bool:
            if key in options:
                val = options[key]
            elif key in data:
                val = data[key]
            else:
                return fallback
            return val if isinstance(val, bool) else fallback

        current_method = cur(CONF_CHLOR_METHOD, DEFAULT_CHLOR_METHOD)

        if user_input is not None:
            cleaned: dict[str, Any] = {}
            for key, value in user_input.items():
                if isinstance(value, bool):
                    cleaned[key] = value
                elif isinstance(value, str):
                    stripped = value.strip()
                    if stripped:
                        cleaned[key] = stripped
                elif value not in (None, ""):
                    cleaned[key] = value
            return self.async_create_entry(title="", data=cleaned)

        schema = vol.Schema(
            {
                vol.Required(CONF_CHLOR_METHOD, default=current_method): vol.In(
                    ("redox", "salt", "none")
                ),
                vol.Optional(CONF_CHLOR_ITEM, default=cur(CONF_CHLOR_ITEM, "")): str,
                vol.Optional(CONF_PH_ITEM, default=cur(CONF_PH_ITEM, PH_ITEM)): str,
                vol.Optional(
                    CONF_DOSING_ON, default=cur(CONF_DOSING_ON, DOSING_ON)
                ): str,
                vol.Optional(
                    CONF_DOSING_OFF, default=cur(CONF_DOSING_OFF, DOSING_OFF)
                ): str,
                vol.Optional(
                    CONF_DEBUG_HTML,
                    default=cur_bool(CONF_DEBUG_HTML, DEFAULT_DEBUG_HTML),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class InvalidAuth(HomeAssistantError):
    """Invalid authentication."""


class CannotConnect(HomeAssistantError):
    """Cannot connect."""


async def _validate_login(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    session = async_get_clientsession(hass)
    client = BayrolApiClient(session)
    try:
        await client.login(data[CONF_USERNAME], data[CONF_PASSWORD])
        controllers = await client.get_controllers()
    except BayrolAuthError as err:
        raise InvalidAuth from err
    except BayrolConnectionError as err:
        raise CannotConnect from err

    if not controllers:
        raise CannotConnect

    return {"controllers": controllers, "client": client}
