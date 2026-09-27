"""Manager-side WebSocket server.

Accepts connections from remote antennas, registers each node, and forwards
their NodeReports into a MultiReceiverService. Pure asyncio + websockets, so
it runs unchanged on macOS, Windows and Linux.

The local computer's own radios do NOT go through this server — they feed the
same MultiReceiverService directly via antennas.local_antenna.LocalAntenna.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

import websockets

from core.models import NodeReport
from net import node_protocol as proto
from services.multireceiver_service import MultiReceiverService


@dataclass
class ConnectedNode:
    node_id: str
    name: str
    x: float
    y: float
    platform: str = ""
    last_seen: float = field(default_factory=time.time)
    remote_addr: str = ""


class ManagerServer:
    """Runs the WebSocket endpoint antennas connect to."""

    def __init__(
        self,
        service: MultiReceiverService,
        host: str = "0.0.0.0",
        port: int = proto.DEFAULT_PORT,
        on_change: Optional[Callable[[], None]] = None,
    ):
        self._service = service
        self._host = host
        self._port = port
        self._on_change = on_change
        self._nodes: Dict[str, ConnectedNode] = {}
        self._server = None

    @property
    def port(self) -> int:
        return self._port

    def connected_nodes(self) -> Dict[str, ConnectedNode]:
        return dict(self._nodes)

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        """Manager can override where an antenna sits (snap-to-radius / manual)."""
        node = self._nodes.get(node_id)
        if node is not None:
            node.x, node.y = x, y

    async def start(self) -> None:
        self._server = await websockets.serve(
            self._handle, self._host, self._port, ping_interval=20, ping_timeout=20)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, ws):
        node_id: Optional[str] = None
        peer = getattr(ws, "remote_address", ("?",))[0]
        try:
            async for raw in ws:
                try:
                    msg = proto.decode(raw)
                except proto.ProtocolError:
                    continue

                mtype = msg.get("type")
                if mtype == "hello":
                    rep = proto.report_from_hello(msg)
                    node_id = rep.node_id
                    self._nodes[node_id] = ConnectedNode(
                        node_id=node_id, name=rep.name, x=rep.x, y=rep.y,
                        platform=str(msg.get("platform", "")), remote_addr=peer)
                    await ws.send(proto.encode_ack(node_id))
                    self._notify()

                elif mtype == "report":
                    if node_id is None:
                        continue
                    node = self._nodes.get(node_id)
                    if node is None:
                        continue
                    node.last_seen = time.time()
                    obs = proto.observations_from_report(msg)
                    # Build a report using the manager's authoritative position
                    # for this node (it may have been snapped/edited locally).
                    self._service.submit(NodeReport(
                        node_id=node_id, name=node.name, x=node.x, y=node.y,
                        observations=obs, is_local=False))

                elif mtype == "ping":
                    await ws.send(proto.encode_pong())

                elif mtype == "bye":
                    break
        except websockets.ConnectionClosed:
            pass
        finally:
            if node_id is not None and node_id in self._nodes:
                del self._nodes[node_id]
                self._notify()

    def _notify(self):
        if self._on_change is not None:
            self._on_change()
