"""Multi-receiver fusion — locate every target seen by 2+ antennas.

Takes the latest NodeReport from each antenna (the local computer, an
iPhone app, an ESP32, …), groups observations by target device, cleans and
(optionally) time-averages each antenna's signal, converts to a distance, and
triangulates the target with weighted least squares + a geometry (GDOP) score.

This sits ABOVE the per-node sensing layer and BELOW the UI, so the same
fusion works no matter what hardware the antennas are.

Pipeline per (antenna, target):
    raw rssi → Hampel→Kalman clean → static time-average → distance → fix(weight)
Then per target: WLS multilateration over the fixes, plus GDOP.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple

from core.models import AnchorMeasurement, NodeObservation, NodeReport, SignalType, TargetEstimate
from engine.distance import rssi_to_distance_two_slope
from engine.gdop import gdop as compute_gdop
from engine.wls_multilaterator import WlsMultilaterator
from filtering.adaptive_kalman import AdaptiveKalmanFilter
from filtering.composite_filter import CompositeFilter
from filtering.hampel_filter import HampelFilter
from filtering.median_filter import MedianFilter

_MIN_WEIGHT = 0.05


def _default_filter() -> CompositeFilter:
    return CompositeFilter([
        MedianFilter(window=5),
        HampelFilter(window=7, n_sigmas=2.5),
        AdaptiveKalmanFilter(),
    ])


class MultiReceiverService:
    OBS_MAX_AGE = 10.0  # seconds a node/observation stays usable

    def __init__(self):
        self._nodes: Dict[str, NodeReport] = {}
        self._locator = WlsMultilaterator()
        self._filters: Dict[Tuple[str, str], CompositeFilter] = {}

    # ── node management ──────────────────────────────────────────────────

    def submit(self, report: NodeReport) -> None:
        """A node (local or remote) hands in its latest scan."""
        self._nodes[report.node_id] = report

    def active_nodes(self, now: float = None) -> List[NodeReport]:
        now = now or time.time()
        return [n for n in self._nodes.values()
                if now - n.timestamp <= self.OBS_MAX_AGE]

    def recalibrate(self) -> None:
        """Clear filters (e.g. after antennas moved)."""
        self._filters.clear()

    # ── per-observation cleaning + averaging ─────────────────────────────

    def _clean_value(self, node_id: str, obs: NodeObservation) -> float:
        """Return the cleaned measurement (same filter chain as Mac)."""
        key = (node_id, obs.target_id)
        raw = obs.distance if obs.distance is not None else float(obs.rssi)

        filt = self._filters.get(key)
        if filt is None:
            filt = _default_filter()
            self._filters[key] = filt
        return filt.filter(raw)

    def _to_distance(self, node: NodeReport, obs: NodeObservation,
                     cleaned: float) -> float:
        if obs.distance is not None:      # cleaned value IS a distance already
            return max(cleaned, 0.05)
        return rssi_to_distance_two_slope(cleaned, node.tx_power, n_far=node.n)

    @staticmethod
    def _weight(node: NodeReport, obs: NodeObservation) -> float:
        """Trust an antenna more when its signal is strong.

        Strong RSSI (closer to 0) → higher weight.
        Hardware-ranging (UWB) observations are trusted highly.
        """
        if obs.distance is not None:
            return 2.0
        return max(_MIN_WEIGHT, min(1.0, (obs.rssi + 100) / 60.0))

    # ── fix collection (shared by fusion + combination comparison) ───────

    def collect_target_fixes(
        self,
        now: float = None,
        only_nodes: Optional[Set[str]] = None,
    ) -> Dict[str, Dict]:
        """Per target: cleaned, weighted fixes tagged with their node id.

        Returns {target_id: {name, signal_type,
                              fixes: [(node_id, x, y, dist, weight)]}}.
        This is the single place the cleaning/averaging pipeline runs, so the
        live fusion and the combination comparison see identical numbers.
        """
        now = now or time.time()
        nodes = self.active_nodes(now)
        if only_nodes is not None:
            nodes = [n for n in nodes if n.node_id in only_nodes]

        per_target: Dict[str, Dict] = {}
        for node in nodes:
            for obs in node.observations:
                if now - obs.timestamp > self.OBS_MAX_AGE:
                    continue
                cleaned = self._clean_value(node.node_id, obs)
                dist = self._to_distance(node, obs, cleaned)
                w = self._weight(node, obs)

                entry = per_target.setdefault(obs.target_id, {
                    "name": obs.name,
                    "signal_type": obs.signal_type,
                    "fixes": [],          # (node_id, x, y, dist, weight)
                })
                entry["fixes"].append((node.node_id, node.x, node.y, dist, w))
                if obs.name and not entry["name"].startswith(("📶", "Unknown")):
                    entry["name"] = obs.name
        return per_target

    @staticmethod
    def estimate_from_fixes(
        tagged_fixes,
        name: str,
        target_id: str,
        signal_type,
        room_w: float,
        room_h: float,
        locator: Optional[WlsMultilaterator] = None,
    ) -> Optional[TargetEstimate]:
        """Locate a target from a set of (node_id, x, y, dist, weight) fixes."""
        if len(tagged_fixes) < 2:
            return None
        loc = locator or WlsMultilaterator()
        wls_fixes = [(x, y, d, w) for (_nid, x, y, d, w) in tagged_fixes]
        sol = loc.locate(wls_fixes, room_w, room_h)
        if sol is None:
            return None
        x, y, unc = sol
        antennas = [(fx, fy) for (_nid, fx, fy, _d, _w) in tagged_fixes]
        return TargetEstimate(
            target_id=target_id,
            name=name,
            x=x, y=y,
            signal_type=signal_type,
            num_nodes=len(tagged_fixes),
            uncertainty_radius=unc,
            gdop=compute_gdop(antennas, (x, y)),
            contributing_nodes=tuple(nid for (nid, *_r) in tagged_fixes),
        )

    # ── self-location ────────────────────────────────────────────────────

    def get_self_measurements(
        self,
        local_name: str,
        now: float = None,
    ) -> List[AnchorMeasurement]:
        """Find remote antennas that see the local computer and return
        AnchorMeasurements suitable for PositioningService.

        Each remote antenna that has an observation whose name fuzzy-matches
        *local_name* contributes one measurement: the antenna's own (x, y) as
        the anchor position, and the RSSI-derived distance to the local computer.
        """
        now = now or time.time()
        needle = local_name.lower().replace("'", "").replace("’", "")
        out: List[AnchorMeasurement] = []
        for node in self.active_nodes(now):
            if node.is_local:
                continue
            for obs in node.observations:
                if now - obs.timestamp > self.OBS_MAX_AGE:
                    continue
                obs_name = obs.name.lower().replace("'", "").replace("’", "")
                if needle not in obs_name and obs_name not in needle:
                    continue
                cleaned = self._clean_value(node.node_id, obs)
                dist = self._to_distance(node, obs, cleaned)
                out.append(AnchorMeasurement(x=node.x, y=node.y, distance=dist))
                break
        return out

    def get_anchor_observations_from_remotes(
        self,
        anchor_ids: Set[str],
        local_name: str,
        now: float = None,
    ) -> Dict[str, float]:
        """Get distances measured by remote antennas (iPhone) to known anchors.

        Returns {target_id: distance} for anchors seen by remote antennas.
        Used for cross-validation via triangle inequality.
        """
        now = now or time.time()
        out: Dict[str, float] = {}
        needle = local_name.lower().replace("’", "").replace("'", "")

        for node in self.active_nodes(now):
            if node.is_local:
                continue
            for obs in node.observations:
                if now - obs.timestamp > self.OBS_MAX_AGE:
                    continue
                obs_name = obs.name.lower().replace("’", "").replace("'", "")
                if needle in obs_name or obs_name in needle:
                    continue
                if obs.target_id not in anchor_ids:
                    continue
                cleaned = self._clean_value(node.node_id, obs)
                dist = self._to_distance(node, obs, cleaned)
                out[obs.target_id] = dist
        return out

    # ── fusion ───────────────────────────────────────────────────────────

    def locate_targets(
        self,
        room_w: float,
        room_h: float,
        now: float = None,
        only_nodes: Optional[Set[str]] = None,
    ) -> List[TargetEstimate]:
        per_target = self.collect_target_fixes(now, only_nodes)
        results: List[TargetEstimate] = []
        for tid, entry in per_target.items():
            est = self.estimate_from_fixes(
                entry["fixes"], entry["name"], tid, entry["signal_type"],
                room_w, room_h, self._locator)
            if est is not None:
                results.append(est)
        return results
