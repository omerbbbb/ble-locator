"""Antenna-side client — streams NodeReports to a manager.

Used by antenna mode (antennas/antenna_app.py). Connects to a manager
(by explicit host, or discovered via mDNS), sends a hello, then pushes a
report every cycle. Auto-reconnects on drop.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

import websockets

from core.models import NodeReport
from net import node_protocol as proto


class NodeClient:
    def __init__(
        self,
        node_report_factory: Callable[[], NodeReport],
        host: str,
        port: int = proto.DEFAULT_PORT,
        platform: str = "",
        send_interval: float = 1.0,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        """`node_report_factory` returns the current NodeReport each cycle
        (identity + position + fresh observations)."""
        self._factory = node_report_factory
        self._host = host
        self._port = port
        self._platform = platform
        self._send_interval = send_interval
        self._on_status = on_status
        self._running = False

    def _status(self, msg: str):
        if self._on_status is not None:
            self._on_status(msg)

    async def run(self) -> None:
        self._running = True
        uri = f"ws://{self._host}:{self._port}"
        while self._running:
            try:
                self._status(f"Connecting to {self._host}…")
                async with websockets.connect(uri, ping_interval=20) as ws:
                    hello = proto.encode_hello(self._factory(), self._platform)
                    await ws.send(hello)
                    self._status("Connected — sending")
                    await self._pump(ws)
            except (OSError, websockets.WebSocketException) as e:
                self._status(f"Disconnected ({e}); retrying…")
                await asyncio.sleep(2.0)

    async def _pump(self, ws) -> None:
        while self._running:
            report = self._factory()
            await ws.send(proto.encode_report(report))
            n = len(report.observations)
            self._status(f"Connected — {n} devices, sending")
            await asyncio.sleep(self._send_interval)

    def stop(self) -> None:
        self._running = False
