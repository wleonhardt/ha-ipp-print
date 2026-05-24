"""Config flow for IPP Print."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_RELAXED_CIPHERS,
    CONF_USER,
    CONF_USE_TLS,
    CONF_VERIFY_TLS,
    DEFAULT_PORT,
    DEFAULT_USER,
    DOMAIN,
)
from .printer import PrinterClient


class IppPrintConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask the user for printer connection details and validate by hitting
    the printer's IPP endpoint with a no-op Get-Job-Attributes for job 1.
    Any IPP response (even "no such job") confirms the network + auth path."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = PrinterClient(
                host=user_input[CONF_HOST],
                port=user_input.get(CONF_PORT, DEFAULT_PORT),
                use_tls=user_input.get(CONF_USE_TLS, True),
                user=user_input.get(CONF_USER) or DEFAULT_USER,
                password=user_input.get(CONF_PASSWORD, ""),
                verify_tls=user_input.get(CONF_VERIFY_TLS, False),
                relaxed_ciphers=user_input.get(CONF_RELAXED_CIPHERS, False),
                timeout=10.0,
            )
            try:
                # IPP probe: ask for job-id 1 attributes. Most printers will
                # return "client-error-not-found" but that's still a valid
                # IPP response — meaning the network/auth/TLS path works.
                await client.get_job_attrs(1)
            except Exception as exc:  # network/TLS errors
                errors["base"] = "cannot_connect"
                self._last_error = str(exc)
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input.get(CONF_PORT, DEFAULT_PORT)}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"IPP printer at {user_input[CONF_HOST]}",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_USE_TLS, default=True): bool,
                vol.Optional(CONF_USER, default=DEFAULT_USER): str,
                vol.Optional(CONF_PASSWORD, default=""): str,
                vol.Optional(CONF_VERIFY_TLS, default=False): bool,
                vol.Optional(CONF_RELAXED_CIPHERS, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "error_detail": getattr(self, "_last_error", "") or ""
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IppPrintOptionsFlow(config_entry)


class IppPrintOptionsFlow(OptionsFlow):
    """Edit credentials/options without re-creating the entry."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        data = {**self._entry.data, **self._entry.options}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=data.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_USE_TLS, default=data.get(CONF_USE_TLS, True)): bool,
                vol.Optional(CONF_USER, default=data.get(CONF_USER, DEFAULT_USER)): str,
                vol.Optional(CONF_PASSWORD, default=data.get(CONF_PASSWORD, "")): str,
                vol.Optional(
                    CONF_VERIFY_TLS, default=data.get(CONF_VERIFY_TLS, False)
                ): bool,
                vol.Optional(
                    CONF_RELAXED_CIPHERS,
                    default=data.get(CONF_RELAXED_CIPHERS, False),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
