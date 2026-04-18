"""Sensor platform for Grid Connect smart plug energy telemetry."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import CONF_MODEL, DOMAIN, SUPPORTED_ENERGY_SENSOR_MODELS
from .device import build_child_device_info

_LOGGER = logging.getLogger(__name__)


SENSORS: tuple[tuple[SensorEntityDescription, str], ...] = (
    (
        SensorEntityDescription(
            key="power",
            name="Power",
            native_unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "power_w",
    ),
    (
        SensorEntityDescription(
            key="current",
            name="Current",
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "current_a",
    ),
    (
        SensorEntityDescription(
            key="voltage",
            name="Voltage",
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
            state_class=SensorStateClass.MEASUREMENT,
        ),
        "voltage_v",
    ),
    (
        SensorEntityDescription(
            key="energy_total",
            name="Energy total",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
        ),
        "energy_kwh_total",
    ),
    (
        SensorEntityDescription(
            key="energy_today",
            name="Energy today",
            native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL,
        ),
        "energy_kwh_today",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Grid Connect sensors."""
    if entry.data.get(CONF_MODEL) not in SUPPORTED_ENERGY_SENSOR_MODELS:
        _LOGGER.debug(
            "Skipping sensor setup for entry %s model=%s",
            entry.entry_id,
            entry.data.get(CONF_MODEL),
        )
        return
    _LOGGER.info(
        "Setting up energy sensor platform for entry %s model=%s",
        entry.entry_id,
        entry.data.get(CONF_MODEL),
    )
    coordinator: DataUpdateCoordinator[Any] = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            GridConnectSensor(entry, coordinator, description, value_key)
            for description, value_key in SENSORS
        ]
    )


class GridConnectSensor(CoordinatorEntity[DataUpdateCoordinator[Any]], SensorEntity):
    """Representation of Grid Connect sensor values."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator[Any],
        description: SensorEntityDescription,
        value_key: str,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._value_key = value_key
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = build_child_device_info(entry)

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        return self.coordinator.data.get(self._value_key)
