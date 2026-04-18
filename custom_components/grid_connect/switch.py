"""Switch platform for Grid Connect smart plugs."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import GridConnectRuntimeData
from .const import CONF_MODEL, DOMAIN, SUPPORTED_SWITCH_MODELS
from .coordinator import GridConnectDataUpdateCoordinator
from .device import build_child_device_info, device_unique_token

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Grid Connect switch platform."""
    runtime_data: GridConnectRuntimeData = hass.data[DOMAIN][entry.entry_id]
    entities: list[GridConnectPlugSwitch] = []
    for index, device in enumerate(runtime_data.devices, start=1):
        if device.get(CONF_MODEL) not in SUPPORTED_SWITCH_MODELS:
            _LOGGER.debug(
                "Skipping switch setup for entry %s device=%s model=%s",
                entry.entry_id,
                device.get("device_name"),
                device.get(CONF_MODEL),
            )
            continue
        device_token = device_unique_token(device, f"device_{index}")
        coordinator = runtime_data.coordinators[device_token]
        entities.append(
            GridConnectPlugSwitch(entry, device, coordinator, f"Device {index}")
        )

    if entities:
        _LOGGER.info("Setting up %d switch entities for entry %s", len(entities), entry.entry_id)
        async_add_entities(entities)


class GridConnectPlugSwitch(
    CoordinatorEntity[GridConnectDataUpdateCoordinator], SwitchEntity
):
    """Representation of Grid Connect smart plug relay."""

    def __init__(
        self,
        entry: ConfigEntry,
        device: dict[str, Any],
        coordinator: GridConnectDataUpdateCoordinator,
        fallback_name: str,
    ) -> None:
        """Initialize switch entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True
        self._attr_name = "Power"
        device_token = device_unique_token(device, fallback_name)
        self._attr_unique_id = f"{entry.entry_id}_{device_token}_power"
        self._attr_device_info = build_child_device_info(entry, device, fallback_name)

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
