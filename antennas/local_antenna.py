"""LocalAntenna — the manager's own radios as 'antenna #1'.

Wraps any ISignalScanner (e.g. the existing MultiScanner) and turns its
current readings into a NodeReport, so the local computer participates in
multi-receiver fusion exactly like a remote antenna — same data shape, no
network hop.
"""

from __future__ import annotations

from typing import Optional

from core.interfaces import ISignalScanner
from core.models import NodeObservation, NodeReport


class LocalAntenna:
    def __init__(
        self,
        scanner: ISignalScanner,
        node_id: str = "local",
        name: str = "This computer",
        x: float = 0.0,
        y: float = 0.0,
        tx_power: float = -59.0,
        n: float = 2.5,
    ):
        self._scanner = scanner
        self.node_id = node_id
        self.name = name
        self.x = x
        self.y = y
        self.tx_power = tx_power
        self.n = n

    def set_position(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def report(self, max_age: float = 15.0) -> NodeReport:
        readings = self._scanner.get_active(max_age)
        observations = [
            NodeObservation(
                target_id=did,
                name=r.name,
                rssi=r.rssi,
                signal_type=r.signal_type,
                distance=r.distance,
                timestamp=r.timestamp,
            )
            for did, r in readings.items()
        ]
        return NodeReport(
            node_id=self.node_id,
            name=self.name,
            x=self.x,
            y=self.y,
            observations=observations,
            tx_power=self.tx_power,
            n=self.n,
            is_local=True,
        )
