"""BLE utilities for sending Wi-Fi credentials to Grid Connect devices."""

from __future__ import annotations

import logging

try:
    from bleak import BleakClient, BleakError
except ImportError:  # pragma: no cover - runtime dependency
    BleakClient = None  # type: ignore[assignment]
    BleakError = Exception  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

# Placeholder UUIDs - replace with actual Grid Connect service/characteristic UUIDs.
GRID_CONNECT_SERVICE_UUID = "0000fd88-0000-1000-8000-00805f9b34fb"
WIFI_WRITE_CHAR_UUID = "0000fd89-0000-1000-8000-00805f9b34fb"


def format_wifi_payload(ssid: str, password: str) -> bytes:
    """Format credential payload expected by the device firmware."""
    return f"{ssid},{password}".encode("utf-8")


async def _is_client_connected(client: BleakClient) -> bool:
    """Get connection state across bleak versions."""
    connected = getattr(client, "is_connected", False)
    if callable(connected):
        connected = connected()
        if hasattr(connected, "__await__"):
            connected = await connected
    return bool(connected)


async def send_wifi_credentials(
    address: str, ssid: str, password: str, timeout: int = 15
) -> str | None:
    """Send Wi-Fi credentials over BLE. Return None on success, error code on failure."""
    if BleakClient is None:
        return "bleak_not_installed"

    payload = format_wifi_payload(ssid, password)

    try:
        async with BleakClient(address, timeout=timeout) as client:
            if not await _is_client_connected(client):
                await client.connect(timeout=timeout)

            if not await _is_client_connected(client):
                return "not_connected"

            await client.write_gatt_char(WIFI_WRITE_CHAR_UUID, payload, response=True)
            return None
    except TimeoutError:
        _LOGGER.exception("BLE operation timed out while provisioning %s", address)
        return "timeout"
    except BleakError:
        _LOGGER.exception("BLE transport/protocol error while provisioning %s", address)
        return "ble_error"
    except Exception:
        _LOGGER.exception("Unexpected BLE Wi-Fi credential send error for %s", address)
        return "ble_unknown_error"
