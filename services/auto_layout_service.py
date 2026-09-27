"""Auto-layout service — bridge between the multi-receiver layer and the
auto-layout solver.

Collects pairwise BLE distances between the Mac, the iPhone antenna, and all
visible devices, then feeds them to the solver along with user direction hints
to compute positions automatically.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple

from core.models import AnchorMeasurement, NodeObservation, NodeReport, SignalType
from engine.auto_layout import (
    AutoLayoutResult,
    DirectionHint,
    PairwiseDistance,
    solve_layout,
)
from engine.distance import rssi_to_distance


class AutoLayoutService:
    OBS_MAX_AGE = 10.0

    def __init__(self):
        self._hints: Dict[str, DirectionHint] = {}
        self._last_result: Optional[AutoLayoutResult] = None
        self._device_names: Dict[str, str] = {}

    # ── hint management ──────────────────────────────────────────────────

    def set_hint(self, device_id: str, direction: str) -> None:
        self._hints[device_id] = DirectionHint(device_id, direction)

    def remove_hint(self, device_id: str) -> None:
        self._hints.pop(device_id, None)

    def hints(self) -> Dict[str, DirectionHint]:
        return dict(self._hints)

    # ── solve ─────────────────────────────────────────────────────────────

    def solve(
        self,
        local_id: str,
        local_report: NodeReport,
        remote_reports: List[NodeReport],
        room_w: float,
        room_h: float,
    ) -> Optional[AutoLayoutResult]:
        """Build pairwise distance matrix and solve positions.

        *local_report*: the Mac's own scan (observations of all nearby devices).
        *remote_reports*: iPhone antenna reports (observations from remote nodes).

        Pairwise distances are extracted from:
        - Mac → each device it sees (from local_report)
        - iPhone → each device it sees (from remote_reports)
        - iPhone ↔ Mac (from remote report seeing the Mac, or Mac seeing iPhone)
        """
        now = time.time()
        pairs: List[PairwiseDistance] = []

        # Mac's observations → pairwise distances Mac↔device
        for obs in local_report.observations:
            if now - obs.timestamp > self.OBS_MAX_AGE:
                continue
            dist = self._obs_to_distance(obs, local_report.tx_power, local_report.n)
            pairs.append(PairwiseDistance(local_id, obs.target_id, dist))
            self._device_names[obs.target_id] = obs.name

        # Each remote antenna's observations → pairwise distances antenna↔device
        for node in remote_reports:
            if now - node.timestamp > self.OBS_MAX_AGE:
                continue
            self._device_names[node.node_id] = node.name
            for obs in node.observations:
                if now - obs.timestamp > self.OBS_MAX_AGE:
                    continue
                dist = self._obs_to_distance(obs, node.tx_power, node.n)
                pairs.append(PairwiseDistance(node.node_id, obs.target_id, dist))
                self._device_names[obs.target_id] = obs.name

        if len(pairs) < 2:
            return None

        result = solve_layout(local_id, pairs, self._hints, room_w, room_h)
        self._last_result = result
        return result

    def get_anchor_measurements(
        self, local_id: str
    ) -> List[AnchorMeasurement]:
        """Convert solved positions into AnchorMeasurements for positioning."""
        if self._last_result is None:
            return []
        my_pos = self._last_result.positions.get(local_id)
        if my_pos is None:
            return []
        out = []
        for did, (x, y) in self._last_result.positions.items():
            if did == local_id:
                continue
            import math
            dist = math.sqrt((x - my_pos[0]) ** 2 + (y - my_pos[1]) ** 2)
            if dist > 0.05:
                out.append(AnchorMeasurement(x=x, y=y, distance=dist))
        return out

    @property
    def last_result(self) -> Optional[AutoLayoutResult]:
        return self._last_result

    @property
    def device_names(self) -> Dict[str, str]:
        return dict(self._device_names)

    @staticmethod
    def _obs_to_distance(obs: NodeObservation, tx_power: float, n: float) -> float:
        if obs.distance is not None:
            return max(obs.distance, 0.05)
        return rssi_to_distance(float(obs.rssi), tx_power, n)
