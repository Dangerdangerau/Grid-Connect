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

from . import GridConnectRuntimeData
from .const import CONF_MODEL, DOMAIN, SUPPORTED_ENERGY_SENSOR_MODELS
from .device import build_child_device_info, device_unique_token

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
    runtime_data: GridConnectRuntimeData = hass.data[DOMAIN][entry.entry_id]
    entities: list[GridConnectSensor] = []
    for index, device in enumerate(runtime_data.devices, start=1):
        if device.get(CONF_MODEL) not in SUPPORTED_ENERGY_SENSOR_MODELS:
            _LOGGER.debug(
                "Skipping sensor setup for entry %s device=%s model=%s",
                entry.entry_id,
                device.get("device_name"),
                device.get(CONF_MODEL),
            )
            continue
        coordinator = runtime_data.coordinators[device_unique_token(device, f"device_{index}")]
        entities.extend(
            GridConnectSensor(entry, device, coordinator, description, value_key, f"Device {index}")
            for description, value_key in SENSORS
        )

    if entities:
        _LOGGER.info(
            "Setting up %d energy sensor entities for entry %s",
            len(entities),
            entry.entry_id,
        )
        async_add_entities(entities)


class GridConnectSensor(CoordinatorEntity[DataUpdateCoordinator[Any]], SensorEntity):
    """Representation of Grid Connect sensor values."""

    def __init__(
        self,
        entry: ConfigEntry,
        device: dict[str, Any],
        coordinator: DataUpdateCoordinator[Any],
        description: SensorEntityDescription,
        value_key: str,
        fallback_name: str,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._value_key = value_key
        self._attr_has_entity_name = True
        self._attr_name = description.name
        device_token = device_unique_token(device, fallback_name)
        self._attr_unique_id = f"{entry.entry_id}_{device_token}_{description.key}"
        self._attr_device_info = build_child_device_info(entry, device, fallback_name)

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        return self.coordinator.data.get(self._value_key)
