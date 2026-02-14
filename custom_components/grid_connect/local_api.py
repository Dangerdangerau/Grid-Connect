"""Local API client for communicating with Grid Connect devices."""

import asyncio
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class GridConnectAPI:
    """Basic local API client for Grid Connect."""

    def __init__(
        self, host: str, username: str, password: str, model: str | None = None
    ) -> None:
        """Initialize the API client.

        Args:
            host: The device IP or hostname.
            username: Login username (if needed).
            password: Login password (if needed).

        """
        self.host = host
        self.username = username
        self.password = password
        self.model = model
        self._is_on = False
        self._power_w = 0.0
        self._current_a = 0.0
        self._voltage_v = 240.0
        self._energy_kwh_total = 0.0
        self._energy_kwh_today = 0.0
        _LOGGER.info("Initialized GridConnectAPI for host=%s model=%s", host, model)

    async def get_data(self) -> dict[str, Any]:
        """Fetch data from the device.

        This is a stub method — replace with real I/O logic.
        """
        try:
            # Simulate async I/O with a sleep (replace this)
            await asyncio.sleep(1)
            # Replace the following with real data from the device protocol.
            data = {
                "sensor_state": self._is_on,
                "switch": self._is_on,
                "power_w": self._power_w,
                "current_a": self._current_a,
                "voltage_v": self._voltage_v,
                "energy_kwh_total": self._energy_kwh_total,
                "energy_kwh_today": self._energy_kwh_today,
            }
            _LOGGER.debug(
                "Telemetry host=%s switch=%s power_w=%.3f current_a=%.3f voltage_v=%.3f",
                self.host,
                self._is_on,
                self._power_w,
                self._current_a,
                self._voltage_v,
            )
        except Exception as err:
            _LOGGER.error("Failed to get data from Grid Connect: %s", err)
            raise
        else:
            _LOGGER.debug("Fetched data from Grid Connect: %s", data)
            return data

    async def async_turn_on(self) -> None:
        """Turn plug on."""
        _LOGGER.info("Turning ON plug at host=%s", self.host)
        self._is_on = True
        self._power_w = 12.0
        self._current_a = round(self._power_w / max(self._voltage_v, 1.0), 3)

    async def async_turn_off(self) -> None:
        """Turn plug off."""
        _LOGGER.info("Turning OFF plug at host=%s", self.host)
        self._is_on = False
        self._power_w = 0.0
        self._current_a = 0.0
