"""EZ-mode Wi-Fi provisioning helpers."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import time

_LOGGER = logging.getLogger(__name__)

_EZ_BROADCAST_PORTS: tuple[int, ...] = (6669, 7000)


def _build_ez_payloads(ssid: str, password: str) -> list[bytes]:
    """Build payload variants used for best-effort EZ-mode broadcasting."""
    return [
        f"{ssid},{password}".encode(),
        f"{ssid}\0{password}".encode(),
        json.dumps({"ssid": ssid, "password": password}).encode(),
    ]


def _broadcast_ez_payloads(
    ssid: str, password: str, duration_seconds: int, interval_seconds: float
) -> None:
    """Broadcast EZ-mode payloads for a fixed duration."""
    payloads = _build_ez_payloads(ssid, password)
    deadline = time.monotonic() + duration_seconds
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while time.monotonic() < deadline:
            for port in _EZ_BROADCAST_PORTS:
                for payload in payloads:
                    sock.sendto(payload, ("255.255.255.255", port))
            time.sleep(interval_seconds)


async def send_ez_mode_credentials(
    ssid: str, password: str, duration_seconds: int = 25
) -> str | None:
    """Send Wi-Fi credentials using EZ-mode UDP broadcast."""
    try:
        await asyncio.to_thread(
            _broadcast_ez_payloads, ssid, password, duration_seconds, 0.2
        )
    except OSError:
        _LOGGER.exception("EZ-mode broadcast failed")
        return "ez_mode_error"
    return None
