"""Switch platform for Grid Connect smart plugs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import CONF_MODEL, DOMAIN, SUPPORTED_SMART_PLUG_MODELS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Grid Connect switch platform."""
    if entry.data.get(CONF_MODEL) not in SUPPORTED_SMART_PLUG_MODELS:
        return
    coordinator: DataUpdateCoordinator[Any] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([GridConnectPlugSwitch(entry, coordinator)])


class GridConnectPlugSwitch(CoordinatorEntity[DataUpdateCoordinator[Any]], SwitchEntity):
    """Representation of Grid Connect smart plug relay."""

    def __init__(self, entry: ConfigEntry, coordinator: DataUpdateCoordinator[Any]) -> None:
        """Initialize switch entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Power"
        self._attr_unique_id = f"{entry.entry_id}_power"

    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return bool(self.coordinator.data.get("switch", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.api_client.async_turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.api_client.async_turn_off()
        await self.coordinator.async_request_refresh()
