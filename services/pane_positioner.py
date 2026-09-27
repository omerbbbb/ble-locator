from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from core.models import AnchorMeasurement, SignalReading, SignalType
from engine.distance import compute_distance
from engine.particle_filter import ParticleFilter
from engine.trilateration import TrilaterationEstimator
from engine.weighted_centroid import WeightedCentroidEstimator
from filtering.adaptive_kalman import AdaptiveKalmanFilter
from filtering.filter_bank import FilterBank
from services.anchor_store import AnchorStore

ANCHOR_WINDOW = 20.0
CENTROID_UNCERTAINTY = 2.0


def weighted_fuse(estimates):
    xs, ys, ws = [], [], []
    for pos, unc in estimates:
        if pos is None:
            continue
        w = 1.0 / max(unc if unc is not None else 2.0, 0.05)
        xs.append(pos[0] * w)
        ys.append(pos[1] * w)
        ws.append(w)
    if not ws:
        return None
    total = sum(ws)
    return sum(xs) / total, sum(ys) / total


class PanePositioner:
    POS_SMOOTH = 0.22
    DEFAULT_TX = -59.0
    DEFAULT_N = 2.5
    PF_PARTICLES = 300

    def __init__(self, anchors: AnchorStore):
        self._anchors = anchors
        self._fb = FilterBank(AdaptiveKalmanFilter)
        self._trilat = TrilaterationEstimator()
        self._pf = ParticleFilter(n_particles=self.PF_PARTICLES)
        self._centroid = WeightedCentroidEstimator()
        self._pos_smooth: Optional[Tuple[float, float]] = None

        self.algorithm = "trilateration"
        self.signal_filter = "all"

    def update(
        self,
        readings: Dict[str, SignalReading],
        room_w: float,
        room_h: float,
    ):
        readings = self._apply_signal_filter(readings)

        measurements = []
        distances: Dict[str, float] = {}
        anchors_ui: Dict[str, Tuple[float, float, str]] = {}
        now = time.time()

        for device_id, reading in readings.items():
            filtered_rssi = self._fb.apply(device_id, reading.rssi)
            anchor = self._anchors.get(device_id)
            if reading.distance is not None:
                dist = reading.distance
            else:
                tx = anchor.tx_power if anchor else self.DEFAULT_TX
                n = anchor.n if anchor else self.DEFAULT_N
                dist = compute_distance(filtered_rssi, tx, n)

            if anchor is not None:
                anchors_ui[device_id] = (anchor.x, anchor.y, anchor.name)
                if now - reading.timestamp <= ANCHOR_WINDOW:
                    measurements.append(AnchorMeasurement(anchor.x, anchor.y, dist))
                    distances[device_id] = dist

        position = self._run(measurements, room_w, room_h)

        if position is not None:
            if self._pos_smooth is None:
                self._pos_smooth = position
            else:
                a = self.POS_SMOOTH
                self._pos_smooth = (
                    a * position[0] + (1 - a) * self._pos_smooth[0],
                    a * position[1] + (1 - a) * self._pos_smooth[1],
                )
            position = self._pos_smooth
        else:
            self._pos_smooth = None

        particles = pw = None
        if self.algorithm in ("particle", "fusion", "ensemble"):
            snap = self._pf.snapshot()
            if snap:
                particles, pw = snap

        return position, anchors_ui, distances, particles, pw

    def reset(self):
        self._pos_smooth = None
        self._pf.reset()

    @property
    def uncertainty(self) -> Optional[float]:
        algo = self.algorithm
        if algo == "trilateration":
            return self._trilat.uncertainty_radius
        if algo == "particle":
            s = self._pf.spread
            return s if s != float("inf") else None
        if algo in ("fusion", "ensemble"):
            unc_t = self._trilat.uncertainty_radius
            s = self._pf.spread
            unc_p = s if s != float("inf") else None
            candidates = [u for u in (unc_t, unc_p) if u is not None]
            return min(candidates) if candidates else None
        return None

    def _apply_signal_filter(self, readings):
        sf = self.signal_filter
        if sf == "ble":
            return {k: v for k, v in readings.items()
                    if v.signal_type == SignalType.BLE}
        if sf == "wifi":
            return {k: v for k, v in readings.items()
                    if v.signal_type == SignalType.WIFI}
        return readings

    def _run(self, measurements, room_w, room_h):
        algo = self.algorithm

        if algo == "centroid":
            return self._centroid.estimate(measurements)

        if algo == "trilateration":
            return self._trilat.estimate(measurements, room_w, room_h)

        if algo == "particle":
            return self._pf.update(measurements, room_w, room_h)

        if algo == "fusion":
            raw_t = self._trilat.estimate(measurements, room_w, room_h)
            raw_p = self._pf.update(measurements, room_w, room_h)
            return weighted_fuse([
                (raw_t, self._trilat.uncertainty_radius),
                (raw_p, self._pf.spread),
            ])

        raw_t = self._trilat.estimate(measurements, room_w, room_h)
        raw_p = self._pf.update(measurements, room_w, room_h)
        raw_c = self._centroid.estimate(measurements)
        return weighted_fuse([
            (raw_t, self._trilat.uncertainty_radius),
            (raw_p, self._pf.spread),
            (raw_c, CENTROID_UNCERTAINTY),
        ])
