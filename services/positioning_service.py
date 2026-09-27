import math
import time
from typing import Dict, Optional, Tuple

from core.events import (
    DistanceEstimatedEvent,
    NoPositionEvent,
    PositionEstimatedEvent,
    PositionSmoothedEvent,
    SignalFilteredEvent,
)
from core.interfaces import ITraceabilityService
from core.models import (
    AnchorMeasurement,
    DeviceEstimate,
    EstimationMode,
    PositionResult,
    SignalReading,
    display_name,
)
from engine.distance import rssi_to_distance, tx_reference
from engine.particle_filter import ParticleFilter
from engine.trilateration import TrilaterationEstimator
from engine.weighted_centroid import WeightedCentroidEstimator
from filtering.filter_bank import FilterBank
from filtering.nlos_detector import NLOSDetector
from services.anchor_store import AnchorStore

_CENTROID_UNC = 2.0  # fixed uncertainty for centroid in ensemble weighting


def _weighted_fuse(estimates):
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


class PositioningService:
    DEFAULT_TX_POWER = -59.0
    DEFAULT_PATH_LOSS_N = 2.5
    ANCHOR_POS_WINDOW = 15.0
    POS_SMOOTH = 0.05  # 5% new, 95% history — stationary-optimized
    # Free-space path loss at 1 m, 2.4 GHz (~40 dB). Converts an advertised BLE
    # TX-power level (radio dBm at source) into the expected RSSI at 1 m.
    TX_OFFSET_1M = 41.0

    def __init__(
        self,
        anchors: AnchorStore,
        estimator: TrilaterationEstimator,
        filter_bank: FilterBank,
        tracer: Optional[ITraceabilityService] = None,
    ):
        self._anchors = anchors
        self._estimator = estimator
        self._filter_bank = filter_bank
        self._tracer = tracer
        self._particle_filter = ParticleFilter(n_particles=800)
        self._centroid = WeightedCentroidEstimator()
        self._nlos: Dict[str, NLOSDetector] = {}
        self.mode: EstimationMode = EstimationMode.TRILATERATION
        self._pos_smooth: Optional[Tuple[float, float]] = None
        self._smooth_tick: int = 0
        self._last_uncertainty_radius: Optional[float] = None
        self._last_uncertainty_ellipse: Optional[Tuple[float, float, float]] = None

    def reset(self):
        self._filter_bank.reset_all()
        self._particle_filter.reset()
        self._nlos.clear()
        self._pos_smooth = None
        self._smooth_tick = 0
        self._last_uncertainty_radius = None
        self._last_uncertainty_ellipse = None

    def nlos_levels(self) -> Dict[str, int]:
        """Per-device NLOS/echo severity (0=clean, 1=mild, 2=severe)."""
        return {did: det._nlos_level for did, det in self._nlos.items()}

    def _reference_tx(self, device_id, reading, anchor) -> float:
        return tx_reference(
            anchor.tx_power if anchor is not None else None,
            reading.tx_power_adv,
            self.DEFAULT_TX_POWER,
            offset=self.TX_OFFSET_1M,
        )

    def update(
        self,
        readings: Dict[str, SignalReading],
        room_w: float,
        room_h: float,
        extra_measurements: Optional[list] = None,
        compute_position: bool = True,
    ) -> PositionResult:
        devices = []
        measurements = []
        anchors_ui: Dict[str, Tuple[float, float, str]] = {}
        distances: Dict[str, float] = {}
        now = time.time()
        cx_room, cy_room = room_w / 2.0, room_h / 2.0

        for device_id, reading in readings.items():
            filtered = self._filter_bank.apply(device_id, reading.rssi)

            if self._tracer:
                self._tracer.emit(SignalFilteredEvent(
                    device_id=device_id,
                    raw_rssi=reading.rssi,
                    filtered_rssi=filtered,
                ))

            anchor = self._anchors.get(device_id)
            if device_id not in self._nlos:
                self._nlos[device_id] = NLOSDetector(window=15)
            self._nlos[device_id].feed(reading.rssi)

            if reading.distance is not None:
                dist = reading.distance
            else:
                # Natural log-distance path loss (single slope), no clamp and no
                # NLOS inflation — the simplest model, like the earliest versions.
                tx = self._reference_tx(device_id, reading, anchor)
                n = anchor.n if anchor else self.DEFAULT_PATH_LOSS_N
                dist = rssi_to_distance(filtered, tx, n)

            if self._tracer:
                self._tracer.emit(DistanceEstimatedEvent(
                    device_id=device_id, filtered_rssi=filtered,
                    distance=dist, tx_power=tx, n=n,
                ))

            angle = (math.atan2(anchor.y - cy_room, anchor.x - cx_room)
                     if anchor else None)

            devices.append(DeviceEstimate(
                device_id=device_id,
                name=display_name(device_id, reading.name, getattr(reading, 'manufacturer', '')),
                raw_rssi=reading.rssi,
                filtered_rssi=filtered,
                distance=dist,
                is_anchor=anchor is not None,
                signal_type=reading.signal_type,
                angle=angle,
            ))

            if anchor is not None:
                anchors_ui[device_id] = (anchor.x, anchor.y, anchor.name)
                if now - reading.timestamp <= self.ANCHOR_POS_WINDOW:
                    measurements.append(AnchorMeasurement(anchor.x, anchor.y, dist))
                    distances[device_id] = dist

        if extra_measurements:
            measurements.extend(extra_measurements)

        # Bound memory: keep per-device filter/NLOS state only for devices we
        # still see (plus anchors). Phantom addresses from BLE randomisation
        # would otherwise accumulate forever.
        keep = set(readings.keys()) | set(self._anchors.all().keys())
        self._filter_bank.retain(keep)
        for did in [d for d in self._nlos if d not in keep]:
            del self._nlos[did]

        # Per-device distances above always run the filter chain (continuous
        # smoothing). The 2-D position fix only runs while measuring.
        if compute_position:
            position, pf_snapshot = self._solve(measurements, room_w, room_h)
            self._last_uncertainty_radius = self._estimator.uncertainty_radius
            self._last_uncertainty_ellipse = self._estimator.uncertainty_ellipse
        else:
            position, pf_snapshot = None, None
            self._last_uncertainty_radius = None
            self._last_uncertainty_ellipse = None

        particles = pw = spread = None
        if pf_snapshot is not None:
            particles, pw = pf_snapshot
            spread = self._particle_filter.spread

        status = self._status(position, len(readings), len(measurements))
        return PositionResult(
            devices, anchors_ui, distances, position, status,
            uncertainty_radius=self._last_uncertainty_radius,
            uncertainty_ellipse=self._last_uncertainty_ellipse,
            particles=particles,
            particle_weights=pw,
            particle_spread=spread,
            estimation_mode=self.mode.value,
        )

    def _solve(
        self,
        measurements,
        room_w: float = None,
        room_h: float = None,
    ):
        """Run the selected algorithm(s). Returns (position, pf_snapshot)."""
        mode = self.mode
        raw_t: Optional[Tuple[float, float]] = None
        raw_p: Optional[Tuple[float, float]] = None
        pf_snapshot = None

        needs_trilat = mode in (EstimationMode.TRILATERATION, EstimationMode.FUSION,
                                 EstimationMode.ENSEMBLE)
        needs_pf = mode in (EstimationMode.PARTICLE, EstimationMode.FUSION,
                             EstimationMode.ENSEMBLE)

        if needs_trilat:
            raw_t = self._estimator.estimate(measurements, room_w=room_w, room_h=room_h)

        if needs_pf:
            raw_p = self._particle_filter.update(measurements, room_w or 8.0, room_h or 6.0)
            pf_snapshot = self._particle_filter.snapshot()
        else:
            self._particle_filter.reset()

        # --- Pick or fuse ---
        if mode == EstimationMode.TRILATERATION:
            raw = raw_t
        elif mode == EstimationMode.PARTICLE:
            raw = raw_p
        elif mode == EstimationMode.CENTROID:
            raw = self._centroid.estimate(measurements)
        elif mode == EstimationMode.FUSION:
            raw = _weighted_fuse([
                (raw_t, self._estimator.uncertainty_radius),
                (raw_p, self._particle_filter.spread),
            ])
        else:  # ENSEMBLE — all three independent estimators
            raw_c = self._centroid.estimate(measurements)
            raw = _weighted_fuse([
                (raw_t, self._estimator.uncertainty_radius),
                (raw_p, self._particle_filter.spread),
                (raw_c, _CENTROID_UNC),
            ])

        if raw is None:
            if self._tracer:
                self._tracer.emit(NoPositionEvent(
                    reason="not enough anchors", num_anchors=len(measurements)))
            self._pos_smooth = None
            self._smooth_tick = 0
            return None, pf_snapshot

        if self._tracer:
            self._tracer.emit(PositionEstimatedEvent(
                x=raw[0], y=raw[1], num_anchors=len(measurements)))

        if self._pos_smooth is None:
            self._pos_smooth = raw
            self._smooth_tick = 1
        else:
            self._smooth_tick += 1
            a = max(self.POS_SMOOTH, 1.0 / self._smooth_tick)
            self._pos_smooth = (
                a * raw[0] + (1 - a) * self._pos_smooth[0],
                a * raw[1] + (1 - a) * self._pos_smooth[1],
            )
            if self._tracer:
                self._tracer.emit(PositionSmoothedEvent(
                    raw_x=raw[0], raw_y=raw[1],
                    smoothed_x=self._pos_smooth[0],
                    smoothed_y=self._pos_smooth[1],
                ))

        return self._pos_smooth, pf_snapshot

    @staticmethod
    def _status(position, n_devices, n_anchors) -> str:
        if position is not None:
            return (f"Position: ({position[0]:.2f}, {position[1]:.2f}) m  |  "
                    f"{n_devices} devices  |  {n_anchors} anchors active")
        need = max(0, 3 - n_anchors)
        if need > 0:
            return f"Need {need} more anchor(s)  |  {n_devices} devices visible"
        return f"Scanning… {n_devices} devices  |  {n_anchors} anchors"
