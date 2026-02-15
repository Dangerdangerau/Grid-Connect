"""BLE utilities for sending Wi-Fi credentials to Grid Connect devices."""

from __future__ import annotations

from inspect import isawaitable
import logging
from typing import Any

_BleakClient: type[Any] | None
_BleakError: type[BaseException] | None

try:
    from bleak import BleakClient as _BleakClient, BleakError as _BleakError
except ImportError:  # pragma: no cover - runtime dependency
    _BleakClient = None
    _BleakError = None

_LOGGER = logging.getLogger(__name__)

# Placeholder UUIDs - replace with actual Grid Connect service/characteristic UUIDs.
GRID_CONNECT_SERVICE_UUID = "0000fd88-0000-1000-8000-00805f9b34fb"
WIFI_WRITE_CHAR_UUID = "0000fd89-0000-1000-8000-00805f9b34fb"


def format_wifi_payload(ssid: str, password: str) -> bytes:
    """Format credential payload expected by the device firmware."""
    return f"{ssid},{password}".encode()


def _get_bleak_client_class() -> type[Any]:
    """Return BleakClient class when available."""
    if _BleakClient is None:
        raise RuntimeError("bleak_not_installed")
    return _BleakClient


def _normalized_uuid(value: str | None) -> str:
    """Return a normalized UUID string for comparisons."""
    return (value or "").strip().lower()


async def _candidate_write_characteristics(
    client: Any, preferred_service_uuid: str | None
) -> list[str]:
    """Return candidate writable characteristic UUIDs in priority order."""
    candidates: list[str] = [WIFI_WRITE_CHAR_UUID]
    preferred_service = _normalized_uuid(preferred_service_uuid)

    try:
        services = await client.get_services()
    except Exception:
        return candidates

    preferred: list[str] = []
    fallback: list[str] = []
    for service in services:
        service_uuid = _normalized_uuid(getattr(service, "uuid", ""))
        for characteristic in getattr(service, "characteristics", []) or []:
            properties = {
                str(prop).lower()
                for prop in (getattr(characteristic, "properties", []) or [])
            }
            if "write" not in properties and "write-without-response" not in properties:
                continue
            char_uuid = str(getattr(characteristic, "uuid", "") or "")
            if not char_uuid:
                continue
            if preferred_service and service_uuid == preferred_service:
                preferred.append(char_uuid)
            else:
                fallback.append(char_uuid)

    for uuid in [*preferred, *fallback]:
        if uuid not in candidates:
            candidates.append(uuid)
    return candidates


async def _is_client_connected(client: Any) -> bool:
    """Get connection state across bleak versions."""
    connected = getattr(client, "is_connected", False)
    if callable(connected):
        connected = connected()
        if isawaitable(connected):
            connected = await connected
    return bool(connected)


async def send_wifi_credentials(
    address: str,
    ssid: str,
    password: str,
    preferred_service_uuid: str | None = None,
    timeout: int = 20,
    retries: int = 2,
) -> str | None:
    """Send Wi-Fi credentials over BLE. Return None on success, error code on failure."""
    if _BleakClient is None:
        return "bleak_not_installed"

    bleak_client = _get_bleak_client_class()
    bleak_error = _BleakError
    payload = format_wifi_payload(ssid, password)

    for attempt in range(1, retries + 1):
        try:
            async with bleak_client(address, timeout=timeout) as client:
                if not await _is_client_connected(client):
                    await client.connect(timeout=timeout)

                if not await _is_client_connected(client):
                    if attempt == retries:
                        return "not_connected"
                    continue

                write_uuids = await _candidate_write_characteristics(
                    client, preferred_service_uuid
                )
                for char_uuid in write_uuids:
                    try:
                        await client.write_gatt_char(char_uuid, payload, response=True)
                        _LOGGER.debug(
                            "Provisioning write succeeded for %s using characteristic %s",
                            address,
                            char_uuid,
                        )
                        return None
                    except Exception:
                        continue
        except TimeoutError:
            if attempt == retries:
                _LOGGER.exception("BLE operation timed out while provisioning %s", address)
                return "timeout"
        except Exception as err:
            if bleak_error is not None and isinstance(err, bleak_error):
                if attempt == retries:
                    _LOGGER.exception(
                        "BLE transport/protocol error while provisioning %s", address
                    )
                    return "ble_error"
            elif attempt == retries:
                _LOGGER.exception(
                    "Unexpected BLE Wi-Fi credential send error for %s", address
                )
                return "ble_unknown_error"

    return "ble_error"
