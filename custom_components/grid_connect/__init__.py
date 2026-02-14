"""The Grid Connect integration."""

from __future__ import annotations

import logging

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
from .coordinator import GridConnectDataUpdateCoordinator
from .const import DOMAIN
from .local_api import GridConnectAPI

_LOGGER = logging.getLogger(__name__)  # Set up the logger

# Define the platforms that this integration supports


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Grid Connect component and register services from services.yaml."""
    # Register custom services
    hass.services.async_register(DOMAIN, "turn_on", lambda call: None)
    hass.services.async_register(DOMAIN, "turn_off", lambda call: None)
    return True

# Define the platforms that this integration supports
_PLATFORMS: list[Platform] = [Platform.EVENT, Platform.BINARY_SENSOR]

# Type alias for better readability
type GridConnectConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: GridConnectConfigEntry) -> bool:
    """Set up Grid Connect from a config entry."""
    try:
        hass.data.setdefault(DOMAIN, {})

        if entry.data.get("use_bluetooth"):
            # Handle Bluetooth device setup
            devices = await discover_bluetooth_devices()
            for device in devices:
                _LOGGER.info("Processing device: %s, %s", device.name, device.address)
            # Add further processing logic as needed
            return True

        # Non-Bluetooth setup path
        try:
            # Build and refresh coordinator used by entity platforms.
            api_client = GridConnectAPI(
                host=entry.data.get("host") or entry.data.get("device_address", ""),
                username=entry.data.get("username", ""),
                password=entry.data.get("password", ""),
            )
            coordinator = GridConnectDataUpdateCoordinator(hass, api_client)
            await coordinator.async_config_entry_first_refresh()
            hass.data[DOMAIN][entry.entry_id] = coordinator

            # Forward the configuration entry to the defined platforms
            await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)
        except (ValueError, ImportError) as err:
            _LOGGER.error("Failed to set up platforms: %s", err)
            return False
        else:
            entry.runtime_data = coordinator
            return True

    except AuthenticationError as err:
        raise ConfigEntryAuthFailed("Authentication failed") from err
    except ConnectionError as err:
        raise ConfigEntryNotReady("Could not connect to the device") from err
    except Exception as err:
        raise ConfigEntryError(f"Unexpected error: {err}") from err

    return False


async def async_unload_entry(
    hass: HomeAssistant, entry: GridConnectConfigEntry
) -> bool:
    """Unload a config entry."""

    # Remove the integration platforms when unloading the configuration entry
    unload_ok = await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
