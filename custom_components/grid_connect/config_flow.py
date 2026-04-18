"""Config flow for the Grid Connect integration in Home Assistant.

This module handles the UI configuration flow, allowing users to
set up and manage their integration settings.
"""

import asyncio
import logging
import re
import time
from typing import Any
from uuid import UUID

import voluptuous as vol

# noinspection PyUnresolvedReferences
from homeassistant import config_entries

# noinspection PyUnresolvedReferences
from homeassistant.components import bluetooth

# noinspection PyUnresolvedReferences
from homeassistant.core import callback

from .ble_wifi import GRID_CONNECT_SERVICE_UUID, send_wifi_credentials
from .const import CONF_MODEL, DOMAIN, MODEL_PC191BKHA, MODEL_PC191HA, MODEL_SG120HA
from .ez_mode import send_ez_mode_credentials

_LOGGER = logging.getLogger(__name__)

_GRID_CONNECT_NAME_HINTS: tuple[str, ...] = (
    "GRID CONNECT",
    "ARLEC",
    "SMART PLUG",
    "SG120HA",
    "SG120",
    MODEL_PC191HA,
    MODEL_PC191BKHA,
    MODEL_SG120HA,
)

_HUB_ENTRY_TITLE = "Grid Connect Hub"
FlowResult = Any


def _is_identifier_like_name(name: str) -> bool:
    """Return True for UUID-like or long hex BLE names used by some plugs."""
    value = name.strip()
    if not value:
        return False
    try:
        UUID(value)
    except (ValueError, TypeError):
        pass
    else:
        return True

    compact = value.replace("-", "")
    if len(compact) >= 12 and re.fullmatch(r"[0-9A-Fa-f]+", compact):
        return True

    return False


def _detect_model_from_name(device_name: str | None) -> str | None:
    """Infer known model from BLE name."""
    if not device_name:
        return None
    normalized = device_name.upper()
    if MODEL_PC191BKHA in normalized:
        return MODEL_PC191BKHA
    if MODEL_PC191HA in normalized:
        return MODEL_PC191HA
    if MODEL_SG120HA in normalized:
        return MODEL_SG120HA
    if "SMART PLUG" in normalized:
        # Bunnings listing references the white variant (PC191HA).
        return MODEL_PC191HA
    return None


def _is_likely_grid_connect_device(service_info: Any) -> bool:
    """Return True when BLE advertisement looks like a Grid Connect plug."""
    candidate_names = [
        str(getattr(service_info, "name", "") or ""),
        str(getattr(service_info, "local_name", "") or ""),
        str(getattr(getattr(service_info, "device", None), "name", "") or ""),
    ]
    combined_name = " ".join(candidate_names).upper()
    if any(hint in combined_name for hint in _GRID_CONNECT_NAME_HINTS):
        return True

    service_uuids = [
        str(uuid).lower()
        for uuid in (getattr(service_info, "service_uuids", []) or [])
    ]
    if GRID_CONNECT_SERVICE_UUID.lower() in service_uuids:
        return True

    if any(_is_identifier_like_name(name) for name in candidate_names):
        return True

    manufacturer_data = getattr(service_info, "manufacturer_data", {}) or {}
    if 0x07D0 in manufacturer_data or 2000 in manufacturer_data:
        return True

    return False


def _friendly_ble_name(service_info: Any) -> str:
    """Build a user-friendly BLE name for selection lists."""
    for name in (
        str(getattr(service_info, "name", "") or ""),
        str(getattr(service_info, "local_name", "") or ""),
        str(getattr(getattr(service_info, "device", None), "name", "") or ""),
    ):
        if not name:
            continue
        if _is_identifier_like_name(name):
            return "Grid Connect BLE Device"
        return name
    return "Unnamed BLE Device"


def _build_device_payload(
    *,
    address: str,
    device_name: str,
    grid_connect_uuid: str,
    host: str,
    wifi_ssid: str,
    model: str | None,
) -> dict[str, Any]:
    """Build a normalized child-device payload for entry storage."""
    return {
        "device_address": address,
        "device_name": device_name,
        "grid_connect_uuid": grid_connect_uuid,
        "host": host,
        "wifi_ssid": wifi_ssid,
        CONF_MODEL: model,
    }


def _build_hub_entry_data(device_payload: dict[str, Any]) -> dict[str, Any]:
    """Build config entry data for the logical Grid Connect hub."""
    return {
        "hub_name": _HUB_ENTRY_TITLE,
        "devices": [device_payload],
        # Keep legacy top-level fields for the current runtime path.
        **device_payload,
    }


def _build_hub_entry_data_from_devices(
    devices: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build config entry data for a hub with one or more child devices."""
    first_device = devices[0] if devices else {}
    return {
        "hub_name": _HUB_ENTRY_TITLE,
        "devices": devices,
        **first_device,
    }


class GridConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Grid Connect."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient config flow state."""
        self._provisioning_method = "ez"
        self._discovered_ble_devices: list[dict[str, Any]] = []
        self._selected_ble_device: dict[str, Any] | None = None
        self._grid_connect_uuid: str | None = None
        self._wifi_ssid = ""
        self._wifi_password = ""
        self._host = ""
        self._device_name: str | None = None
        self._selected_model: str | None = None
        self._ez_provisioned = False

    def _show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
        errors: dict[str, str] | None = None,
        description_placeholders: dict[str, str] | None = None,
    ) -> FlowResult:
        """Return a typed form result."""
        return self.async_show_form(
            step_id=step_id,
            data_schema=data_schema,
            errors=errors or {},
            description_placeholders=description_placeholders,
        )

    def _abort(self, reason: str) -> FlowResult:
        """Return a typed abort result."""
        return self.async_abort(reason=reason)

    def _create_entry(
        self, *, title: str, data: dict[str, Any]
    ) -> FlowResult:
        """Return a typed create-entry result."""
        return self.async_create_entry(title=title, data=data)

    def _get_hub_entry(self) -> config_entries.ConfigEntry | None:
        """Return the existing hub entry when one has already been created."""
        current_entries = self._async_current_entries()
        return current_entries[0] if current_entries else None

    def _existing_devices(
        self, entry: config_entries.ConfigEntry | None
    ) -> list[dict[str, Any]]:
        """Return device payloads stored on an existing hub entry."""
        if entry is None:
            return []
        devices = entry.data.get("devices")
        if isinstance(devices, list):
            return [device for device in devices if isinstance(device, dict)]
        if entry.data.get("device_address") or entry.data.get("host"):
            return [
                _build_device_payload(
                    address=str(entry.data.get("device_address") or ""),
                    device_name=str(
                        entry.data.get("device_name")
                        or entry.title
                        or "Grid Connect Device"
                    ),
                    grid_connect_uuid=str(entry.data.get("grid_connect_uuid") or ""),
                    host=str(entry.data.get("host") or ""),
                    wifi_ssid=str(entry.data.get("wifi_ssid") or ""),
                    model=entry.data.get(CONF_MODEL)
                    if isinstance(entry.data.get(CONF_MODEL), str)
                    else None,
                )
            ]
        return []

    def _device_already_added(
        self,
        devices: list[dict[str, Any]],
        new_device: dict[str, Any],
    ) -> bool:
        """Return True when the candidate device already exists on the hub."""
        new_address = str(new_device.get("device_address") or "")
        new_host = str(new_device.get("host") or "")
        for existing_device in devices:
            existing_address = str(existing_device.get("device_address") or "")
            existing_host = str(existing_device.get("host") or "")
            if new_address and existing_address == new_address:
                return True
            if new_host and existing_host == new_host:
                return True
        return False

    async def _store_device_on_hub(
        self,
        *,
        address: str,
        device_name: str,
        grid_connect_uuid: str,
        host: str,
        wifi_ssid: str,
        model: str | None,
    ) -> FlowResult:
        """Create the hub entry or append a device to the existing hub entry."""
        device_payload = _build_device_payload(
            address=address,
            device_name=device_name,
            grid_connect_uuid=grid_connect_uuid,
            host=host,
            wifi_ssid=wifi_ssid,
            model=model,
        )
        existing_entry = self._get_hub_entry()
        if existing_entry is None:
            return self._create_entry(
                title=_HUB_ENTRY_TITLE,
                data=_build_hub_entry_data(device_payload),
            )

        existing_devices = self._existing_devices(existing_entry)
        if self._device_already_added(existing_devices, device_payload):
            return self._abort("already_configured")

        updated_devices = [*existing_devices, device_payload]
        self.hass.config_entries.async_update_entry(
            existing_entry,
            title=_HUB_ENTRY_TITLE,
            data=_build_hub_entry_data_from_devices(updated_devices),
        )
        await self.hass.config_entries.async_reload(existing_entry.entry_id)
        return self._abort("device_added_to_hub")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Entry step: start BLE scan or manual add."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get("action") == "ez":
                self._provisioning_method = "ez"
                return await self.async_step_wifi_credentials()
            if user_input.get("action") == "scan":
                self._provisioning_method = "ble"
                return await self.async_step_ble_scan()
            if user_input.get("action") == "manual":
                return await self.async_step_manual()
        return self._show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="ez"): vol.In(
                        {
                            "ez": "EZ Mode (Wi-Fi pairing mode)",
                            "scan": "BLE Scan (legacy)",
                            "manual": "Specify Device Manually",
                        }
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_ble_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Scan for Grid Connect devices via BLE and present selection."""
        del user_input
        # We'll scan for 10 seconds and collect all BLE devices
        devices: list[dict[str, Any]] = []
        seen_addresses: set[str] = set()
        scan_duration = 10  # seconds
        start_time = time.monotonic()
        _LOGGER.debug("Starting BLE scan for Grid Connect devices (%ss)", scan_duration)

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

                # Some devices advertise as non-connectable during parts of pairing mode.
                try:
                    discovered_non_connectable = bluetooth.async_discovered_service_info(
                        self.hass, connectable=False
                    )
                except TypeError:
                    discovered_non_connectable = []

                for service_info in [*discovered, *discovered_non_connectable]:
                    if not _is_likely_grid_connect_device(service_info):
                        continue
                    # Collect all BLE devices by address; UUIDs may be absent in advertisements.
                    if (
                        hasattr(service_info, "address")
                        and service_info.address
                        and service_info.address not in seen_addresses
                    ):
                        devices.append({
                            "id": service_info.address,
                            "name": _friendly_ble_name(service_info),
                            "address": service_info.address,
                            "service_uuids": list(getattr(service_info, "service_uuids", []) or []),
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

        _LOGGER.info("Discovered %d BLE candidate devices", len(devices))
        self._discovered_ble_devices = devices
        return await self.async_step_select_ble_device()

    async def async_step_no_devices_found(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show options when no devices are found during BLE scan."""
        errors: dict[str, str] = {}

        if user_input is not None:
            action = user_input.get("action")
            if action == "scan_again":
                _LOGGER.info("User chose to scan again from no devices found step.")
                return await self.async_step_ble_scan()
            if action == "manual":
                _LOGGER.info("User chose manual entry from no devices found step.")
                return await self.async_step_manual()

        return self._show_form(
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

    async def async_step_select_ble_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Present discovered BLE devices and let the user select one."""
        errors: dict[str, str] = {}
        discovered_devices = self._discovered_ble_devices
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
                _LOGGER.debug(
                    "Selected BLE device: %s (%s)",
                    selected_device.get("name"),
                    selected_device.get("address"),
                )
                self._selected_ble_device = selected_device
                return await self.async_step_identify_grid_connect_uuid()
            errors["base"] = "device_not_found"

        return self._show_form(
            step_id="select_ble_device",
            data_schema=vol.Schema(
                {vol.Required("selected_device"): vol.In(devices_for_selection)}
            ),
            errors=errors,
            description_placeholders={
                "devices": ", ".join(devices_for_selection.values())
            },
        )

    async def async_step_identify_grid_connect_uuid(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Identify the Grid Connect UUID from the selected device's service UUIDs."""
        del user_input
        selected_device = self._selected_ble_device

        if not selected_device:
            _LOGGER.error("Selected BLE device not found in context.")
            return await self.async_step_manual()

        service_uuids = list(selected_device.get("service_uuids", []))
        if not service_uuids:
            # Many low-cost plugs do not expose custom service UUIDs in advertisements.
            _LOGGER.info(
                "No advertised service UUIDs for %s; using default Grid Connect UUID %s",
                selected_device.get("address"),
                GRID_CONNECT_SERVICE_UUID,
            )
            self._grid_connect_uuid = GRID_CONNECT_SERVICE_UUID
            return await self.async_step_wifi_credentials()

        # Heuristic to find a non-standard, custom UUID that is likely the Grid Connect service.
        # This is a basic approach and might need refinement based on actual device behavior.
        grid_connect_uuid: str | None = None
        for uuid in service_uuids:
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
            detected_model = _detect_model_from_name(selected_device.get("name"))
            if detected_model:
                _LOGGER.info(
                    "Detected model %s from device name '%s'",
                    detected_model,
                    selected_device.get("name"),
                )
            self._grid_connect_uuid = grid_connect_uuid
            return await self.async_step_wifi_credentials()

        _LOGGER.warning(
            "Could not identify a unique Grid Connect UUID for device %s, "
            "falling back to manual UUID selection.",
            selected_device["address"],
        )
        return await self.async_step_select_fallback_uuid()

    async def async_step_select_fallback_uuid(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick a UUID or trigger a new scan when heuristic fails."""
        selected_device = self._selected_ble_device

        if not selected_device or "service_uuids" not in selected_device:
            _LOGGER.error(
                "No selected device or service UUIDs available in context for fallback UUID selection."
            )
            return await self.async_step_manual()

        raw_service_uuids = selected_device.get("service_uuids")
        service_uuids = (
            [str(uuid) for uuid in raw_service_uuids]
            if isinstance(raw_service_uuids, list)
            else []
        )
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
                    self._grid_connect_uuid = str(selected_uuid)
                    _LOGGER.info(
                        "User selected UUID %s for device %s",
                        selected_uuid,
                        selected_device.get("address"),
                    )
                    return await self.async_step_wifi_credentials()

        return self._show_form(
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
    ) -> FlowResult:
        """Ask the user for Wi-Fi credentials and provision via EZ mode."""
        selected_device = self._selected_ble_device
        grid_connect_uuid = self._grid_connect_uuid
        provisioning_method = self._provisioning_method

        errors: dict[str, str] = {}

        if self._ez_provisioned and selected_device and grid_connect_uuid:
            model = self._selected_model
            selected_name = selected_device.get("name")
            selected_address = selected_device.get("address")
            host = self._host
            return await self._store_device_on_hub(
                address=str(selected_address or ""),
                device_name=str(selected_name or self._device_name or "Grid Connect Device"),
                grid_connect_uuid=grid_connect_uuid,
                host=host,
                wifi_ssid=self._wifi_ssid,
                model=model,
            )

        if user_input is not None:
            ssid = str(user_input["ssid"])
            password = str(user_input["password"])
            host = str(user_input.get("host") or "")
            selected_name = (
                str(selected_device.get("name") or "") if selected_device else None
            )
            device_name_input = user_input.get("device_name")
            device_name = (
                str(device_name_input) if device_name_input else selected_name
            )
            model_value = user_input.get(CONF_MODEL)
            model_input = model_value if isinstance(model_value, str) else None
            _LOGGER.info(
                "Attempting EZ-mode Wi-Fi provisioning on SSID '%s'",
                ssid,
            )

            if provisioning_method == "ez":
                result = await send_ez_mode_credentials(ssid, password)
                if result is None:
                    self._wifi_ssid = ssid
                    self._wifi_password = password
                    self._host = host
                    self._selected_model = model_input
                    self._device_name = device_name
                    self._ez_provisioned = True
                    return await self.async_step_ble_scan()
            else:
                result = "ble_error"
                if (
                    selected_device
                    and grid_connect_uuid
                    and selected_device.get("address")
                ):
                    result = await send_wifi_credentials(
                        str(selected_device["address"]),
                        ssid,
                        password,
                        preferred_service_uuid=grid_connect_uuid,
                    )

            if (
                result is None
                and selected_device
                and grid_connect_uuid
                and selected_device.get("address")
            ):
                result = await send_wifi_credentials(
                    str(selected_device["address"]),
                    ssid,
                    password,
                    preferred_service_uuid=grid_connect_uuid,
                )

            if result is None:
                selected_address = (
                    str(selected_device.get("address") or "")
                    if selected_device
                    else ""
                )
                detected_model = _detect_model_from_name(selected_name)
                _LOGGER.info(
                    "Wi-Fi provisioning succeeded for %s (model=%s)",
                    selected_address or host,
                    detected_model or user_input.get(CONF_MODEL),
                )
                return await self._store_device_on_hub(
                    address=selected_address,
                    device_name=device_name or selected_name or "Grid Connect Device",
                    grid_connect_uuid=grid_connect_uuid or GRID_CONNECT_SERVICE_UUID,
                    host=host,
                    wifi_ssid=ssid,
                    model=detected_model or model_input,
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
            elif result == "ez_mode_error":
                errors["base"] = "ble_unknown_error"
            else:
                errors["base"] = "ble_unknown_error"

        selected_name = (
            str(selected_device.get("name") or "") if selected_device else None
        )
        suggested_model = _detect_model_from_name(
            selected_name
        ) or self._selected_model
        model_field: Any
        if suggested_model in {MODEL_PC191HA, MODEL_PC191BKHA, MODEL_SG120HA}:
            model_field = vol.Optional(CONF_MODEL, default=suggested_model)
        else:
            model_field = vol.Optional(CONF_MODEL)

        return self._show_form(
            step_id="wifi_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required("ssid"): str,
                    vol.Required("password"): str,
                    vol.Optional("host"): str,
                    vol.Optional("device_name"): str,
                    model_field: vol.In(
                        {
                            MODEL_PC191HA: "Arlec Smart Plug + Energy (PC191HA)",
                            MODEL_PC191BKHA: "Arlec Smart Plug + Energy (PC191BKHA)",
                            MODEL_SG120HA: "Arlec Smart Plug (SG120HA)",
                        }
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Fallback: let user manually specify device details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Store manual entry data in context and proceed to Wi-Fi provisioning
            self._selected_ble_device = {
                "address": str(user_input["device_address"]),
                "name": str(user_input["device_name"]),
            }
            self._grid_connect_uuid = str(user_input["grid_connect_uuid"])
            model_value = user_input.get(CONF_MODEL)
            self._selected_model = model_value if isinstance(model_value, str) else None
            _LOGGER.info(
                "Manual entry: device %s with UUID %s, proceeding to Wi-Fi provisioning",
                user_input["device_name"],
                user_input["grid_connect_uuid"],
            )
            return await self.async_step_wifi_credentials()
        return self._show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required("device_name"): str,
                    vol.Required("grid_connect_uuid"): str,
                    vol.Required("device_address"): str,
                    vol.Optional(CONF_MODEL): vol.In(
                        {
                            MODEL_PC191HA: "Arlec Smart Plug + Energy (PC191HA)",
                            MODEL_PC191BKHA: "Arlec Smart Plug + Energy (PC191BKHA)",
                            MODEL_SG120HA: "Arlec Smart Plug (SG120HA)",
                        }
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Redirect to BLE scan as the primary device selection method."""
        del user_input
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
        self._config_entry = config_entry

    def _show_form(
        self,
        *,
        step_id: str,
        data_schema: vol.Schema,
    ) -> FlowResult:
        """Return a typed options-form result."""
        return self.async_show_form(step_id=step_id, data_schema=data_schema)

    def _create_entry(self, data: dict[str, Any]) -> FlowResult:
        """Return a typed options entry result."""
        return self.async_create_entry(title="", data=data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self._create_entry(user_input)

        return self._show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "option1", default=self._config_entry.options.get("option1", "")
                    ): str
                }
            ),
        )


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""
