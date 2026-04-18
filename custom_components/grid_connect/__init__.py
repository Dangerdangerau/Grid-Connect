"""The Grid Connect integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)

from .api import AuthenticationError
from .bluetooth import discover_bluetooth_devices
from .const import DOMAIN
from .coordinator import GridConnectDataUpdateCoordinator
from .device import (
    async_ensure_child_device,
    async_ensure_hub_device,
    device_unique_token,
    get_entry_devices,
)
from .local_api import GridConnectAPI
from .server import async_setup_provisioning_server

_LOGGER = logging.getLogger(__name__)  # Set up the logger

# Define the platforms that this integration supports


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Grid Connect component and register services from services.yaml."""
    hass.data.setdefault(DOMAIN, {})
    async_setup_provisioning_server(hass)
    # Register custom services
    hass.services.async_register(DOMAIN, "turn_on", lambda call: None)
    hass.services.async_register(DOMAIN, "turn_off", lambda call: None)
    return True

# Define the platforms that this integration supports
_PLATFORMS: list[Platform] = [
    Platform.EVENT,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SENSOR,
]

# Type alias for better readability
GridConnectConfigEntry = ConfigEntry


@dataclass(slots=True)
class GridConnectRuntimeData:
    """Runtime state for a Grid Connect hub entry."""

    devices: list[dict[str, Any]]
    coordinators: dict[str, GridConnectDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: GridConnectConfigEntry) -> bool:
    """Set up Grid Connect from a config entry."""
    try:
        hass.data.setdefault(DOMAIN, {})
        _LOGGER.info("Setting up Grid Connect entry_id=%s", entry.entry_id)
        async_ensure_hub_device(hass, entry)
        configured_devices = get_entry_devices(entry)
        for index, device in enumerate(configured_devices, start=1):
            async_ensure_child_device(hass, entry, device, f"Device {index}")

        if entry.data.get("use_bluetooth"):
            # Handle Bluetooth device setup
            devices = await discover_bluetooth_devices()
            for device in devices:
                _LOGGER.info("Processing device: %s, %s", device.name, device.address)
            # Add further processing logic as needed
            return True

        # Non-Bluetooth setup path
        try:
            coordinators: dict[str, GridConnectDataUpdateCoordinator] = {}
            for index, device in enumerate(configured_devices, start=1):
                host = str(device.get("host") or device.get("device_address") or "")
                api_client = GridConnectAPI(
                    host=host,
                    username=entry.data.get("username", ""),
                    password=entry.data.get("password", ""),
                    model=device.get("model"),
                )
                coordinator = GridConnectDataUpdateCoordinator(hass, api_client)
                await coordinator.async_config_entry_first_refresh()
                coordinators[device_unique_token(device, f"device_{index}")] = coordinator
                _LOGGER.debug(
                    "Coordinator initialized for entry_id=%s host=%s",
                    entry.entry_id,
                    host,
                )

            runtime_data = GridConnectRuntimeData(
                devices=configured_devices,
                coordinators=coordinators,
            )
            hass.data[DOMAIN][entry.entry_id] = runtime_data

            # Forward the configuration entry to the defined platforms
            await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
        except (ValueError, ImportError) as err:
            _LOGGER.error("Failed to set up platforms: %s", err)
            return False
        else:
            entry.runtime_data = runtime_data
            _LOGGER.info("Grid Connect setup complete for entry_id=%s", entry.entry_id)
            return True

    except AuthenticationError as err:
        raise ConfigEntryAuthFailed("Authentication failed") from err
    except ConnectionError as err:
        raise ConfigEntryNotReady("Could not connect to the device") from err
    except Exception as err:
        raise ConfigEntryError(f"Unexpected error: {err}") from err


async def async_unload_entry(
    hass: HomeAssistant, entry: GridConnectConfigEntry
) -> bool:
    """Unload a config entry."""

    # Remove the integration platforms when unloading the configuration entry
    _LOGGER.info("Unloading Grid Connect entry_id=%s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
