"""Config flow for IPP Print: manual entry, zeroconf discovery, options."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

try:  # HA ≥ 2025.2
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # pragma: no cover - older cores
    from homeassistant.components.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PATH,
    CONF_PORT,
    CONF_RELAXED_CIPHERS,
    CONF_USER,
    CONF_USE_TLS,
    CONF_VERIFY_TLS,
    DEFAULT_PATH,
    DEFAULT_PORT,
    DEFAULT_USER,
    DOMAIN,
)
from .printer import PrinterClient, PrinterInfo

PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD)
)


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    d = defaults
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=d.get(CONF_HOST, vol.UNDEFINED)): str,
            vol.Optional(CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Optional(CONF_PATH, default=d.get(CONF_PATH, DEFAULT_PATH)): str,
            vol.Optional(CONF_USE_TLS, default=d.get(CONF_USE_TLS, True)): bool,
            vol.Optional(CONF_USER, default=d.get(CONF_USER, DEFAULT_USER)): str,
            vol.Optional(
                CONF_PASSWORD, default=d.get(CONF_PASSWORD, "")
            ): PASSWORD_SELECTOR,
            vol.Optional(
                CONF_VERIFY_TLS, default=d.get(CONF_VERIFY_TLS, False)
            ): bool,
            vol.Optional(
                CONF_RELAXED_CIPHERS, default=d.get(CONF_RELAXED_CIPHERS, False)
            ): bool,
        }
    )


def _normalize_uuid(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    if v.startswith("urn:uuid:"):
        v = v[len("urn:uuid:"):]
    return v or None


def _unique_id(info: PrinterInfo | None, data: dict[str, Any]) -> str:
    uuid = _normalize_uuid(info.uuid) if info else None
    return uuid or f"{data[CONF_HOST]}:{data.get(CONF_PORT, DEFAULT_PORT)}"


def _title(info: PrinterInfo | None, host: str) -> str:
    if info:
        for candidate in (info.info, info.make_and_model, info.name):
            if candidate and candidate.strip():
                return candidate.strip()
    return f"IPP printer at {host}"


async def _probe(data: dict[str, Any]) -> PrinterInfo:
    """Get-Printer-Attributes against the given connection settings.

    Raises on any network/TLS/auth/IPP failure. A successful response also
    yields the printer's identity and capabilities for the entry title,
    unique id, and later format checks.
    """
    client = PrinterClient(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        path=data.get(CONF_PATH, DEFAULT_PATH),
        use_tls=data.get(CONF_USE_TLS, True),
        user=data.get(CONF_USER) or DEFAULT_USER,
        password=data.get(CONF_PASSWORD, ""),
        verify_tls=data.get(CONF_VERIFY_TLS, False),
        relaxed_ciphers=data.get(CONF_RELAXED_CIPHERS, False),
        timeout=10.0,
    )
    try:
        return await client.get_printer_attrs()
    finally:
        await client.async_close()


class IppPrintConfigFlow(ConfigFlow, domain=DOMAIN):
    """Manual setup or zeroconf-discovered setup of one IPP printer."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] | None = None
        self._discovered_name: str = ""
        self._last_error: str = ""

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _probe(user_input)
            except Exception as exc:  # network/TLS/auth/IPP errors
                errors["base"] = "cannot_connect"
                self._last_error = str(exc)
            else:
                await self.async_set_unique_id(_unique_id(info, user_input))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_title(info, user_input[CONF_HOST]),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
            description_placeholders={"error_detail": self._last_error},
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo):
        """Printer advertised `_ipp._tcp` / `_ipps._tcp` on the LAN."""
        props = discovery_info.properties or {}
        tls = discovery_info.type == "_ipps._tcp.local."
        host = discovery_info.host
        port = discovery_info.port or (443 if tls else 631)
        # `rp` is the resource path without a leading slash (e.g. "ipp/print").
        path = "/" + str(props.get("rp") or DEFAULT_PATH).strip("/")

        uuid = _normalize_uuid(props.get("UUID"))
        await self.async_set_unique_id(uuid or f"{host}:{port}")
        self._abort_if_unique_id_configured()
        self._async_abort_entries_match({CONF_HOST: host})

        self._discovered = {
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_PATH: path,
            CONF_USE_TLS: tls,
            CONF_USER: DEFAULT_USER,
            CONF_PASSWORD: "",
            CONF_VERIFY_TLS: False,
            CONF_RELAXED_CIPHERS: False,
        }
        self._discovered_name = (
            str(props.get("ty") or "").strip()
            or discovery_info.name.split(".")[0]
            or host
        )
        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ):
        assert self._discovered is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _probe(self._discovered)
            except Exception as exc:
                errors["base"] = "cannot_connect"
                self._last_error = str(exc)
            else:
                return self.async_create_entry(
                    title=_title(info, self._discovered[CONF_HOST])
                    if info and (info.info or info.make_and_model or info.name)
                    else self._discovered_name,
                    data=self._discovered,
                )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            errors=errors,
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered[CONF_HOST],
                "error_detail": self._last_error,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IppPrintOptionsFlow()


class IppPrintOptionsFlow(OptionsFlow):
    """Edit connection settings without re-creating the entry.

    Note: HA ≥ 2024.12 injects `self.config_entry` automatically. The older
    pattern of accepting the entry in `__init__` short-circuits HA's
    update-listener wiring, which is why this class deliberately has no
    constructor.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        data = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(data))
