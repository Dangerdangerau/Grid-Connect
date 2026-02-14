"""Switch platform for Grid Connect smart plugs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

from .const import CONF_MODEL, DOMAIN, SUPPORTED_SMART_PLUG_MODELS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Grid Connect switch platform."""
    if entry.data.get(CONF_MODEL) not in SUPPORTED_SMART_PLUG_MODELS:
        _LOGGER.debug(
            "Skipping switch setup for entry %s model=%s",
            entry.entry_id,
            entry.data.get(CONF_MODEL),
        )
        return
    _LOGGER.info(
        "Setting up switch platform for entry %s model=%s",
        entry.entry_id,
        entry.data.get(CONF_MODEL),
    )
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
        _LOGGER.debug("Switch turn_on requested for entry %s", self._entry.entry_id)
        await self.coordinator.api_client.async_turn_on()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("Switch turn_off requested for entry %s", self._entry.entry_id)
        await self.coordinator.api_client.async_turn_off()
        await self.coordinator.async_request_refresh()
