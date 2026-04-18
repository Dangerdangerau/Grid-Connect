"""Device-registry helpers for Grid Connect."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_MODEL, DOMAIN

MANUFACTURER = "Grid Connect"
HUB_IDENTIFIER = (DOMAIN, "hub")


def _device_identifier(entry: ConfigEntry) -> tuple[str, str]:
    """Return a stable identifier for the configured child device."""
    return (
        DOMAIN,
        str(
            entry.data.get("device_address")
            or entry.data.get("host")
            or entry.entry_id
        ),
    )


def _device_name(entry: ConfigEntry) -> str:
    """Return the display name for the configured child device."""
    return str(entry.data.get("device_name") or entry.title or "Grid Connect Device")


def _device_model(entry: ConfigEntry) -> str:
    """Return the configured model or a fallback label."""
    return str(entry.data.get(CONF_MODEL) or "Grid Connect Device")


def build_child_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Build child-device metadata for entity `device_info`."""
    return {
        "identifiers": {_device_identifier(entry)},
        "manufacturer": MANUFACTURER,
        "model": _device_model(entry),
        "name": _device_name(entry),
        "via_device": HUB_IDENTIFIER,
    }


def async_ensure_hub_device(
    hass: HomeAssistant, entry: ConfigEntry
) -> dr.DeviceEntry:
    """Ensure the logical Grid Connect hub exists in the device registry."""
    device_registry = dr.async_get(hass)
    return device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={HUB_IDENTIFIER},
        manufacturer=MANUFACTURER,
        model="Integration Hub",
        name="Grid Connect Hub",
    )


def async_ensure_child_device(
    hass: HomeAssistant, entry: ConfigEntry
) -> dr.DeviceEntry:
    """Ensure the configured child device exists and is linked to the hub."""
    device_registry = dr.async_get(hass)
    kwargs: dict[str, Any] = {
        "config_entry_id": entry.entry_id,
        "identifiers": {_device_identifier(entry)},
        "manufacturer": MANUFACTURER,
        "model": _device_model(entry),
        "name": _device_name(entry),
        "via_device": HUB_IDENTIFIER,
    }
    device_address = entry.data.get("device_address")
    if device_address:
        kwargs["connections"] = {(dr.CONNECTION_BLUETOOTH, str(device_address))}
    return device_registry.async_get_or_create(**kwargs)
