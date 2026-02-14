"""Config flow for the Grid Connect integration in Home Assistant.

This module handles the UI configuration flow, allowing users to
set up and manage their integration settings.
"""

import asyncio
import logging
import time
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.core import callback

from .const import DOMAIN
from .ble_wifi import send_wifi_credentials

_LOGGER = logging.getLogger(__name__)


class GridConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grid Connect."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Entry step: start BLE scan or manual add."""
        errors = {}
        if user_input is not None:
            if user_input.get("action") == "scan":
                return await self.async_step_ble_scan()
            if user_input.get("action") == "manual":
                return await self.async_step_manual()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("action", default="scan"): vol.In({"scan": "Scan for Devices", "manual": "Specify Device Manually"})}),
            errors=errors,
        )

    async def async_step_ble_scan(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Scan for Grid Connect devices via BLE and present selection."""
        # We'll scan for 10 seconds and collect all BLE devices
        devices = []
        seen_addresses = set()
        scan_duration = 10  # seconds
        start_time = time.monotonic()

        try:
            while time.monotonic() - start_time < scan_duration:
                # Use Home Assistant's bluetooth API to get discovered advertisements.
                try:
                    discovered = bluetooth.async_discovered_service_info(
                        self.hass, connectable=True
                    )
                except TypeError:
                    # Backward compatibility with older signatures.
                    discovered = bluetooth.async_discovered_service_info(self.hass)

                for service_info in discovered:
                    # Collect all devices that have service_uuids and haven't been seen yet
                    if (
                        hasattr(service_info, "service_uuids")
                        and service_info.service_uuids
                        and service_info.address not in seen_addresses
                    ):
                        devices.append({
                            "id": service_info.address,
                            "name": service_info.name or "Unnamed BLE Device",
                            "address": service_info.address,
                            "service_uuids": list(service_info.service_uuids),
                        })
                        seen_addresses.add(service_info.address)
                await asyncio.sleep(1)
        except (TimeoutError, AttributeError) as e:
            _LOGGER.warning("BLE scan error during discovery: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected BLE scan error during discovery: %s", e)
            raise

        if not devices:
            _LOGGER.info("No BLE devices discovered, showing no devices found step.")
            return await self.async_step_no_devices_found()

        self.context["discovered_ble_devices"] = devices
        return await self.async_step_select_ble_device()

    async def async_step_no_devices_found(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Show options when no devices are found during BLE scan."""
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get("action")
            if action == "scan_again":
                _LOGGER.info("User chose to scan again from no devices found step.")
                return await self.async_step_ble_scan()
            elif action == "manual":
                _LOGGER.info("User chose manual entry from no devices found step.")
                return await self.async_step_manual()

        return self.async_show_form(
            step_id="no_devices_found",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="scan_again"): vol.In(
                        {
                            "scan_again": "Scan again",
                            "manual": "Manual entry",
                        }
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "note": "Is your device in pairing mode?",
            },
        )

    async def async_step_select_ble_device(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Present discovered BLE devices and let the user select one."""
        errors = {}
        discovered_devices = self.context.get("discovered_ble_devices", [])
        if not discovered_devices:
            _LOGGER.warning("No BLE devices found in context for selection.")
            errors["base"] = "no_devices_for_selection"
            return await self.async_step_manual()

        # Create a mapping of address to a more user-friendly name for the form
        devices_for_selection = {
            d["address"]: f"{d['name']} ({d['address']})" for d in discovered_devices
        }

        if user_input is not None:
            selected_address = user_input["selected_device"]
            selected_device = next(
                (d for d in discovered_devices if d["address"] == selected_address), None
            )

            if selected_device:
                self.context["selected_ble_device"] = selected_device
                return await self.async_step_identify_grid_connect_uuid()
            else:
                errors["base"] = "device_not_found"

        return self.async_show_form(
            step_id="select_ble_device",
            data_schema=vol.Schema({
                vol.Required("selected_device"): vol.In(devices_for_selection)
            }),
            errors=errors,
            description_placeholders={"devices": ", ".join(devices_for_selection.values())}
        )


    async def async_step_identify_grid_connect_uuid(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Identify the Grid Connect UUID from the selected device's service UUIDs."""
        selected_device = self.context.get("selected_ble_device")

        if not selected_device or "service_uuids" not in selected_device:
            _LOGGER.error("Selected BLE device or its service UUIDs not found in context.")
            return await self.async_step_manual()

        # Heuristic to find a non-standard, custom UUID that is likely the Grid Connect service.
        # This is a basic approach and might need refinement based on actual device behavior.
        grid_connect_uuid: str | None = None
        for uuid in selected_device["service_uuids"]:
            # Exclude obvious standard 16-bit-based UUIDs; treat others as custom candidates.
            if uuid.startswith("0000") and len(uuid) > 8:
                # Placeholder for more detailed filtering if needed.
                continue

            grid_connect_uuid = uuid
            break

        if grid_connect_uuid:
            _LOGGER.info(
                "Identified Grid Connect UUID: %s for device %s",
                grid_connect_uuid,
                selected_device["address"],
            )
            self.context["grid_connect_uuid"] = grid_connect_uuid
            return await self.async_step_wifi_credentials()

        _LOGGER.warning(
            "Could not identify a unique Grid Connect UUID for device %s, "
            "falling back to manual UUID selection.",
            selected_device["address"],
        )
        return await self.async_step_select_fallback_uuid()

    async def async_step_select_fallback_uuid(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user pick a UUID or trigger a new scan when heuristic fails."""
        selected_device = self.context.get("selected_ble_device")

        if not selected_device or "service_uuids" not in selected_device:
            _LOGGER.error(
                "No selected device or service UUIDs available in context for fallback UUID selection."
            )
            return await self.async_step_manual()

        service_uuids = selected_device["service_uuids"]
        if not service_uuids:
            _LOGGER.error(
                "Selected device %s has no service UUIDs for fallback selection.",
                selected_device.get("address"),
            )
            return await self.async_step_manual()

        uuid_options = {uuid: uuid for uuid in service_uuids}

        schema = vol.Schema(
            {
                vol.Required("action", default="use_uuid"): vol.In(
                    {"use_uuid": "Use selected UUID", "scan_again": "Scan again"}
                ),
                vol.Optional("selected_uuid"): vol.In(uuid_options),
            }
        )

        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get("action")
            if action == "scan_again":
                _LOGGER.info("User chose to scan again from fallback UUID step.")
                return await self.async_step_ble_scan()

            if action == "use_uuid":
                selected_uuid = user_input.get("selected_uuid")
                if not selected_uuid:
                    errors["base"] = "no_uuid_selected"
                else:
                    self.context["grid_connect_uuid"] = selected_uuid
                    _LOGGER.info(
                        "User selected UUID %s for device %s",
                        selected_uuid,
                        selected_device.get("address"),
                    )
                    return await self.async_step_wifi_credentials()

        return self.async_show_form(
            step_id="select_fallback_uuid",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "uuids": ", ".join(service_uuids),
                "device": selected_device.get("name") or selected_device.get("address"),
            },
        )

    async def async_step_wifi_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Ask the user for Wi-Fi credentials and send them via BLE."""
        selected_device = self.context.get("selected_ble_device")
        grid_connect_uuid = self.context.get("grid_connect_uuid")

        if not selected_device or not grid_connect_uuid:
            _LOGGER.error(
                "Missing selected device or grid_connect_uuid in context before Wi-Fi step."
            )
            return await self.async_step_manual()

        errors: dict[str, str] = {}

        if user_input is not None:
            ssid = user_input["ssid"]
            password = user_input["password"]

            # Attempt to send Wi-Fi credentials over BLE
            result = await send_wifi_credentials(
                selected_device["address"], ssid, password
            )

            if result is None:
                # Success - create the config entry
                return self.async_create_entry(
                    title=selected_device.get("name") or "Grid Connect Device",
                    data={
                        "device_address": selected_device["address"],
                        "grid_connect_uuid": grid_connect_uuid,
                        "device_name": selected_device.get("name") or "Grid Connect Device",
                        "wifi_ssid": ssid,
                    },
                )

            # Map specific error codes from send_wifi_credentials to form errors
            _LOGGER.warning("Failed to send Wi-Fi credentials: %s", result)
            if result == "bleak_not_installed":
                errors["base"] = "bleak_not_installed"
            elif result == "not_connected":
                errors["base"] = "ble_not_connected"
            elif result == "ble_error":
                errors["base"] = "ble_error"
            elif result == "timeout":
                errors["base"] = "ble_timeout"
            else:
                errors["base"] = "ble_unknown_error"

        return self.async_show_form(
            step_id="wifi_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required("ssid"): str,
                    vol.Required("password"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_manual(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Fallback: let user manually specify device details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Store manual entry data in context and proceed to Wi-Fi provisioning
            self.context["selected_ble_device"] = {
                "address": user_input["device_address"],
                "name": user_input["device_name"],
            }
            self.context["grid_connect_uuid"] = user_input["grid_connect_uuid"]
            _LOGGER.info(
                "Manual entry: device %s with UUID %s, proceeding to Wi-Fi provisioning",
                user_input["device_name"],
                user_input["grid_connect_uuid"],
            )
            return await self.async_step_wifi_credentials()
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({
                vol.Required("device_name"): str,
                vol.Required("grid_connect_uuid"): str,
                vol.Required("device_address"): str,
            }),
            errors=errors,
        )

    async def async_step_select_device(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        """Redirect to BLE scan as the primary device selection method."""
        _LOGGER.info("Attempted to access async_step_select_device. Redirecting to BLE scan.")
        return await self.async_step_ble_scan()


    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow handler for Grid Connect."""
        return GridConnectOptionsFlowHandler(config_entry)


class GridConnectOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Grid Connect."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> config_entries.ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "option1", default=self.config_entry.options.get("option1", "")
                    ): str
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
