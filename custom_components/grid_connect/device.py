"""Device-registry helpers for Grid Connect."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_MODEL, DOMAIN

MANUFACTURER = "Grid Connect"
HUB_IDENTIFIER = (DOMAIN, "hub")


def get_entry_devices(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return normalized device payloads stored on the config entry."""
    devices = entry.data.get("devices")
    if isinstance(devices, list):
        normalized = [device for device in devices if isinstance(device, dict)]
        if normalized:
            return normalized

    legacy_device = {
        "device_address": entry.data.get("device_address", ""),
        "device_name": entry.data.get("device_name", entry.title),
        "grid_connect_uuid": entry.data.get("grid_connect_uuid", ""),
        "host": entry.data.get("host", ""),
        "wifi_ssid": entry.data.get("wifi_ssid", ""),
        CONF_MODEL: entry.data.get(CONF_MODEL),
    }
    if legacy_device["device_address"] or legacy_device["host"]:
        return [legacy_device]
    return []


def device_identifier(device: dict[str, Any], fallback: str) -> tuple[str, str]:
    """Return a stable identifier for a child device."""
    return (
        DOMAIN,
        str(device.get("device_address") or device.get("host") or fallback),
    )


def device_unique_token(device: dict[str, Any], fallback: str) -> str:
    """Return a stable token safe for entity unique IDs."""
    identifier = device_identifier(device, fallback)[1]
    return identifier.replace(":", "_").replace("-", "_").lower()


def device_name(device: dict[str, Any], fallback: str) -> str:
    """Return the display name for a child device."""
    return str(device.get("device_name") or fallback)


def device_model(device: dict[str, Any]) -> str:
    """Return the configured model or a fallback label."""
    return str(device.get(CONF_MODEL) or "Grid Connect Device")


def build_child_device_info(
    entry: ConfigEntry, device: dict[str, Any], fallback: str
) -> DeviceInfo:
    """Build child-device metadata for entity `device_info`."""
    return DeviceInfo(
        identifiers={device_identifier(device, fallback)},
        manufacturer=MANUFACTURER,
        model=device_model(device),
        name=device_name(device, fallback),
        via_device=HUB_IDENTIFIER,
    )


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
        name=str(entry.data.get("hub_name") or "Grid Connect Hub"),
    )


def async_ensure_child_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: dict[str, Any],
    fallback: str,
) -> dr.DeviceEntry:
    """Ensure a configured child device exists and is linked to the hub."""
    device_registry = dr.async_get(hass)
    kwargs: dict[str, Any] = {
        "config_entry_id": entry.entry_id,
        "identifiers": {device_identifier(device, fallback)},
        "manufacturer": MANUFACTURER,
        "model": device_model(device),
        "name": device_name(device, fallback),
        "via_device": HUB_IDENTIFIER,
    }
    device_address = device.get("device_address")
    if device_address:
        kwargs["connections"] = {(dr.CONNECTION_BLUETOOTH, str(device_address))}
    return device_registry.async_get_or_create(**kwargs)
