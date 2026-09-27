"""LAN discovery via mDNS/Bonjour (zeroconf).

The manager advertises a `_blelocator._tcp` service; antennas browse for it so
the user doesn't have to type an IP. Manual host entry remains the fallback.

IMPORTANT: the app runs inside an asyncio (qasync) event loop, so we MUST use
zeroconf's ASYNC API (AsyncZeroconf). The synchronous API throws
EventLoopBlocked when called from within a running loop.
"""

from __future__ import annotations

import asyncio
import socket
from typing import List, Optional, Tuple

from zeroconf import ServiceInfo
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from net import node_protocol as proto

_SERVICE = proto.SERVICE_TYPE


def _local_ip() -> str:
    """Best-effort primary LAN IP (no traffic actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class ManagerAdvertiser:
    """Manager side: announce ourselves on the LAN (async-safe)."""

    def __init__(self, name: str = "BLE Locator Manager", port: int = proto.DEFAULT_PORT):
        self._azc: Optional[AsyncZeroconf] = None
        self._info: Optional[ServiceInfo] = None
        self._name = name
        self._port = port

    async def async_start(self) -> None:
        ip = _local_ip()
        self._info = ServiceInfo(
            _SERVICE,
            f"{self._name}.{_SERVICE}",
            addresses=[socket.inet_aton(ip)],
            port=self._port,
            properties={"role": "manager"},
        )
        self._azc = AsyncZeroconf()
        await self._azc.async_register_service(self._info)

    async def async_stop(self) -> None:
        if self._azc is not None:
            try:
                if self._info is not None:
                    await self._azc.async_unregister_service(self._info)
            finally:
                await self._azc.async_close()
                self._azc = None


async def async_discover_managers(timeout: float = 2.5) -> List[Tuple[str, int]]:
    """Browse for managers without blocking the event loop."""
    found: List[Tuple[str, int]] = []
    azc = AsyncZeroconf()

    def _on_change(zeroconf, service_type, name, state_change):
        # resolve in a task so we don't block the callback
        asyncio.ensure_future(_resolve(zeroconf, service_type, name))

    async def _resolve(zeroconf, service_type, name):
        info = AsyncServiceInfo(service_type, name)
        if await info.async_request(zeroconf, 1500):
            for addr in info.parsed_addresses():
                found.append((addr, info.port))

    browser = AsyncServiceBrowser(
        azc.zeroconf, _SERVICE, handlers=[_on_change])
    try:
        await asyncio.sleep(timeout)
    finally:
        await browser.async_cancel()
        await azc.async_close()
    # de-dup, keep order
    return list(dict.fromkeys(found))
