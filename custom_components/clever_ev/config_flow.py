"""Config flow for Clever EV."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CleverApi, CleverAuthError
from .const import CONF_EMAIL, CONF_REFRESH_TOKEN, DOMAIN

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required("password"): str,
    }
)


class CleverConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                tokens = await self._sign_in(
                    user_input[CONF_EMAIL], user_input["password"]
                )
            except CleverAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_REFRESH_TOKEN: tokens["refresh_token"],
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data):
        self._entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                tokens = await self._sign_in(
                    self._entry.data[CONF_EMAIL], user_input["password"]
                )
            except CleverAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._entry,
                    data={**self._entry.data, CONF_REFRESH_TOKEN: tokens["refresh_token"]},
                    reason="reauth_successful",
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required("password"): str}),
            description_placeholders={"email": self._entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def _sign_in(self, email: str, password: str) -> dict:
        session = async_get_clientsession(self.hass)
        api = CleverApi(session)
        return await api.async_sign_in(email, password)
